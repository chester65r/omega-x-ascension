from omega.domain import ApprovalPolicy


def test_deploy_requires_human_approval():
    assert ApprovalPolicy().requires_approval({"deploy"})


def test_analysis_does_not_require_approval():
    assert not ApprovalPolicy().requires_approval({"analyze"})
