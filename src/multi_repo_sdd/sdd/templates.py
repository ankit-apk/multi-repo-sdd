from __future__ import annotations

from multi_repo_sdd.workflows import slugify


def constitution_markdown(workspace_name: str) -> str:
    return f"""# Constitution — {workspace_name}

This constitution governs multi-repository Spec-Driven Development.

1. Understand the existing system before changing it.
2. Define the intended change before implementing it.
3. Validate the implementation against the specification before considering work complete.
4. Preserve existing architecture unless an ADR records a change.
5. Baseline discovery knowledge is not an approved business specification.
6. Distinguish current behaviour, expected behaviour, and proposed behaviour.
7. Require human approval before implementation, material schema changes, and architecture changes.
8. Discovery remains read-only with respect to application repositories.
9. Never invent missing business rules. Label inferred facts.
10. Keep evidence, commit SHAs, and unknowns in knowledge artifacts.
11. Spec Kit owns the SDD lifecycle artifacts. OpenSpec-style folders in this workspace own change proposals and archives.
12. Do not install a second competing SDD workflow into application repositories by default.
"""


def proposal_markdown(change_id: str, description: str, impact_table: str) -> str:
    return f"""# Change proposal — {change_id}

## Business context

{description}

## Problem statement

The requested behaviour is not currently specified as an approved cross-repository capability.

## Scope

In scope: repositories listed in the impact analysis with Modify or Evaluate actions.

## Functional requirements

- FR-1: The system supports the requested capability described as `{description}`.
- FR-2: Existing happy-path behaviour remains available unless the specification explicitly replaces it.
- FR-3: Failures return a documented error and do not corrupt upstream records.

## Non-functional requirements

- NFR-1: Changes remain backward compatible unless a migration is approved.
- NFR-2: Secrets are never written into knowledge files or specifications.

## Acceptance criteria

- AC-1: Each impacted repository has tasks with test requirements.
- AC-2: Human approval is recorded for the specification before implementation.
- AC-3: Verification reports pass or record an explicit exception.

## Existing behaviour

See discovery knowledge. Existing implementation may contain defects; it is not automatically the desired specification.

## Expected new behaviour

{description}

## Backward compatibility

Preserve public APIs unless the design records a breaking change.

## Out of scope

- Automatic production deployment.
- Unrelated refactors.
- Rewriting architecture without an ADR.

## Open questions

- What is the source of truth for the new capability?
- Which repository owns the API contract?
- What is the compensation path on partial failure?

## Impact

{impact_table}

This proposal uses OpenSpec-inspired change folders (proposal, design, tasks, archive) while Spec Kit remains the primary SDD lifecycle.
"""


def spec_markdown(change_id: str, description: str, repos: list[str], evidence: str = "") -> str:
    sections = [
        f"# Feature specification — {change_id}",
        "",
        "Spec Kit phase: specify.",
        "",
        f"## User story",
        "",
        f"As a developer, I want `{description}` so that the business capability is available across repositories.",
        "",
        "## Requirements",
        "",
        f"1. The change `{change_id}` is identified once and shared across repositories.",
        "2. Each impacted repository has an implementation section and tests.",
        "3. Discovery evidence is cited rather than assumed.",
        "",
        "## Repository-specific sections",
        "",
    ]
    for repo in repos:
        sections.extend(
            [
                f"### {repo}",
                "",
                f"- Owner: `{repo}`",
                "- Existing behaviour: see `sdd-workspace/repositories/" + repo + "/`",
                "- Expected behaviour: implement only the approved tasks for this change.",
                "",
            ]
        )
    if not repos:
        sections.append("Unknown: impact analysis did not identify repositories.")
    sections.extend(
        [
            "## Existing behaviour",
            "",
            "Baseline discovery is not an approved specification. Quoted lines are evidence, labeled by the discovery agent.",
            "",
            evidence or "Unknown: no discovery excerpts matched this change. Do not invent the current behaviour.",
            "",
            "## Expected new behaviour",
            "",
            description,
            "",
            "Where cited evidence conflicts with the request, the approved specification replaces only that cited behaviour.",
            "",
        ]
    )
    sections.extend(
        [
            "## Spec Kit mapping",
            "",
            "- Constitution: `governance/sdd-principles.md`",
            "- Specify: this file",
            "- Clarify: `clarifications.md`",
            "- Plan: `design.md`",
            "- Checklist: `checklist.md`",
            "- Tasks: `tasks/`",
            "- Analyze: `analysis.md`",
            "- Implement: gated by approvals",
            "- Converge: `convergence.md`",
        ]
    )
    return "\n".join(sections)


def design_markdown(change_id: str, description: str, repos: list[str], evidence: str = "") -> str:
    lines = [
        f"# Technical design — {change_id}",
        "",
        "Spec Kit phase: plan.",
        "",
        "## High-level design",
        "",
        description,
        "",
        "## Reuse existing architecture",
        "",
        "Reuse current service boundaries unless an ADR is recorded under `decisions/architecture-decisions/`.",
        "",
        evidence or "Unknown: no architecture excerpts were attached.",
        "",
        "## Repository-level design",
        "",
    ]
    for repo in repos:
        lines.extend(
            [
                f"### {repo}",
                "",
                "- API changes: document request/response deltas.",
                "- Database changes: none unless explicitly required.",
                "- Events: document new or modified messages.",
                "- Security: do not log secrets; preserve authz checks.",
                "- Failure handling: define timeouts and compensation.",
                "",
            ]
        )
    lines.extend(
        [
            "## Migration and rollout",
            "",
            "Roll out producer compatibility first, then consumers.",
            "",
            "## Test strategy",
            "",
            "Unit tests in each repository, contract tests for APIs, and a cross-repository verification report.",
        ]
    )
    return "\n".join(lines)


def checklist_markdown(change_id: str) -> str:
    return f"""# Requirements checklist — {change_id}

Spec Kit phase: checklist.

- [ ] Functional requirements are testable
- [ ] Backward compatibility is explicit
- [ ] Impacted repositories are listed
- [ ] Open questions are assigned or accepted as residual risk
- [ ] Human reviewer approved the specification
"""


def clarifications_markdown() -> str:
    return """# Clarifications

Spec Kit phase: clarify.

Record unresolved questions here. The Guardian must not approve its own unverified assumptions.

- [ ] Source of truth for the new capability
- [ ] API owner
- [ ] Failure compensation
"""


def analysis_markdown(change_id: str) -> str:
    return f"""# Cross-artifact analysis — {change_id}

Spec Kit phase: analyze.

- Specification, design, and tasks must name the same repositories.
- Tasks must cite acceptance criteria.
- Implementation must not start while required approvals are missing.
"""


def tasks_markdown(change_id: str, repo: str, index: int, depends_on: list[str]) -> str:
    task_id = f"{change_id}-{index:02d}-{slugify(repo)}"
    deps = ", ".join(depends_on) if depends_on else "none"
    return f"""# Tasks — {repo}

- Task ID: `{task_id}`
- Repository owner: `{repo}`
- Dependencies: {deps}
- Specification: `../spec.md`
- Design: `../design.md`

## Work

- [ ] T{index}-1 Read the approved specification and repository knowledge
- [ ] T{index}-2 Inspect current source in `{repo}`
- [ ] T{index}-3 Implement only the assigned scope
- [ ] T{index}-4 Add or update tests
- [ ] T{index}-5 Report deviations, modified files, and verification results

## Acceptance criteria

- Behaviour matches the approved specification for `{repo}`
- Existing behaviour is covered by tests or an explicit exception
- No unrelated refactors
"""


def integration_tasks_markdown(change_id: str, repos: list[str]) -> str:
    return f"""# Tasks — integration tests

- Task ID: `{change_id}-99-integration`
- Repository owner: workspace
- Dependencies: {', '.join(repos) if repos else 'none'}

## Work

- [ ] Cross-repository contract tests
- [ ] Regression tests for existing workflows
- [ ] Convergence report
"""
