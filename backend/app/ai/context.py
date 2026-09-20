from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.tools import build_tool_registry
from app.core.config import Settings
from app.core.errors import AppError
from app.models.domain import Alert, Incident
from app.rag.service import RAGService


class IncidentContextBuilder:
    """Builds a finite, explicitly whitelisted context from PostgreSQL."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.tools = build_tool_registry()

    async def build(self, incident_id: uuid.UUID) -> dict[str, Any]:
        incident = await self.session.scalar(
            select(Incident).where(Incident.id == incident_id)
            .options(selectinload(Incident.service), selectinload(Incident.alerts))
        )
        if incident is None:
            raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
        service_id = incident.service_id
        end_time = incident.detected_at
        start_time = end_time - timedelta(minutes=self.settings.incident_correlation_window_minutes)

        args = {
            "service_id": service_id, 
            "limit": self.settings.ai_max_events,
            "start_time": start_time,
            "end_time": end_time
        }
        events = await self.tools["get_recent_events"].invoke(self.session, args)
        
        logs_args = {
            "service_id": service_id, 
            "limit": self.settings.ai_max_logs,
            "start_time": start_time,
            "end_time": end_time
        }
        logs = await self.tools["search_logs"].invoke(self.session, logs_args)
        deployments = await self.tools["get_recent_deployments"].invoke(self.session, {"service_id": service_id, "limit": self.settings.ai_max_deployments})
        history = await self.tools["get_incident_history"].invoke(self.session, {"service_id": service_id, "limit": 20})
        health = await self.tools["get_service_health"].invoke(self.session, {"service_id": service_id})
        rag_status = "available"
        try:
            knowledge = await self.tools["search_knowledge"].invoke(
                self.session,
                {"query": f"{incident.title} {incident.description}", "service_id": service_id,
                 "environment": incident.service.environment.value if incident.service else None, "top_k": self.settings.rag_top_k},
            )
        except Exception:
            knowledge = []
            rag_status = "unavailable"
        metrics = []
        for metric_name in self._metric_names(events):
            metrics_args = {
                "service_id": service_id, 
                "metric_name": metric_name, 
                "limit": self.settings.ai_max_metric_points,
                "start_time": start_time,
                "end_time": end_time
            }
            metrics.extend(await self.tools["get_service_metrics"].invoke(self.session, metrics_args))
        alerts = [{"source_type": "alert", "source_id": str(item.id), "description": item.message,
                   "severity": item.severity.value, "alert_type": item.alert_type, "timestamp": item.occurred_at}
                  for item in list(incident.alerts)[: self.settings.ai_max_alerts]]
        evidence = alerts + events[: self.settings.ai_max_events] + logs[: self.settings.ai_max_logs] + \
            metrics[: self.settings.ai_max_metric_points] + deployments[: self.settings.ai_max_deployments]
        context = {
            "incident": {"id": str(incident.id), "number": incident.incident_number, "title": incident.title,
                         "description": incident.description, "service_id": str(service_id),
                         "severity": incident.severity.value, "status": incident.status.value,
                         "detected_at": incident.detected_at, "assigned_to": str(incident.assigned_to) if incident.assigned_to else None},
            "service": health,
            "alerts": alerts,
            "events": events[: self.settings.ai_max_events],
            "logs": logs[: self.settings.ai_max_logs],
            "metrics": metrics[: self.settings.ai_max_metric_points],
            "deployments": deployments[: self.settings.ai_max_deployments],
            "incident_history": history[:20],
            "evidence": evidence,
            "retrieved_knowledge": knowledge,
            "rag_status": rag_status,
            "untrusted_operational_data": {"logs": logs[: self.settings.ai_max_logs], "event_payloads": [item.get("payload", {}) for item in events[:20]]},
        }
        serialized = json.dumps(context, default=str)
        if len(serialized) > self.settings.ai_max_context_chars:
            context["logs"] = context["logs"][:10]
            context["events"] = context["events"][:20]
            context["evidence"] = context["evidence"][:40]
            context["untrusted_operational_data"] = {"logs": context["logs"], "event_payloads": []}
        return context

    @staticmethod
    def _metric_names(events: list[dict[str, Any]]) -> list[str]:
        names = []
        for event in events:
            value = event.get("payload", {}).get("metric")
            if isinstance(value, str) and value and value not in names:
                names.append(value)
        return names[:5]
