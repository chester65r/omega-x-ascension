from __future__ import annotations

"""Probe a configured model provider with a real, non-empty chat completion."""

import asyncio
import sys

import httpx

from omega.adapters.models import StaticRegistry, build_gateways
from omega.config import get_settings
from omega.model_router import ModelRouter, NoEligibleModel


async def verify_live_inference(router: ModelRouter) -> tuple[str, int]:
    """Perform a real completion through the normal capability router."""
    decision = await router.select("planning")
    answer = await decision.gateway.complete(
        system="You are verifying an AI model connection. Do not use tools or speculate.",
        prompt="Reply with a short confirmation that the model is responding.",
    )
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("the provider returned an empty completion")
    return str(decision.gateway.name), len(answer.strip())


async def _run() -> tuple[str, int]:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        router = ModelRouter(StaticRegistry(build_gateways(settings, client)))
        return await verify_live_inference(router)


def main() -> int:
    try:
        name, length = asyncio.run(_run())
    except NoEligibleModel:
        print(
            "FAIL: no healthy provider supports planning. Configure a real OpenAI-compatible "
            "provider or a local model, then retry.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        # Avoid echoing response bodies, credentials, or full request URLs into shared logs.
        print(
            f"FAIL: live model inference did not complete ({type(exc).__name__}). "
            "Check the provider endpoint, model ID, credentials, and usage limits.",
            file=sys.stderr,
        )
        return 1

    print(f"PASS: live inference completed through provider '{name}' ({length} response characters).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
