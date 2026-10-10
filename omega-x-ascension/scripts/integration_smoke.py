from __future__ import annotations

"""Exercise API auth -> Postgres queue -> worker -> model gateway -> persisted output."""

import os
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt

from omega.config import get_settings

BASE_URL = os.environ.get("OMEGA_INTEGRATION_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    cfg = get_settings()
    tenant_id = uuid4()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "github-actions-integration-test",
            "tenant_id": str(tenant_id),
            "scope": "runs:read runs:write runs:approve",
            "iss": cfg.jwt_issuer,
            "aud": cfg.jwt_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        cfg.jwt_secret.get_secret_value(),
        algorithm=cfg.jwt_algorithm,
    )
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=10) as client:
        live = client.get(f"{BASE_URL}/health/live")
        require(live.status_code == 200 and live.json().get("status") == "ok",
                f"API liveness check failed: HTTP {live.status_code}")

        ready = client.get(f"{BASE_URL}/health/ready")
        require(ready.status_code == 200 and ready.json().get("healthy_models", 0) >= 1,
                f"API not ready with fixture model: HTTP {ready.status_code}, body={ready.text[:300]}")

        models = client.get(f"{BASE_URL}/health/models")
        require(models.status_code == 200 and models.json().get("healthy_models", 0) >= 1,
                f"Model gateway check failed: HTTP {models.status_code}")

        unauthorized = client.get(f"{BASE_URL}/v1/runs")
        require(unauthorized.status_code == 401,
                f"Unauthenticated run history should be rejected; got HTTP {unauthorized.status_code}")

        # These endpoints must enforce capability scopes before checking runtime policy.
        files_without_scope = client.get(f"{BASE_URL}/v1/computer/files", headers=headers)
        require(files_without_scope.status_code == 403,
                f"Workspace files must require computer:read; got HTTP {files_without_scope.status_code}")
        shell_without_scope = client.post(
            f"{BASE_URL}/v1/computer/execute",
            headers=headers,
            json={"command": "echo must-not-run"},
        )
        require(shell_without_scope.status_code == 403,
                f"Shell execution must require computer:execute; got HTTP {shell_without_scope.status_code}")

        created = client.post(
            f"{BASE_URL}/v1/runs",
            headers=headers,
            json={
                "goal": "Verify that authenticated task creation reaches a worker and persists a final result.",
                "task_type": "planning",
            },
        )
        require(created.status_code == 202,
                f"Task submission failed: HTTP {created.status_code}, body={created.text[:500]}")
        run_id = created.json()["id"]

        deadline = time.monotonic() + 90
        last = created.json()
        while time.monotonic() < deadline:
            response = client.get(f"{BASE_URL}/v1/runs/{run_id}", headers=headers)
            require(response.status_code == 200,
                    f"Run polling failed: HTTP {response.status_code}, body={response.text[:300]}")
            last = response.json()
            if last["status"] == "succeeded":
                break
            if last["status"] == "failed":
                raise RuntimeError(f"Worker did not complete fixture run: {last}")
            time.sleep(1)

        require(last["status"] == "succeeded",
                f"Timed out waiting for worker completion; last status={last.get('status')}")
        require("E2E integration completed" in (last.get("output") or ""),
                "Final output was not produced by the expected test model response")

        events = client.get(f"{BASE_URL}/v1/events", headers=headers, params={"run_id": run_id})
        require(events.status_code == 200, f"Audit event endpoint failed: HTTP {events.status_code}")
        require(len(events.json()) >= 2, "Expected persisted start/completion audit events")

        # Tenant isolation: a different valid tenant cannot enumerate this run by ID.
        other_tenant = uuid4()
        other_now = datetime.now(UTC)
        other_token = jwt.encode(
            {
                "sub": "github-actions-other-tenant",
                "tenant_id": str(other_tenant),
                "scope": "runs:read",
                "iss": cfg.jwt_issuer,
                "aud": cfg.jwt_audience,
                "iat": other_now,
                "exp": other_now + timedelta(minutes=5),
            },
            cfg.jwt_secret.get_secret_value(),
            algorithm=cfg.jwt_algorithm,
        )
        cross_tenant = client.get(
            f"{BASE_URL}/v1/runs/{run_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        require(cross_tenant.status_code == 404,
                f"Cross-tenant run reads must be hidden; got HTTP {cross_tenant.status_code}")

        # A sensitive action must wait for approval, then be enqueued and persisted as complete.
        gated = client.post(
            f"{BASE_URL}/v1/runs",
            headers=headers,
            json={
                "goal": "Verify approval-gated workflow execution and persisted completion.",
                "task_type": "planning",
                "requested_actions": ["deploy"],
            },
        )
        require(gated.status_code == 202,
                f"Approval-gated task creation failed: HTTP {gated.status_code}, body={gated.text[:300]}")
        gated_run = gated.json()
        require(gated_run.get("status") == "waiting_approval",
                f"Sensitive task must wait for approval, got status={gated_run.get('status')}")

        no_approval_token = jwt.encode(
            {
                "sub": "github-actions-without-approval",
                "tenant_id": str(tenant_id),
                "scope": "runs:read runs:write",
                "iss": cfg.jwt_issuer,
                "aud": cfg.jwt_audience,
                "iat": now,
                "exp": now + timedelta(minutes=5),
            },
            cfg.jwt_secret.get_secret_value(),
            algorithm=cfg.jwt_algorithm,
        )
        denied_approval = client.post(
            f"{BASE_URL}/v1/runs/{gated_run['id']}/approve",
            headers={"Authorization": f"Bearer {no_approval_token}"},
        )
        require(denied_approval.status_code == 403,
                f"Approving must require runs:approve; got HTTP {denied_approval.status_code}")

        approved = client.post(f"{BASE_URL}/v1/runs/{gated_run['id']}/approve", headers=headers)
        require(approved.status_code == 204,
                f"Explicit approval failed: HTTP {approved.status_code}, body={approved.text[:300]}")

        approval_deadline = time.monotonic() + 90
        final_approved = gated_run
        while time.monotonic() < approval_deadline:
            response = client.get(f"{BASE_URL}/v1/runs/{gated_run['id']}", headers=headers)
            require(response.status_code == 200,
                    f"Approved run polling failed: HTTP {response.status_code}")
            final_approved = response.json()
            if final_approved["status"] == "succeeded":
                break
            if final_approved["status"] == "failed":
                raise RuntimeError(f"Approved run failed in worker: {final_approved.get('error')}")
            time.sleep(1)
        require(final_approved["status"] == "succeeded" and bool(final_approved.get("output")),
                "Approved run was not processed to a non-empty persisted result")

        # A token with full computer scopes still cannot bypass a server-disabled feature flag.
        computer_token = jwt.encode(
            {
                "sub": "github-actions-computer-policy-check",
                "tenant_id": str(tenant_id),
                "scope": "runs:read runs:write runs:approve computer:read computer:write computer:execute",
                "iss": cfg.jwt_issuer,
                "aud": cfg.jwt_audience,
                "iat": now,
                "exp": now + timedelta(minutes=5),
            },
            cfg.jwt_secret.get_secret_value(),
            algorithm=cfg.jwt_algorithm,
        )
        computer_headers = {"Authorization": f"Bearer {computer_token}"}
        file_policy = client.get(f"{BASE_URL}/v1/computer/files", headers=computer_headers)
        require(file_policy.status_code == 503,
                f"Disabled file tools must fail closed; got HTTP {file_policy.status_code}")
        execution_policy = client.post(
            f"{BASE_URL}/v1/computer/execute",
            headers=computer_headers,
            json={"command": "echo must-not-run"},
        )
        require(execution_policy.status_code == 503,
                f"Disabled shell execution must fail closed; got HTTP {execution_policy.status_code}")

        approval_events = client.get(
            f"{BASE_URL}/v1/events",
            headers=headers,
            params={"run_id": str(gated_run["id"])},
        )
        require(approval_events.status_code == 200 and len(approval_events.json()) >= 2,
                "Approval-gated run should have persisted audit events")

    # Do not print JWTs, credentials, environment values, or task payload contents.
    print("PASS: liveness, model gateway health, authentication, tenant isolation,")
    print("      durable queue/worker completion, approval gate, audit trail, and disabled-tool policy.")


if __name__ == "__main__":
    main()
