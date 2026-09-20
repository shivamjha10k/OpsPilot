import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles
from app.core.database import get_db_session
from app.models.user import Role, User
from app.schemas.simulator import SimulationRead, SimulationTriggerRequest
from app.simulator import get_simulator_manager

router = APIRouter(prefix="/simulator", tags=["simulator"])


def _read(run) -> dict:
    return SimulationRead(
        id=run.id, scenario=run.scenario, target_service_id=run.target_service_id,
        target_service_name=run.target_service.name if run.target_service else "unknown",
        actor_id=run.actor_id, status=run.status, started_at=run.started_at, stopped_at=run.stopped_at,
        configuration=run.configuration or {}, result=run.result or {}, current_state=run.current_state or {},
        created_at=run.created_at,
    ).model_dump(mode="json")


@router.get("/services", summary="List simulated services")
async def list_simulator_services(_: User = Depends(get_current_user),
                                  session: AsyncSession = Depends(get_db_session)) -> dict:
    return {"data": await get_simulator_manager().services(session)}


@router.get("/scenarios", summary="List simulator scenarios")
async def list_simulator_scenarios(_: User = Depends(get_current_user)) -> dict:
    return {"data": get_simulator_manager().scenarios()}


@router.post("/scenarios/{scenario}/trigger", status_code=201, summary="Trigger a simulator scenario")
async def trigger_scenario(
    scenario: str,
    payload: SimulationTriggerRequest,
    current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    run = await get_simulator_manager().trigger(session, scenario, current_user, payload.configuration)
    return {"data": _read(run)}


@router.post("/simulations/{simulation_id}/stop", summary="Stop a simulator scenario")
async def stop_simulation(
    simulation_id: uuid.UUID,
    current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    run = await get_simulator_manager().stop(session, simulation_id, current_user)
    return {"data": _read(run)}


@router.get("/simulations/{simulation_id}", summary="Get a simulator execution")
async def get_simulation(simulation_id: uuid.UUID, _: User = Depends(get_current_user),
                         session: AsyncSession = Depends(get_db_session)) -> dict:
    run = await get_simulator_manager().get(session, simulation_id)
    return {"data": _read(run)}


@router.get("/simulations", summary="List simulator executions")
async def list_simulations(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                           _: User = Depends(get_current_user),
                           session: AsyncSession = Depends(get_db_session)) -> dict:
    runs, total = await get_simulator_manager().list(session, page, page_size)
    return {"data": [_read(run) for run in runs],
            "pagination": {"page": page, "page_size": page_size, "total": total,
                           "total_pages": (total + page_size - 1) // page_size if total else 0}}
