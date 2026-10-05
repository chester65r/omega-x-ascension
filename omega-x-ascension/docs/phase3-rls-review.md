# Phase 3 Database-Enforced Tenant Isolation

## Architecture review

Phase 2 correctly propagated tenant IDs through repository calls, but the database still trusted every query to include the right predicate. Phase 3 makes PostgreSQL the final enforcement boundary.

## Design

- `omega` remains the schema owner and migration role.
- `omega_app` is a restricted login role with `NOSUPERUSER` and `NOBYPASSRLS`.
- The API connects as `omega_app`; migrations and LangGraph checkpoint setup continue through the owner connection.
- `workflow_runs` and `audit_events` use forced row-level security.
- Policies compare row `tenant_id` with transaction-local `omega.tenant_id`.
- Repository operations open an explicit transaction and call `set_config(..., true)` before any tenant query. The local setting expires with the transaction, avoiding pooled-connection tenant leakage.
- Policies use both `USING` and `WITH CHECK`, protecting reads/deletes and inserts/updates.
- Repository queries retain ordinary tenant design semantics, but security no longer depends solely on them.

## Deployment order

1. Back up PostgreSQL.
2. Apply `002_auth_tenancy.sql` if upgrading directly from Phase 1.
3. Replace the placeholder role password in `003_database_rls.sql`.
4. Apply `003_database_rls.sql` with the owner/migration role.
5. Set `OMEGA_DATABASE_URL` to the restricted `omega_app` account.
6. Keep `OMEGA_CHECKPOINT_DATABASE_URL` on the migration-capable owner account until checkpoint schema provisioning is split into a dedicated migration job.

## Security properties

If tenant context is absent or malformed, policy comparison is false or errors before rows are exposed. Cross-tenant inserts and updates fail `WITH CHECK`. Table-owner bypass is closed with `FORCE ROW LEVEL SECURITY`; the API does not connect as a superuser or role with `BYPASSRLS`.

## Remaining boundary

LangGraph checkpoint tables are partitioned by tenant namespace at the application layer, not by PostgreSQL RLS, because their schema is owned by the external checkpoint package and does not expose a first-class tenant column. Protect checkpoint access behind the workflow service and use a separate database/schema and credentials in production.
