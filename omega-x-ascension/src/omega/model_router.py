from __future__ import annotations
from dataclasses import dataclass
from omega.config import Capability
from omega.ports import ModelGateway, ModelRegistry

class NoEligibleModel(RuntimeError): pass

@dataclass(frozen=True)
class RouteDecision:
    gateway: ModelGateway
    score: float

class ModelRouter:
    def __init__(self, registry: ModelRegistry): self._registry = registry
    async def select(self, capability: Capability) -> RouteDecision:
        candidates=[]
        for gateway in self._registry.all():
            if capability in gateway.capabilities and await gateway.healthy():
                candidates.append(RouteDecision(gateway, float(gateway.priority)))
        if not candidates:
            raise NoEligibleModel(f"no healthy model configured for capability={capability}")
        return max(candidates, key=lambda item: item.score)

    async def status(self) -> list[dict[str, object]]:
        """Return real health checks without exposing provider URLs or credentials."""
        providers = []
        for gateway in self._registry.all():
            try:
                healthy = bool(await gateway.healthy())
            except Exception:
                healthy = False
            providers.append({
                "name": str(gateway.name),
                "healthy": healthy,
                "priority": int(gateway.priority),
                "capabilities": sorted(str(item) for item in gateway.capabilities),
            })
        return providers
