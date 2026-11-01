from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from multi_repo_sdd import __version__
from multi_repo_sdd.context import init_workspace, load_app
from multi_repo_sdd.deps import collect_dependencies, render_dependencies, transitive
from multi_repo_sdd.discovery.engine import discover_repositories
from multi_repo_sdd.errors import SddError
from multi_repo_sdd.knowledge import rebuild_system_knowledge
from multi_repo_sdd.registry import load_registry, register_repository
from multi_repo_sdd.sdd.governance import approve_change
from multi_repo_sdd.sdd.implement import record_implementation
from multi_repo_sdd.sdd.speckit import SpecKitAdapter
from multi_repo_sdd.safety import resolve_path

app = typer.Typer(no_args_is_help=True, help="Multi-repository Spec-Driven Development guardian.")
repo_app = typer.Typer(no_args_is_help=True, help="Register and inspect repositories.")
change_app = typer.Typer(no_args_is_help=True, help="Change proposals, approvals, and verification.")
system_app = typer.Typer(no_args_is_help=True, help="System-level knowledge.")
workflow_app = typer.Typer(no_args_is_help=True, help="Cross-repository workflows.")
app.add_typer(repo_app, name="repo")
app.add_typer(change_app, name="change")
app.add_typer(system_app, name="system")
app.add_typer(workflow_app, name="workflow")
console = Console()


def _fail(exc: Exception) -> None:
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(code=1)


@app.callback()
def _version_callback(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit()


@app.command("init")
def init_cmd(
    path: Path = typer.Option(Path("."), "--path", help="Directory that will contain sdd.config.yaml"),
    knowledge_root: str = typer.Option("./sdd-workspace", "--knowledge-root"),
    repositories_root: Optional[str] = typer.Option(None, "--repositories-root"),
    name: str = typer.Option("sdd-workspace", "--name"),
) -> None:
    config_path = init_workspace(path, knowledge_root=knowledge_root, repositories_root=repositories_root, name=name)
    console.print(f"Initialized SDD workspace config at {config_path}")


@repo_app.command("add")
def repo_add(
    path: Path = typer.Argument(..., help="Filesystem path to an existing repository"),
    name: Optional[str] = typer.Option(None, "--name"),
) -> None:
    try:
        ctx = load_app()
        repo = register_repository(ctx.layout, resolve_path(path), name=name)
        ctx.audit.record("repo-add", name=repo.name, path=repo.path)
        console.print(f"Registered {repo.name} at {repo.path} (read-only)")
    except SddError as exc:
        _fail(exc)


@repo_app.command("show")
def repo_show(name: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        console.print(ctx.guardian.get_repository_overview(name))
        console.print(ctx.guardian.get_repository_architecture(name))
    except SddError as exc:
        _fail(exc)


@repo_app.command("list")
def repo_list() -> None:
    try:
        ctx = load_app()
        table = Table("name", "path", "language", "last_sha")
        for repo in load_registry(ctx.layout).repositories:
            table.add_row(repo.name, repo.path, repo.language or "", repo.last_discovered_sha or "")
        console.print(table)
    except SddError as exc:
        _fail(exc)


@app.command("discover")
def discover_cmd(
    all_repos: bool = typer.Option(False, "--all"),
    repo: Optional[str] = typer.Option(None, "--repo"),
    mode: Optional[str] = typer.Option(None, "--mode", help="initial|incremental|targeted"),
    target: Optional[str] = typer.Option(None, "--target"),
) -> None:
    try:
        ctx = load_app()
        names = None if all_repos or not repo else [repo]
        if not all_repos and not repo:
            raise SddError("Provide --all or --repo NAME")
        reports = discover_repositories(ctx.layout, ctx.config, names=names, mode=mode, target=target)
        collect_dependencies(ctx.layout)
        rebuild_system_knowledge(ctx.layout)
        for report in reports:
            console.print(
                f"Discovered {report.name}: {report.language or 'unknown'} "
                f"({len(report.apis)} apis, {len(report.dependencies)} deps, sha={report.commit_sha or 'n/a'})"
            )
    except SddError as exc:
        _fail(exc)


@app.command("refresh")
def refresh_cmd(all_repos: bool = typer.Option(True, "--all")) -> None:
    try:
        ctx = load_app()
        ctx.guardian.refresh_all()
        console.print("Incremental refresh complete")
    except SddError as exc:
        _fail(exc)


@system_app.command("overview")
def system_overview() -> None:
    try:
        ctx = load_app()
        console.print(ctx.guardian.get_system_overview())
    except SddError as exc:
        _fail(exc)


@app.command("dependencies")
def dependencies_cmd(
    repo: Optional[str] = typer.Option(None, "--repo"),
    transitive_from: Optional[str] = typer.Option(None, "--transitive-from"),
) -> None:
    try:
        ctx = load_app()
        console.print(ctx.guardian.get_repository_dependencies(repo))
        if transitive_from:
            deps = collect_dependencies(ctx.layout)
            console.print("Transitive: " + ", ".join(transitive(deps, transitive_from) or ["none"]))
    except SddError as exc:
        _fail(exc)


@workflow_app.command("discover")
def workflow_discover(description: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        path = ctx.guardian.get_business_workflow(description)
        console.print(f"Wrote {path}")
        console.print(path.read_text(encoding="utf-8"))
    except SddError as exc:
        _fail(exc)


@app.command("impact")
def impact_cmd(change: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        path = ctx.guardian.analyze_change_impact(change)
        console.print(path.read_text(encoding="utf-8"))
    except SddError as exc:
        _fail(exc)


@change_app.command("propose")
def change_propose(description: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        path = ctx.guardian.create_change_proposal(description)
        console.print(f"Created change at {path}")
    except SddError as exc:
        _fail(exc)


@change_app.command("validate")
def change_validate(change_id: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        result = ctx.guardian.validate_specification(change_id)
        console.print(result)
        if not result["ok"]:
            raise typer.Exit(code=1)
    except SddError as exc:
        _fail(exc)


@change_app.command("approve")
def change_approve(
    change_id: str = typer.Argument(...),
    artifact: str = typer.Option(..., "--artifact", help="specification|design|implementation"),
    reviewer: str = typer.Option("human", "--reviewer"),
) -> None:
    try:
        ctx = load_app()
        approve_change(ctx.layout, change_id, artifact, reviewer)
        console.print(f"Recorded {artifact} approval for {change_id} by {reviewer}")
    except SddError as exc:
        _fail(exc)


@change_app.command("implement")
def change_implement(
    change_id: str = typer.Argument(...),
    authorize_writes: bool = typer.Option(False, "--authorize-writes"),
) -> None:
    try:
        ctx = load_app()
        result = ctx.guardian.coordinate_implementation(change_id, authorize_writes=authorize_writes)
        console.print(result)
    except SddError as exc:
        _fail(exc)


@change_app.command("verify")
def change_verify(change_id: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        result = ctx.guardian.verify_implementation(change_id)
        console.print(result)
    except SddError as exc:
        _fail(exc)


@change_app.command("record")
def change_record(
    change_id: str = typer.Argument(...),
    repo: str = typer.Option(..., "--repo"),
    file: list[str] = typer.Option(..., "--file"),
) -> None:
    try:
        ctx = load_app()
        record_implementation(ctx.layout, change_id, repo, list(file))
        console.print(f"Recorded {len(file)} file(s) for {repo} on {change_id}")
    except SddError as exc:
        _fail(exc)


@change_app.command("archive")
def change_archive(change_id: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        path = ctx.guardian.archive(change_id)
        console.print(f"Archived {path}")
    except SddError as exc:
        _fail(exc)


@app.command("capabilities")
def capabilities_cmd(repo: Optional[str] = typer.Option(None, "--repo")) -> None:
    try:
        ctx = load_app()
        console.print(ctx.guardian.get_business_capabilities(repo))
    except SddError as exc:
        _fail(exc)


@app.command("evidence")
def evidence_cmd(query: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        hits = ctx.guardian.get_source_evidence(query)
        if not hits:
            console.print("Unknown: no source evidence matched.")
            return
        for hit in hits:
            console.print(f"[bold]{hit['path']}[/bold] ({hit['score']}) {hit['snippet']}")
    except SddError as exc:
        _fail(exc)


@app.command("search")
def search_cmd(query: str = typer.Argument(...)) -> None:
    try:
        ctx = load_app()
        hits = ctx.guardian.search_knowledge(query)
        if not hits:
            console.print("Unknown: no matching knowledge.")
            return
        for hit in hits:
            console.print(f"[bold]{hit['path']}[/bold] ({hit['score']}) {hit['snippet']}")
    except SddError as exc:
        _fail(exc)


@app.command("freshness")
def freshness_cmd() -> None:
    try:
        ctx = load_app()
        console.print(ctx.guardian.check_knowledge_freshness())
    except SddError as exc:
        _fail(exc)


@app.command("speckit")
def speckit_cmd(
    init_dir: Optional[Path] = typer.Option(None, "--init-in", help="Optional knowledge subdirectory only"),
) -> None:
    try:
        ctx = load_app()
        adapter = SpecKitAdapter(ctx.config)
        version = adapter.version()
        console.print(f"specify available={adapter.available()} version={version or 'not installed'}")
        if init_dir:
            target = resolve_path(init_dir)
            if ctx.layout.knowledge_root not in target.parents and target != ctx.layout.knowledge_root:
                raise SddError("Spec Kit init is allowed only inside the knowledge workspace, never in app repos")
            console.print(adapter.init_workspace(target))
    except SddError as exc:
        _fail(exc)
