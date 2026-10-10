from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from omega.auth import Principal, current_principal
from omega.config import Capability
from omega.domain import ApprovalPolicy, RunStatus, WorkflowRun
from omega.model_router import NoEligibleModel

router = APIRouter()


class RunCreate(BaseModel):
    goal: str = Field(min_length=3, max_length=20000)
    task_type: Capability
    requested_actions: list[str] = Field(default_factory=list, max_length=20)


class RunView(BaseModel):
    id: UUID
    goal: str
    task_type: str
    status: RunStatus
    output: str | None
    error: str | None


def services(request: Request):
    return request.app.state.services


def view(run: WorkflowRun) -> RunView:
    return RunView(
        id=run.id,
        goal=run.goal,
        task_type=run.task_type,
        status=run.status,
        output=run.output,
        error=run.error,
    )


@router.post("/runs", response_model=RunView, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    body: RunCreate,
    principal: Principal = Security(current_principal, scopes=["runs:write"]),
    svc=Depends(services),
):
    try:
        await svc.router.select(body.task_type)
    except NoEligibleModel as exc:
        raise HTTPException(503, str(exc)) from exc

    run = WorkflowRun(
        goal=body.goal,
        task_type=body.task_type,
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        requested_actions=body.requested_actions,
    )
    if ApprovalPolicy().requires_approval(set(body.requested_actions)):
        run.status = RunStatus.WAITING_APPROVAL
        run.approval_digest = run.digest()

    await svc.repo.create_run(
        run,
        principal.user_id,
        run.status == RunStatus.PENDING,
    )
    return view(run)


@router.get("/runs", response_model=list[RunView])
async def list_runs(
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Security(current_principal, scopes=["runs:read"]),
    svc=Depends(services),
):
    runs = await svc.repo.list_runs(principal.tenant_id, limit)
    return [view(run) for run in runs]


@router.get("/runs/{run_id}", response_model=RunView)
async def get_run(
    run_id: UUID,
    principal: Principal = Security(current_principal, scopes=["runs:read"]),
    svc=Depends(services),
):
    run = await svc.repo.get(principal.tenant_id, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return view(run)


@router.post("/runs/{run_id}/approve", status_code=204)
async def approve(
    run_id: UUID,
    principal: Principal = Security(current_principal, scopes=["runs:approve"]),
    svc=Depends(services),
):
    run = await svc.repo.get(principal.tenant_id, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if (
        run.status != RunStatus.WAITING_APPROVAL
        or run.approval_digest != run.digest()
    ):
        raise HTTPException(409, "approval request is stale or invalid")
    if not await svc.repo.approve_and_enqueue(
        run.tenant_id,
        run.id,
        run.approval_digest,
        principal.user_id,
    ):
        raise HTTPException(409, "approval request changed concurrently")


class ComputerCommand(BaseModel):
    command: str = Field(min_length=1, max_length=1000)


@router.get("/browser/search")
async def browser_search(
    q: str,
    principal: Principal = Security(current_principal, scopes=["runs:read"]),
    svc=Depends(services),
):
    return await svc.browser.search(q)


@router.get("/browser/proxy", response_class=HTMLResponse)
async def browser_proxy(
    url: str,
    principal: Principal = Security(current_principal, scopes=["runs:read"]),
    svc=Depends(services),
):
    try:
        html, content_type = await svc.browser.proxy(url)
        return HTMLResponse(
            content=html,
            media_type=content_type.split(";")[0],
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            502,
            f"Failed to fetch URL: {type(exc).__name__}",
        ) from exc


@router.post("/computer/execute")
async def computer_execute(
    body: ComputerCommand,
    principal: Principal = Security(current_principal, scopes=["runs:write"]),
    svc=Depends(services),
):
    if not svc.computer.enabled:
        raise HTTPException(
            503,
            "computer execution is disabled; enable it only in a trusted deployment",
        )
    try:
        return await svc.computer.execute(body.command)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/computer/files")
async def computer_files(
    path: str = ".",
    principal: Principal = Security(current_principal, scopes=["runs:read"]),
    svc=Depends(services),
):
    if not svc.computer.enabled:
        raise HTTPException(
            503,
            "computer execution is disabled; enable it only in a trusted deployment",
        )
    return await svc.computer.list_dir(path)
