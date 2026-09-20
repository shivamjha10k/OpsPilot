from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.domain import Deployment, DeploymentStatus, Environment, Event, Log, Metric, Service, SimulationRun, SimulationStatus
from app.models.user import User
from app.services.incident_engine import IncidentEngine

from .scenarios import SCENARIOS, ScenarioDefinition
from .state import ServiceBaseline, ServiceState, SimulatedServiceState, baseline_metrics


SERVICE_BASELINES: dict[str, ServiceBaseline] = {
    "payment-service": ServiceBaseline(45, 52, 120, 0.01, 150, 10, db_connection_utilization=25),
    "order-service": ServiceBaseline(40, 48, 100, 0.008, 180, 8),
    "user-service": ServiceBaseline(35, 45, 90, 0.005, 200, 12),
    "notification-service": ServiceBaseline(50, 55, 130, 0.01, 100, 20, queue_depth=20, worker_utilization=55),
    "search-service": ServiceBaseline(48, 60, 80, 0.004, 300, 15),
}


class SimulatorManager:
    """Explicit tick-driven simulator. It never starts an uncontrolled loop."""

    def __init__(self) -> None:
        self._states: dict[uuid.UUID, ServiceState] = {}
        self._active: set[uuid.UUID] = set()
        self._lock = asyncio.Lock()

    async def services(self, session: AsyncSession) -> list[dict]:
        services = list((await session.scalars(select(Service).order_by(Service.name))).all())
        now = datetime.now(timezone.utc)
        result = []
        for service in services:
            state = self._state_for(service, now)
            result.append(state.snapshot())
        return result

    def scenarios(self) -> list[dict]:
        return [definition.metadata() for definition in SCENARIOS.values()]

    async def trigger(self, session: AsyncSession, scenario_name: str, actor: User,
                      configuration: dict | None = None) -> SimulationRun:
        settings = get_settings()
        if not settings.simulator_enabled or settings.environment.lower() == "production":
            raise AppError("SIMULATOR_DISABLED", "The simulator is disabled in this environment", 403)
        definition = SCENARIOS.get(scenario_name)
        if definition is None:
            raise AppError("UNKNOWN_SCENARIO", "Unknown simulator scenario", 404)

        async with self._lock:
            service = await session.scalar(select(Service).where(Service.name == definition.target_services[0]))
            if service is None:
                raise AppError("SERVICE_NOT_FOUND", "Scenario target service does not exist", 404)
            existing = await session.scalar(select(SimulationRun).where(
                SimulationRun.scenario == scenario_name,
                SimulationRun.target_service_id == service.id,
                SimulationRun.status.in_({SimulationStatus.CREATED, SimulationStatus.RUNNING, SimulationStatus.STOPPING}),
            ))
            if existing is not None:
                raise AppError("SIMULATION_ALREADY_RUNNING", "A simulation is already running for this scenario", 409)

            now = datetime.now(timezone.utc)
            state = self._state_for(service, now)
            run = SimulationRun(
                id=uuid.uuid4(), scenario=scenario_name, target_service_id=service.id, actor_id=actor.id,
                target_service=service,
                status=SimulationStatus.CREATED, started_at=now,
                configuration=configuration or {"tick_interval_seconds": settings.simulator_tick_interval_seconds,
                                                "random_seed": settings.simulator_random_seed},
                current_state=state.snapshot(), result={},
            )
            session.add(run)
            await session.flush()
            self._active.add(run.id)
            run.status = SimulationStatus.RUNNING
            await self._tick(session, run, service, state, definition, actor)
            run.current_state = state.snapshot()
            service.simulation_state = state.snapshot()
            run.result = {"ticks": state.tick_count, "generated": "telemetry_and_events", "incident_created_by": "phase4"}
            await self._audit(session, actor, "SIMULATION_TRIGGERED", run, {"scenario": scenario_name})
            await session.commit()
            return run

    async def advance(self, session: AsyncSession, simulation_id: uuid.UUID, actor: User | None = None) -> SimulationRun:
        async with self._lock:
            run = await self._get_run(session, simulation_id)
            if run.status is not SimulationStatus.RUNNING:
                raise AppError("SIMULATION_NOT_RUNNING", "Only running simulations can advance", 409)
            service = run.target_service
            state = self._state_for(service, datetime.now(timezone.utc))
            definition = SCENARIOS[run.scenario]
            self._active.add(run.id)
            await self._tick(session, run, service, state, definition, actor)
            run.current_state = state.snapshot()
            service.simulation_state = state.snapshot()
            run.result = {"ticks": state.tick_count, "generated": "telemetry_and_events", "incident_created_by": "phase4"}
            await session.commit()
            return run

    async def stop(self, session: AsyncSession, simulation_id: uuid.UUID, actor: User) -> SimulationRun:
        async with self._lock:
            run = await self._get_run(session, simulation_id)
            if run.status in {SimulationStatus.STOPPED, SimulationStatus.COMPLETED}:
                return run
            if run.status is SimulationStatus.FAILED:
                raise AppError("SIMULATION_FAILED", "A failed simulation cannot be stopped", 409)
            run.status = SimulationStatus.STOPPING
            await session.flush()
            run.status = SimulationStatus.STOPPED
            run.stopped_at = datetime.now(timezone.utc)
            run.result = {**(run.result or {}), "stopped": True, "incident_resolution": "unchanged"}
            self._active.discard(run.id)
            
            # Reset target service to baseline
            service = run.target_service
            state = self._state_for(service, datetime.now(timezone.utc))
            state.reset(datetime.now(timezone.utc))
            service.simulation_state = state.snapshot()
            await self._audit(session, actor, "SIMULATION_STOPPED", run, {"scenario": run.scenario})
            await session.commit()
            return run

    async def recover_stale_runs(self, session: AsyncSession) -> None:
        async with self._lock:
            now = datetime.now(timezone.utc)
            stale_runs = list((await session.scalars(
                select(SimulationRun)
                .options(selectinload(SimulationRun.target_service))
                .where(SimulationRun.status == SimulationStatus.RUNNING)
            )).all())

            if not stale_runs:
                return

            from app.models.domain import AuditLog

            for run in stale_runs:
                if run.id in self._active:
                    continue  # Safety check
                
                run.status = SimulationStatus.FAILED
                run.stopped_at = now
                run.result = {**(run.result or {}), "error": "aborted_due_to_restart", "incident_resolution": "unchanged"}
                
                service = run.target_service
                state = self._state_for(service, now)
                state.reset(now)
                service.simulation_state = state.snapshot()

                session.add(AuditLog(
                    actor_id=run.actor_id,
                    action="SIMULATION_RECOVERED_ON_RESTART",
                    resource_type="SimulationRun",
                    resource_id=str(run.id),
                    result="SUCCESS",
                    metadata_json={"scenario": run.scenario, "reason": "Backend restarted"}
                ))
            
            await session.commit()

    async def get(self, session: AsyncSession, simulation_id: uuid.UUID) -> SimulationRun:
        return await self._get_run(session, simulation_id)

    async def list(self, session: AsyncSession, page: int = 1, page_size: int = 50) -> tuple[list[SimulationRun], int]:
        if page < 1 or page_size < 1 or page_size > 100:
            raise AppError("INVALID_PAGINATION", "page must be positive and page_size must be between 1 and 100", 422)
        total = await session.scalar(select(func.count()).select_from(SimulationRun)) or 0
        items = list((await session.scalars(
            select(SimulationRun).options(selectinload(SimulationRun.target_service))
            .order_by(SimulationRun.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )).all())
        return items, total

    async def restart_service(self, session: AsyncSession, service_id: uuid.UUID, reason: str | None = None) -> dict:
        async with self._lock:
            service = await session.scalar(select(Service).where(Service.id == service_id))
            if service is None:
                raise AppError("SERVICE_NOT_FOUND", "Service does not exist", 404)
            state = self._state_for(service, datetime.now(timezone.utc))
            before = state.snapshot()
            state.lifecycle = SimulatedServiceState.NORMAL
            state.metrics = baseline_metrics(state.baseline)
            state.last_updated = datetime.now(timezone.utc)
            service.simulation_state = state.snapshot()
            return {"state_before": before, "state_after": state.snapshot(), "reason": reason}

    async def scale_service(self, session: AsyncSession, service_id: uuid.UUID, desired_replicas: int) -> dict:
        async with self._lock:
            service = await session.scalar(select(Service).where(Service.id == service_id))
            if service is None:
                raise AppError("SERVICE_NOT_FOUND", "Service does not exist", 404)
            state = self._state_for(service, datetime.now(timezone.utc))
            before = state.snapshot()
            state.replicas = desired_replicas
            state.last_updated = datetime.now(timezone.utc)
            service.simulation_state = state.snapshot()
            return {"state_before": before, "state_after": state.snapshot()}

    async def rollback_deployment(self, session: AsyncSession, service_id: uuid.UUID, deployment_id: uuid.UUID) -> dict:
        async with self._lock:
            deployment = await session.scalar(select(Deployment).where(Deployment.id == deployment_id, Deployment.service_id == service_id))
            if deployment is None:
                raise AppError("DEPLOYMENT_NOT_FOUND", "Deployment does not belong to the service", 404)
            if deployment.status not in {DeploymentStatus.FAILED, DeploymentStatus.ROLLED_BACK}:
                raise AppError("DEPLOYMENT_NOT_ELIGIBLE", "Only failed deployments can be rolled back", 409)
            service = await session.scalar(select(Service).where(Service.id == service_id))
            state = self._state_for(service, datetime.now(timezone.utc))
            before = state.snapshot()
            state.version = "v1.0.0"
            state.lifecycle = SimulatedServiceState.NORMAL
            state.metrics = baseline_metrics(state.baseline)
            state.last_updated = datetime.now(timezone.utc)
            service.simulation_state = state.snapshot()
            return {"state_before": before, "state_after": state.snapshot(), "deployment_id": str(deployment.id)}

    async def clear_cache(self, session: AsyncSession, service_id: uuid.UUID) -> dict:
        async with self._lock:
            service = await session.scalar(select(Service).where(Service.id == service_id))
            if service is None:
                raise AppError("SERVICE_NOT_FOUND", "Service does not exist", 404)
            state = self._state_for(service, datetime.now(timezone.utc))
            before = state.snapshot()
            state.cache_generation += 1
            state.last_updated = datetime.now(timezone.utc)
            service.simulation_state = state.snapshot()
            return {"state_before": before, "state_after": state.snapshot()}

    async def scale_workers(self, session: AsyncSession, service_id: uuid.UUID, desired_workers: int) -> dict:
        async with self._lock:
            service = await session.scalar(select(Service).where(Service.id == service_id))
            if service is None:
                raise AppError("SERVICE_NOT_FOUND", "Service does not exist", 404)
            state = self._state_for(service, datetime.now(timezone.utc))
            if state.baseline.worker_utilization is None:
                raise AppError("WORKERS_UNSUPPORTED", "This simulated service has no worker pool", 422)
            before = state.snapshot()
            state.workers = desired_workers
            if state.baseline.queue_depth is not None:
                state.metrics["queue_depth"] = state.baseline.queue_depth
            if state.baseline.worker_utilization is not None:
                state.metrics["worker_utilization"] = state.baseline.worker_utilization
            state.lifecycle = SimulatedServiceState.NORMAL
            state.last_updated = datetime.now(timezone.utc)
            service.simulation_state = state.snapshot()
            return {"state_before": before, "state_after": state.snapshot()}

    async def _get_run(self, session: AsyncSession, simulation_id: uuid.UUID) -> SimulationRun:
        run = await session.scalar(select(SimulationRun).options(selectinload(SimulationRun.target_service)).where(SimulationRun.id == simulation_id))
        if run is None:
            raise AppError("SIMULATION_NOT_FOUND", "Simulation does not exist", 404)
        return run

    def _state_for(self, service: Service, now: datetime) -> ServiceState:
        state = self._states.get(service.id)
        if state is None:
            baseline = SERVICE_BASELINES.get(service.name, ServiceBaseline(40, 50, 100, 0.01, 100, 10))
            state = ServiceState(
                service_id=service.id, service_name=service.name, environment=service.environment.value,
                version="v1.0.0", lifecycle=SimulatedServiceState.NORMAL, baseline=baseline,
                metrics=baseline_metrics(baseline), dependencies={"database": "HEALTHY"}, last_updated=now,
            )
            self._states[service.id] = state
        persisted = service.simulation_state or {}
        if persisted:
            state.version = str(persisted.get("version", state.version))
            state.lifecycle = SimulatedServiceState(persisted.get("state", state.lifecycle.value))
            state.metrics = dict(persisted.get("metrics", state.metrics))
            state.replicas = int(persisted.get("replicas", state.replicas))
            state.workers = int(persisted.get("workers", state.workers))
            state.cache_generation = int(persisted.get("cache_generation", state.cache_generation))
        return state

    async def _tick(self, session: AsyncSession, run: SimulationRun, service: Service,
                    state: ServiceState, definition: ScenarioDefinition, actor: User | None) -> None:
        now = datetime.now(timezone.utc)
        state.tick_count += 1
        self._apply_scenario(state, definition.name, now)
        for metric_name, value in state.metrics.items():
            session.add(Metric(service_id=service.id, metric_name=metric_name, value=value,
                               labels={"source": "simulator", "scenario": definition.name, "simulation_id": str(run.id)},
                               occurred_at=now))
        for message, metadata in self._logs_for(definition.name, state, run.id):
            session.add(Log(service_id=service.id, level="ERROR" if state.lifecycle is not SimulatedServiceState.NORMAL else "INFO",
                            message=message, metadata_json=metadata, occurred_at=now))
        if definition.name == "failed_deployment" and state.tick_count == 1:
            session.add(Deployment(service_id=service.id, version=state.version, environment=Environment(service.environment),
                                   status=DeploymentStatus.FAILED, deployed_by=actor.id if actor else None, deployed_at=now))
        for index, (event_type, payload) in enumerate(self._events_for(definition.name, state, run.id)):
            event = Event(event_id=f"sim-{run.id}-{state.tick_count}-{index}", event_type=event_type,
                          source="simulator", service_id=service.id, payload=payload, occurred_at=now)
            await IncidentEngine(session).ingest(event, actor)
        state.last_updated = now

    @staticmethod
    def _apply_scenario(state: ServiceState, name: str, now: datetime) -> None:
        metrics = baseline_metrics(state.baseline)
        state.lifecycle = SimulatedServiceState.DEGRADED
        if name == "high_cpu":
            metrics.update(cpu_usage=94 + min(state.tick_count, 4), latency_ms=420 + state.tick_count * 20, error_rate=0.06)
        elif name == "error_spike":
            state.lifecycle = SimulatedServiceState.FAILED
            metrics.update(error_rate=0.25, latency_ms=650, cpu_usage=75)
        elif name == "db_connection_exhaustion":
            metrics.update(db_connection_utilization=99, latency_ms=900, error_rate=0.30, active_requests=80)
        elif name == "queue_backlog":
            metrics.update(queue_depth=800 + state.tick_count * 250, worker_utilization=96, latency_ms=500, error_rate=0.08)
        elif name == "memory_leak":
            metrics.update(memory_usage=min(96, 78 + state.tick_count * 8), latency_ms=300 + state.tick_count * 25, error_rate=0.04)
        elif name == "failed_deployment":
            state.lifecycle = SimulatedServiceState.FAILED
            state.version = "v2.9.0"
            metrics.update(error_rate=0.22, latency_ms=700, cpu_usage=72)
        state.metrics = metrics
        state.last_updated = now

    @staticmethod
    def _events_for(name: str, state: ServiceState, simulation_id: uuid.UUID) -> list[tuple[str, dict]]:
        common = {"scenario": name, "simulation_id": str(simulation_id), "state": state.lifecycle.value}
        if name == "high_cpu":
            return [("cpu.threshold_crossed", {**common, "metric": "cpu_usage", "value": state.metrics["cpu_usage"], "severity": "HIGH", "message": "CPU saturation threshold exceeded"})]
        if name == "error_spike":
            return [("error_rate.spike", {**common, "metric": "error_rate", "value": state.metrics["error_rate"], "severity": "CRITICAL", "message": "5xx error rate increased sharply"})]
        if name == "db_connection_exhaustion":
            return [
                ("db_connection.exhaustion", {**common, "metric": "db_connection_utilization", "value": 99, "severity": "CRITICAL", "alert_type": "DB_CONNECTION_EXHAUSTION", "message": "Database connection pool utilization reached critical level"}),
                ("high_latency", {**common, "metric": "latency_ms", "value": state.metrics["latency_ms"], "severity": "HIGH", "alert_type": "HIGH_LATENCY", "message": "Request latency increased during database exhaustion"}),
                ("error_rate.spike", {**common, "metric": "error_rate", "value": state.metrics["error_rate"], "severity": "HIGH", "alert_type": "ERROR_RATE_SPIKE", "message": "Database timeouts increased request failures"}),
            ]
        if name == "queue_backlog":
            return [("queue.backlog", {**common, "metric": "queue_depth", "value": state.metrics["queue_depth"], "severity": "HIGH", "message": "Notification queue backlog is increasing"})]
        if name == "memory_leak":
            return [("memory.pressure", {**common, "metric": "memory_usage", "value": state.metrics["memory_usage"], "severity": "HIGH", "message": "Memory utilization is increasing continuously"})]
        return [
            ("deployment.failed", {**common, "version": state.version, "message": "Deployment completed with failed health checks"}),
            ("health.check_failed", {**common, "severity": "CRITICAL", "alert_type": "HEALTH_CHECK_FAILURE", "message": "Health checks failed after deployment"}),
            ("error_rate.spike", {**common, "severity": "HIGH", "alert_type": "ERROR_RATE_SPIKE", "message": "Error rate increased after deployment"}),
        ]

    @staticmethod
    def _logs_for(name: str, state: ServiceState, simulation_id: uuid.UUID) -> list[tuple[str, dict]]:
        metadata = {"scenario": name, "simulation_id": str(simulation_id)}
        messages = {
            "high_cpu": "CPU utilization exceeded threshold",
            "error_spike": "Request error rate increased sharply",
            "db_connection_exhaustion": "Database connection pool utilization reached critical level",
            "queue_backlog": "Notification queue backlog increasing",
            "memory_leak": "Memory utilization increasing continuously",
            "failed_deployment": "Health checks failing after deployment",
        }
        return [(messages[name], {**metadata, "metrics": dict(state.metrics)})]

    async def _audit(self, session: AsyncSession, actor: User, action: str, run: SimulationRun, metadata: dict) -> None:
        from app.models.domain import AuditLog
        session.add(AuditLog(actor_id=actor.id, action=action, resource_type="SimulationRun",
                             resource_id=str(run.id), result="SUCCESS", metadata_json=metadata))


_manager = SimulatorManager()


def get_simulator_manager() -> SimulatorManager:
    return _manager
