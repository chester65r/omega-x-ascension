from pathlib import Path

SQL = Path("alembic/versions/0001_production_baseline.py").read_text()
DB = Path("src/omega/adapters/database.py").read_text()


def test_rls_enabled_and_forced():
    assert 'for table in ("workflow_runs", "audit_events", "workflow_jobs")' in SQL
    assert "ENABLE ROW LEVEL SECURITY" in SQL
    assert "FORCE ROW LEVEL SECURITY" in SQL


def test_policy_is_permissive_with_read_and_write_checks():
    assert "AS RESTRICTIVE" not in SQL
    assert "USING (tenant_id =" in SQL and "WITH CHECK (tenant_id =" in SQL


def test_context_is_transaction_local():
    assert "set_config('omega.tenant_id', :tenant_id, true)" in DB
