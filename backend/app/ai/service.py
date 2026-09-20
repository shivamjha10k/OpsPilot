from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.agent import InvestigationAgent
from app.ai.context import IncidentContextBuilder
from app.ai.provider import AIProviderError, provider_from_settings
from app.ai.schemas import InvestigationResult, RiskLevel
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.domain import AIInvestigation, AuditLog, Incident, IncidentStatus, InvestigationStatus, RiskLevel as DomainRisk


TRANSIENT_CODES = {"AI_PROVIDER_TIMEOUT", "AI_PROVIDER_UNAVAILABLE", "AI_INVESTIGATION_TIMEOUT"}
ACTION_RISK = {"rollback_deployment": DomainRisk.HIGH, "restart_service": DomainRisk.LOW,
               "scale_service": DomainRisk.MEDIUM, "clear_cache": DomainRisk.MEDIUM,
               "scale_workers": DomainRisk.MEDIUM}


class AIInvestigationService:
    def __init__(self, session: AsyncSession, provider=None) -> None:
        self.session = session
        self.settings = get_settings()
        self.provider = provider or provider_from_settings(self.settings)

    async def request_investigation(self, incident_id: uuid.UUID, actor_id: uuid.UUID, task_id: str | None = None) -> tuple[AIInvestigation, bool]:
        incident = await self.session.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
        if incident is None:
            raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
        existing = await self._active_or_latest(incident_id)
        if existing is not None and existing.status in {InvestigationStatus.PENDING, InvestigationStatus.RUNNING}:
            return existing, False
        investigation = AIInvestigation(
            incident_id=incident_id, model=self.settings.ai_model, summary="Investigation queued.",
            root_cause="Not yet determined.", confidence=0, evidence={}, recommendation="No action has been executed.",
            risk_level=DomainRisk.LOW, status=InvestigationStatus.PENDING, requested_by=actor_id, task_id=task_id,
            prompt_version=self.settings.ai_prompt_version,
        )
        self.session.add(investigation)
        await self.session.flush()
        self._audit(actor_id, "INVESTIGATION_REQUESTED", str(investigation.id), {"incident_id": str(incident_id)})
        await self.session.commit()
        return investigation, True

    async def attach_task(self, investigation_id: uuid.UUID, task_id: str) -> None:
        investigation = await self.session.get(AIInvestigation, investigation_id)
        if investigation:
            investigation.task_id = task_id
            await self.session.commit()

    async def investigate_incident(self, incident_id: uuid.UUID, investigation_id: uuid.UUID | None = None, current_task_id: str | None = None) -> AIInvestigation:
        investigation = await self._select_investigation(incident_id, investigation_id)
        if investigation.status is InvestigationStatus.COMPLETED:
            return investigation
        if investigation.status is InvestigationStatus.RUNNING:
            if current_task_id and investigation.task_id == current_task_id:
                pass # Redelivery of the exact same task, allow retry
            else:
                return investigation
        
        investigation.status = InvestigationStatus.RUNNING
        if current_task_id:
            investigation.task_id = current_task_id
        investigation.started_at = datetime.now(timezone.utc)
        await self.session.commit()
        self._audit(None, "INVESTIGATION_STARTED", str(investigation.id), {})
        started = time.monotonic()
        try:
            context = await IncidentContextBuilder(self.session, self.settings).build(incident_id)
            result = await InvestigationAgent(self.provider, self.settings).run(context)
            self._validate_evidence(result, context)
            self._validate_knowledge_citations(result, context)
            result, final_risk = self._validate_risk(result)
            self._store_success(investigation, result, final_risk, int((time.monotonic() - started) * 1000))
            self._audit(None, "INVESTIGATION_COMPLETED", str(investigation.id), {"confidence": result.confidence})
        except asyncio.TimeoutError:
            self._store_failure(investigation, "AI_PROVIDER_TIMEOUT", int((time.monotonic() - started) * 1000))
        except AIProviderError:
            self._store_failure(investigation, "AI_PROVIDER_UNAVAILABLE", int((time.monotonic() - started) * 1000))
        except AppError as exc:
            self._store_failure(investigation, exc.code, int((time.monotonic() - started) * 1000))
        except (ValueError, TypeError, TimeoutError):
            self._store_failure(investigation, "AI_INVALID_OUTPUT", int((time.monotonic() - started) * 1000))
        except Exception:
            self._store_failure(investigation, "AI_INVESTIGATION_FAILED", int((time.monotonic() - started) * 1000))
        await self.session.commit()
        return investigation

    async def get(self, investigation_id: uuid.UUID) -> AIInvestigation:
        investigation = await self.session.get(AIInvestigation, investigation_id)
        if investigation is None:
            raise AppError("INVESTIGATION_NOT_FOUND", "Investigation does not exist", 404)
        return investigation

    async def _select_investigation(self, incident_id: uuid.UUID, investigation_id: uuid.UUID | None) -> AIInvestigation:
        if investigation_id:
            item = await self.session.scalar(select(AIInvestigation).where(AIInvestigation.id == investigation_id).with_for_update())
        else:
            item = await self.session.scalar(select(AIInvestigation).where(AIInvestigation.incident_id == incident_id)
                                             .order_by(AIInvestigation.created_at.desc()).with_for_update())
        if item is None:
            raise AppError("INVESTIGATION_NOT_FOUND", "Investigation does not exist", 404)
        return item

    async def _active_or_latest(self, incident_id: uuid.UUID) -> AIInvestigation | None:
        return await self.session.scalar(select(AIInvestigation).where(AIInvestigation.incident_id == incident_id)
                                         .order_by(AIInvestigation.created_at.desc()).with_for_update())

    def _validate_evidence(self, result: InvestigationResult, context: dict[str, Any]) -> None:
        available = {(str(item["source_type"]), str(item["source_id"])) for item in context.get("evidence", [])}
        for item in result.evidence:
            if (item.source_type, item.source_id) not in available:
                raise ValueError("provider referenced evidence that was not supplied")
        available_ids = {item.source_id for item in result.evidence}
        for cause in result.probable_root_causes:
            if not set(cause.evidence).issubset(available_ids):
                raise ValueError("root cause referenced unsupported evidence")

    def _validate_knowledge_citations(self, result: InvestigationResult, context: dict[str, Any]) -> None:
        available = {f"{item['document_id']}:{item['chunk_id']}" for item in context.get("retrieved_knowledge", [])}
        if not set(result.knowledge_citations).issubset(available):
            raise ValueError("provider referenced knowledge that was not retrieved")

    def _validate_risk(self, result: InvestigationResult) -> tuple[InvestigationResult, DomainRisk]:
        requested = DomainRisk(result.risk_level.value)
        minimum = ACTION_RISK.get(result.recommended_action.type, DomainRisk.LOW)
        order = {DomainRisk.LOW: 0, DomainRisk.MEDIUM: 1, DomainRisk.HIGH: 2, DomainRisk.CRITICAL: 3}
        final = minimum if order[minimum] > order[requested] else requested
        if result.recommended_action.type in ACTION_RISK and final is DomainRisk.LOW:
            final = minimum
        return result, final

    def _store_success(self, item: AIInvestigation, result: InvestigationResult, risk: DomainRisk, duration: int) -> None:
        item.model = self.settings.ai_model
        item.summary = result.summary
        item.root_cause = result.probable_root_causes[0].cause if result.probable_root_causes else "No probable root cause identified."
        item.confidence = result.confidence
        item.evidence = {"items": [entry.model_dump(mode="json") for entry in result.evidence]}
        item.knowledge_references = list(result.knowledge_citations)
        item.recommendation = result.recommended_action.reason
        item.recommendation_data = result.recommended_action.model_dump(mode="json")
        item.observations = [entry.model_dump(mode="json") for entry in result.observations]
        item.probable_root_causes = [entry.model_dump(mode="json") for entry in result.probable_root_causes]
        item.risk_level = risk
        item.requires_approval = result.requires_approval or risk in {DomainRisk.HIGH, DomainRisk.CRITICAL}
        item.status = InvestigationStatus.COMPLETED
        item.duration_ms = duration
        item.completed_at = datetime.now(timezone.utc)

    def _store_failure(self, item: AIInvestigation, code: str, duration: int) -> None:
        item.status = InvestigationStatus.FAILED
        item.error_code = code
        item.duration_ms = duration
        item.completed_at = datetime.now(timezone.utc)
        item.recommendation = "No action has been executed. Investigation failed safely."
        self._audit(None, "INVESTIGATION_FAILED", str(item.id), {"error_code": code})

    def _audit(self, actor_id: uuid.UUID | None, action: str, resource_id: str, metadata: dict) -> None:
        self.session.add(AuditLog(actor_id=actor_id, action=action, resource_type="AIInvestigation",
                                  resource_id=resource_id, result="SUCCESS", metadata_json=metadata))
