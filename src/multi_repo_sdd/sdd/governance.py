from __future__ import annotations

import yaml

from multi_repo_sdd.config import SddConfig
from multi_repo_sdd.errors import ApprovalRequired, GovernanceError
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.sdd.changes import find_change, move_change, validate_change
from multi_repo_sdd.safety import AuditLog, utc_now


def approve_change(layout: WorkspaceLayout, change_id: str, artifact: str, reviewer: str) -> dict:
    if artifact not in {"specification", "design", "implementation"}:
        raise GovernanceError("artifact must be specification, design, or implementation")
    stage, path = find_change(layout, change_id)
    status = yaml.safe_load((path / "status.yaml").read_text(encoding="utf-8"))
    approvals = status.setdefault("approvals", {})
    approvals[artifact] = True
    history = status.setdefault("approval_history", [])
    history.append({"artifact": artifact, "reviewer": reviewer, "at": utc_now()})
    (path / "status.yaml").write_text(yaml.safe_dump(status, sort_keys=False), encoding="utf-8")
    AuditLog(layout.audit_log()).record("approve", change=change_id, artifact=artifact, reviewer=reviewer)
    if artifact == "specification" and stage == "proposals":
        move_change(layout, change_id, "approved")
    return status


def require_approvals(layout: WorkspaceLayout, config: SddConfig, change_id: str, for_implementation: bool = False) -> dict:
    if not config.governance.require_human_approval:
        _, path = find_change(layout, change_id)
        return yaml.safe_load((path / "status.yaml").read_text(encoding="utf-8"))
    validation = validate_change(layout, change_id)
    if not validation["ok"]:
        raise GovernanceError("Change is not valid: " + "; ".join(validation["issues"]))
    _, path = find_change(layout, change_id)
    status = yaml.safe_load((path / "status.yaml").read_text(encoding="utf-8"))
    approvals = status.get("approvals") or {}
    if config.sdd.require_spec_approval and not approvals.get("specification"):
        raise ApprovalRequired("Human approval of the specification is required before implementation")
    if for_implementation and config.sdd.require_design_approval and not approvals.get("design"):
        raise ApprovalRequired("Human approval of the technical design is required before implementation")
    return status
