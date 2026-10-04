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
    solution: str
    critique: str
    final: str

class CoreWorkflow:
    def __init__(self, router: ModelRouter, checkpointer: BaseCheckpointSaver):
        self.router = router
        self.graph = self._build(checkpointer)

    async def _ask(self, capability: Capability, system: str, prompt: str) -> str:
        route = await self.router.select(capability)
        return await route.gateway.complete(system=system, prompt=prompt)

    async def ceo(self, state: State) -> dict[str, str]:
        return {"plan": await self._ask("planning", "You are the CEO agent. Clarify the objective, constraints, risks, and acceptance criteria.", state["goal"])}

    async def planner(self, state: State) -> dict[str, str]:
        prompt = "GOAL:\n" + state["goal"] + "\nCEO ANALYSIS:\n" + state["plan"]
        return {"plan": await self._ask("planning", "You are the Planner agent. Produce an ordered, dependency-aware plan with verifiable milestones.", prompt)}

    async def specialist(self, state: State) -> dict[str, str]:
        prompt = "GOAL:\n" + state["goal"] + "\nPLAN:\n" + state["plan"]
        return {"solution": await self._ask(cast(Capability, state["task_type"]), "You are the assigned specialist. Produce a concrete, secure, maintainable solution. Do not claim actions you did not perform.", prompt)}

    async def critic(self, state: State) -> dict[str, str]:
        return {"critique": await self._ask("analysis", "You are the Critic. Evaluate accuracy, completeness, logic, performance, maintainability, and security. List blocking defects first.", state["solution"])}

    async def judge(self, state: State) -> dict[str, str]:
        prompt = "CANDIDATE:\n" + state["solution"] + "\nCRITIQUE:\n" + state["critique"]
        return {"final": await self._ask("reasoning", "You are the Judge. Reconcile the candidate and critique. Return the best corrected result and explicit residual risks.", prompt)}

    def _build(self, checkpointer: BaseCheckpointSaver):
        graph = StateGraph(State)
        for name, node in (("ceo", self.ceo), ("planner", self.planner), ("specialist", self.specialist), ("critic", self.critic), ("judge", self.judge)): graph.add_node(name, node)
        graph.add_edge(START, "ceo"); graph.add_edge("ceo", "planner"); graph.add_edge("planner", "specialist"); graph.add_edge("specialist", "critic"); graph.add_edge("critic", "judge"); graph.add_edge("judge", END)
        return graph.compile(checkpointer=checkpointer)

    async def run(self, tenant_id: UUID, run_id: UUID, goal: str, task_type: Capability) -> State:
        config = {"configurable": {"thread_id": str(run_id), "checkpoint_ns": str(tenant_id)}}
        return await self.graph.ainvoke({"goal": goal, "task_type": task_type}, config=config)
