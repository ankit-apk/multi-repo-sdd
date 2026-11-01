from __future__ import annotations


def execution_batches(
    repositories: list[str], prerequisites: dict[str, list[str]]
) -> tuple[list[list[str]], list[str]]:
    """Return dependency-ordered batches and any repositories left in a cycle."""
    remaining = {repo: set(prerequisites.get(repo, [])) & set(repositories) for repo in repositories}
    batches: list[list[str]] = []
    placed: set[str] = set()
    while len(placed) < len(repositories):
        ready = [repo for repo in repositories if repo not in placed and remaining[repo] <= placed]
        if not ready:
            leftover = [repo for repo in repositories if repo not in placed]
            return batches, leftover
        batches.append(ready)
        placed.update(ready)
    return batches, []
