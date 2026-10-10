from __future__ import annotations

"""Deterministic OpenAI-compatible model fixture for isolated integration tests only."""

import os
import time

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="OMEGA test-only model fixture")


@app.get("/health")
async def health():
    return {"status": "ok", "purpose": "test-fixture-only"}


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)):
    if authorization != "Bearer fixture":
        raise HTTPException(status_code=401, detail="invalid test fixture credential")
    return {"object": "list", "data": [{"id": "omega-test", "object": "model"}]}


class ChatRequest(BaseModel):
    model: str
    messages: list[dict[str, str]]
    temperature: float | None = 0.1


@app.post("/v1/chat/completions")
async def chat(request: ChatRequest, authorization: str | None = Header(default=None)):
    if authorization != "Bearer fixture":
        raise HTTPException(status_code=401, detail="invalid test fixture credential")
    if request.model != "omega-test":
        raise HTTPException(status_code=404, detail="unknown fixture model")
    system = request.messages[0].get("content", "") if request.messages else ""

    if "CEO agent" in system:
        content = "Set a clear objective and verify the connected workflow components."
    elif "Planner agent" in system:
        content = "1. Submit an authenticated task.\n2. Verify the persisted result and audit events."
    elif "research agent" in system:
        # Empty query intentionally causes BrowserTool to return locally without external browsing.
        content = ""
    elif "assigned specialist" in system:
        content = "The fixture completed the requested integration task."
    elif "Critic" in system:
        content = "No blocking defects were found in this deterministic integration run."
    elif "Judge" in system:
        content = "E2E integration completed: the task was authenticated, queued, processed by the worker, and persisted."
    else:
        content = "Fixture model response."

    return {
        "id": "chatcmpl-omega-integration",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8001")),
        log_level="warning",
    )
