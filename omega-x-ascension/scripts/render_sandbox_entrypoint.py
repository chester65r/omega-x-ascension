from __future__ import annotations

"""Render entry point for the separate, authenticated OMEGA-X file sandbox."""

import os
import sys


def main() -> None:
    raw_port = os.environ.get("PORT", "8090")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be an integer between 1 and 65535")
    if len(os.environ.get("OMEGA_SANDBOX_TOKEN", "")) < 32:
        raise SystemExit("OMEGA_SANDBOX_TOKEN must be a strong, server-side secret")

    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "omega.sandbox_service:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--proxy-headers",
            "--no-access-log",
        ],
    )


if __name__ == "__main__":
    main()
