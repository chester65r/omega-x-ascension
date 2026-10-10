from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse

DEFAULT_CAPABILITIES = [
    "reasoning", "coding", "mathematics", "planning", "analysis", "summarization", "research"
]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "ollama", "host.docker.internal"}


def validate_base_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base URL must be a full http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base URL must not contain credentials, a query, or a fragment")
    if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS:
        raise ValueError("non-local model providers must use HTTPS")
    return value.strip().rstrip("/")


def update_env(path: Path, provider: dict) -> None:
    if path.is_symlink():
        raise ValueError("refusing to write through a symlink .env file")
    if not path.exists():
        raise FileNotFoundError("Missing .env. Run python scripts/generate_env.py first.")
    lines = path.read_text(encoding="utf-8").splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith("OMEGA_MODEL_PROVIDERS=")]
    if len(matches) > 1:
        raise ValueError("Found duplicate OMEGA_MODEL_PROVIDERS entries; fix .env manually first.")
    current = []
    if matches:
        try:
            current = json.loads(lines[matches[0]].partition("=")[2].strip())
        except json.JSONDecodeError as exc:
            raise ValueError("OMEGA_MODEL_PROVIDERS must contain valid JSON.") from exc
        if not isinstance(current, list):
            raise ValueError("OMEGA_MODEL_PROVIDERS must be a JSON array.")
    current = [item for item in current if not (isinstance(item, dict) and item.get("name") == provider["name"])]
    current.append(provider)
    assignment = "OMEGA_MODEL_PROVIDERS=" + json.dumps(current, separators=(",", ":"), ensure_ascii=False)
    if matches:
        lines[matches[0]] = assignment
    else:
        lines.append(assignment)
    payload = "\n".join(lines).rstrip() + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".env.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely add or replace an OpenAI-compatible model provider in .env.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--name", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--capabilities", default=",".join(DEFAULT_CAPABILITIES))
    args = parser.parse_args()

    name = args.name.strip() or input("Provider name (e.g. openai, local-ollama): ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
        parser.error("provider name must use only letters, numbers, dot, underscore, or dash")
    raw_url = args.base_url.strip() or input("OpenAI-compatible base URL (including /v1 if required): ").strip()
    try:
        base_url = validate_base_url(raw_url)
    except ValueError as exc:
        parser.error(str(exc))
    model = args.model.strip() or input("Model ID: ").strip()
    if not model or len(model) > 200:
        parser.error("model ID is required and must be 200 characters or fewer")
    host = urlparse(base_url).hostname
    if urlparse(base_url).scheme == "http" and host in LOCAL_HOSTS:
        api_key = getpass.getpass("Local endpoint API key (blank uses 'local'): ").strip() or "local"
    else:
        api_key = getpass.getpass("Provider API key (input hidden): ").strip()
        if not api_key:
            parser.error("API key is required for a remote provider")

    capabilities = sorted(set(item.strip() for item in args.capabilities.split(",") if item.strip()))
    unknown = set(capabilities) - set(DEFAULT_CAPABILITIES)
    if not capabilities or unknown:
        parser.error("capabilities must be a comma-separated subset of: " + ", ".join(DEFAULT_CAPABILITIES))
    provider = {
        "name": name,
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "capabilities": capabilities,
        "priority": 50,
        "timeout_seconds": 90,
    }
    try:
        update_env(Path(args.env_file), provider)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Provider saved to .env (permissions set to 0600). The key was not printed.")
    print("Restart API/worker after configuring it: docker compose up --build -d api worker")


if __name__ == "__main__":
    main()
