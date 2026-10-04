from pathlib import Path

import pytest

from omega.tools.computer import ComputerTool
from omega.tools.browser import BrowserTool


def test_computer_workspace_rejects_path_escape(tmp_path):
    tool = ComputerTool(str(tmp_path / "workspace"))
    with pytest.raises(ValueError):
        tool._resolve("../outside")


def test_browser_rejects_internal_urls():
    with pytest.raises(ValueError):
        BrowserTool._validate_url("http://127.0.0.1:8000")


def test_docker_image_contains_static_assets():
    dockerfile = Path("Dockerfile").read_text()
    assert "COPY static ./static" in dockerfile
