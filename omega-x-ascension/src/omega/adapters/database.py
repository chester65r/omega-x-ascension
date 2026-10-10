from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import AsyncIterator
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from omega.domain import RunStatus, WorkflowRun


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "workflow_runs"

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(255), index=True)
    goal: Mapped[str] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(
            RunStatus,
            name="run_status",
            values_callable=lambda cls: [item.value for item in cls],
        )
    )
    requested_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    approval_digest: Mapped[str | None] = mapped_column(String(64))
    output: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_workflow_runs_tenant_created", "tenant_id", "created_at"),
    )


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    COMPLETED = "COMPLETED"
    DEAD_LETTER = "DEAD_LETTER"


class WorkflowJobRow(Base):
    __tablename__ = "workflow_jobs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(
            JobStatus,
            name="job_status",
            values_callable=lambda cls: [item.value for item in cls],
        ),
        default=JobStatus.QUEUED,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["workflow_runs.tenant_id", "workflow_runs.id"],
            ondelete="CASCADE",
        ),
        Index("uq_job_tenant_run", "tenant_id", "run_id", unique=True),
    )


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["workflow_runs.tenant_id", "workflow_runs.id"],
            ondelete="CASCADE",
        ),
        Index("ix_audit_events_tenant_run", "tenant_id", "run_id"),
    )


def build_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)


class SqlRunRepository:
    def __init__(self, maker: async_sessionmaker[AsyncSession]):
        self._maker = maker

    @asynccontextmanager
    async def _tenant_session(self, tenant_id: UUID) -> AsyncIterator[AsyncSession]:
        async with self._maker() as session:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('omega.tenant_id', :tenant_id, true)"),
                    {"tenant_id": str(tenant_id)},
                )
                yield session

    @staticmethod
    def _run_from_row(row: RunRow) -> WorkflowRun:
        return WorkflowRun(
            id=row.id,
            tenant_id=row.tenant_id,
            created_by=row.created_by,
            goal=row.goal,
            task_type=row.task_type,
            status=row.status,
            requested_actions=row.requested_actions or [],
            approval_digest=row.approval_digest,
            output=row.output,
            error=row.error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def add(self, run: WorkflowRun) -> None:
        async with self._tenant_session(run.tenant_id) as session:
            session.add(
                RunRow(
                    tenant_id=run.tenant_id,
                    id=run.id,
                    created_by=run.created_by,
                    goal=run.goal,
                    task_type=run.task_type,
                    status=run.status,
                    requested_actions=run.requested_actions,
                    approval_digest=run.approval_digest,
                    output=run.output,
                    error=run.error,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                )
            )

    async def get(self, tenant_id: UUID, run_id: UUID) -> WorkflowRun | None:
        async with self._tenant_session(tenant_id) as session:
            row = (
                await session.execute(
                    select(RunRow).where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.id == run_id,
                    )
                )
            ).scalar_one_or_none()
            return None if row is None else self._run_from_row(row)

    async def list_runs(self, tenant_id: UUID, limit: int = 50) -> list[WorkflowRun]:
        """Return recent runs for one tenant, newest first."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        async with self._tenant_session(tenant_id) as session:
            rows = (
                await session.execute(
                    select(RunRow)
                    .where(RunRow.tenant_id == tenant_id)
                    .order_by(RunRow.created_at.desc(), RunRow.id.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [self._run_from_row(row) for row in rows]

    async def save(self, tenant_id: UUID, run: WorkflowRun) -> None:
        if tenant_id != run.tenant_id:
            raise PermissionError("cross-tenant write rejected")

        async with self._tenant_session(tenant_id) as session:
            row = (
                await session.execute(
                    select(RunRow)
                    .where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.id == run.id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise LookupError(str(run.id))

            row.status = run.status
            row.approval_digest = run.approval_digest
            row.output = run.output
            row.error = run.error
            row.updated_at = datetime.now(UTC)

    async def list_events(
        self,
        tenant_id: UUID,
        limit: int = 100,
        run_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        """Read recent audit events for the active tenant only."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        async with self._tenant_session(tenant_id) as session:
            statement = (
                select(AuditEventRow)
                .where(AuditEventRow.tenant_id == tenant_id)
                .order_by(AuditEventRow.created_at.desc(), AuditEventRow.id.desc())
                .limit(limit)
            )
            if run_id is not None:
                statement = statement.where(AuditEventRow.run_id == run_id)
            rows = (await session.execute(statement)).scalars().all()
            return [
                {
                    "id": row.id,
                    "run_id": str(row.run_id),
                    "kind": row.kind,
                    "payload": row.payload,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    async def append_event(
        self,
        tenant_id: UUID,
        run_id: UUID,
        kind: str,
        payload: dict[str, object],
    ) -> None:
        async with self._tenant_session(tenant_id) as session:
            exists = (
                await session.execute(
                    select(RunRow.id).where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.id == run_id,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                raise LookupError(str(run_id))

            session.add(
                AuditEventRow(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    kind=kind,
                    payload=payload,
                )
            )

    async def enqueue(self, tenant_id: UUID, run_id: UUID) -> None:
        async with self._tenant_session(tenant_id) as session:
            run_exists = (
                await session.execute(
                    select(RunRow.id).where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.id == run_id,
                    )
                )
            ).scalar_one_or_none()
            if run_exists is None:
                raise LookupError(str(run_id))

            existing = (
                await session.execute(
                    select(WorkflowJobRow).where(
                        WorkflowJobRow.tenant_id == tenant_id,
                        WorkflowJobRow.run_id == run_id,
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(WorkflowJobRow(tenant_id=tenant_id, run_id=run_id))
            elif existing.status in {JobStatus.COMPLETED, JobStatus.DEAD_LETTER}:
                existing.status = JobStatus.QUEUED
                existing.available_at = datetime.now(UTC)
                existing.last_error_code = None
                existing.updated_at = datetime.now(UTC)

    async def claim(self, worker_id: str, lease_seconds: int = 120):
        if not worker_id or lease_seconds <= 0:
            raise ValueError("worker_id must be non-empty and lease_seconds must be positive")

        async with self._maker() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        text("SELECT * FROM claim_workflow_job(:worker, :lease)"),
                        {"worker": worker_id, "lease": lease_seconds},
                    )
                ).mappings().first()

                if row is None:
                    return None

                return (
                    row["tenant_id"],
                    row["run_id"],
                    row["id"],
                    row["attempt_count"],
                )

    async def heartbeat(
        self,
        tenant_id: UUID,
        job_id: UUID,
        attempt: int,
        worker_id: str,
        lease_seconds: int = 120,
    ) -> bool:
        if attempt < 0 or lease_seconds <= 0 or not worker_id:
            return False

        async with self._tenant_session(tenant_id) as session:
            result = await session.execute(
                text(
                    """
                    UPDATE workflow_jobs
                    SET lease_expires_at = now() + make_interval(secs => :lease),
                        updated_at = now()
                    WHERE tenant_id = :tenant_id
                      AND id = :id
                      AND status = 'LEASED'
                      AND attempt_count = :attempt
                      AND lease_owner = :worker
                    """
                ),
                {
                    "tenant_id": str(tenant_id),
                    "lease": lease_seconds,
                    "id": job_id,
                    "attempt": attempt,
                    "worker": worker_id,
                },
            )
            return result.rowcount == 1

    async def finish_job(
        self,
        tenant_id: UUID,
        job_id: UUID,
        attempt: int,
        worker_id: str,
        ok: bool,
        error_code: str | None = None,
    ) -> bool:
        if attempt < 0 or not worker_id:
            return False

        async with self._tenant_session(tenant_id) as session:
            job = (
                await session.execute(
                    select(WorkflowJobRow)
                    .where(
                        WorkflowJobRow.tenant_id == tenant_id,
                        WorkflowJobRow.id == job_id,
                        WorkflowJobRow.attempt_count == attempt,
                        WorkflowJobRow.lease_owner == worker_id,
                        WorkflowJobRow.status == JobStatus.LEASED,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None:
                return False

            run = (
                await session.execute(
                    select(RunRow)
                    .where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.id == job.run_id,
                    )
                    .with_for_update()
                )
            ).scalar_one()

            now = datetime.now(UTC)
            job.last_error_code = error_code
            job.lease_owner = None
            job.lease_expires_at = None
            job.updated_at = now

            if ok:
                job.status = JobStatus.COMPLETED
                run.status = RunStatus.SUCCEEDED
                run.error = None
                run.updated_at = now
                session.add(
                    AuditEventRow(
                        tenant_id=tenant_id,
                        run_id=run.id,
                        kind="run.succeeded",
                        payload={"attempt": attempt},
                    )
                )
                return True

            if job.attempt_count >= job.max_attempts:
                job.status = JobStatus.DEAD_LETTER
                run.status = RunStatus.FAILED
                run.error = f"workflow failed after retries; reference={run.id}"
                event_kind = "run.failed"
            else:
                job.status = JobStatus.QUEUED
                job.available_at = now + timedelta(
                    seconds=min(300, 2**job.attempt_count)
                )
                run.status = RunStatus.PENDING
                run.error = f"workflow failed; reference={run.id}"
                event_kind = "run.retry_scheduled"

            run.updated_at = now
            session.add(
                AuditEventRow(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    kind=event_kind,
                    payload={"error_code": error_code, "attempt": attempt},
                )
            )
            return True

    async def create_run(self, run: WorkflowRun, actor: str, enqueue: bool) -> None:
        async with self._tenant_session(run.tenant_id) as session:
            session.add(
                RunRow(
                    tenant_id=run.tenant_id,
                    id=run.id,
                    created_by=run.created_by,
                    goal=run.goal,
                    task_type=run.task_type,
                    status=run.status,
                    requested_actions=run.requested_actions,
                    approval_digest=run.approval_digest,
                    output=run.output,
                    error=run.error,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                )
            )
            await session.flush()

            session.add(
                AuditEventRow(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    kind="run.created",
                    payload={"actor": actor, "approval_required": not enqueue},
                )
            )

            if enqueue:
                session.add(
                    WorkflowJobRow(
                        tenant_id=run.tenant_id,
                        run_id=run.id,
                    )
                )

    async def approve_and_enqueue(
        self,
        tenant_id: UUID,
        run_id: UUID,
        expected_digest: str,
        actor: str,
    ) -> bool:
        async with self._tenant_session(tenant_id) as session:
            run = (
                await session.execute(
                    select(RunRow)
                    .where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.id == run_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()

            if (
                run is None
                or run.status != RunStatus.WAITING_APPROVAL
                or run.approval_digest != expected_digest
            ):
                return False

            run.status = RunStatus.PENDING
            run.updated_at = datetime.now(UTC)

            session.add(
                AuditEventRow(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    kind="run.approved",
                    payload={"actor": actor, "digest": expected_digest},
                )
            )

            existing = (
                await session.execute(
                    select(WorkflowJobRow.id).where(
                        WorkflowJobRow.tenant_id == tenant_id,
                        WorkflowJobRow.run_id == run_id,
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    WorkflowJobRow(
                        tenant_id=tenant_id,
                        run_id=run_id,
                    )
                )

            return True

    async def complete_success(
        self,
        tenant_id: UUID,
        job_id: UUID,
        attempt: int,
        worker_id: str,
        output: str,
    ) -> bool:
        async with self._tenant_session(tenant_id) as session:
            job = (
                await session.execute(
                    select(WorkflowJobRow)
                    .where(
                        WorkflowJobRow.tenant_id == tenant_id,
                        WorkflowJobRow.id == job_id,
                        WorkflowJobRow.attempt_count == attempt,
                        WorkflowJobRow.lease_owner == worker_id,
                        WorkflowJobRow.status == JobStatus.LEASED,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None:
                return False

            run = (
                await session.execute(
                    select(RunRow)
                    .where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.id == job.run_id,
                    )
                    .with_for_update()
                )
            ).scalar_one()

            now = datetime.now(UTC)
            run.output = output
            run.error = None
            run.status = RunStatus.SUCCEEDED
            run.updated_at = now

            job.status = JobStatus.COMPLETED
            job.lease_owner = None
            job.lease_expires_at = None
            job.updated_at = now

            session.add(
                AuditEventRow(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    kind="run.succeeded",
                    payload={"attempt": attempt},
                )
            )
            return True

    async def fail_attempt(
        self,
        tenant_id: UUID,
        job_id: UUID,
        attempt: int,
        worker_id: str,
        error_code: str,
    ) -> bool:
        async with self._tenant_session(tenant_id) as session:
            job = (
                await session.execute(
                    select(WorkflowJobRow)
                    .where(
                        WorkflowJobRow.tenant_id == tenant_id,
                        WorkflowJobRow.id == job_id,
                        WorkflowJobRow.attempt_count == attempt,
                        WorkflowJobRow.lease_owner == worker_id,
                        WorkflowJobRow.status == JobStatus.LEASED,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None:
                return False

            run = (
                await session.execute(
                    select(RunRow)
                    .where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.id == job.run_id,
                    )
                    .with_for_update()
                )
            ).scalar_one()

            now = datetime.now(UTC)
            job.last_error_code = error_code
            job.lease_owner = None
            job.lease_expires_at = None
            job.updated_at = now

            if job.attempt_count >= job.max_attempts:
                job.status = JobStatus.DEAD_LETTER
                run.status = RunStatus.FAILED
                run.error = f"workflow failed after retries; reference={run.id}"
                kind = "run.failed"
            else:
                job.status = JobStatus.QUEUED
                job.available_at = now + timedelta(
                    seconds=min(300, 2**job.attempt_count)
                )
                run.status = RunStatus.PENDING
                run.error = f"workflow failed; reference={run.id}"
                kind = "run.retry_scheduled"

            run.updated_at = now
            session.add(
                AuditEventRow(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    kind=kind,
                    payload={"error_code": error_code, "attempt": attempt},
                )
            )
            return True
