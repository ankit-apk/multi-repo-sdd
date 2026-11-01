# multi-repo-sdd

Spec-driven development for brownfield systems that span more than one repository.

The framework discovers what each repository actually does, keeps that knowledge in versioned Markdown and YAML, and runs a Guardian in front of the GitHub Spec Kit lifecycle. Discovery is read-only. Implementation does not start until a person approves the specification and the design.

## What owns which artifact

| Artifact | Owner | Where it lives |
|---|---|---|
| Baseline discovery (what the code appears to do) | Repository discovery | `sdd-workspace/repositories/` |
| System summary, dependency map, workflows | Guardian | `sdd-workspace/system/` and `workflows/` |
| Change proposal, specification, design, tasks, archive | This framework, using OpenSpec-style change folders | `sdd-workspace/changes/` |
| Living specification after a verified archive | This framework | `sdd-workspace/specifications/` |
| Spec Kit templates and agent commands | Official `specify` CLI, optional | Knowledge workspace only, never application repos by default |
| Application source | Application repositories | Registered paths |

Baseline discovery is not an approved business specification. Existing code can contain defects, legacy behaviour, and undocumented workarounds.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd multi-repo-sdd
uv sync
uv run sdd --version
```

Spec Kit is optional and pinned to **1.2.5**. Install it only when you want the official templates in the knowledge workspace:

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v1.2.5
specify version
```

Upgrade by reading the [Spec Kit upgrade guide](https://github.github.com/spec-kit/), installing the new pinned tag, then changing `sdd.framework_version` in `sdd.config.yaml`. Do not copy Spec Kit source into this repository. See [integrations/spec-kit.md](integrations/spec-kit.md).

## Initialize a workspace

Paths are configuration. Repository names are not hardcoded.

```bash
# From the directory that should hold sdd.config.yaml
uv run sdd init \
  --path . \
  --name enterprise-platform \
  --knowledge-root ../sdd-workspace \
  --repositories-root ../repositories

uv run sdd repo add ../repositories/order-service
uv run sdd repo add ../repositories/payment-service
uv run sdd repo list
```

`repo add` records the path. It does not modify the repository.

Repositories may sit under one parent or anywhere on disk. Registration is what authorizes discovery to read that path.

## Discover and ask

```bash
uv run sdd discover --all
uv run sdd discover --repo payment-service
uv run sdd discover --repo payment-service --mode targeted --target refunds
uv run sdd refresh --all
uv run sdd system overview
uv run sdd repo show payment-service
uv run sdd dependencies
uv run sdd dependencies --transitive-from order-service
uv run sdd capabilities
uv run sdd search refund
uv run sdd evidence refund
uv run sdd freshness
uv run sdd workflow discover "Customer order creation"
```

Discovery modes:

- `initial` scans the repository and rewrites its knowledge files.
- `incremental` reuses the last report when the git work tree still matches that commit. A dirty or changed repository is scanned again.
- `targeted` reads files whose path or contents match `--target` and merges them into the previous baseline.

Important claims include a file path, symbol when one is known, commit SHA, timestamp, and a confidence of `verified`, `inferred`, or `unknown`.

## Start a change

```bash
uv run sdd impact "Introduce partial refund support"
uv run sdd change propose "Introduce partial refund support"
uv run sdd change validate introduce-partial-refund-support
uv run sdd change approve introduce-partial-refund-support --artifact specification --reviewer "your-name"
uv run sdd change approve introduce-partial-refund-support --artifact design --reviewer "your-name"
uv run sdd change implement introduce-partial-refund-support
```

`implement` writes one packet per repository and does **not** edit application code. Packets list the specification, design, and tasks. Dependent repositories are ordered after the repositories they call. A batch with more than one repository is marked parallel-eligible; the default runner still executes a batch sequentially so logs stay ordered.

To let an external command edit repositories, set both of these and pass `--authorize-writes`:

```yaml
agents:
  implementation_provider: command
  implementation_command: ["your-agent", "run-packet"]
governance:
  authorize_repository_writes: true
```

The command is an argv list from configuration. The framework does not turn specification text into a shell command. The process receives `SDD_PACKET_JSON` and the spec, design, and task paths.

After the coding agent edits the repositories, check the task boxes in the change folder, then:

```bash
uv run sdd change record introduce-partial-refund-support --repo payment-service --file src/server.js
uv run sdd change verify introduce-partial-refund-support
uv run sdd change archive introduce-partial-refund-support
```

Verification fails while checklist items are open, while tests fail, or while no git diff or recorded files show that the repository changed. A coding agent's claim of success is not convergence. Archive copies the approved spec into `specifications/` and refreshes discovery so the baseline knowledge matches the new code. The living spec and the discovery baseline stay separate.

## Proof of concept

The sample order and payment services live in `../examples`. Walk through them with [docs/poc.md](docs/poc.md).

## Layout

```text
multi-repo-sdd/
├── src/multi_repo_sdd/    # CLI, discovery, guardian, change lifecycle
├── tests/
├── templates/
├── schemas/
├── integrations/          # How Spec Kit and OpenSpec are used
├── prompts/
├── config/sdd.config.example.yaml
└── docs/
```

Generated knowledge follows the tree in the architecture doc. `knowledge_root` chooses where it is written.

## Safety

- Discovery refuses to run unless `discovery.read_only` is true.
- Writes stay inside the knowledge workspace unless implementation is explicitly authorized.
- Repository names and change ids must be single path segments.
- Symlinks that point outside a repository are not read.
- Generated knowledge redacts common credential assignments and is marked as untrusted data, not instructions.
- Agent output cannot change these rules.

## Limitations

- Static analysis misses dynamic dispatch, service meshes, and relationships that exist only in documentation.
- Incremental discovery needs git. Without a commit SHA, every refresh scans the repository.
- The default implementation provider prepares packets. It does not embed a model.
- Archive records a pointer on overlapping workflow documents. It does not invent a new business sequence.
- Spec Kit's own slash commands still run inside the coding agent after `specify init`. This CLI maps the same phases onto change files so the lifecycle works without that init.

## Tests

```bash
uv run pytest
```
