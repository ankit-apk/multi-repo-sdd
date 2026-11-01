# Spec Kit integration

Primary SDD lifecycle: [GitHub Spec Kit](https://github.com/github/spec-kit) 1.2.5.

Documentation: https://github.github.com/spec-kit/

## Pinned install

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v1.2.5
specify version
```

`sdd.framework_version` in `sdd.config.yaml` records the pin. To upgrade:

1. Read the Spec Kit release notes and upgrade guide.
2. Install the new tag with `uv tool install --force`.
3. Change `framework_version`.
4. Re-run `specify init --here --force` only inside a knowledge subdirectory, then review the diff.
5. Do not vendor Spec Kit's source into this repository.

## What we call, and what we do not

`SpecKitAdapter` in `src/multi_repo_sdd/sdd/speckit.py` runs:

```bash
specify version
specify init --here --force --integration <key> --ignore-agent-tools
```

`sdd speckit` refuses to point that init at an application repository. `sdd.auto_init_speckit_in_app_repos` cannot be turned on; the adapter rejects that setting.

The non-interactive default integration key is `copilot`, matching Spec Kit's own fallback. Set `sdd.integration` to the key your agent documents (`claude`, `gemini`, or another key from `specify init --help`). This framework's packet provider is separate from that integration key.

## Phase map

| Spec Kit phase | Change file |
|---|---|
| constitution | `governance/sdd-principles.md` |
| specify | `changes/.../spec.md` |
| clarify | `clarifications.md` |
| plan | `design.md` |
| checklist | `checklist.md` |
| tasks | `tasks/*.md` |
| analyze | `analysis.md` |
| implement | packets plus repository edits after approval |
| converge | `convergence.md` |

The Guardian can run this map without `specify init`. Init is how a team also gets Spec Kit's native slash commands in the knowledge workspace.
