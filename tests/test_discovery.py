from pathlib import Path

from multi_repo_sdd.discovery.engine import discover_repositories
from multi_repo_sdd.knowledge import rebuild_system_knowledge


def test_discovery_does_not_modify_application_repos(workspace) -> None:
    order = Path(workspace.layout.knowledge_root).parent / "repos" / "order-service"
    before = {path: path.stat().st_mtime_ns for path in order.rglob("*") if path.is_file()}
    discover_repositories(workspace.layout, workspace.config, mode="initial")
    after = {path: path.stat().st_mtime_ns for path in order.rglob("*") if path.is_file()}
    assert before == after


def test_discovery_writes_evidence_backed_artifacts(workspace) -> None:
    reports = discover_repositories(workspace.layout, workspace.config, mode="initial")
    names = {item.name for item in reports}
    assert names == {"order-service", "payment-service"}
    order = next(item for item in reports if item.name == "order-service")
    assert order.language == "python"
    assert "FastAPI" in order.frameworks
    assert any(api.path == "/orders" for api in order.apis)
    assert any(dep.target == "payment-service" and dep.confidence == "verified" for dep in order.dependencies)
    evidence_files = list((workspace.layout.repo_knowledge_dir("order-service")).glob("*.md"))
    assert len(evidence_files) >= 8
    overview = (workspace.layout.repo_knowledge_dir("order-service") / "repository-overview.md").read_text()
    assert "approved business specification" in overview.lower() or "not an approved" in overview.lower()
    deps = (workspace.layout.repo_knowledge_dir("order-service") / "dependencies.yaml").read_text()
    assert "payment-service" in deps
    assert "verified" in deps or "inferred" in deps


def test_payment_refund_constraint_is_discovered(workspace) -> None:
    reports = discover_repositories(workspace.layout, workspace.config, mode="initial")
    payment = next(item for item in reports if item.name == "payment-service")
    assert any("/refunds" in api.path for api in payment.apis)
    rules = (workspace.layout.repo_knowledge_dir("payment-service") / "business-rules.md").read_text()
    assert "refund" in rules.lower()


def test_system_overview_does_not_invent_facts(workspace) -> None:
    discover_repositories(workspace.layout, workspace.config, mode="initial")
    rebuild_system_knowledge(workspace.layout)
    overview = (workspace.layout.system_dir() / "system-overview.md").read_text()
    assert "order-service" in overview
    assert "payment-service" in overview
