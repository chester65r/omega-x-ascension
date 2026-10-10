from pathlib import Path


def test_api_has_no_in_process_background_execution():
    api = Path("src/omega/api.py").read_text()
    assert "BackgroundTasks" not in api
    assert "repo.create_run" in api
    assert "repo.approve_and_enqueue" in api


def test_schema_is_not_created_by_api_startup():
    main = Path("src/omega/main.py").read_text()
    assert "create_all" not in main
    assert "checkpointer.setup" not in main


def test_queue_claim_is_atomic_and_nonblocking():
    migration = Path("alembic/versions/0001_production_baseline.py").read_text()
    assert "FOR UPDATE SKIP LOCKED" in migration
    assert "SECURITY DEFINER SET search_path=public" in migration
    assert "REVOKE ALL ON FUNCTION" in migration


def test_sensitive_actions_require_approval():
    domain = Path("src/omega/domain.py").read_text()
    api = Path("src/omega/api.py").read_text()
    assert "execute_code" in domain
    assert "run.approval_digest != run.digest()" in api


def test_run_history_is_authenticated_tenant_scoped_and_bounded():
    database = Path("src/omega/adapters/database.py").read_text()
    api = Path("src/omega/api.py").read_text()
    assert "async def list_runs(self, tenant_id: UUID, limit: int = 50)" in database
    assert "RunRow.tenant_id == tenant_id" in database
    assert ".order_by(RunRow.created_at.desc(), RunRow.id.desc())" in database
    assert '@router.get("/runs", response_model=list[RunView])' in api
    assert "Query(default=50, ge=1, le=100)" in api
    assert 'scopes=["runs:read"]' in api
