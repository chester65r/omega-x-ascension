from __future__ import annotations

import logging
from typing import Any
import httpx
from pydantic import SecretStr

from omega.domain import RunStatus, WorkflowRun

logger = logging.getLogger("omega.notifications")


def _secret_value(val: SecretStr | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, SecretStr):
        return val.get_secret_value()
    return str(val)


async def send_slack_notification(
    webhook_url: SecretStr | str | None,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    url = _secret_value(webhook_url)
    if not url:
        return False

    payload: dict[str, Any] = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await http.post(url, json=payload)
        if resp.status_code >= 400:
            logger.warning("Slack notification failed: HTTP %s %s", resp.status_code, resp.text)
            return False
        return True
    except Exception as exc:
        logger.warning("Slack notification error: %s", exc)
        return False
    finally:
        if owns_client:
            await http.aclose()


async def send_telegram_notification(
    bot_token: SecretStr | str | None,
    chat_id: str | None,
    text: str,
    parse_mode: str = "HTML",
    client: httpx.AsyncClient | None = None,
) -> bool:
    token = _secret_value(bot_token)
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await http.post(url, json=payload)
        if resp.status_code >= 400:
            logger.warning("Telegram notification failed: HTTP %s %s", resp.status_code, resp.text)
            return False
        return True
    except Exception as exc:
        logger.warning("Telegram notification error: %s", exc)
        return False
    finally:
        if owns_client:
            await http.aclose()


async def notify_approval_requested(
    run: WorkflowRun,
    *,
    slack_webhook_url: SecretStr | str | None = None,
    telegram_bot_token: SecretStr | str | None = None,
    telegram_chat_id: str | None = None,
    dashboard_base_url: str = "https://omega.lovable.app",
    client: httpx.AsyncClient | None = None,
) -> dict[str, bool]:
    results = {"slack": False, "telegram": False}
    actions_str = ", ".join(run.requested_actions) or "gated execution"

    # Slack message
    slack_text = f"🚨 *OMEGA-X Approval Required* for Run `{run.id}`\n*Goal:* {run.goal[:200]}\n*Actions:* `{actions_str}`"
    slack_blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🚨 OMEGA-X Approval Required", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Run ID:*\n`{run.id}`"},
                {"type": "mrkdwn", "text": f"*Task Type:*\n`{run.task_type}`"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Goal:*\n{run.goal[:300]}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Gated Actions Requiring Approval:*\n`{actions_str}`"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Review in Mission Control"},
                    "url": f"{dashboard_base_url}/#run-{run.id}",
                    "style": "primary",
                }
            ],
        },
    ]

    # Telegram message
    tg_text = (
        f"🚨 <b>OMEGA-X Approval Required</b>\n\n"
        f"<b>Run ID:</b> <code>{run.id}</code>\n"
        f"<b>Task Type:</b> <code>{run.task_type}</code>\n"
        f"<b>Actions:</b> <code>{actions_str}</code>\n\n"
        f"<b>Goal:</b>\n{run.goal[:300]}\n\n"
        f"<a href=\"{dashboard_base_url}/#run-{run.id}\">Review in Mission Control</a>"
    )

    if slack_webhook_url:
        results["slack"] = await send_slack_notification(
            slack_webhook_url, slack_text, blocks=slack_blocks, client=client
        )
    if telegram_bot_token and telegram_chat_id:
        results["telegram"] = await send_telegram_notification(
            telegram_bot_token, telegram_chat_id, tg_text, parse_mode="HTML", client=client
        )

    return results


async def notify_run_status_change(
    run: WorkflowRun,
    status: RunStatus,
    *,
    slack_webhook_url: SecretStr | str | None = None,
    telegram_bot_token: SecretStr | str | None = None,
    telegram_chat_id: str | None = None,
    dashboard_base_url: str = "https://omega.lovable.app",
    client: httpx.AsyncClient | None = None,
) -> dict[str, bool]:
    results = {"slack": False, "telegram": False}
    emoji = "✅" if status == RunStatus.SUCCEEDED else "❌" if status == RunStatus.FAILED else "ℹ️"
    
    text = (
        f"{emoji} *OMEGA-X Run {status.value.upper()}*\n"
        f"*ID:* `{run.id}`\n"
        f"*Goal:* {run.goal[:150]}\n"
    )
    if run.error:
        text += f"*Error:* `{run.error[:200]}`\n"

    tg_text = (
        f"{emoji} <b>OMEGA-X Run {status.value.upper()}</b>\n\n"
        f"<b>ID:</b> <code>{run.id}</code>\n"
        f"<b>Goal:</b> {run.goal[:150]}\n"
    )
    if run.error:
        tg_text += f"<b>Error:</b> <code>{run.error[:200]}</code>\n"

    if slack_webhook_url:
        results["slack"] = await send_slack_notification(slack_webhook_url, text, client=client)
    if telegram_bot_token and telegram_chat_id:
        results["telegram"] = await send_telegram_notification(
            telegram_bot_token, telegram_chat_id, tg_text, parse_mode="HTML", client=client
        )

    return results
