from __future__ import annotations

import asyncio
from typing import Coroutine, TypeVar

T = TypeVar("T")
_worker_loop: asyncio.AbstractEventLoop | None = None


def run_in_worker_loop(coroutine: Coroutine[object, object, T]) -> T:
    """Run Celery coroutines on one loop per prefork worker process."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coroutine)
