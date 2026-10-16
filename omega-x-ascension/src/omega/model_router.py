from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from omega.config import Capability
from omega.ports import ModelGateway, ModelRegistry

logger = logging.getLogger("omega.model_router")


class NoEligibleModel(RuntimeError):
    pass


@dataclass(frozen=True)
class RouteDecision:
    gateway: ModelGateway
    score: float


class ModelExecutionFailed(RuntimeError):
    """Safe summary of model failure and whether a queue retry can plausibly help."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class ModelRouter:
    def __init__(self, registry: ModelRegistry):
        self._registry = registry

    async def _eligible(self, capability: Capability) -> list[RouteDecision]:
        candidates = []
        for gateway in self._registry.all():
            if capability not in gateway.capabilities:
                continue
            try:
                healthy = await gateway.healthy()
            except Exception as exc:
                logger.warning(
                    "model provider health check failed; provider=%s error_type=%s",
                    gateway.name,
                    type(exc).__name__,
                )
                healthy = False
            if healthy:
                candidates.append(RouteDecision(gateway, float(gateway.priority)))
        return sorted(candidates, key=lambda item: item.score, reverse=True)

    async def select(self, capability: Capability) -> RouteDecision:
        candidates = await self._eligible(capability)
        if not candidates:
            raise NoEligibleModel(f"no healthy model configured for capability={capability}")
        return candidates[0]

    async def complete(self, capability: Capability, *, system: str, prompt: str) -> str:
        """Try every healthy configured provider in priority order; never return empty output."""
        candidates = await self._eligible(capability)
        if not candidates:
            raise NoEligibleModel(f"no healthy model configured for capability={capability}")

        # Do not hard-limit fallback to two providers: a configured third provider may
        # be the only one with available quota. Continue in priority order until success.
        failures: list[Exception] = []
        for candidate in candidates:
            try:
                output = await candidate.gateway.complete(system=system, prompt=prompt)
                if not isinstance(output, str) or not output.strip():
                    raise RuntimeError("provider returned an empty completion")
                return output
            except Exception as exc:
                failures.append(exc)
                # Log only the provider name, exception class, and numeric HTTP status.
                # Never log provider response bodies, request URLs, or credentials.
                http_status = (
                    exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                )
                logger.warning(
                    "model provider attempt failed; provider=%s error_type=%s http_status=%s",
                    candidate.gateway.name,
                    type(exc).__name__,
                    http_status,
                )

        # Retry the queued run only if at least one provider failure looks transient.
        def is_retryable(exc: Exception) -> bool:
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                return status in {408, 409, 425, 429} or status >= 500
            return bool(getattr(exc, "retryable", True))

        retryable = any(is_retryable(exc) for exc in failures)
        raise ModelExecutionFailed(
            f"all {len(candidates)} attempted model providers failed to complete the request",
            retryable=retryable,
        ) from failures[-1]

    async def status(self) -> list[dict[str, object]]:
        """Return real health checks without exposing provider URLs or credentials."""
        providers = []
        for gateway in self._registry.all():
            try:
                healthy = bool(await gateway.healthy())
            except Exception:
                healthy = False
            providers.append(
                {
                    "name": str(gateway.name),
                    "healthy": healthy,
                    "priority": int(gateway.priority),
                    "capabilities": sorted(str(item) for item in gateway.capabilities),
                }
            )
        return providers
