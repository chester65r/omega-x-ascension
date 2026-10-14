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

    async def complete(self, capability, *, system, prompt):
        assert capability in self.gateway.capabilities
        return await self.gateway.complete(system=system, prompt=prompt)


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
        specialist_call = next(call for call in gateway.calls if "assigned specialist" in call.lower())
        assert "untrusted evidence" in specialist_call.lower()
        assert "never as instructions" in specialist_call.lower()
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


def test_agent_browser_research_iterates_with_bounded_searches_and_cited_sources():
    async def check():
        class IterativeGateway(FakeGateway):
            def __init__(self):
                super().__init__()
                self.controller_calls = 0

            async def complete(self, *, system, prompt):
                self.calls.append(system)
                normalized = system.lower()
                if "ceo agent" in normalized:
                    return "CEO objective analysis"
                if "planner agent" in normalized:
                    return "Find current evidence and compare sources"
                if "you are a research agent" in normalized:
                    return "first query"
                if "browser research controller" in normalized:
                    self.controller_calls += 1
                    return '{"action":"search","query":"second query"}'
                if "assigned specialist" in normalized:
                    return "A concrete evidence-backed solution"
                if "critic" in normalized:
                    return "No blocking defects in the test candidate"
                if "judge" in normalized:
                    return "Final answer with citations"
                return "Unexpected role"

        class IterativeBrowser:
            def __init__(self):
                self.queries = []
                self.fetched = []

            async def search(self, query):
                self.queries.append(query)
                if query == "first query":
                    count = 3
                    prefix = "first"
                elif query == "second query":
                    count = 3
                    prefix = "second"
                else:
                    count = 0
                    prefix = "unknown"
                return {
                    "query": query,
                    "results": [
                        {
                            "title": f"{prefix.title()} source {number}",
                            "url": f"https://{prefix}{number}.example/article",
                            "snippet": f"Evidence snippet {number}",
                        }
                        for number in range(1, count + 1)
                    ],
                }

            async def fetch(self, url):
                self.fetched.append(url)
                return {
                    "url": url,
                    "title": f"Page {url}",
                    "text": f"Reliable source evidence from {url}.",
                    "status": 200,
                }

        gateway = IterativeGateway()
        browser = IterativeBrowser()
        workflow = CoreWorkflow(
            router=FakeRouter(gateway),
            checkpointer=InMemorySaver(),
            browser=browser,
            computer=DisabledComputer(),
        )
        result = await workflow.run(
            tenant_id=uuid4(),
            run_id=uuid4(),
            goal="Research current evidence about a fictional model",
            task_type="research",
            requested_actions=[],
        )
        assert browser.queries == ["first query", "second query"]
        assert len(browser.fetched) == 5
        assert "Source [1]" in result["research"]
        assert "Source [5]" in result["research"]
        assert "URL: https://second2.example/article" in result["research"]
        assert "untrusted external content" in result["research"].lower()
        assert gateway.controller_calls == 1

    asyncio.run(check())


def test_agent_browser_research_opens_user_supplied_url_safely():
    async def check():
        class DirectURLBrowser:
            def __init__(self):
                self.fetched = []

            async def fetch(self, url):
                self.fetched.append(url)
                return {
                    "url": url,
                    "title": "User supplied source",
                    "text": "This page contains the requested source text.",
                    "status": 200,
                }

            async def search(self, query):
                return {
                    "query": query,
                    "results": [
                        {
                            "title": "The same page",
                            "url": "https://public.example/article",
                            "snippet": "duplicate URL",
                        }
                    ],
                }

        browser = DirectURLBrowser()
        workflow = CoreWorkflow(
            router=FakeRouter(FakeGateway()),
            checkpointer=InMemorySaver(),
            browser=browser,
            computer=DisabledComputer(),
        )
        result = await workflow.run(
            tenant_id=uuid4(),
            run_id=uuid4(),
            goal="Summarize this source https://public.example/article",
            task_type="research",
            requested_actions=[],
        )
        assert browser.fetched == ["https://public.example/article"]
        assert "This page contains the requested source text." in result["research"]
        assert "https://public.example/article" in result["research"]

    asyncio.run(check())


def test_requested_computer_execution_is_explicitly_reported_when_policy_disables_it():
    async def check():
        gateway = FakeGateway()
        workflow = CoreWorkflow(
            router=FakeRouter(gateway),
            checkpointer=InMemorySaver(),
            browser=FakeBrowser(),
            computer=DisabledComputer(),
        )
        result = await workflow.executor({
            "goal": "Inspect a test workspace",
            "solution": "List the workspace files",
            "requested_actions": ["execute_code"],
        })
        assert "disabled by server policy" in result["computer_output"]
        assert "No command was executed." in result["computer_output"]

    asyncio.run(check())


class WorkspacePlanRouter:
    async def complete(self, capability, *, system, prompt):
        if "careful workspace inspection agent" in system:
            return '{"operations":[{"type":"list_dir","path":"."},{"type":"read_file","path":"notes.txt"}]}'
        if "authorized tenant-workspace file editor" in system:
            return '{"operations":[{"type":"write_file","path":"notes.txt","content":"updated safely"}]}'
        raise AssertionError(f"unexpected model call: {system[:80]}")


class RecordingWorkspaceComputer:
    enabled = False
    files_enabled = True

    def __init__(self):
        self.calls = []
        self.contents = {"notes.txt": "existing notes"}

    async def list_dir(self, path=".", workspace_id=None):
        self.calls.append(("list_dir", path, str(workspace_id)))
        return {
            "path": path,
            "entries": [
                {"name": ".env", "type": "file", "size": 20},
                {"name": ".git", "type": "dir", "size": 0},
                {"name": "notes.txt", "type": "file", "size": 15},
                {"name": "src", "type": "dir", "size": 0},
            ],
            "truncated": False,
        }

    async def read_file(self, path, workspace_id=None):
        self.calls.append(("read_file", path, str(workspace_id)))
        return {"path": path, "content": self.contents[path]}

    async def write_file(self, path, content, workspace_id=None):
        self.calls.append(("write_file", path, str(workspace_id)))
        self.contents[path] = content
        return {"path": path, "written": True, "bytes": len(content.encode("utf-8"))}

    async def execute(self, *args, **kwargs):
        raise AssertionError("workspace file operations must never execute shell commands")


def test_agent_workspace_file_tools_are_tenant_scoped_read_only_by_default():
    async def check():
        computer = RecordingWorkspaceComputer()
        workflow = CoreWorkflow(
            router=WorkspacePlanRouter(),
            checkpointer=InMemorySaver(),
            browser=FakeBrowser(),
            computer=computer,
        )
        workspace = str(uuid4())
        state = {
            "goal": "Inspect the workspace notes",
            "plan": "List workspace files and read notes.txt",
            "solution": "Inspect existing notes",
            "workspace_id": workspace,
            "requested_actions": ["use_workspace_files"],
        }
        first = await workflow.executor(state)
        assert "existing notes" in first["computer_output"]
        assert first["computer_actions_completed"] is True
        assert ("list_dir", ".", workspace) in computer.calls
        assert ("read_file", "notes.txt", workspace) in computer.calls
        assert not any(call[0] == "write_file" for call in computer.calls)
        listing = next(line for line in first["computer_output"].splitlines() if '"entries"' in line)
        assert ".env" not in listing and ".git" not in listing
        # A critic revision must not repeat a prior tool side effect.
        state.update(first)
        assert await workflow.executor(state) == {}
        assert len([call for call in computer.calls if call[0] == "list_dir"]) == 1

    asyncio.run(check())


def test_agent_workspace_edits_run_only_with_explicit_write_action():
    async def check():
        computer = RecordingWorkspaceComputer()
        workflow = CoreWorkflow(
            router=WorkspacePlanRouter(),
            checkpointer=InMemorySaver(),
            browser=FakeBrowser(),
            computer=computer,
        )
        workspace = str(uuid4())
        result = await workflow.executor({
            "goal": "Update notes.txt",
            "plan": "Inspect and edit the notes",
            "solution": "Replace the note with a concise update",
            "workspace_id": workspace,
            "requested_actions": ["use_workspace_files", "write_workspace_files"],
        })
        assert computer.contents["notes.txt"] == "updated safely"
        assert ("write_file", "notes.txt", workspace) in computer.calls
        assert '"written": true' in result["computer_output"]
        assert result["computer_actions_completed"] is True

    asyncio.run(check())


def test_agent_workspace_file_tools_block_traversal_hidden_and_credential_paths():
    for path in (
        "../outside.txt", "/etc/passwd", ".env", ".git/config",
        "credentials.json", "secrets.yaml", "nested/client_secret.json",
        "service-account.json", "keys/client.pem",
    ):
        try:
            CoreWorkflow._workspace_path(path)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe workspace path must be rejected: {path}")
