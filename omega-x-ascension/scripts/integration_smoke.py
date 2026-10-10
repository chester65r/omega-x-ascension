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
            "scope": "runs:read runs:write",
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

    # Do not print JWTs, credentials, environment values, or task payload contents.
    print("PASS: liveness, model readiness, auth rejection, authenticated task submission,")
    print("      database persistence, queue/worker processing, model gateway and audit events.")


if __name__ == "__main__":
    main()
