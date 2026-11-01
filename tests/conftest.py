from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from multi_repo_sdd.context import init_workspace, load_app
from multi_repo_sdd.registry import register_repository

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "ws"
    order_src = EXAMPLES / "order-service"
    payment_src = EXAMPLES / "payment-service"
    order = root / "repos" / "order-service"
    payment = root / "repos" / "payment-service"
    shutil.copytree(order_src, order)
    shutil.copytree(payment_src, payment)
    init_workspace(root, knowledge_root="./sdd-workspace", name="poc")
    monkeypatch.chdir(root)
    ctx = load_app(root)
    register_repository(ctx.layout, order)
    register_repository(ctx.layout, payment)
    return load_app(root)
