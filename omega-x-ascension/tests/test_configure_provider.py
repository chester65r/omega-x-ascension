import json
import runpy
from pathlib import Path

import pytest


_module = runpy.run_path("scripts/configure_provider.py")
validate_base_url = _module["validate_base_url"]
update_env = _module["update_env"]


def test_external_model_provider_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_base_url("http://example.com/v1")
    assert validate_base_url("https://example.com/v1/") == "https://example.com/v1"


def test_local_ollama_endpoint_can_use_http():
    assert validate_base_url("http://ollama:11434/v1") == "http://ollama:11434/v1"


def test_provider_config_preserves_other_env_and_secures_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OMEGA_MODEL_PROVIDERS=[]\nOTHER_SETTING=leave-me\n", encoding="utf-8")
    provider = {
        "name": "test-provider",
        "base_url": "https://example.com/v1",
        "api_key": "test-secret",
        "model": "test-model",
        "capabilities": ["reasoning", "planning"],
        "priority": 50,
        "timeout_seconds": 90,
    }

    update_env(env, provider)
    lines = env.read_text(encoding="utf-8").splitlines()
    setting = next(line for line in lines if line.startswith("OMEGA_MODEL_PROVIDERS="))
    providers = json.loads(setting.partition("=")[2])

    assert providers == [provider]
    assert "OTHER_SETTING=leave-me" in lines
    assert env.stat().st_mode & 0o777 == 0o600


def test_provider_config_replaces_same_name_without_duplicate(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        'OMEGA_MODEL_PROVIDERS=[{"name":"p","api_key":"old"}]\n',
        encoding="utf-8",
    )
    update_env(env, {"name": "p", "api_key": "new"})
    providers = json.loads(env.read_text().partition("=")[2])
    assert providers == [{"name": "p", "api_key": "new"}]


def test_provider_config_rejects_duplicate_env_entries(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OMEGA_MODEL_PROVIDERS=[]\nOMEGA_MODEL_PROVIDERS=[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        update_env(env, {"name": "p", "api_key": "x"})


def test_provider_config_refuses_symlink(tmp_path):
    real = tmp_path / "real.env"
    real.write_text("OMEGA_MODEL_PROVIDERS=[]\n", encoding="utf-8")
    link = tmp_path / ".env"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        update_env(link, {"name": "p", "api_key": "x"})
