from __future__ import annotations

import asyncio
import time
from typing import Any

from app.ai.provider import AIProvider, parse_provider_output
from app.ai.schemas import InvestigationResult
from app.core.config import Settings


class InvestigationAgent:
    """One bounded investigation agent. Tools are read during context construction only."""

    def __init__(self, provider: AIProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    async def run(self, context: dict[str, Any]) -> InvestigationResult:
        started = time.monotonic()
        if self.settings.ai_max_tool_calls < 1:
            raise ValueError("investigation tool budget is exhausted")
        raw = await asyncio.wait_for(self.provider.investigate(context), timeout=self.settings.ai_timeout_seconds)
        if time.monotonic() - started > self.settings.ai_max_investigation_seconds:
            raise TimeoutError("investigation budget exceeded")
        return parse_provider_output(raw)
