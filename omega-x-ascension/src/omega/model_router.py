from __future__ import annotations

from dataclasses import dataclass
import logging

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
    """Raised when every healthy provider fails to complete a request."""


class ModelRouter:
    def __init__(self, registry: ModelRegistry):
        self._registry = registry

    async def _eligible(self, capability: Capability) -> list[RouteDecision]:
        candidates = []
        for gateway in self._registry.all():
            if capability in gateway.capabilities and await gateway.healthy():
                candidates.append(RouteDecision(gateway, float(gateway.priority)))
        return sorted(candidates, key=lambda item: item.score, reverse=True)

    async def select(self, capability: Capability) -> RouteDecision:
        candidates = await self._eligible(capability)
        if not candidates:
            raise NoEligibleModel(f"no healthy model configured for capability={capability}")
        return candidates[0]

    async def complete(self, capability: Capability, *, system: str, prompt: str) -> str:
        """Try healthy providers in priority order; never return an empty completion."""
        candidates = await self._eligible(capability)
        if not candidates:
            raise NoEligibleModel(f"no healthy model configured for capability={capability}")

        failures: list[Exception] = []
        for candidate in candidates:
            try:
                output = await candidate.gateway.complete(system=system, prompt=prompt)
                if not isinstance(output, str) or not output.strip():
                    raise RuntimeError("provider returned an empty completion")
                return output
            except Exception as exc:
                failures.append(exc)
                logger.warning(
                    "model provider attempt failed; provider=%s error_type=%s",
                    candidate.gateway.name,
                    type(exc).__name__,
                )

        raise ModelExecutionFailed(
            f"all {len(candidates)} eligible model providers failed to complete the request"
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
