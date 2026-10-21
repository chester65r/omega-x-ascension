from __future__ import annotations

"""Render entry point for the OMEGA-X API container.

Render's existing service configuration invokes this file directly. Bind to
Render's assigned PORT when present, while retaining 8000 for local/container use.
"""

import os
import sys


def main() -> None:
    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be an integer between 1 and 65535")

    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "omega.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--proxy-headers",
        ],
    )


if __name__ == "__main__":
    main()
