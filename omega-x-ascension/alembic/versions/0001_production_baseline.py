"""Production baseline: tenant data, durable jobs, approvals, and RLS."""

from alembic import op

revision = "0001_production_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("REVOKE CREATE ON SCHEMA public FROM omega_app, omega_worker")
    op.execute(
        """DO $$ BEGIN CREATE TYPE run_status AS ENUM ('pending','running','waiting_approval','succeeded','failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )
    op.execute(
        """DO $$ BEGIN CREATE TYPE job_status AS ENUM ('QUEUED','LEASED','COMPLETED','DEAD_LETTER'); EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )
    op.execute("""CREATE TABLE IF NOT EXISTS workflow_runs (
      tenant_id uuid NOT NULL, id uuid NOT NULL, created_by varchar(255) NOT NULL,
      goal text NOT NULL, task_type varchar(32) NOT NULL, status run_status NOT NULL,
      requested_actions jsonb NOT NULL DEFAULT '[]'::jsonb, approval_digest varchar(64),
      output text, error text, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
      PRIMARY KEY (tenant_id,id))""")
    op.execute(
        "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS requested_actions jsonb NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS approval_digest varchar(64)")
    op.execute("""CREATE TABLE IF NOT EXISTS audit_events (
      id bigserial PRIMARY KEY, tenant_id uuid NOT NULL, run_id uuid NOT NULL, kind varchar(80) NOT NULL,
      payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY (tenant_id,run_id) REFERENCES workflow_runs(tenant_id,id) ON DELETE CASCADE)""")
    op.execute("""CREATE TABLE IF NOT EXISTS workflow_jobs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, run_id uuid NOT NULL,
      status job_status NOT NULL DEFAULT 'QUEUED', available_at timestamptz NOT NULL DEFAULT now(),
      lease_owner varchar(255), lease_expires_at timestamptz, attempt_count integer NOT NULL DEFAULT 0,
      max_attempts integer NOT NULL DEFAULT 5, last_error_code varchar(100), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (tenant_id,run_id), FOREIGN KEY (tenant_id,run_id) REFERENCES workflow_runs(tenant_id,id) ON DELETE CASCADE)""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_tenant_created ON workflow_runs(tenant_id,created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_events_tenant_run ON audit_events(tenant_id,run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_jobs_claim ON workflow_jobs(status,available_at,lease_expires_at)"
    )
    op.execute("""CREATE OR REPLACE FUNCTION claim_workflow_job(p_worker text, p_lease_seconds integer DEFAULT 120)
      RETURNS TABLE(id uuid,tenant_id uuid,run_id uuid,attempt_count integer) LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
      BEGIN RETURN QUERY WITH candidate AS (
        SELECT j.id FROM workflow_jobs j WHERE (j.status='QUEUED' AND j.available_at<=now()) OR (j.status='LEASED' AND j.lease_expires_at<now())
        ORDER BY j.available_at FOR UPDATE SKIP LOCKED LIMIT 1)
      UPDATE workflow_jobs j SET status='LEASED',lease_owner=p_worker,lease_expires_at=now()+make_interval(secs=>p_lease_seconds),attempt_count=j.attempt_count+1,updated_at=now()
      FROM candidate c WHERE j.id=c.id RETURNING j.id,j.tenant_id,j.run_id,j.attempt_count; END $$""")
    op.execute("REVOKE ALL ON FUNCTION claim_workflow_job(text,integer) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION claim_workflow_job(text,integer) TO omega_worker")
    for table in ("workflow_runs", "audit_events", "workflow_jobs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"""CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL TO omega_app, omega_worker
          USING (tenant_id = NULLIF(current_setting('omega.tenant_id',true),'')::uuid)
          WITH CHECK (tenant_id = NULLIF(current_setting('omega.tenant_id',true),'')::uuid)""")
    op.execute("GRANT SELECT,INSERT,UPDATE ON workflow_runs TO omega_app")
    op.execute("GRANT SELECT,INSERT ON audit_events TO omega_app")
    op.execute("GRANT SELECT,INSERT,UPDATE ON workflow_jobs TO omega_app")
    op.execute("GRANT SELECT,UPDATE ON workflow_runs TO omega_worker")
    op.execute("GRANT SELECT,INSERT ON audit_events TO omega_worker")
    op.execute("GRANT SELECT,INSERT,UPDATE ON workflow_jobs TO omega_worker")
    op.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO omega_app,omega_worker")


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade is intentionally unsupported; restore a tested backup"
    )
