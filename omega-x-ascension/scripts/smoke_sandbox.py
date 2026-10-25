from __future__ import annotations

"""Live internal HTTP smoke test for the isolated sandbox from the API network namespace."""

import os
from uuid import uuid4

import httpx

SANDBOX_URL = os.environ.get("OMEGA_SANDBOX_URL", "http://sandbox:8090").rstrip("/")
SANDBOX_TOKEN = os.environ.get("OMEGA_SANDBOX_TOKEN", "")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    require(
        len(SANDBOX_TOKEN) >= 32, "sandbox shared token is not configured for integration smoke"
    )
    headers = {"X-OMEGA-SANDBOX-TOKEN": SANDBOX_TOKEN}
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    relative_dir = "ci-sandbox-smoke"
    file_path = f"{relative_dir}/probe.txt"
    expected_content = f"omega-sandbox-smoke:{uuid4()}"

    with httpx.Client(base_url=SANDBOX_URL, timeout=8, follow_redirects=False) as client:
        health = client.get("/health")
        require(
            health.status_code == 200 and health.json().get("workspace_ready") is True,
            f"sandbox is not ready for file operations: HTTP {health.status_code}, body={health.text[:240]}",
        )
        require(
            health.json().get("command_execution") is False,
            "shell execution must remain disabled during sandbox smoke checks",
        )
        matching_credential_health = client.get("/health", headers=headers)
        require(
            matching_credential_health.status_code == 200,
            "authenticated sandbox health check failed; verify API/sandbox shared credential alignment: "
            f"HTTP {matching_credential_health.status_code}, body={matching_credential_health.text[:240]}",
        )
        mismatched_credential_health = client.get(
            "/health", headers={"X-OMEGA-SANDBOX-TOKEN": "x" * 64}
        )
        require(
            mismatched_credential_health.status_code == 401,
            "sandbox health route did not reject a mismatched internal credential",
        )

        no_credential = client.get("/files", params={"workspace_id": tenant_a, "path": "."})
        require(
            no_credential.status_code == 401,
            f"workspace file routes must require the internal credential; got HTTP {no_credential.status_code}",
        )

        written = client.put(
            "/files",
            headers=headers,
            json={"workspace_id": tenant_a, "path": file_path, "content": expected_content},
        )
        require(
            written.status_code == 200 and written.json().get("written") is True,
            f"sandbox workspace write failed: HTTP {written.status_code}, body={written.text[:240]}",
        )

        read_back = client.get(
            "/files/read",
            headers=headers,
            params={"workspace_id": tenant_a, "path": file_path},
        )
        require(
            read_back.status_code == 200 and read_back.json().get("content") == expected_content,
            f"sandbox workspace readback failed: HTTP {read_back.status_code}, body={read_back.text[:240]}",
        )

        listing = client.get(
            "/files",
            headers=headers,
            params={"workspace_id": tenant_a, "path": relative_dir},
        )
        require(
            listing.status_code == 200
            and any(
                entry.get("name") == "probe.txt" for entry in listing.json().get("entries", [])
            ),
            f"sandbox directory listing failed: HTTP {listing.status_code}, body={listing.text[:240]}",
        )

        other_listing = client.get(
            "/files", headers=headers, params={"workspace_id": tenant_b, "path": "."}
        )
        require(
            other_listing.status_code == 200
            and not any(
                entry.get("name") == relative_dir
                for entry in other_listing.json().get("entries", [])
            ),
            "sandbox workspace content crossed a tenant boundary",
        )

        traversal = client.get(
            "/files/read",
            headers=headers,
            params={"workspace_id": tenant_a, "path": "../outside.txt"},
        )
        require(
            traversal.status_code == 400,
            f"sandbox path traversal should be rejected; got HTTP {traversal.status_code}",
        )

        execution = client.post(
            "/execute",
            headers=headers,
            json={"workspace_id": tenant_a, "command": "echo must-not-run", "timeout": 2},
        )
        require(
            execution.status_code == 503 and "disabled" in execution.json().get("detail", ""),
            f"sandbox shell execution must fail closed; got HTTP {execution.status_code}",
        )

    # Do not print tokens, workspace contents, or credentials.
    print("PASS: sandbox readiness, internal authentication, write/read/list, tenant isolation,")
    print("      path traversal rejection, and disabled command-execution policy.")


if __name__ == "__main__":
    main()
