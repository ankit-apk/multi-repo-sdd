from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from multi_repo_sdd.config import SddConfig
from multi_repo_sdd.errors import GovernanceError
from multi_repo_sdd.gitutil import changed_files_since, working_tree_dirty
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.registry import load_registry
from multi_repo_sdd.sdd.changes import find_change, unchecked_tasks
from multi_repo_sdd.safety import utc_now


def verify_change(layout: WorkspaceLayout, config: SddConfig, change_id: str) -> dict:
    _, path = find_change(layout, change_id)
    status = yaml.safe_load((path / "status.yaml").read_text(encoding="utf-8"))
    registry = load_registry(layout)
    test_results: list[dict] = []
    gaps: list[str] = []
    spec = (path / "spec.md").read_text(encoding="utf-8")
    open_items = unchecked_tasks(path)
    if open_items:
        gaps.append(f"{len(open_items)} task checklist items are still open")
    recorded = status.get("recorded_files") or {}
    for repo_name in status.get("repositories") or []:
        repo = registry.get(repo_name)
        root = Path(repo.path)
        if repo_name not in spec:
            gaps.append(f"{repo_name} is missing from the specification")
        changed, detail = _source_changed(root, repo.last_discovered_sha, list(recorded.get(repo_name) or []))
        if not changed:
            gaps.append(f"No implementation changes detected in {repo_name} ({detail})")
        result = _run_repo_tests(root)
        result["repository_name"] = repo_name
        result["source_change"] = detail
        test_results.append(result)
        if result["status"] == "failed":
            gaps.append(f"Tests failed in {repo_name}")
        elif result["status"] == "unknown" and config.governance.require_regression_tests:
            gaps.append(f"No executable test command was found in {repo_name}")
    passed = not gaps
    if not passed and config.governance.require_convergence:
        extra = path / "tasks" / "convergence-followups.md"
        extra.write_text(
            "# Convergence follow-ups\n\n"
            + "\n".join(f"- [ ] {gap}" for gap in gaps)
            + "\n",
            encoding="utf-8",
        )
    report = {
        "change": change_id,
        "passed": passed,
        "gaps": gaps,
        "tests": test_results,
        "verified_at": utc_now(),
    }
    (path / "convergence.md").write_text(_convergence_markdown(report), encoding="utf-8")
    status["verification"] = report
    (path / "status.yaml").write_text(yaml.safe_dump(status, sort_keys=False), encoding="utf-8")
    if not passed:
        raise GovernanceError("Convergence incomplete: " + "; ".join(gaps))
    return report


def _source_changed(root: Path, since_sha: str | None, recorded: list[str]) -> tuple[bool, str]:
    if recorded:
        return True, "recorded files: " + ", ".join(recorded)
    if since_sha:
        changes = changed_files_since(root, since_sha)
        if changes:
            return True, "git diff: " + ", ".join(changes[:20])
        if changes == []:
            return False, "work tree matches the discovery commit"
    dirty = working_tree_dirty(root)
    if dirty:
        return True, "working tree has uncommitted changes and no discovery commit to compare"
    if since_sha is None:
        return False, "repository has no discovery commit and no recorded files"
    return False, "no source changes detected"


def _run_repo_tests(root: Path) -> dict:
    command = _test_command(root)
    if command is None:
        return {"repository": str(root), "status": "unknown", "detail": "No test runner detected"}
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"repository": str(root), "status": "unknown", "detail": str(exc), "command": command}
    status = "passed" if completed.returncode == 0 else "failed"
    return {
        "repository": str(root),
        "status": status,
        "command": command,
        "exit_code": completed.returncode,
        "output": (completed.stdout + completed.stderr)[-4000:],
    }


def _test_command(root: Path) -> list[str] | None:
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        scripts = data.get("scripts") if isinstance(data, dict) else None
        if isinstance(scripts, dict) and scripts.get("test"):
            return ["npm", "test"]
    if (root / "go.mod").is_file():
        return ["go", "test", "./..."]
    if (root / "pom.xml").is_file():
        return ["mvn", "-q", "test"]
    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file() or (root / "tests").is_dir():
        return [sys.executable, "-m", "pytest", "-q", f"--rootdir={root}"]
    return None


def _convergence_markdown(report: dict) -> str:
    lines = [
        f"# Convergence — {report['change']}",
        "",
        f"- Verified: {report['verified_at']}",
        f"- Status: {'converged' if report['passed'] else 'gaps-remain'}",
        "",
        "## Gaps",
        "",
    ]
    if report["gaps"]:
        lines.extend(f"- {gap}" for gap in report["gaps"])
    else:
        lines.append("- None. Specification, tasks, and tests are aligned for this change.")
    lines.extend(["", "## Tests", ""])
    for item in report["tests"]:
        lines.append(f"- `{item.get('repository')}`: {item.get('status')}")
    lines.extend(
        [
            "",
            "A coding agent report of success is not sufficient. This file is the Guardian convergence record.",
        ]
    )
    return "\n".join(lines) + "\n"
