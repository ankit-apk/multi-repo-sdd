# Templates

Change documents are assembled in `src/multi_repo_sdd/sdd/templates.py` so repository sections, evidence excerpts, and task ids stay consistent. The files in this directory are the human-readable contracts those generators follow.

- `knowledge-contract.md` — discovery output for one repository.
- `constitution.md` — principles copied into `governance/sdd-principles.md` when a change is proposed. The generator keeps the same rules in code so a missing template file cannot drop a safety principle.
