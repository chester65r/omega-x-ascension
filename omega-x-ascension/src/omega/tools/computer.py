from __future__ import annotations

import asyncio
from pathlib import Path


class ComputerTool:
    """Computer execution tool constrained to an isolated workspace."""

    def __init__(self, workspace: str = "/tmp/omega-workspace"):
        self._workspace = Path(workspace).resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        candidate = (self._workspace / path).resolve()
        try:
            candidate.relative_to(self._workspace)
        except ValueError as exc:
            raise ValueError("path escapes the computer workspace") from exc
        return candidate

    async def execute(self, command: str, timeout: int = 30) -> dict:
        """Execute an explicitly approved shell command inside the workspace."""
        if not command.strip():
            return {"command": command, "returncode": -1, "stdout": "", "stderr": "empty command"}
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._workspace),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "command": command,
                "returncode": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:8000],
                "stderr": stderr.decode(errors="replace")[:8000],
            }
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"command": command, "returncode": -1, "stdout": "", "stderr": "Command timed out"}
        except Exception as exc:
            return {"command": command, "returncode": -1, "stdout": "", "stderr": str(exc)}

    async def read_file(self, path: str) -> dict:
        try:
            full = self._resolve(path)
            return {"path": path, "content": full.read_text()[:10000]}
        except Exception as exc:
            return {"path": path, "error": str(exc)}

    async def write_file(self, path: str, content: str) -> dict:
        try:
            full = self._resolve(path)
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
            return {"path": path, "written": True}
        except Exception as exc:
            return {"path": path, "error": str(exc)}

    async def list_dir(self, path: str = ".") -> dict:
        try:
            full = self._resolve(path)
            entries = [
                {"name": entry.name, "type": "dir" if entry.is_dir() else "file",
                 "size": entry.stat().st_size if entry.is_file() else 0}
                for entry in sorted(full.iterdir())
            ]
            return {"path": path, "entries": entries}
        except Exception as exc:
            return {"path": path, "error": str(exc)}
