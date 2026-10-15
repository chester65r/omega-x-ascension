from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from omega.config import Capability


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentRole(StrEnum):
    CEO = "ceo"
    PLANNER = "planner"
    RESEARCH = "research"
    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    DATABASE = "database"
    DEVOPS = "devops"
    SECURITY = "security"
    QA = "qa"
    CRITIC = "critic"
    JUDGE = "judge"
    MEMORY_MANAGER = "memory_manager"
    TOOL_MANAGER = "tool_manager"
    WORKFLOW_ORCHESTRATOR = "workflow_orchestrator"
    META = "meta"


@dataclass(slots=True)
class WorkflowRun:
    goal: str
    task_type: Capability
    tenant_id: UUID
    created_by: str
    requested_actions: list[str] = field(default_factory=list)
    approval_digest: str | None = None
    id: UUID = field(default_factory=uuid4)
    status: RunStatus = RunStatus.PENDING
    output: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def digest(self) -> str:
        raw = json.dumps(
            {
                "goal": self.goal,
                "task_type": self.task_type,
                "actions": sorted(self.requested_actions),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode()).hexdigest()


class ApprovalPolicy:
    _gated = frozenset(
        {"deploy", "release", "delete", "rotate_secret", "modify_infrastructure", "execute_code"}
    )

    def requires_approval(self, actions: set[str]) -> bool:
        return bool(self._gated.intersection(actions))
