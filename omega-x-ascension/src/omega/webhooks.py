from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, Security, status
from pydantic import BaseModel, Field, SecretStr

from omega.auth import Principal, current_principal
from omega.config import Capability, get_settings
from omega.domain import ApprovalPolicy, Principal, RunStatus, WorkflowRun
from omega.notifications import (
    notify_approval_requested,
    notify_run_status_change,
    send_slack_notification,
    send_telegram_notification,
)

logger = logging.getLogger("omega.webhooks")
router = APIRouter()


def verify_github_signature(
    payload: bytes,
    signature_header: str | None,
    secret: SecretStr | str | None,
) -> bool:
    if secret is None:
        logger.warning(
            "OMEGA_GITHUB_WEBHOOK_SECRET is not configured; allowing unverified webhook in development mode."
        )
        return True
    if not signature_header:
        return False

    secret_bytes = (
        secret.get_secret_value().encode()
        if isinstance(secret, SecretStr)
        else str(secret).encode()
    )
    if not secret_bytes:
        return True

    if not signature_header.startswith("sha256="):
        return False

    expected_sig = "sha256=" + hmac.new(secret_bytes, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature_header)


def services(request: Request):
    return request.app.state.services


class NotificationTestRequest(BaseModel):
    channel: str = Field(pattern="^(slack|telegram|all)$")
    message: str = Field(default="OMEGA-X Ascension test notification", max_length=500)


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    svc=Depends(services),
):
    body_bytes = await request.body()
    cfg = get_settings()

    if not verify_github_signature(body_bytes, x_hub_signature_256, cfg.github_webhook_secret):
        logger.warning("Invalid GitHub webhook signature received")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not x_github_event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    if x_github_event == "ping":
        return {"status": "pong", "message": "OMEGA-X Ascension GitHub webhook endpoint ready"}

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    action = payload.get("action", "")

    # 1. GitHub Issues triage
    if x_github_event == "issues":
        if action not in ("opened", "reopened", "labeled"):
            return {"status": "ignored", "event": "issues", "action": action}

        issue = payload.get("issue", {})
        issue_num = issue.get("number", "unknown")
        title = issue.get("title", "Untitled issue")
        body = issue.get("body") or "No description provided."
        labels = [lbl.get("name", "") for lbl in issue.get("labels", []) if isinstance(lbl, dict)]
        html_url = issue.get("html_url", "")

        is_code_related = any(
            lbl.lower() in ("bug", "enhancement", "feature", "refactor") for lbl in labels
        ) or any(kw in title.lower() for kw in ("fix", "bug", "implement", "error", "crash"))

        task_type: Capability = "coding" if is_code_related else "reasoning"
        goal = (
            f"[GitHub Issue #{issue_num}] {title}\n"
            f"URL: {html_url}\n"
            f"Labels: {', '.join(labels)}\n\n"
            f"Description:\n{body}"
        )

        requested_actions = ["analyze_issue", "propose_solution"]
        run = WorkflowRun(
            goal=goal,
            task_type=task_type,
            tenant_id=cfg.webhook_tenant_id,
            created_by="github-webhook",
            requested_actions=requested_actions,
        )

        await svc.repo.create_run(run, run.created_by, is_enqueued=True)
        logger.info("Triaged GitHub issue #%s into run %s", issue_num, run.id)

        # Notify via Slack / Telegram
        if cfg.notifications_enabled:
            if ApprovalPolicy.is_approval_required(run.requested_actions):
                await notify_approval_requested(
                    run,
                    slack_webhook_url=cfg.slack_webhook_url,
                    telegram_bot_token=cfg.telegram_bot_token,
                    telegram_chat_id=cfg.telegram_chat_id,
                    client=svc.http,
                )
            else:
                await notify_run_status_change(
                    run,
                    RunStatus.PENDING,
                    slack_webhook_url=cfg.slack_webhook_url,
                    telegram_bot_token=cfg.telegram_bot_token,
                    telegram_chat_id=cfg.telegram_chat_id,
                    client=svc.http,
                )

        return {
            "status": "triaged",
            "event": "issues",
            "action": action,
            "run_id": str(run.id),
            "task_type": task_type,
        }

    # 2. Pull Request triage & automated review
    if x_github_event == "pull_request":
        if action not in ("opened", "synchronize", "reopened"):
            return {"status": "ignored", "event": "pull_request", "action": action}

        pr = payload.get("pull_request", {})
        pr_num = pr.get("number", "unknown")
        title = pr.get("title", "Untitled PR")
        body = pr.get("body") or "No description provided."
        html_url = pr.get("html_url", "")
        head = pr.get("head", {})
        ref = head.get("ref", "unknown")
        sha = head.get("sha", "unknown")

        goal = (
            f"[GitHub PR #{pr_num}] Automated Code Review: {title}\n"
            f"Branch: {ref} ({sha})\n"
            f"URL: {html_url}\n\n"
            f"PR Summary:\n{body}"
        )

        requested_actions = ["code_review", "security_check"]
        run = WorkflowRun(
            goal=goal,
            task_type="coding",
            tenant_id=cfg.webhook_tenant_id,
            created_by="github-webhook",
            requested_actions=requested_actions,
        )

        await svc.repo.create_run(run, run.created_by, is_enqueued=True)
        logger.info("Triaged GitHub PR #%s into review run %s", pr_num, run.id)

        if cfg.notifications_enabled:
            await notify_run_status_change(
                run,
                RunStatus.PENDING,
                slack_webhook_url=cfg.slack_webhook_url,
                telegram_bot_token=cfg.telegram_bot_token,
                telegram_chat_id=cfg.telegram_chat_id,
                client=svc.http,
            )

        return {
            "status": "triaged",
            "event": "pull_request",
            "action": action,
            "run_id": str(run.id),
            "task_type": "coding",
        }

    return {"status": "unhandled_event", "event": x_github_event}


@router.post("/test-notification")
async def test_notification(
    body: NotificationTestRequest,
    principal: Principal = Security(current_principal, scopes=["runs:write"]),
    svc=Depends(services),
):
    cfg = get_settings()
    results = {}

    if body.channel in ("slack", "all"):
        if not cfg.slack_webhook_url:
            results["slack"] = {"configured": False, "status": "missing_slack_webhook_url"}
        else:
            success = await send_slack_notification(
                cfg.slack_webhook_url, f"🔔 {body.message}", client=svc.http
            )
            results["slack"] = {"configured": True, "delivered": success}

    if body.channel in ("telegram", "all"):
        if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
            results["telegram"] = {
                "configured": False,
                "status": "missing_telegram_credentials",
            }
        else:
            success = await send_telegram_notification(
                cfg.telegram_bot_token,
                cfg.telegram_chat_id,
                f"🔔 <b>OMEGA-X Test:</b> {body.message}",
                client=svc.http,
            )
            results["telegram"] = {"configured": True, "delivered": success}

    return {"status": "completed", "results": results}
