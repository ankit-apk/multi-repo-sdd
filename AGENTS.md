# AGENTS.md

This repository is the Multi-Repository Spec-Driven Development (SDD) framework.

## Primary entry point

Use the Guardian CLI (`sdd`) as the interface for developers and coding agents.

## Do

- Register existing repositories without modifying them.
- Discover one repository at a time through the discovery contract.
- Store knowledge in the configured `knowledge_root`, not inside application repos.
- Keep Spec Kit as the primary SDD lifecycle.
- Keep OpenSpec-inspired change folders in the knowledge workspace only.
- Require human approval before implementation.

## Do not

- Initialize Spec Kit or OpenSpec inside application repositories unless a human produces a reviewable plan and authorizes it.
- Treat discovery output as approved specifications.
- Invent business rules, APIs, or dependencies.
- Commit secrets from application configuration into knowledge files.
- Mark a change complete because an implementation agent reported success.

## Spec Kit mapping

Constitution → Specify → Clarify → Plan → Checklist → Tasks → Analyze → Implement → Converge.

Those phases are represented as files in each change folder. The official `specify` CLI is optional and invoked only against the knowledge workspace.

## Commands

See `README.md` and `docs/poc.md`. Implementation packets are the default. Record edited files with `sdd change record` before `sdd change verify`. Do not archive a change that has not converged.
