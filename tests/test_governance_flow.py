from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from multi_repo_sdd.cli import app
from multi_repo_sdd.discovery.adapters import discover_dependencies, discover_dotnet, discover_go, discover_java
from multi_repo_sdd.discovery.engine import discover_repositories
from multi_repo_sdd.discovery.lock import DiscoveryLock
from multi_repo_sdd.errors import DiscoveryError, GovernanceError, RegistryError
from multi_repo_sdd.registry import load_registry, register_repository
from multi_repo_sdd.sdd.changes import archive_change, find_change, propose_change
from multi_repo_sdd.sdd.implement import implement_change
from multi_repo_sdd.sdd.verify import verify_change

runner = CliRunner()


def _git_commit(path: Path, message: str = "baseline") -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=sdd@example.com", "-c", "user.name=sdd", "commit", "-m", message],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_markdown_mention_is_not_a_dependency(tmp_path: Path) -> None:
    repo = tmp_path / "order-service"
    repo.mkdir()
    readme = repo / "notes.md"
    readme.write_text("This document mentions payment-service but does not call it.\n", encoding="utf-8")
    deps = discover_dependencies(repo, [readme], "order-service", None, ["order-service", "payment-service"])
    assert deps == []


def test_language_adapters_read_routes(tmp_path: Path) -> None:
    root = tmp_path / "svc"
    root.mkdir()
    go_file = root / "main.go"
    go_file.write_text('package main\nfunc main(){ http.HandleFunc("/health", nil) }\n', encoding="utf-8")
    java_file = root / "Api.java"
    java_file.write_text('@GetMapping("/customers")\nclass Api {}\n', encoding="utf-8")
    cs_file = root / "Api.cs"
    cs_file.write_text('[HttpPost("/refunds")]\nclass Api {}\n', encoding="utf-8")
    assert discover_go(root, [go_file], "svc", None)[0].path == "/health"
    assert discover_java(root, [java_file], "svc", None)[0].path == "/customers"
    assert discover_dotnet(root, [cs_file], "svc", None)[0].path == "/refunds"


def test_secrets_and_external_symlinks_stay_out_of_knowledge(workspace, tmp_path: Path) -> None:
    repo = tmp_path / "secret-svc"
    repo.mkdir()
    (repo / "app.py").write_text(
        'raise RuntimeError("must not refund")  # token=supersecretvalue\n',
        encoding="utf-8",
    )
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside-secret-token-value", encoding="utf-8")
    (repo / "leak.txt").symlink_to(outside)
    register_repository(workspace.layout, repo, name="secret-svc")
    discover_repositories(workspace.layout, workspace.config, names=["secret-svc"], mode="initial")
    blob = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in workspace.layout.repo_knowledge_dir("secret-svc").rglob("*")
        if path.is_file()
    )
    assert "supersecretvalue" not in blob
    assert "outside-secret-token-value" not in blob


def test_rejects_path_like_names_and_discovery_writes(workspace, tmp_path: Path) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()
    with pytest.raises(RegistryError):
        register_repository(workspace.layout, repo, name="../etc")
    with pytest.raises(GovernanceError):
        find_change(workspace.layout, "../etc")
    workspace.config.discovery.read_only = False
    with pytest.raises(DiscoveryError):
        discover_repositories(workspace.layout, workspace.config, mode="initial")


def test_incremental_skips_clean_git_repo_and_freshness_tracks_edits(workspace) -> None:
    registry = load_registry(workspace.layout)
    for repo in registry.repositories:
        _git_commit(Path(repo.path))
    discover_repositories(workspace.layout, workspace.config, mode="initial")
    overview = workspace.layout.repo_knowledge_dir("order-service") / "repository-overview.md"
    marker = overview.stat().st_mtime_ns
    discover_repositories(workspace.layout, workspace.config, mode="incremental")
    assert overview.stat().st_mtime_ns == marker
    rows = {row["repository"]: row for row in workspace.guardian.check_knowledge_freshness()}
    assert rows["order-service"]["state"] == "fresh"
    readme = Path(registry.get("order-service").path) / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nEdited.\n", encoding="utf-8")
    rows = {row["repository"]: row for row in workspace.guardian.check_knowledge_freshness()}
    assert rows["order-service"]["state"] == "dirty"


def test_targeted_discovery_keeps_unrelated_endpoints(workspace) -> None:
    discover_repositories(workspace.layout, workspace.config, names=["order-service"], mode="initial")
    order = Path(load_registry(workspace.layout).get("order-service").path)
    health = order / "app" / "health.py"
    health.write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health():\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    report = discover_repositories(
        workspace.layout,
        workspace.config,
        names=["order-service"],
        mode="targeted",
        target="health",
    )[0]
    paths = {api.path for api in report.apis}
    assert "/orders" in paths
    assert "/health" in paths


def test_active_lock_rejects_a_second_discovery(workspace) -> None:
    lock = workspace.layout.governance_dir() / "locks" / "order-service.lock"
    with DiscoveryLock(lock):
        with pytest.raises(DiscoveryError):
            discover_repositories(workspace.layout, workspace.config, names=["order-service"], mode="initial")


def test_duplicate_proposal_is_rejected(workspace) -> None:
    discover_repositories(workspace.layout, workspace.config, mode="initial")
    propose_change(workspace.layout, "Introduce partial refund support")
    with pytest.raises(GovernanceError):
        propose_change(workspace.layout, "Introduce partial refund support")


def test_packet_mode_does_not_execute_spec_text(workspace, tmp_path: Path) -> None:
    discover_repositories(workspace.layout, workspace.config, mode="initial")
    path = propose_change(workspace.layout, "Introduce partial refund support")
    (path / "spec.md").write_text((path / "spec.md").read_text(encoding="utf-8") + "\nrm -rf /\n", encoding="utf-8")
    from multi_repo_sdd.sdd.governance import approve_change

    approve_change(workspace.layout, "introduce-partial-refund-support", "specification", "tester")
    approve_change(workspace.layout, "introduce-partial-refund-support", "design", "tester")
    marker = tmp_path / "should-not-run"
    workspace.config.agents.implementation_provider = "command"
    workspace.config.agents.implementation_command = ["touch", str(marker)]
    result = implement_change(workspace.layout, workspace.config, "introduce-partial-refund-support")
    assert result["mode"] == "packets"
    assert not marker.exists()
    assert result["batches"]


def test_command_provider_runs_configured_argv_only(workspace, tmp_path: Path) -> None:
    discover_repositories(workspace.layout, workspace.config, mode="initial")
    propose_change(workspace.layout, "Introduce partial refund support")
    from multi_repo_sdd.sdd.governance import approve_change

    approve_change(workspace.layout, "introduce-partial-refund-support", "specification", "tester")
    approve_change(workspace.layout, "introduce-partial-refund-support", "design", "tester")
    marker = tmp_path / "ran"
    workspace.config.governance.authorize_repository_writes = True
    workspace.config.agents.implementation_provider = "command"
    workspace.config.agents.implementation_command = ["touch", str(marker)]
    result = implement_change(
        workspace.layout,
        workspace.config,
        "introduce-partial-refund-support",
        authorize_writes=True,
    )
    assert result["mode"] == "dispatched"
    assert marker.is_file()
    assert all(item["status"] == "completed" for item in result["results"])


def test_verify_and_archive_require_real_convergence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from multi_repo_sdd.context import init_workspace, load_app

    root = tmp_path / "ws"
    init_workspace(root, knowledge_root="./sdd-workspace", name="verify")
    monkeypatch.chdir(root)
    ctx = load_app(root)
    repo = tmp_path / "demo-svc"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _git_commit(repo)
    register_repository(ctx.layout, repo, name="demo-svc")
    change = ctx.layout.change_stage_dir("in-progress") / "demo-change"
    (change / "tasks").mkdir(parents=True)
    (change / "spec.md").write_text("# spec\n\ndemo-svc must keep the passing test.\n", encoding="utf-8")
    (change / "design.md").write_text("demo-svc\n", encoding="utf-8")
    (change / "proposal.md").write_text("proposal\n", encoding="utf-8")
    (change / "impact-analysis.md").write_text("impact\n", encoding="utf-8")
    (change / "checklist.md").write_text("- [x] done\n", encoding="utf-8")
    (change / "analysis.md").write_text("analysis\n", encoding="utf-8")
    (change / "tasks" / "demo-svc.md").write_text("- [x] implement\n", encoding="utf-8")
    (change / "convergence.md").write_text("# Convergence — demo-change\n\n- Status: not-started\n", encoding="utf-8")
    (change / "status.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "demo-change",
                "repositories": ["demo-svc"],
                "approvals": {"specification": True, "design": True, "implementation": False},
                "recorded_files": {"demo-svc": ["tests/test_ok.py"]},
            }
        ),
        encoding="utf-8",
    )
    report = verify_change(ctx.layout, ctx.config, "demo-change")
    assert report["passed"] is True
    archived = archive_change(ctx.layout, "demo-change", config=ctx.config)
    assert archived.parent.name == "archive"
    living = ctx.layout.knowledge_root / "specifications" / "demo-change" / "spec.md"
    assert living.is_file()
    assert "demo-svc" in living.read_text(encoding="utf-8")


def test_cli_refuses_speckit_init_in_an_application_repo(workspace) -> None:
    repo = load_registry(workspace.layout).repositories[0]
    result = runner.invoke(app, ["speckit", "--init-in", repo.path])
    assert result.exit_code == 1
    assert "knowledge workspace" in result.output.lower() or "allowed only" in result.output.lower()
