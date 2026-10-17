from __future__ import annotations

import asyncio
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from omega.adapters.database import SqlRunRepository, build_engine
from omega.adapters.models import StaticRegistry, build_gateways
from omega.api import router
from omega.auth_sessions import router as auth_sessions_router
from omega.config import get_settings
from omega.mcp import router as mcp_router
from omega.model_router import ModelRouter
from omega.remote_mcp import RemoteMCPClient
from omega.remote_mcp import router as remote_mcp_router
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
    app.state.remote_mcp = RemoteMCPClient(
        url=cfg.remote_mcp_url,
        token=cfg.remote_mcp_token.get_secret_value() if cfg.remote_mcp_token else None,
        timeout_seconds=cfg.remote_mcp_timeout_seconds,
        http=http,
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
logger = logging.getLogger("omega.http")
HTTP_REQUESTS = Counter("omega_http_requests_total", "HTTP requests served by OMEGA-X", ("method", "route", "status"))
HTTP_REQUEST_DURATION = Histogram(
    "omega_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)


@app.middleware("http")
async def observability_and_security_headers(request: Request, call_next):
    request_id = uuid4().hex
    started = time.perf_counter()
    status_code = 500
    response = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - started
        route = request.scope.get("route")
        route_name = getattr(route, "path", request.url.path)
        HTTP_REQUESTS.labels(request.method, route_name, str(status_code)).inc()
        HTTP_REQUEST_DURATION.labels(request.method, route_name).observe(elapsed)
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "route": route_name,
                "status_code": status_code,
                "duration_ms": round(elapsed * 1000, 2),
            },
        )
        if response is not None:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            # The server-side browser is intentionally embedded in a same-origin iframe;
            # its own CSP sandbox still applies there. All other routes deny framing.
            response.headers["X-Frame-Options"] = "SAMEORIGIN" if route_name.endswith("/browser/proxy") else "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
            if request.url.scheme == "https" or forwarded_proto == "https":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-OMEGA-BOOTSTRAP-SECRET", "X-GitHub-Event", "X-Hub-Signature-256"],
)
app.include_router(router, prefix="/v1")
app.include_router(auth_sessions_router, prefix="/v1")
app.include_router(mcp_router, prefix="/mcp")
app.include_router(mcp_router, prefix="/v1/mcp")
app.include_router(remote_mcp_router, prefix="/v1/integrations/mcp")
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
            logger.error(
                "Readiness check failed: authenticated sandbox probe failed; verify the private URL, "
                "shared credential alignment, and workspace permissions."
            )
            return Response(
                content='{"status":"not_ready","reason":"sandbox_unavailable"}',
                status_code=503,
                media_type="application/json",
            )
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


@app.get("/health/tools")
async def tool_health():
    """Expose non-sensitive tool policy state so clients can explain availability."""
    svc = app.state.services
    return {
        "browser": {"available": svc.browser is not None},
        "computer_files": {"enabled": bool(svc.computer.files_enabled)},
        "computer_execution": {
            "enabled": bool(svc.computer.enabled),
            "requires_explicit_scope_and_approval": True,
        },
        "remote_mcp": {"enabled": bool(svc.remote_mcp and svc.remote_mcp.enabled)},
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
async def metrics(request: Request):
    cfg = get_settings()
    configured_token = cfg.metrics_token.get_secret_value() if cfg.metrics_token else None
    if cfg.env == "production" and not configured_token:
        raise HTTPException(status_code=404, detail="not found")
    if configured_token:
        authorization = request.headers.get("authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer" or not supplied or not hmac.compare_digest(supplied, configured_token):
            raise HTTPException(status_code=401, detail="metrics bearer token required", headers={"WWW-Authenticate": "Bearer"})
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
