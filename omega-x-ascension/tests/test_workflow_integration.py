import asyncio
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from omega.workflow import CoreWorkflow


class FakeGateway:
    name = "workflow-test"
    capabilities = frozenset(
        {"reasoning", "coding", "mathematics", "planning", "analysis", "summarization", "research"}
    )
    priority = 10

    def __init__(self):
        self.calls = []

    async def healthy(self):
        return True

    async def complete(self, *, system, prompt):
        self.calls.append(system)
        if "CEO agent" in system:
            return "CEO objective analysis"
        if "Planner agent" in system:
            return "1. Inspect inputs\n2. Verify output"
        if "research agent" in system:
            return "example research query"
        if "assigned specialist" in system:
            return "A concrete candidate solution"
        if "Critic" in system:
            return "No blocking defects in the test candidate"
        if "Judge" in system:
            return "Final verified test result"
        return "Unexpected role"


class FakeDecision:
    def __init__(self, gateway):
        self.gateway = gateway
        self.score = 1.0


class FakeRouter:
    def __init__(self, gateway):
        self.gateway = gateway

    async def select(self, capability):
        assert capability in self.gateway.capabilities
        return FakeDecision(self.gateway)


class FakeBrowser:
    async def search(self, query):
        assert query == "example research query"
        return {
            "query": query,
            "results": [
                {
                    "title": "Fixture source",
                    "url": "https://fixture.example/article",
                    "snippet": "fixture",
                }
            ],
        }

    async def fetch(self, url):
        assert url == "https://fixture.example/article"
        return {
            "title": "Fixture source",
            "url": url,
            "text": "Deterministic source content",
            "status": 200,
        }


class DisabledComputer:
    enabled = False

    async def execute(self, *args, **kwargs):
        raise AssertionError("the disabled computer tool must never execute")


def test_agent_workflow_executes_all_model_roles_and_research_with_fixtures():
    async def check():
        gateway = FakeGateway()
        workflow = CoreWorkflow(
            router=FakeRouter(gateway),
            checkpointer=InMemorySaver(),
            browser=FakeBrowser(),
            computer=DisabledComputer(),
        )
        result = await workflow.run(
            tenant_id=uuid4(),
            run_id=uuid4(),
            goal="Build a testable and secure plan",
            task_type="planning",
            requested_actions=[],
        )
        joined_calls = "\n".join(gateway.calls)
        assert "CEO agent" in joined_calls
        assert "Planner agent" in joined_calls
        assert "research agent" in joined_calls
        assert "assigned specialist" in joined_calls
        assert "Critic" in joined_calls
        assert "Judge" in joined_calls
        assert result["final"] == "Final verified test result"
        assert "Deterministic source content" in result["research"]
        assert "computer_output" not in result

    asyncio.run(check())
