from __future__ import annotations
import asyncio, contextlib, logging, os, socket
import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.ext.asyncio import async_sessionmaker
from omega.adapters.database import SqlRunRepository, build_engine
from omega.adapters.models import OpenAICompatibleGateway, StaticRegistry
from omega.config import get_settings
from omega.domain import RunStatus
from omega.model_router import ModelRouter
from omega.tools import BrowserTool, ComputerTool
from omega.workflow import CoreWorkflow

log=logging.getLogger(__name__)

async def maintain_lease(repo, tenant_id, job_id, attempt, worker_id):
    while True:
        await asyncio.sleep(30)
        if not await repo.heartbeat(tenant_id,job_id,attempt,worker_id):
            raise RuntimeError("job lease lost")

async def process(repo,workflow,tenant_id,run_id,job_id,attempt,worker_id):
    lease_task=asyncio.create_task(maintain_lease(repo,tenant_id,job_id,attempt,worker_id))
    try:
        run=await repo.get(tenant_id,run_id)
        if not run or run.status not in {RunStatus.PENDING,RunStatus.RUNNING}:
            await repo.finish_job(tenant_id,job_id,attempt,worker_id,True); return
        run.status=RunStatus.RUNNING; await repo.save(tenant_id,run); await repo.append_event(tenant_id,run_id,'run.started',{'attempt':attempt})
        try:
            result=await workflow.run(tenant_id,run_id,run.goal,run.task_type)
            if lease_task.done(): await lease_task
            if not await repo.complete_success(tenant_id,job_id,attempt,worker_id,result['final']): raise RuntimeError("stale worker completion rejected")
        except Exception as exc:
            code=type(exc).__name__
            await repo.fail_attempt(tenant_id,job_id,attempt,worker_id,code)
            log.exception('workflow failed run_id=%s error_code=%s',run_id,code)
    finally:
        lease_task.cancel()
        with contextlib.suppress(asyncio.CancelledError): await lease_task

async def main():
    cfg=get_settings()
    if not cfg.worker_database_url: raise RuntimeError('OMEGA_WORKER_DATABASE_URL is required')
    engine=build_engine(cfg.worker_database_url); maker=async_sessionmaker(engine,expire_on_commit=False); repo=SqlRunRepository(maker)
    http=httpx.AsyncClient(); router=ModelRouter(StaticRegistry([OpenAICompatibleGateway(p,http) for p in cfg.model_providers])); worker_id=f'{socket.gethostname()}:{os.getpid()}'
    try:
        browser=BrowserTool(http); computer=ComputerTool(enabled=cfg.enable_computer_execution)
        async with AsyncPostgresSaver.from_conn_string(cfg.checkpoint_database_url) as saver:
            workflow=CoreWorkflow(router,saver,browser,computer)
            while True:
                claimed=await repo.claim(worker_id)
                if claimed is None: await asyncio.sleep(1); continue
                await process(repo,workflow,*claimed,worker_id)
    finally:
        await http.aclose(); await engine.dispose()
if __name__=='__main__': asyncio.run(main())
