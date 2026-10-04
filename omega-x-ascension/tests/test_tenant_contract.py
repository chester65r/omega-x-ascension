from uuid import uuid4
from omega.domain import WorkflowRun

def test_run_requires_explicit_tenant_and_actor():
    tenant_id = uuid4()
    run = WorkflowRun(goal="Build", task_type="planning", tenant_id=tenant_id, created_by="user-1")
    assert run.tenant_id == tenant_id
    assert run.created_by == "user-1"
