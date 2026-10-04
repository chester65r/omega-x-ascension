"""Add workflow idempotency and harden expired job leases."""
from alembic import op

revision = "0002_phase5_hardening"
down_revision = "0001_production_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS idempotency_key varchar(255)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_runs_idempotency ON workflow_runs(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL")
    op.execute("""
CREATE OR REPLACE FUNCTION claim_workflow_job(p_worker text, p_lease_seconds integer DEFAULT 120)
RETURNS TABLE(id uuid, tenant_id uuid, run_id uuid, attempt_count integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE workflow_runs r
     SET status = 'failed',
         error = 'workflow failed after worker lease retries; reference=' || j.run_id,
         updated_at = now()
    FROM workflow_jobs j
   WHERE j.tenant_id = r.tenant_id
     AND j.run_id = r.id
     AND j.status = 'LEASED'
     AND j.lease_expires_at < now()
     AND j.attempt_count >= j.max_attempts;

  UPDATE workflow_jobs
     SET status = 'DEAD_LETTER',
         lease_owner = NULL,
         lease_expires_at = NULL,
         updated_at = now(),
         last_error_code = COALESCE(last_error_code, 'LEASE_EXPIRED_MAX_ATTEMPTS')
   WHERE status = 'LEASED'
     AND lease_expires_at < now()
     AND attempt_count >= max_attempts;

  RETURN QUERY
  WITH candidate AS (
    SELECT j.id
      FROM workflow_jobs j
     WHERE j.status = 'QUEUED'
       AND j.available_at <= now()
     ORDER BY j.available_at
     FOR UPDATE SKIP LOCKED
     LIMIT 1
  )
  UPDATE workflow_jobs j
     SET status = 'LEASED',
         lease_owner = p_worker,
         lease_expires_at = now() + make_interval(secs => p_lease_seconds),
         attempt_count = j.attempt_count + 1,
         updated_at = now()
    FROM candidate c
   WHERE j.id = c.id
  RETURNING j.id, j.tenant_id, j.run_id, j.attempt_count;
END
$$;
REVOKE ALL ON FUNCTION claim_workflow_job(text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_workflow_job(text,integer) TO omega_worker;
