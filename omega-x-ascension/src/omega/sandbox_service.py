from __future__ import annotations

import asyncio
import ctypes
import os
from pathlib import Path
import secrets
import signal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

MAX_OUTPUT_BYTES = 16_000
MAX_FILE_BYTES = 100_000
MAX_DIRECTORY_ENTRIES = 200
WORKSPACE_ROOT = Path(os.environ.get("OMEGA_SANDBOX_WORKSPACE", "/workspace")).resolve()
app = FastAPI(title="OMEGA isolated computer sandbox", docs_url=None, redoc_url=None, openapi_url=None)


class WorkspaceInput(BaseModel):
    workspace_id: UUID = UUID("00000000-0000-0000-0000-000000000001")


class ExecuteInput(WorkspaceInput):
    command: str = Field(min_length=1, max_length=1000)
    timeout: int = Field(default=30, ge=1, le=120)


class FileWriteInput(WorkspaceInput):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=MAX_FILE_BYTES)


class SandboxRuntime:
    """A network-isolated workspace runtime. Run only as a separate restricted container."""

    def __init__(self, root: Path | str = WORKSPACE_ROOT):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def workspace(self, workspace_id: UUID | str) -> Path:
        canonical = str(UUID(str(workspace_id)))
        target = (self.root / canonical).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("invalid workspace id") from exc
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        return target

    def resolve_path(self, workspace_id: UUID | str, relative: str) -> Path:
        if not relative or len(relative) > 240:
            raise ValueError("path must be between 1 and 240 characters")
        raw = Path(relative)
        if raw.is_absolute():
            raise ValueError("absolute paths are not allowed")
        home = self.workspace(workspace_id).resolve()
        candidate = (home / raw).resolve()
        try:
            candidate.relative_to(home)
        except ValueError as exc:
            raise ValueError("path escapes the workspace") from exc
        return candidate

    async def execute(self, workspace_id: UUID | str, command: str, timeout: int = 30) -> dict:
        if not command.strip():
            raise ValueError("command must not be empty")
        if len(command) > 1000:
            raise ValueError("command must be 1000 characters or fewer")
        timeout = min(max(int(timeout), 1), 120)
        home = self.workspace(workspace_id)
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(home),
            "TMPDIR": "/tmp",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(home),
            env=env,
            start_new_session=True,
        )
        overflow = asyncio.Event()

        async def collect(stream):
            parts = []
            total = 0
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                remaining = MAX_OUTPUT_BYTES - total
                if remaining > 0:
                    parts.append(chunk[:remaining])
                    total += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    overflow.set()
            return b"".join(parts).decode("utf-8", errors="replace")

        stdout_task = asyncio.create_task(collect(proc.stdout))
        stderr_task = asyncio.create_task(collect(proc.stderr))
        wait_task = asyncio.create_task(proc.wait())
        overflow_task = asyncio.create_task(overflow.wait())
        timed_out = False
        try:
            done, _ = await asyncio.wait(
                {wait_task, overflow_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if wait_task not in done:
                timed_out = overflow_task not in done
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await wait_task
            stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
            if timed_out:
                stderr = (stderr + "\nCommand timed out; process group terminated").strip()
            elif overflow.is_set():
                stderr = (stderr + "\nOutput truncated at 16 KB; process group terminated").strip()
            return {
                "command": command,
                "returncode": proc.returncode if not (timed_out or overflow.is_set()) else -1,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": timed_out,
                "output_limited": overflow.is_set(),
            }
        finally:
            # Do not leave an untrusted process group running if the API request is cancelled.
            if proc.returncode is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except (asyncio.TimeoutError, ProcessLookupError):
                    proc.kill()
            for task in (overflow_task, wait_task, stdout_task, stderr_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(overflow_task, wait_task, stdout_task, stderr_task, return_exceptions=True)

    def list_dir(self, workspace_id: UUID | str, path: str = ".") -> dict:
        target = self.resolve_path(workspace_id, path)
        if not target.is_dir():
            raise ValueError("path is not a directory")
        entries = []
        for entry in sorted(target.iterdir(), key=lambda item: item.name.casefold())[:MAX_DIRECTORY_ENTRIES]:
            if entry.is_symlink():
                kind, size = "link", 0
            elif entry.is_dir():
                kind, size = "dir", 0
            else:
                try:
                    kind, size = "file", entry.stat().st_size
                except OSError:
                    kind, size = "file", 0
            entries.append({"name": entry.name, "type": kind, "size": size})
        return {"path": path, "entries": entries, "truncated": len(entries) == MAX_DIRECTORY_ENTRIES}

    def read_file(self, workspace_id: UUID | str, path: str) -> dict:
        target = self.resolve_path(workspace_id, path)
        if target.is_symlink() or not target.is_file():
            raise ValueError("path must refer to a regular file")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("file exceeds the 100 KB read limit")
        return {"path": path, "content": target.read_text(encoding="utf-8")}

    def write_file(self, workspace_id: UUID | str, path: str, content: str) -> dict:
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("file content exceeds the 100 KB write limit")
        target = self.resolve_path(workspace_id, path)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self.resolve_path(workspace_id, path)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "written": True, "bytes": len(content.encode("utf-8"))}


runtime: SandboxRuntime | None = None


def get_runtime() -> SandboxRuntime:
    global runtime
    if runtime is None:
        runtime = SandboxRuntime()
    return runtime

async def require_shared_token(
    request: Request,
    supplied: str | None = Header(default=None, alias="X-OMEGA-SANDBOX-TOKEN"),
) -> None:
    expected = os.environ.get("OMEGA_SANDBOX_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="sandbox shared token is not configured")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid sandbox service credential")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/execute")
async def execute(body: ExecuteInput, _: None = Depends(require_shared_token)):
    try:
        return await get_runtime().execute(body.workspace_id, body.command, body.timeout)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/files")
async def list_files(
    workspace_id: UUID,
    path: str = ".",
    _: None = Depends(require_shared_token),
):
    try:
        return get_runtime().list_dir(workspace_id, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/files/read")
async def read_file(
    workspace_id: UUID,
    path: str,
    _: None = Depends(require_shared_token),
):
    try:
        return get_runtime().read_file(workspace_id, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OSError, UnicodeError) as exc:
        raise HTTPException(status_code=400, detail="file cannot be read as UTF-8 text") from exc


@app.put("/files")
async def write_file(body: FileWriteInput, _: None = Depends(require_shared_token)):
    try:
        return get_runtime().write_file(body.workspace_id, body.path, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail="file cannot be written") from exc


if __name__ == "__main__":
    import uvicorn

    if len(os.environ.get("OMEGA_SANDBOX_TOKEN", "")) < 32:
        raise RuntimeError("OMEGA_SANDBOX_TOKEN must contain at least 32 characters")
    try:
        ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)  # PR_SET_DUMPABLE = 4
    except Exception:
        pass
    uvicorn.run(app, host="0.0.0.0", port=8090, access_log=False)
