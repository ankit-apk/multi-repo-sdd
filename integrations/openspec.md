# OpenSpec concepts used here

[OpenSpec](https://github.com/Fission-AI/OpenSpec) is not installed beside Spec Kit. Two SDD products in one application repository would create two sources of truth. Spec Kit remains the lifecycle. OpenSpec contributes the change-management shape:

| OpenSpec idea | How this framework uses it |
|---|---|
| Change proposal | `changes/proposals/<id>/proposal.md` |
| Delta spec | `spec.md` quotes discovery evidence as current behaviour and states the requested behaviour separately |
| Design | `design.md` |
| Task checklist | `tasks/<repository>.md` |
| Archive | `changes/archive/<id>/` after convergence |
| Spec sync | `specifications/<id>/` is the living copy written at archive time |

We do not run `openspec archive` or the `/opsx:*` commands. Archive here additionally requires a converged verification report and checked tasks, which is stricter than OpenSpec's warning-only incomplete-task behaviour.

Delta sections are not a free-form rewrite of `openspec/specs`. The living specification is the archived change spec. Discovery files stay a description of the code, including defects.
