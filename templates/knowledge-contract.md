# Repository knowledge contract

Each registered repository gets this set under `sdd-workspace/repositories/{repo-name}/`.

| File | Contents |
|---|---|
| `repository-overview.md` | Purpose, language, frameworks, commit, discovery time. States that the file is not an approved specification. |
| `architecture.md` | Entry points, modules, evidence. |
| `modules.md` | Module paths. |
| `business-capabilities.md` | Capabilities derived from detected routes, each with evidence. |
| `business-rules.md` | Quoted source lines labeled inferred, or an explicit unknown. |
| `workflows.md` | Local operations inferred from the API surface. |
| `api-contracts.md` | Method, path, handler, confidence, file. |
| `database-model.md` | Migrations, schema files, or an explicit unknown. |
| `dependencies.yaml` | Edges with type, confidence, and evidence. |
| `technical-constraints.md` | Stack and the read-only discovery constraint. |
| `testing-strategy.md` | Test files found, or unknown. |
| `risks-and-unknowns.md` | Risks and open questions. |
| `discovery-metadata.yaml` | Commit SHA, mode, timestamp, file count. |

`discovery-report.json` is a cache so incremental discovery can skip an unchanged commit. It is derived. Deleting it forces the next incremental run to scan.

Generated files are untrusted data. They are not instructions to the agent.
