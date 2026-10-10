from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from pydantic import SecretStr

from omega.config import Settings
from omega.domain import RunStatus, WorkflowRun
from omega.notifications import (
    notify_approval_requested,
    send_slack_notification,
    send_telegram_notification,
)
from omega.webhooks import verify_github_signature


def test_verify_github_signature_valid():
    secret = SecretStr("my-webhook-secret-12345")
    payload = b'{"action":"opened","issue":{"number":42}}'
    expected_hmac = "sha256=" + hmac.new(
        secret.get_secret_value().encode(), payload, hashlib.sha256
    ).hexdigest()

    assert verify_github_signature(payload, expected_hmac, secret) is True


def test_verify_github_signature_invalid():
    secret = SecretStr("my-webhook-secret-12345")
    payload = b'{"action":"opened"}'
    fake_hmac = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    assert verify_github_signature(payload, fake_hmac, secret) is False
    assert verify_github_signature(payload, None, secret) is False


def test_verify_github_signature_no_secret():
    payload = b'{"action":"opened"}'
    # If no secret is configured, passes through
    assert verify_github_signature(payload, None, None) is True


@pytest.mark.asyncio
async def test_send_slack_notification_success():
    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_client.post.return_value = mock_resp

    res = await send_slack_notification(
        webhook_url="https://hooks.slack.com/services/T00/B00/X00",
        text="Test message",
        client=mock_client,
    )
    assert res is True
    assert mock_client.post.called


@pytest.mark.asyncio
async def test_send_telegram_notification_success():
    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_client.post.return_value = mock_resp

    res = await send_telegram_notification(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        chat_id="-1001234567890",
        text="Test message",
        client=mock_client,
    )
    assert res is True
    assert mock_client.post.called


@pytest.mark.asyncio
async def test_notify_approval_requested():
    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_client.post.return_value = mock_resp

    run = WorkflowRun(
        goal="Deploy new staging cluster",
        task_type="planning",
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        created_by="tester",
        requested_actions=["deploy", "modify_infrastructure"],
    )

    results = await notify_approval_requested(
        run,
        slack_webhook_url="https://hooks.slack.com/services/T00/B00/X00",
        telegram_bot_token="123456:TOKEN",
        telegram_chat_id="-100999",
        client=mock_client,
    )
    assert results["slack"] is True
    assert results["telegram"] is True
