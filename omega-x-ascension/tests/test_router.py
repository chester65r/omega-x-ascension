import asyncio
import pytest
from omega.model_router import ModelRouter, NoEligibleModel
class Gateway:
    def __init__(self,name,capabilities,priority,healthy=True): self.name=name; self.capabilities=frozenset(capabilities); self.priority=priority; self._healthy=healthy
    async def healthy(self): return self._healthy
    async def complete(self,**kwargs): return 'ok'
class Registry:
    def __init__(self,*items): self.items=items
    def all(self): return self.items
def test_selects_highest_priority_healthy_capable_model():
    decision=asyncio.run(ModelRouter(Registry(Gateway('low',{'coding'},10),Gateway('high',{'coding'},90),Gateway('down',{'coding'},100,False))).select('coding'))
    assert decision.gateway.name=='high'
def test_rejects_missing_capability():
    with pytest.raises(NoEligibleModel): asyncio.run(ModelRouter(Registry(Gateway('x',{'coding'},1))).select('research'))


def test_provider_status_reports_unhealthy_models_without_leaking_urls():
    router = ModelRouter(Registry(
        Gateway("healthy-model", {"reasoning", "planning"}, 50, True),
        Gateway("offline-model", {"coding"}, 10, False),
    ))
    status = asyncio.run(router.status())
    assert status == [
        {
            "name": "healthy-model",
            "healthy": True,
            "priority": 50,
            "capabilities": ["planning", "reasoning"],
        },
        {
            "name": "offline-model",
            "healthy": False,
            "priority": 10,
            "capabilities": ["coding"],
        },
    ]
    assert all("url" not in provider and "api_key" not in provider for provider in status)
