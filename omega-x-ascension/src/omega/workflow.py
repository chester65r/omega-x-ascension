from __future__ import annotations
from typing import TypedDict, cast
from uuid import UUID
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from omega.config import Capability
from omega.model_router import ModelRouter

class State(TypedDict, total=False):
    goal: str
    task_type: Capability
    plan: str
    research: str
    solution: str
    computer_output: str
    critique: str
    final: str

class CoreWorkflow:
    def __init__(self, router: ModelRouter, checkpointer: BaseCheckpointSaver, browser=None, computer=None):
        self.router = router
        self.browser = browser
        self.computer = computer
        self.graph = self._build(checkpointer)

    async def _ask(self, capability: Capability, system: str, prompt: str) -> str:
        route = await self.router.select(capability)
        return await route.gateway.complete(system=system, prompt=prompt)

    async def ceo(self, state: State) -> dict[str, str]:
        return {"plan": await self._ask("planning", "You are the CEO agent. Clarify the objective, constraints, risks, and acceptance criteria.", state["goal"])}

    async def planner(self, state: State) -> dict[str, str]:
        prompt = "GOAL:\n" + state["goal"] + "\nCEO ANALYSIS:\n" + state["plan"]
        return {"plan": await self._ask("planning", "You are the Planner agent. Produce an ordered, dependency-aware plan with verifiable milestones.", prompt)}

    async def researcher(self, state: State) -> dict[str, str]:
        if not self.browser:
            return {}
        try:
            query = await self._ask("research", "You are a research agent. Generate a concise web search query to gather information for the following goal and plan. Return only the search query, nothing else.", f"GOAL: {state['goal']}\nPLAN: {state['plan']}")
            search_results = await self.browser.search(query.strip())
            research_parts = []
            for result in search_results.get("results", [])[:3]:
                page = await self.browser.fetch(result["url"])
                if page.get("text"):
                    research_parts.append(f"Source: {page['title']}\nURL: {page['url']}\nContent: {page['text'][:2000]}")
            research = "\n\n---\n\n".join(research_parts) if research_parts else "No research results found."
            return {"research": research}
        except Exception:
            return {"research": "Research failed; continuing without external data."}

    async def specialist(self, state: State) -> dict[str, str]:
        prompt = "GOAL:\n" + state["goal"] + "\nPLAN:\n" + state["plan"]
        if state.get("research"):
            prompt += "\nRESEARCH:\n" + state["research"]
        return {"solution": await self._ask(cast(Capability, state["task_type"]), "You are the assigned specialist. Produce a concrete, secure, maintainable solution. Do not claim actions you did not perform.", prompt)}

    async def executor(self, state: State) -> dict[str, str]:
        if not self.computer or not self.computer.enabled:
            return {}
        try:
            plan = await self._ask("coding", "You are a computer execution agent. Based on the goal and solution, generate shell commands to accomplish the task. Return only the commands, one per line.", f"GOAL: {state['goal']}\nSOLUTION: {state['solution']}")
            commands = [cmd.strip() for cmd in plan.strip().split("\n") if cmd.strip()]
            outputs = []
            for cmd in commands[:5]:
                result = await self.computer.execute(cmd)
                outputs.append(f"$ {result['command']}\n{result['stdout']}\n{result['stderr']}")
            return {"computer_output": "\n\n".join(outputs)}
        except Exception:
            return {"computer_output": "Computer execution failed; continuing without execution results."}

    async def critic(self, state: State) -> dict[str, str]:
        prompt = "SOLUTION:\n" + state["solution"]
        if state.get("computer_output"):
            prompt += "\nEXECUTION OUTPUT:\n" + state["computer_output"]
        return {
            "critique": await self._ask(
                "analysis",
                "You are the Critic. Evaluate accuracy, completeness, logic, performance, maintainability, security, and execution evidence. List blocking defects first.",
                prompt,
            )
        }

    async def judge(self, state: State) -> dict[str, str]:
        prompt = "CANDIDATE:\n" + state["solution"]
        if state.get("computer_output"):
            prompt += "\nEXECUTION OUTPUT:\n" + state["computer_output"]
        prompt += "\nCRITIQUE:\n" + state["critique"]
        return {"final": await self._ask("reasoning", "You are the Judge. Reconcile the candidate and critique. Return the best corrected result and explicit residual risks.", prompt)}

    def _build(self, checkpointer: BaseCheckpointSaver):
        graph = StateGraph(State)
        for name, node in (("ceo", self.ceo), ("planner", self.planner), ("researcher", self.researcher), ("specialist", self.specialist), ("executor", self.executor), ("critic", self.critic), ("judge", self.judge)): graph.add_node(name, node)
        graph.add_edge(START, "ceo"); graph.add_edge("ceo", "planner"); graph.add_edge("planner", "researcher"); graph.add_edge("researcher", "specialist"); graph.add_edge("specialist", "executor"); graph.add_edge("executor", "critic"); graph.add_edge("critic", "judge"); graph.add_edge("judge", END)
        return graph.compile(checkpointer=checkpointer)

    async def run(self, tenant_id: UUID, run_id: UUID, goal: str, task_type: Capability) -> State:
        config = {"configurable": {"thread_id": str(run_id), "checkpoint_ns": str(tenant_id)}}
        return await self.graph.ainvoke({"goal": goal, "task_type": task_type}, config=config)
