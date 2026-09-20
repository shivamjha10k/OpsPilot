"""Safe, repeatable read-only HTTP load harness for Phase 14.

Examples:
    python performance/load_test.py --profile A --host http://localhost:8000
    python performance/load_test.py --users 25 --duration 30 --path /health/live
    python performance/load_test.py --users 100 --path /api/v1/incidents --token "$env:OPSPILOT_TOKEN"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROFILES = {
    "A": {"users": 100, "spawn_rate": 10},
    "B": {"users": 500, "spawn_rate": 25},
    "C": {"users": 1000, "spawn_rate": 50},
}


@dataclass
class Sample:
    path: str
    status_code: int | None
    latency_ms: float
    error: str | None = None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return round(ordered[index], 3)


def summarize(samples: list[Sample], duration: float) -> dict[str, Any]:
    latencies = [sample.latency_ms for sample in samples]
    errors = [sample for sample in samples if sample.error or sample.status_code is None or sample.status_code >= 400]
    return {
        "requests": len(samples),
        "successes": len(samples) - len(errors),
        "errors": len(errors),
        "error_rate": round(len(errors) / len(samples), 6) if samples else None,
        "throughput_requests_per_second": round(len(samples) / duration, 3) if duration else None,
        "latency_ms": {
            "average": round(statistics.fmean(latencies), 3) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p90": percentile(latencies, 0.90),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": round(max(latencies), 3) if latencies else None,
        },
        "errors_by_type": _error_counts(errors),
    }


def _error_counts(samples: list[Sample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        key = sample.error or f"http_{sample.status_code}"
        counts[key] = counts.get(key, 0) + 1
    return counts


async def run_load(host: str, paths: list[str], users: int, spawn_rate: float, duration: float,
                   token: str | None, timeout: float) -> tuple[list[Sample], float]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    limits = httpx.Limits(max_connections=max(users, 10), max_keepalive_connections=max(users, 10))
    samples: list[Sample] = []
    started = time.perf_counter()
    stop_at = started + duration
    async with httpx.AsyncClient(base_url=host.rstrip("/"), headers=headers, timeout=timeout, limits=limits) as client:
        async def worker(worker_id: int) -> None:
            # Spawn is paced to avoid creating a client-side connection storm.
            await asyncio.sleep(worker_id / max(spawn_rate, 1))
            if time.perf_counter() >= stop_at:
                return
            path_index = worker_id % len(paths)
            while time.perf_counter() < stop_at:
                path = paths[path_index % len(paths)]
                path_index += 1
                request_started = time.perf_counter()
                try:
                    response = await client.get(path)
                    samples.append(Sample(path, response.status_code,
                                          (time.perf_counter() - request_started) * 1000,
                                          None if response.status_code < 400 else f"http_{response.status_code}"))
                except Exception as exc:
                    samples.append(Sample(path, None, (time.perf_counter() - request_started) * 1000, type(exc).__name__))

        await asyncio.gather(*(worker(worker_id) for worker_id in range(users)))
    return samples, time.perf_counter() - started


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only OpsPilot HTTP load test")
    parser.add_argument("--profile", choices=sorted(PROFILES), help="A=100, B=500, C=1000 users")
    parser.add_argument("--host", default=os.getenv("OPSPILOT_HOST", "http://localhost:8000"))
    parser.add_argument("--users", type=int)
    parser.add_argument("--spawn-rate", type=float)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--path", action="append", dest="paths", default=None,
                        help="Read-only endpoint path; repeat for a mixed workload")
    parser.add_argument("--token", default=os.getenv("OPSPILOT_TOKEN"))
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = PROFILES[args.profile] if args.profile else {}
    users = args.users or profile.get("users", 10)
    spawn_rate = args.spawn_rate or profile.get("spawn_rate", users)
    if users < 1 or users > 1000 or args.duration <= 0 or args.duration > 3600:
        raise SystemExit("users must be 1..1000 and duration must be >0 and <=3600 seconds")
    paths = args.paths or ["/health/live"]
    started_at = datetime.now(timezone.utc).isoformat()
    samples, elapsed = asyncio.run(run_load(args.host, paths, users, spawn_rate, args.duration, args.token, args.timeout))
    result = {
        "started_at": started_at,
        "host": args.host,
        "profile": args.profile,
        "configuration": {"users": users, "spawn_rate": spawn_rate, "duration_seconds": args.duration,
                           "timeout_seconds": args.timeout, "paths": paths, "authenticated": bool(args.token)},
        "environment": {"python": sys.version, "platform": platform.platform(), "processor": platform.processor()},
        "elapsed_seconds": round(elapsed, 3),
        "summary": summarize(samples, elapsed),
        "samples": [asdict(sample) for sample in samples],
    }
    output = args.output or Path("performance/results") / f"load-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": result["summary"]}, indent=2))
    return 0 if not result["summary"]["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
