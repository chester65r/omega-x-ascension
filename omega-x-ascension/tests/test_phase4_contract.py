from pathlib import Path

def test_api_has_no_in_process_background_execution():
    api=Path('src/omega/api.py').read_text()
    assert 'BackgroundTasks' not in api
    assert 'repo.create_run' in api
    assert 'repo.approve_and_enqueue' in api

def test_schema_is_not_created_by_api_startup():
    main=Path('src/omega/main.py').read_text()
    assert 'create_all' not in main
    assert 'checkpointer.setup' not in main

def test_queue_claim_is_atomic_and_nonblocking():
    migration=Path('alembic/versions/0001_production_baseline.py').read_text()
    assert 'FOR UPDATE SKIP LOCKED' in migration
    assert 'SECURITY DEFINER SET search_path=public' in migration
    assert 'REVOKE ALL ON FUNCTION' in migration

def test_sensitive_actions_require_approval():
    domain=Path('src/omega/domain.py').read_text()
    api=Path('src/omega/api.py').read_text()
    assert 'execute_code' in domain
    assert 'run.approval_digest != run.digest()' in api
