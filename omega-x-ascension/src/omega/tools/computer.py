from __future__ import annotations

import asyncio
from pathlib import Path


class ComputerTool:
    """Computer execution tool for AI agents — shell commands and file ops in a sandboxed workspace."""

    def __init__(self, workspace: str = "/tmp/omega-workspace"):
        self._workspace = Path(workspace)
        self._workspace.mkdir(parents=True, exist_ok=True)

    async def execute(self, command: str, timeout: int = 30) -> dict:
        """Execute a shell command in the workspace directory."""
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
            return {"command": command, "returncode": -1, "stdout": "", "stderr": "Command timed out"}
        except Exception as exc:
            return {"command": command, "returncode": -1, "stdout": "", "stderr": str(exc)}

    async def read_file(self, path: str) -> dict:
        """Read a file from the workspace."""
        try:
            full = self._workspace / path
            content = full.read_text()
            return {"path": path, "content": content[:10000]}
        except Exception as exc:
            return {"path": path, "error": str(exc)}

    async def write_file(self, path: str, content: str) -> dict:
        """Write a file to the workspace."""
        try:
            full = self._workspace / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
            return {"path": path, "written": True}
        except Exception as exc:
            return {"path": path, "error": str(exc)}

    async def list_dir(self, path: str = ".") -> dict:
        """List directory contents in the workspace."""
        try:
            full = self._workspace / path
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
