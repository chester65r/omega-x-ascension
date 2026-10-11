"""Vercel ASGI entrypoint for the Omega X Ascension API."""
from pathlib import Path
import sys


_SOURCE_DIR = Path(__file__).resolve().parent / "src"
if str(_SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(_SOURCE_DIR))

from omega_api.main import app  # noqa: E402
