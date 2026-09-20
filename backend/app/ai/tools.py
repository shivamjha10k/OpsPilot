from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Alert, Deployment, Event, Incident, Log, Metric, Service
from app.rag.service import RAGService


class ToolInput(BaseModel):
    model_config = {"extra": "forbid"}


class ServiceInput(ToolInput):
    service_id: uuid.UUID


class MetricsInput(ServiceInput):
    metric_name: str = Field(min_length=1, max_length=255)
    limit: int = Field(default=100, ge=1, le=500)
    start_time: datetime | None = None
    end_time: datetime | None = None


class LogsInput(ServiceInput):
    query: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=50, ge=1, le=200)
    start_time: datetime | None = None
    end_time: datetime | None = None


class LimitedServiceInput(ServiceInput):
    limit: int = Field(default=20, ge=1, le=100)
    start_time: datetime | None = None
    end_time: datetime | None = None


class IncidentHistoryInput(ToolInput):
    service_id: uuid.UUID
    limit: int = Field(default=20, ge=1, le=100)


class KnowledgeSearchInput(ToolInput):
    query: str = Field(min_length=1, max_length=2000)
    service_id: uuid.UUID | None = None
    environment: str | None = Field(default=None, max_length=32)
    document_types: list[str] = Field(default_factory=list, max_length=4)
    top_k: int = Field(default=5, ge=1, le=20)


class Tool:
    def __init__(self, name: str, description: str, input_model: type[BaseModel], maximum_result_size: int,
                 handler: Callable[[AsyncSession, BaseModel], Awaitable[list[dict[str, Any]]]]) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model
        self.maximum_result_size = maximum_result_size
        self.handler = handler
        self.read_only = True

    async def invoke(self, session: AsyncSession, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        validated = self.input_model.model_validate(arguments)
        return (await self.handler(session, validated))[: self.maximum_result_size]


async def get_service_health(session: AsyncSession, args: ServiceInput) -> list[dict[str, Any]]:
    service = await session.scalar(select(Service).where(Service.id == args.service_id))
    return [] if service is None else [{"service_id": str(service.id), "name": service.name, "status": service.status.value,
                                        "environment": service.environment.value}]


async def get_service_metrics(session: AsyncSession, args: MetricsInput) -> list[dict[str, Any]]:
    query = select(Metric).where(Metric.service_id == args.service_id, Metric.metric_name == args.metric_name)
    if args.start_time:
        query = query.where(Metric.occurred_at >= args.start_time)
    if args.end_time:
        query = query.where(Metric.occurred_at <= args.end_time)
    query = query.order_by(Metric.occurred_at.desc()).limit(args.limit)
    rows = (await session.scalars(query)).all()
    return [{"source_type": "metric", "source_id": str(row.id), "metric_name": row.metric_name,
             "value": row.value, "description": f"{row.metric_name} measured {row.value}", "timestamp": row.occurred_at} for row in rows]


async def search_logs(session: AsyncSession, args: LogsInput) -> list[dict[str, Any]]:
    query = select(Log).where(Log.service_id == args.service_id)
    if args.start_time:
        query = query.where(Log.occurred_at >= args.start_time)
    if args.end_time:
        query = query.where(Log.occurred_at <= args.end_time)
    query = query.order_by(Log.occurred_at.desc()).limit(args.limit)
    rows = (await session.scalars(query)).all()
    needle = args.query.lower() if args.query else None
    return [{"source_type": "log", "source_id": str(row.id), "message": row.message,
             "description": row.message, "level": row.level, "timestamp": row.occurred_at}
            for row in rows if needle is None or needle in row.message.lower()]


async def get_recent_deployments(session: AsyncSession, args: LimitedServiceInput) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(Deployment).where(Deployment.service_id == args.service_id)
                                  .order_by(Deployment.deployed_at.desc()).limit(args.limit))).all()
    return [{"source_type": "deployment", "source_id": str(row.id), "version": row.version,
             "status": row.status.value, "description": f"deployment {row.version} was {row.status.value}",
             "timestamp": row.deployed_at} for row in rows]


async def get_incident_history(session: AsyncSession, args: IncidentHistoryInput) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(Incident).where(Incident.service_id == args.service_id)
                                  .order_by(Incident.detected_at.desc()).limit(args.limit))).all()
    return [{"source_type": "incident", "source_id": str(row.id), "description": row.title,
             "status": row.status.value, "timestamp": row.detected_at} for row in rows]


async def _events(session: AsyncSession, args: LimitedServiceInput) -> list[dict[str, Any]]:
    query = select(Event).where(Event.service_id == args.service_id)
    if args.start_time:
        query = query.where(Event.occurred_at >= args.start_time)
    if args.end_time:
        query = query.where(Event.occurred_at <= args.end_time)
    query = query.order_by(Event.occurred_at.desc()).limit(args.limit)
    rows = (await session.scalars(query)).all()
    return [{"source_type": "event", "source_id": str(row.id), "description": row.event_type,
             "event_type": row.event_type, "payload": dict(row.payload or {}), "timestamp": row.occurred_at} for row in rows]


async def search_knowledge(session: AsyncSession, args: KnowledgeSearchInput) -> list[dict[str, Any]]:
    return await RAGService(session).retrieve(args.query, service_id=args.service_id, environment=args.environment,
                                               document_types=args.document_types or None, top_k=args.top_k)


def build_tool_registry() -> dict[str, Tool]:
    return {
        "get_service_health": Tool("get_service_health", "Read current service health", ServiceInput, 1, get_service_health),
        "get_service_metrics": Tool("get_service_metrics", "Read bounded service metrics", MetricsInput, 500, get_service_metrics),
        "search_logs": Tool("search_logs", "Search bounded operational logs", LogsInput, 200, search_logs),
        "get_recent_deployments": Tool("get_recent_deployments", "Read recent deployments", LimitedServiceInput, 100, get_recent_deployments),
        "get_incident_history": Tool("get_incident_history", "Read incident history", IncidentHistoryInput, 100, get_incident_history),
        "get_recent_events": Tool("get_recent_events", "Read recent events", LimitedServiceInput, 100, _events),
        "search_knowledge": Tool("search_knowledge", "Read retrieved knowledge references", KnowledgeSearchInput, 20, search_knowledge),
    }
