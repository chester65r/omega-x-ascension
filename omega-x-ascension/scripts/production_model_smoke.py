from __future__ import annotations

"""Run one explicitly authorized, real model-backed production smoke task.

Run only from a trusted operator environment with OMEGA_JWT_SECRET available.
This submits a small task and may consume provider quota.
"""

import os
import sys
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt


def main() -> int:
    if os.environ.get("OMEGA_SMOKE_CONFIRM_REAL_INFERENCE") != "YES":
        print(
            "Refusing to submit a real inference task without OMEGA_SMOKE_CONFIRM_REAL_INFERENCE=YES.",
            file=sys.stderr,
        )
        return 2

    secret = os.environ.get("OMEGA_JWT_SECRET", "")
    if len(secret) < 32:
        print(
            "OMEGA_JWT_SECRET must be available in this trusted runtime; no secret was printed.",
            file=sys.stderr,
        )
        return 2

    base_url = os.environ.get(
        "OMEGA_API_BASE_URL", "https://omega-x-ascension-api.onrender.com"
    ).rstrip("/")
    issuer = os.environ.get("OMEGA_JWT_ISSUER", "omega-x")
    audience = os.environ.get("OMEGA_JWT_AUDIENCE", "omega-x-api")
    algorithm = os.environ.get("OMEGA_JWT_ALGORITHM", "HS256")
    tenant_id = uuid4()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "production-model-smoke",
            "tenant_id": str(tenant_id),
            "scope": "runs:read runs:write",
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        secret,
        algorithm=algorithm,
    )
    headers = {"Authorization": f"Bearer {token}"}
    goal = (
        "Production inference smoke test. Reply with exactly this text and nothing else: "
        "OMEGA_MODEL_SMOKE_OK"
    )

    with httpx.Client(timeout=15.0) as client:
        live = client.get(f"{base_url}/health/live")
        if live.status_code != 200 or live.json().get("status") != "ok":
            print(f"API liveness failed: HTTP {live.status_code}", file=sys.stderr)
            return 1
        created = client.post(
            f"{base_url}/v1/runs",
            headers=headers,
            json={"goal": goal, "task_type": "planning", "requested_actions": []},
        )
        if created.status_code != 202:
            print(
                f"Authenticated task creation failed: HTTP {created.status_code}", file=sys.stderr
            )
            return 1
        run_id = created.json().get("id")
        if not run_id:
            print("API did not return a run ID.", file=sys.stderr)
            return 1

        deadline = time.monotonic() + 150
        last_status = "unknown"
        while time.monotonic() < deadline:
            result = client.get(f"{base_url}/v1/runs/{run_id}", headers=headers)
            if result.status_code != 200:
                print(f"Could not read smoke run: HTTP {result.status_code}", file=sys.stderr)
                return 1
            data = result.json()
            last_status = str(data.get("status", "unknown"))
            if last_status == "succeeded":
                output = str(data.get("output") or "")
                if not output.strip():
                    print("Run succeeded but returned no model output.", file=sys.stderr)
                    return 1
                print(
                    f"PASS: real model-backed task succeeded; run_id={run_id}; output_chars={len(output)}"
                )
                return 0
            if last_status == "failed":
                print(
                    "FAIL: model-backed task failed; inspect protected worker logs using the run ID.",
                    file=sys.stderr,
                )
                print(f"run_id={run_id}", file=sys.stderr)
                return 1
            time.sleep(2)

    print(
        f"Timed out waiting for real model inference; run_id={run_id}; last_status={last_status}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
