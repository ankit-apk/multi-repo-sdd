from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from multi_repo_sdd.config import SddConfig
from multi_repo_sdd.discovery import adapters
from multi_repo_sdd.discovery.lock import DiscoveryLock
from multi_repo_sdd.discovery.scan import iter_files
from multi_repo_sdd.discovery.writer import load_cached_report, write_report
from multi_repo_sdd.errors import DiscoveryError
from multi_repo_sdd.gitutil import changed_files_since, commit_sha
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.models import ApiEndpoint, Dependency, DiscoveryReport, Evidence
from multi_repo_sdd.registry import RegisteredRepository, load_registry, save_registry
from multi_repo_sdd.safety import AuditLog, assert_within, redact_text, utc_now

MANIFESTS = {
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
}


def discover_repositories(
    layout: WorkspaceLayout,
    config: SddConfig,
    names: list[str] | None = None,
    mode: str | None = None,
    target: str | None = None,
) -> list[DiscoveryReport]:
    registry = load_registry(layout)
    selected = registry.repositories if not names else [registry.get(name) for name in names]
    if not selected:
        raise DiscoveryError("No repositories are registered")
    mode = mode or config.discovery.default_mode
    if target:
        mode = "targeted"
    reports: list[DiscoveryReport] = []
    if config.agents.repository_discovery.execution_mode == "parallel" and len(selected) > 1:
        with ThreadPoolExecutor(max_workers=min(8, len(selected))) as pool:
            futures = {
                pool.submit(_discover_one, layout, config, repo, mode, target, registry.names()): repo.name
                for repo in selected
            }
            for future in as_completed(futures):
                reports.append(future.result())
    else:
        for repo in selected:
            reports.append(_discover_one(layout, config, repo, mode, target, registry.names()))
    reports.sort(key=lambda item: item.name)
    registry = load_registry(layout)
    for report in reports:
        item = registry.get(report.name)
        item.language = report.language
        item.last_discovered_sha = report.commit_sha
        item.last_discovered_at = report.discovered_at
        registry.upsert(item)
    save_registry(layout, registry)
    return reports


def discover_repository(
    layout: WorkspaceLayout,
    config: SddConfig,
    name: str,
    mode: str | None = None,
    target: str | None = None,
) -> DiscoveryReport:
    return discover_repositories(layout, config, names=[name], mode=mode, target=target)[0]


def _discover_one(
    layout: WorkspaceLayout,
    config: SddConfig,
    repo: RegisteredRepository,
    mode: str,
    target: str | None,
    registry_names: list[str],
) -> DiscoveryReport:
    if not config.discovery.read_only:
        raise DiscoveryError("Discovery must remain read-only in this version")
    root = assert_within(Path(repo.path), Path(repo.path))
    if not root.is_dir():
        raise DiscoveryError(f"Repository path is missing: {root}")
    lock_path = layout.governance_dir() / "locks" / f"{repo.name}.lock"
    with DiscoveryLock(lock_path):
        sha = commit_sha(root)
        if mode == "incremental" and sha and repo.last_discovered_sha == sha:
            changes = changed_files_since(root, sha)
            cached = load_cached_report(layout, repo.name)
            if changes == [] and cached is not None:
                AuditLog(layout.audit_log()).record(
                    "discover-skipped",
                    repository=repo.name,
                    mode=mode,
                    commit_sha=sha,
                    reason="work tree matches the last discovered commit",
                )
                return cached
        files = iter_files(root, config.discovery)
        scanned_rels: set[str] | None = None
        if mode == "targeted":
            if not target:
                raise DiscoveryError("Targeted discovery requires a target")
            needle = target.lower()
            matched = [path for path in files if _matches_target(path, root, needle)]
            if not matched:
                raise DiscoveryError(f"No files matched target {target!r} in {repo.name}")
            manifests = [path for path in files if path.name in MANIFESTS]
            files = _unique_paths(matched + manifests)
            scanned_rels = {path.relative_to(root).as_posix() for path in matched}
        report = _build_report(root, repo, files, registry_names, sha, mode)
        if mode == "targeted" and scanned_rels is not None:
            previous = load_cached_report(layout, repo.name)
            if previous is not None:
                report = _merge_targeted(previous, report, scanned_rels)
            else:
                report.unknowns.append(
                    "Targeted discovery did not scan the rest of the repository. Run initial discovery for a baseline."
                )
        report.business_rules = [redact_text(rule) for rule in report.business_rules]
        report.purpose = redact_text(report.purpose)
        write_report(layout, report)
        AuditLog(layout.audit_log()).record(
            "discover",
            repository=repo.name,
            mode=mode,
            commit_sha=sha,
            files_scanned=report.files_scanned,
        )
        return report


def _build_report(
    root: Path,
    repo: RegisteredRepository,
    files: list[Path],
    registry_names: list[str],
    sha: str | None,
    mode: str,
) -> DiscoveryReport:
    language, frameworks = adapters.detect_stack(root, files)
    apis, entry_points, symbols = adapters.discover_python(root, files, repo.name, sha)
    js_apis, js_entries = adapters.discover_javascript(root, files, repo.name, sha)
    apis.extend(js_apis)
    apis.extend(adapters.discover_java(root, files, repo.name, sha))
    apis.extend(adapters.discover_go(root, files, repo.name, sha))
    apis.extend(adapters.discover_dotnet(root, files, repo.name, sha))
    entry_points.extend(js_entries)
    modules = adapters.discover_modules(root, files)
    capabilities = adapters.discover_capabilities(apis, repo.name, sha)
    dependencies = adapters.discover_dependencies(root, files, repo.name, sha, registry_names)
    tests = adapters.discover_tests(files, root)
    db_notes = adapters.discover_database_notes(files, root)
    purpose, unknowns = _purpose(root, repo.name, language, frameworks, apis)
    rules = adapters.discover_business_rules(files, root)
    constraints = _constraints(language, frameworks)
    risks = _risks(tests, dependencies, rules)
    evidence = [item for api in apis for item in api.evidence]
    evidence.extend(item for dep in dependencies for item in dep.evidence)
    if symbols:
        evidence.append(
            Evidence(
                description=f"{len(symbols)} Python symbols inspected",
                repository=repo.name,
                file=None,
                symbol=None,
                commit_sha=sha,
                timestamp=utc_now(),
                confidence="verified",
                evidence_type="scan",
            )
        )
    workflows = [f"{api.method} {api.path}" for api in apis[:12]]
    return DiscoveryReport(
        name=repo.name,
        path=str(root),
        purpose=purpose,
        language=language,
        frameworks=frameworks,
        entry_points=sorted(set(entry_points)),
        modules=modules,
        capabilities=capabilities,
        apis=apis,
        database_notes=db_notes,
        workflows=workflows,
        business_rules=rules,
        tests=tests,
        dependencies=dependencies,
        constraints=constraints,
        risks=risks,
        unknowns=unknowns,
        evidence=evidence,
        commit_sha=sha,
        mode=mode,
        discovered_at=utc_now(),
        files_scanned=len(files),
    )


def _merge_targeted(previous: DiscoveryReport, fresh: DiscoveryReport, scanned_rels: set[str]) -> DiscoveryReport:
    fresh.apis = _merge_apis(previous.apis, fresh.apis, scanned_rels)
    fresh.capabilities = adapters.discover_capabilities(fresh.apis, fresh.name, fresh.commit_sha)
    fresh.dependencies = _merge_dependencies(previous.dependencies, fresh.dependencies, scanned_rels)
    fresh.business_rules = _merge_rules(previous.business_rules, fresh.business_rules, scanned_rels)
    fresh.tests = sorted(set(previous.tests) | set(fresh.tests))
    fresh.modules = _unique_modules(previous.modules + fresh.modules)
    fresh.database_notes = list(dict.fromkeys(previous.database_notes + fresh.database_notes))
    fresh.entry_points = sorted(set(previous.entry_points) | set(fresh.entry_points))
    fresh.workflows = [f"{api.method} {api.path}" for api in fresh.apis[:12]]
    fresh.unknowns = list(dict.fromkeys(
        previous.unknowns
        + fresh.unknowns
        + ["Targeted scan merged into the previous baseline. Files outside the target were not re-read."]
    ))
    fresh.evidence = [item for api in fresh.apis for item in api.evidence]
    fresh.evidence.extend(item for dep in fresh.dependencies for item in dep.evidence)
    return fresh


def _merge_apis(previous: list[ApiEndpoint], fresh: list[ApiEndpoint], scanned: set[str]) -> list[ApiEndpoint]:
    kept = [api for api in previous if _files(api.evidence).isdisjoint(scanned)]
    combined = kept + fresh
    deduped: dict[tuple[str, str], ApiEndpoint] = {}
    for api in combined:
        deduped[(api.method, api.path)] = api
    return list(deduped.values())


def _merge_dependencies(previous: list[Dependency], fresh: list[Dependency], scanned: set[str]) -> list[Dependency]:
    kept = [item for item in previous if _files(item.evidence).isdisjoint(scanned)]
    combined = kept + fresh
    deduped: dict[tuple[str, str, str], Dependency] = {}
    for item in combined:
        deduped[(item.source, item.target, item.type)] = item
    return list(deduped.values())


def _merge_rules(previous: list[str], fresh: list[str], scanned: set[str]) -> list[str]:
    kept = [rule for rule in previous if _rule_file(rule) not in scanned]
    return list(dict.fromkeys(kept + fresh))


def _files(items: list[Evidence]) -> set[str]:
    return {item.file for item in items if item.file}


def _rule_file(rule: str) -> str | None:
    text = rule.split(" at ", 1)[1] if " at " in rule else rule
    path = text.split(":", 1)[0].strip()
    return path or None


def _matches_target(path: Path, root: Path, needle: str) -> bool:
    if needle in path.relative_to(root).as_posix().lower():
        return True
    if path.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".java", ".go", ".cs", ".md", ".yml", ".yaml"}:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:80_000]
    except OSError:
        return False
    return needle in text.lower()


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _unique_modules(modules):
    seen: set[str] = set()
    unique = []
    for module in modules:
        if module.path in seen:
            continue
        seen.add(module.path)
        unique.append(module)
    return unique[:40]


def _purpose(root: Path, name: str, language: str | None, frameworks: list[str], apis) -> tuple[str, list[str]]:
    unknowns: list[str] = []
    readme = root / "README.md"
    if readme.is_file():
        text = redact_text(readme.read_text(encoding="utf-8", errors="replace")).strip().splitlines()
        summary = next((line.strip("# ").strip() for line in text if line.strip()), "")
        if summary:
            stack = " ".join(part for part in [language or "unknown", ", ".join(frameworks)] if part)
            return (f"{name} — {summary}. Detected stack: {stack}.", unknowns)
    if apis:
        return (
            f"{name} exposes {len(apis)} HTTP endpoints and appears to be a {language or 'unknown'} service.",
            ["Business purpose was inferred from API surface; no README title was found."],
        )
    unknowns.append("Repository purpose is unknown; no README or API surface was found.")
    return f"{name} is a registered repository. Purpose is unknown.", unknowns


def _constraints(language: str | None, frameworks: list[str]) -> list[str]:
    constraints = ["Discovery is read-only and does not modify application files."]
    if language:
        constraints.append(f"Primary language appears to be {language}.")
    if frameworks:
        constraints.append(f"Detected frameworks: {', '.join(frameworks)}.")
    return constraints


def _risks(tests: list[str], dependencies, rules: list[str]) -> list[str]:
    risks: list[str] = []
    if not tests:
        risks.append("No tests were detected; regression coverage is unknown.")
    if not dependencies:
        risks.append("No cross-repository dependencies were verified from this scan.")
    if rules:
        risks.append("Business rules were inferred from source text and are not approved policy.")
    return risks
