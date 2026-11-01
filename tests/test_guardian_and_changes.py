import pytest

from multi_repo_sdd.discovery.engine import discover_repositories
from multi_repo_sdd.errors import ApprovalRequired, GovernanceError
from multi_repo_sdd.knowledge import rebuild_system_knowledge
from multi_repo_sdd.sdd.changes import propose_change, validate_change
from multi_repo_sdd.sdd.governance import approve_change
from multi_repo_sdd.sdd.implement import implement_change


def _discover(workspace) -> None:
    discover_repositories(workspace.layout, workspace.config, mode="initial")
    rebuild_system_knowledge(workspace.layout)


def test_guardian_retrieves_on_demand_knowledge(workspace) -> None:
    _discover(workspace)
    overview = workspace.guardian.get_system_overview()
    assert "order-service" in overview
    search = workspace.guardian.search_knowledge("partial refund")
    assert search
    deps = workspace.guardian.get_repository_dependencies("order-service")
    assert "payment-service" in deps
    graph = (workspace.layout.system_dir() / "dependency-graph.md").read_text()
    assert "mermaid" in graph
    assert "order-service" in graph
    workflow = workspace.guardian.get_business_workflow("Customer order creation")
    text = workflow.read_text()
    assert "order-service" in text
    assert "payment-service" in text


def test_impact_and_proposal_require_approval(workspace) -> None:
    _discover(workspace)
    impact = workspace.guardian.analyze_change_impact("Introduce partial refund support")
    table = impact.read_text()
    assert "payment-service" in table
    assert "order-service" in table
    path = propose_change(workspace.layout, "Introduce partial refund support")
    assert (path / "spec.md").is_file()
    assert (path / "tasks" / "payment-service.md").is_file()
    assert "refund" in (path / "spec.md").read_text().lower()
    order_tasks = (path / "tasks" / "order-service.md").read_text()
    assert "payment-service" in order_tasks
    assert "Dependencies: none" in (path / "tasks" / "payment-service.md").read_text()
    result = validate_change(workspace.layout, "introduce-partial-refund-support")
    assert result["ok"]
    with pytest.raises(ApprovalRequired):
        implement_change(workspace.layout, workspace.config, "introduce-partial-refund-support")
    approve_change(workspace.layout, "introduce-partial-refund-support", "specification", "tester")
    approve_change(workspace.layout, "introduce-partial-refund-support", "design", "tester")
    packets = implement_change(workspace.layout, workspace.config, "introduce-partial-refund-support")
    assert packets["mode"] == "packets"
    assert packets["results"][0]["status"] == "packet-written"


def test_archive_without_verification_fails(workspace) -> None:
    _discover(workspace)
    propose_change(workspace.layout, "Introduce partial refund support")
    with pytest.raises(GovernanceError):
        workspace.guardian.archive("introduce-partial-refund-support")
