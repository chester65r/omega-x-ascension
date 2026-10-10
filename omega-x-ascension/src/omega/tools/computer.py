from __future__ import annotations

from uuid import UUID

import httpx


_DEFAULT_WORKSPACE = "00000000-0000-0000-0000-000000000001"


class ComputerTool:
    """Client for the separately isolated sandbox service; never runs commands in the API process."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        base_url: str = "http://sandbox:8090",
        token: str | None = None,
        enabled: bool = False,
    ):
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._token = token or ""
        self.enabled = enabled

    def _workspace_id(self, workspace_id: str | UUID | None) -> str:
        try:
            return str(UUID(str(workspace_id or _DEFAULT_WORKSPACE)))
        except ValueError as exc:
            raise ValueError("workspace_id must be a UUID") from exc

    async def _request(self, method: str, path: str, *, workspace_id: str | UUID | None = None,
                       timeout: float = 15, **kwargs) -> dict:
        if not self.enabled:
            raise RuntimeError("computer tools are disabled by server policy")
        if self._client is None or len(self._token) < 32:
            raise RuntimeError("sandbox service is not configured; set OMEGA_SANDBOX_TOKEN")
        headers = dict(kwargs.pop("headers", {}))
        headers["X-OMEGA-SANDBOX-TOKEN"] = self._token
        if workspace_id is not None:
            if "json" in kwargs and isinstance(kwargs["json"], dict):
                kwargs["json"]["workspace_id"] = self._workspace_id(workspace_id)
            else:
                kwargs.setdefault("params", {})
                kwargs["params"]["workspace_id"] = self._workspace_id(workspace_id)
        try:
            response = await self._client.request(
                method, self._base_url + path, headers=headers, timeout=timeout, **kwargs
            )
        except httpx.HTTPError as exc:
            raise RuntimeError("isolated sandbox service is unreachable") from exc
        try:
            body = response.json()
        except ValueError:
            body = {"detail": "sandbox returned an invalid response"}
        if not response.is_success:
            detail = body.get("detail", f"sandbox HTTP {response.status_code}") if isinstance(body, dict) else f"sandbox HTTP {response.status_code}"
            if response.status_code in (400, 413, 422):
                raise ValueError(str(detail))
            raise RuntimeError(str(detail))
        if not isinstance(body, dict):
            raise RuntimeError("sandbox returned an unexpected response")
        return body

    async def health(self) -> bool:
        if not self.enabled:
            return True
        if self._client is None or len(self._token) < 32:
            return False
        try:
            response = await self._client.get(self._base_url + "/health", timeout=3)
            return response.is_success
        except httpx.HTTPError:
            return False

    async def execute(self, command: str, timeout: int = 30,
                      workspace_id: str | UUID | None = None) -> dict:
        command = command.strip()
        if not command:
            raise ValueError("command must not be empty")
        if len(command) > 1000:
            raise ValueError("command must be 1000 characters or fewer")
        timeout = min(max(int(timeout), 1), 120)
        return await self._request(
            "POST", "/execute", workspace_id=workspace_id, timeout=timeout + 10,
            json={"command": command, "timeout": timeout},
        )

    async def list_dir(self, path: str = ".", workspace_id: str | UUID | None = None) -> dict:
        return await self._request(
            "GET", "/files", workspace_id=workspace_id, params={"path": path}
        )

    async def read_file(self, path: str, workspace_id: str | UUID | None = None) -> dict:
        return await self._request(
            "GET", "/files/read", workspace_id=workspace_id, params={"path": path}
        )

    async def write_file(self, path: str, content: str,
                         workspace_id: str | UUID | None = None) -> dict:
        if len(content) > 100_000:
            raise ValueError("file content must be 100 KB or less")
        return await self._request(
            "PUT", "/files", workspace_id=workspace_id,
            json={"path": path, "content": content},
        )
