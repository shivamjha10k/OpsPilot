"""Create idempotent development users. Never run this in production."""

import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.domain import Environment, Runbook, RunbookStatus, Service, ServiceStatus
from app.models.user import Role
from app.repositories.user_repository import UserRepository
from app.services.auth_service import hash_password


async def seed() -> None:
    settings = get_settings()
    if settings.environment.lower() != "development":
        raise RuntimeError("Development seed is only allowed when APP_ENV=development")

    users = (
        ("OpsPilot Admin", settings.dev_admin_email, settings.dev_admin_password, Role.ADMIN),
        ("OpsPilot Engineer", settings.dev_engineer_email, settings.dev_engineer_password, Role.ENGINEER),
        ("OpsPilot Viewer", settings.dev_viewer_email, settings.dev_viewer_password, Role.VIEWER),
    )
    if any(not password.strip() for _, _, password, _ in users):
        raise RuntimeError("Set DEV_*_PASSWORD values before running the development seed")
    async with SessionLocal() as session:
        repository = UserRepository(session)
        for name, email, password, role in users:
            if await repository.get_by_email(email):
                continue
            try:
                await repository.create(
                    name=name,
                    email=email,
                    password_hash=hash_password(password),
                    role=role,
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise

        admin = await repository.get_by_email(settings.dev_admin_email)
        if admin is None:
            raise RuntimeError("development admin user was not created")

        services = (
            ("payment-service", "Payment processing service", Environment.PRODUCTION),
            ("order-service", "Order lifecycle service", Environment.PRODUCTION),
            ("user-service", "Identity and profile service", Environment.PRODUCTION),
            ("notification-service", "Outbound notification service", Environment.PRODUCTION),
            ("search-service", "Search and indexing service", Environment.STAGING),
        )
        for name, description, environment in services:
            exists = await session.scalar(select(Service).where(Service.name == name))
            if exists is None:
                session.add(
                    Service(
                        name=name,
                        description=description,
                        environment=environment,
                        status=ServiceStatus.HEALTHY,
                        owner_id=admin.id,
                    )
                )
        await session.commit()

        runbooks = (
            (
                "Database Connection Exhaustion",
                "Diagnose and contain connection pool exhaustion.",
                "Check database connection utilization, recent deployments, pool settings, and timeout logs. Roll back the latest deployment when evidence supports a regression.",
            ),
            (
                "High CPU Troubleshooting",
                "Investigate sustained CPU saturation.",
                "Inspect CPU, latency, error rate, and recent deployment telemetry. Restart or scale only after confirming the affected service and environment.",
            ),
            (
                "Failed Deployment Rollback",
                "Safely assess a failed deployment.",
                "Confirm the deployment version, compare health before and after release, and request a controlled rollback when policy allows.",
            ),
            (
                "Queue Backlog Recovery",
                "Recover from growing asynchronous work queues.",
                "Inspect queue depth, worker utilization, and processing latency. Increase worker capacity within approved limits and verify backlog recovery.",
            ),
            (
                "Memory Leak Investigation",
                "Investigate continuously increasing memory usage.",
                "Compare memory over time, correlate with deployments and request volume, and document whether a restart is a temporary or permanent mitigation.",
            ),
        )
        for title, description, content in runbooks:
            exists = await session.scalar(select(Runbook).where(Runbook.title == title, Runbook.version == 1))
            if exists is None:
                session.add(
                    Runbook(
                        title=title,
                        description=description,
                        content=content,
                        version=1,
                        status=RunbookStatus.ACTIVE,
                        created_by=admin.id,
                    )
                )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
