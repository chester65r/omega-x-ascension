from pathlib import Path

from fastapi.testclient import TestClient

from omega import sandbox_service
from omega.sandbox_service import SandboxRuntime


def test_sandbox_health_reports_ready_workspace_and_disabled_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("OMEGA_SANDBOX_TOKEN", "s" * 40)
    runtime = SandboxRuntime(tmp_path / "workspace")
    monkeypatch.setattr(sandbox_service, "get_runtime", lambda: runtime)

    with TestClient(sandbox_service.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["command_execution"] is False
    assert response.json()["file_tools"] is True
    assert response.json()["workspace_ready"] is True
    assert response.json()["credential_configured"] is True


def test_sandbox_execute_fails_closed_even_with_valid_internal_token(monkeypatch):
    token = "s" * 40
    monkeypatch.setenv("OMEGA_SANDBOX_TOKEN", token)
    with TestClient(sandbox_service.app) as client:
        response = client.post(
            "/execute",
            headers={"X-OMEGA-SANDBOX-TOKEN": token},
            json={
                "workspace_id": "11111111-1111-1111-1111-111111111111",
                "command": "echo should-not-run",
                "timeout": 2,
            },
        )
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"]


def test_android_backup_is_disabled_and_rules_exclude_private_app_data():
    root = Path("../android/app/src/main")
    manifest = (root / "AndroidManifest.xml").read_text(encoding="utf-8")
    backup = (root / "res/xml/backup_rules.xml").read_text(encoding="utf-8")
    extraction = (root / "res/xml/data_extraction_rules.xml").read_text(encoding="utf-8")
    extraction_v36 = (root / "res/xml-v36/data_extraction_rules.xml").read_text(encoding="utf-8")

    assert 'android:allowBackup="false"' in manifest
    assert 'android:dataExtractionRules="@xml/data_extraction_rules"' in manifest
    assert 'android:fullBackupContent="@xml/backup_rules"' in manifest
    for domain in ("root", "file", "database", "sharedpref", "external"):
        assert f'domain="{domain}"' in backup
        assert f'domain="{domain}"' in extraction
        assert f'domain="{domain}"' in extraction_v36


def test_sandbox_internal_smoke_gate_is_wired_into_full_stack_ci():
    workflow = Path("../.github/workflows/ci.yml").read_text(encoding="utf-8")
    smoke = Path("scripts/smoke_sandbox.py").read_text(encoding="utf-8")
    assert "Verify sandbox health and tenant-scoped workspace file operations" in workflow
    assert "exec -T api python scripts/smoke_sandbox.py" in workflow
    for contract in (
        '"/health"',
        '"/files/read"',
        '"/files"',
        '"../outside.txt"',
        '"/execute"',
        'health.json().get("command_execution") is False',
    ):
        assert contract in smoke
