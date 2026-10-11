from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from omega.adapters.database import SqlRunRepository, build_engine
from omega.adapters.models import StaticRegistry, build_gateways
from omega.api import router
from omega.config import get_settings
from omega.mcp import router as mcp_router
from omega.model_router import ModelRouter
from omega.tools import BrowserTool, ComputerTool
from omega.webhooks import router as webhooks_router


@dataclass
class Services:
    repo: SqlRunRepository
    router: ModelRouter
    redis: Redis
    engine: AsyncEngine
    http: httpx.AsyncClient
    browser: BrowserTool
    computer: ComputerTool


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    engine = build_engine(cfg.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    http = httpx.AsyncClient()
    model_router = ModelRouter(StaticRegistry(build_gateways(cfg, http)))
    redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    browser = BrowserTool(http)
    computer = ComputerTool(
        client=http,
        base_url=cfg.sandbox_url,
        token=cfg.sandbox_token.get_secret_value() if cfg.sandbox_token else None,
        enabled=cfg.enable_computer_execution,
        files_enabled=cfg.enable_computer_files,
    )
    app.state.services = Services(
        SqlRunRepository(maker), model_router, redis, engine, http, browser, computer
    )
    worker_task = None
    if os.environ.get("OMEGA_EMBEDDED_WORKER", "").lower() == "true":
        from omega.worker import main as worker_main

        worker_task = asyncio.create_task(worker_main(), name="omega-embedded-worker")
    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
        await http.aclose()
        await redis.aclose()
        await engine.dispose()


app = FastAPI(title="OMEGA-X ASCENSION", version=__import__("omega").__version__, lifespan=lifespan)
allowed_origins = ["https://appassets.androidplatform.net"]
allowed_origins.extend(
    origin.strip()
    for origin in os.environ.get("OMEGA_CORS_ORIGINS", "").split(",")
    if origin.strip()
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-GitHub-Event", "X-Hub-Signature-256"],
)
app.include_router(router, prefix="/v1")
app.include_router(mcp_router, prefix="/mcp")
app.include_router(mcp_router, prefix="/v1/mcp")
app.include_router(webhooks_router, prefix="/webhooks")
app.include_router(webhooks_router, prefix="/v1/webhooks")

_static_candidates = (
    Path(__file__).resolve().parents[2] / "static",
    Path.cwd() / "static",
    Path("/app/static"),
)
_static_dir = next((path for path in _static_candidates if path.is_dir()), _static_candidates[0])
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return (_static_dir / "index.html").read_text()


@app.get("/health/live")
async def live():
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    svc = app.state.services
    try:
        async with svc.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await svc.redis.ping()
        if (svc.computer.enabled or svc.computer.files_enabled) and not await svc.computer.health():
            raise RuntimeError("sandbox_unavailable")
        providers = await svc.router.status()
        healthy_models = sum(1 for provider in providers if provider["healthy"])
        if healthy_models == 0:
            return Response(
                content='{"status":"not_ready","reason":"no_healthy_model_configured"}',
                status_code=503,
                media_type="application/json",
            )
        return {
            "status": "ready",
            "configured_models": len(providers),
            "healthy_models": healthy_models,
        }
    except Exception as exc:
        return Response(
            content=f'{{"status":"not_ready","reason":"{type(exc).__name__}"}}',
            status_code=503,
            media_type="application/json",
        )


@app.get("/health/models")
async def model_health():
    svc = app.state.services
    providers = await svc.router.status()
    return {
        "configured_models": len(providers),
        "healthy_models": sum(1 for provider in providers if provider["healthy"]),
        "providers": providers,
    }


@app.get("/version")
async def version_info():
    return {
        "name": "OMEGA-X ASCENSION",
        "version": __import__("omega").__version__,
        "api_version": "v1",
        "features": [
            "langgraph_feedback_loop",
            "mcp_server",
            "hitl_approval",
            "github_webhooks",
            "slack_notifications",
            "telegram_notifications",
        ],
    }


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
