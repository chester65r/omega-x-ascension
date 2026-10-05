import asyncio
from pathlib import Path

import httpx
import pytest

from omega.tools.browser import BrowserTool
from omega.tools.computer import ComputerTool


def test_computer_execution_is_disabled_by_default():
    tool = ComputerTool()
    with pytest.raises(RuntimeError):
        asyncio.run(tool.execute("echo blocked"))


def test_computer_workspace_blocks_path_traversal(tmp_path):
    tool = ComputerTool(workspace=str(tmp_path), enabled=True)
    result = asyncio.run(tool.write_file("../escape.txt", "blocked"))
    assert "path escapes" in result["error"]


def test_browser_blocks_private_literal_addresses():
    async def check():
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError):
                await BrowserTool(client)._validate_url("http://127.0.0.1:8000")

    asyncio.run(check())


def test_dashboard_iframe_does_not_grant_same_origin():
    index = Path("static/index.html").read_text()
    assert 'sandbox="allow-scripts allow-forms allow-popups"' in index
    assert "allow-same-origin" not in index


def test_docker_image_copies_static_assets():
    dockerfile = Path("Dockerfile").read_text()
    assert "COPY static ./static" in dockerfile


def test_job_requeue_has_app_update_privilege():
    migration = Path("alembic/versions/0001_production_baseline.py").read_text()
    assert "GRANT SELECT,INSERT,UPDATE ON workflow_jobs TO omega_app" in migration
