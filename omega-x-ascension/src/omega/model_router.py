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
