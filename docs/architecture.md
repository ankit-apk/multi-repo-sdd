# Architecture

## Decision

The framework is a Python 3.12 command-line application. The local environment provides `uv`, Python 3.12, Git, and Node. GitHub Spec Kit's official CLI (`specify`, release **1.2.5**) is also Python, so the Spec Kit adapter is a subprocess around that CLI rather than a fork of Spec Kit.

Node is used only by the sample payment service.

Knowledge is Markdown and YAML under a configurable `knowledge_root`. A database, vector store, or graph database is not required. `FileKnowledgeStore` behaviour is the set of functions in `knowledge.py` (`search_knowledge`, `read_text_if_exists`, `rebuild_system_knowledge`). A later store can replace those functions without changing discovery or the change lifecycle.

## Layers

1. **CLI** — `sdd` commands are the developer and coding-agent interface. They call the Guardian.
2. **Guardian** — retrieval, impact, workflow reconstruction, approvals, implementation dispatch, and verification. System truth is the knowledge files, not the chat transcript.
3. **Repository discovery** — one repository per run, read-only, with adapters for Python, JavaScript/TypeScript, Java, Go, and .NET route attributes. Other stacks are still registered and described from their manifests.
4. **Knowledge layer** — per-repository contract, system index, dependency map, and Mermaid projection (`system/dependency-graph.md`) for a future UI.
5. **SDD execution** — Spec Kit phase names on change files, plus OpenSpec-style folders (`proposals`, `approved`, `in-progress`, `archive`).

## Agent providers

`AgentProvider.submit` and `AgentProvider.cancel` are the only implementation hooks.

| Provider | Behaviour |
|---|---|
| `local-packet` (default) | Writes a YAML packet per repository. Does not modify application code. |
| `command` | Runs `agents.implementation_command` as an argv list, with `shell=False`, after both write flags are set. Specification text is never parsed as a command. |

`agents.provider` records the intended coding environment (for example Cursor). It does not import a vendor SDK.

## Spec Kit and OpenSpec

Spec Kit owns the lifecycle vocabulary:

Constitution → Specify → Clarify → Plan → Checklist → Tasks → Analyze → Implement → Converge.

Those phases are files inside each change directory (`governance/sdd-principles.md`, `spec.md`, `clarifications.md`, `design.md`, `checklist.md`, `tasks/`, `analysis.md`, implementation packets, `convergence.md`). Optional `sdd speckit --init-in <knowledge-subdirectory>` runs `specify init` only inside the knowledge workspace.

OpenSpec contributes the change folder, delta-style review, and archive. Delta text lives in the change spec under existing versus expected behaviour. This repository does not install the OpenSpec CLI into application repositories. See [integrations/openspec.md](../integrations/openspec.md).

## Dependency graph versus workflow

A dependency edge means one repository's code or configuration references another. A workflow is an ordered business sequence that may include repositories without a direct call. `sdd dependencies` prints the graph. `sdd workflow discover` writes a separate document and says when the next hop is unknown.

## Security boundary

- Path checks reject repository names and change ids that could escape the knowledge tree.
- Discovery locks are per repository so two runs cannot replace the same knowledge directory.
- A report is written to a staging directory and swapped into place only after every file is produced.
- Knowledge files start with an untrusted-data banner.

## Unresolved decisions

- Whether a future build should add a vector index behind `search_knowledge`. The file search is the MVP.
- Which external agent binary teams put in `implementation_command`. Cursor is the development environment for this repository; the framework does not call the Cursor SDK.
- When, if ever, to run `specify init` inside an application repository. The default remains no, and only after a human reviews the diff.

## Deferred

- Web dashboard.
- Mandatory vector or graph database.
- Automatic merge and deployment.
- Rewriting application architecture.
- Installing a second SDD product into application repositories.
