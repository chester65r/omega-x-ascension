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
            return "No blocking defects in the test candidate. [STATUS: APPROVED]"
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


def test_agent_workflow_self_correcting_feedback_loop():
    async def check():
        class RevisingGateway:
            name = "workflow-revision-test"
            capabilities = frozenset(
                {"reasoning", "coding", "mathematics", "planning", "analysis", "summarization", "research"}
            )
            priority = 10

            def __init__(self):
                self.calls = []
                self.specialist_calls = 0
                self.critic_calls = 0

            async def healthy(self):
                return True

            async def complete(self, *, system, prompt):
                self.calls.append(system)
                if "CEO agent" in system:
                    return "CEO objective analysis"
                if "Planner agent" in system:
                    return "1. Step one\n2. Step two"
                if "research agent" in system:
                    return "example research query"
                if "assigned specialist" in system:
                    self.specialist_calls += 1
                    if self.specialist_calls == 1:
                        return "First attempt with flaw"
                    return "Second corrected attempt addressing flaw"
                if "Critic" in system:
                    self.critic_calls += 1
                    if self.critic_calls == 1:
                        return "Found defect in attempt 1. [STATUS: REVISE]"
                    return "Corrected solution verified. [STATUS: APPROVED]"
                if "Judge" in system:
                    return "Final verified test result after revision"
                return "Unexpected role"

        gateway = RevisingGateway()
        workflow = CoreWorkflow(
            router=FakeRouter(gateway),
            checkpointer=InMemorySaver(),
            browser=FakeBrowser(),
            computer=DisabledComputer(),
        )
        result = await workflow.run(
            tenant_id=uuid4(),
            run_id=uuid4(),
            goal="Build a secure and revised plan",
            task_type="planning",
            requested_actions=[],
        )
        assert gateway.specialist_calls == 2, f"Expected 2 specialist calls, got {gateway.specialist_calls}"
        assert gateway.critic_calls == 2, f"Expected 2 critic calls, got {gateway.critic_calls}"
        assert result["revision_count"] == 1
        assert result["critique_approved"] is True
        assert result["solution"] == "Second corrected attempt addressing flaw"
        assert result["final"] == "Final verified test result after revision"

    asyncio.run(check())


def test_critic_does_not_treat_ambiguous_response_as_approval():
    async def check():
        class AmbiguousCriticGateway(FakeGateway):
            async def complete(self, *, system, prompt):
                if "Critic" in system:
                    self.calls.append(system)
                    return "The candidate appears acceptable."
                return await super().complete(system=system, prompt=prompt)

        gateway = AmbiguousCriticGateway()
        workflow = CoreWorkflow(
            router=FakeRouter(gateway),
            checkpointer=InMemorySaver(),
        )
        result = await workflow.critic({"solution": "Candidate without explicit approval"})
        assert result["critique_approved"] is False

    asyncio.run(check())


