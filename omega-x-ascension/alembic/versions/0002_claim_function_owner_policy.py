"""Let the job-claim function see queued jobs under FORCE ROW LEVEL SECURITY."""

from alembic import op

revision = "0002_claim_function_owner_policy"
down_revision = "0001_production_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""DO $$
    BEGIN
      EXECUTE 'DROP POLICY IF EXISTS workflow_jobs_claim_owner ON workflow_jobs';
      EXECUTE format(
        'CREATE POLICY workflow_jobs_claim_owner ON workflow_jobs FOR ALL TO %I USING (true) WITH CHECK (true)',
        current_user
      );
    END $$""")


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade is intentionally unsupported; restore a tested backup"
    )
