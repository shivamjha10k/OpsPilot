"""Non-destructive dependency latency probes for the local OpsPilot environment."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


async def probe_http(name: str, url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        return {"dependency": name, "available": response.is_success, "status_code": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": None}
    except Exception as exc:
        return {"dependency": name, "available": False, "status_code": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": type(exc).__name__}


async def probe_redis(url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from redis.asyncio import Redis
        client = Redis.from_url(url, socket_connect_timeout=timeout, socket_timeout=timeout)
        await client.ping()
        await client.aclose()
        return {"dependency": "redis", "available": True, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": None}
    except Exception as exc:
        return {"dependency": "redis", "available": False, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": type(exc).__name__}


async def probe_celery(redis_url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from celery import Celery
        app = Celery("performance-probe", broker=redis_url)
        replies = await asyncio.to_thread(lambda: app.control.inspect(timeout=timeout).ping() or {})
        return {"dependency": "celery", "available": bool(replies), "workers": sorted(replies),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": None}
    except Exception as exc:
        return {"dependency": "celery", "available": False, "workers": [],
                "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": type(exc).__name__}


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe OpsPilot dependencies without mutating data")
    parser.add_argument("--host", default=os.getenv("OPSPILOT_HOST", "http://localhost:8000"))
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument("--timeout", type=float, default=2)
    parser.add_argument("--output", type=Path, default=Path("performance/results/dependencies.json"))
    args = parser.parse_args()
    results = await asyncio.gather(
        probe_http("api_live", f"{args.host.rstrip('/')}/health/live", args.timeout),
        probe_http("api_ready", f"{args.host.rstrip('/')}/health/ready", args.timeout),
        probe_http("qdrant", f"{os.getenv('QDRANT_URL', 'http://localhost:6333').rstrip('/')}/", args.timeout),
        probe_redis(args.redis_url, args.timeout),
        probe_celery(args.redis_url, args.timeout),
    )
    payload = {"measured_at": datetime.now(timezone.utc).isoformat(), "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if all(item["available"] for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
