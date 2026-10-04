from __future__ import annotations

import asyncio
import os
from pathlib import Path


class ComputerTool:
    """Trusted-environment computer tool; execution is disabled by default."""

    def __init__(self, workspace: str = "/tmp/omega-workspace", enabled: bool = False):
        self._workspace = Path(workspace).resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)
        self.enabled = enabled

    def _resolve_path(self, path: str) -> Path:
        candidate = (self._workspace / path).resolve()
        try:
            candidate.relative_to(self._workspace)
        except ValueError as exc:
            raise ValueError("path escapes the computer workspace") from exc
        return candidate

    async def execute(self, command: str, timeout: int = 30) -> dict:
        """Execute a shell command in a trusted deployment."""
        if not self.enabled:
            raise RuntimeError(
                "computer execution is disabled; enable it only in a trusted deployment"
            )
        command = command.strip()
        if not command:
            raise ValueError("command must not be empty")
        timeout = min(max(timeout, 1), 120)
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(self._workspace),
            "TMPDIR": "/tmp",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._workspace),
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "command": command,
                "returncode": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:8000],
                "stderr": stderr.decode(errors="replace")[:8000],
            }
        except asyncio.TimeoutError:
            return {"command": command, "returncode": -1, "stdout": "", "stderr": "Command timed out"}
        except Exception as exc:
            return {"command": command, "returncode": -1, "stdout": "", "stderr": str(exc)}

    async def read_file(self, path: str) -> dict:
        """Read a file from the workspace."""
        try:
            full = self._resolve_path(path)
            content = full.read_text()
            return {"path": path, "content": content[:10000]}
        except Exception as exc:
            return {"path": path, "error": str(exc)}

    async def write_file(self, path: str, content: str) -> dict:
        """Write a file to the workspace."""
        try:
            full = self._resolve_path(path)
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
            return {"path": path, "written": True}
        except Exception as exc:
            return {"path": path, "error": str(exc)}

    async def list_dir(self, path: str = ".") -> dict:
        """List directory contents in the workspace."""
        try:
            full = self._resolve_path(path)
            entries = []
            for entry in sorted(full.iterdir()):
                entries.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": entry.stat().st_size if entry.is_file() else 0,
                })
            return {"path": path, "entries": entries}
        except Exception as exc:
            return {"path": path, "error": str(exc)}
