from __future__ import annotations
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
import httpx
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from omega.adapters.database import SqlRunRepository, build_engine
from omega.adapters.models import OpenAICompatibleGateway, StaticRegistry
from omega.api import router
from omega.config import get_settings
from omega.model_router import ModelRouter
from omega.tools import BrowserTool, ComputerTool

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
    cfg=get_settings(); engine=build_engine(cfg.database_url); maker=async_sessionmaker(engine,expire_on_commit=False); http=httpx.AsyncClient()
    model_router=ModelRouter(StaticRegistry([OpenAICompatibleGateway(p,http) for p in cfg.model_providers])); redis=Redis.from_url(cfg.redis_url,decode_responses=True)
    browser=BrowserTool(http); computer=ComputerTool()
    app.state.services=Services(SqlRunRepository(maker),model_router,redis,engine,http,browser,computer)
    try: yield
    finally: await http.aclose(); await redis.aclose(); await engine.dispose()

app=FastAPI(title="OMEGA-X ASCENSION",version=__import__("omega").__version__,lifespan=lifespan)
app.include_router(router,prefix="/v1")
_static_dir=Path(__file__).parent.parent.parent/"static"
app.mount("/static",StaticFiles(directory=str(_static_dir)),name="static")
@app.get("/",response_class=HTMLResponse)
async def dashboard(): return (_static_dir/"index.html").read_text()
@app.get("/health/live")
async def live(): return {"status":"ok"}
@app.get("/health/ready")
async def ready():
    svc=app.state.services
    try:
        async with svc.engine.connect() as conn: await conn.execute(text("SELECT 1"))
        await svc.redis.ping()
        return {"status":"ready","configured_models":len(svc.router._registry.all())}
    except Exception as exc:
        return Response(content=f'{{"status":"not_ready","reason":"{type(exc).__name__}"}}',status_code=503,media_type="application/json")
@app.get("/metrics")
async def metrics(): return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
