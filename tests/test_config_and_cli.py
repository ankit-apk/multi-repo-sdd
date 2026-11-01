from pathlib import Path

import pytest
from typer.testing import CliRunner

from multi_repo_sdd.cli import app
from multi_repo_sdd.config import load_config, save_config, default_config
from multi_repo_sdd.context import init_workspace, load_app
from multi_repo_sdd.registry import register_repository

runner = CliRunner()


def test_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sdd.config.yaml"
    config = default_config()
    config.workspace.name = "demo"
    save_config(config, path)
    loaded = load_config(path)
    assert loaded.workspace.name == "demo"
    assert loaded.discovery.read_only is True


def test_cli_init_register_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "project"
    ws.mkdir()
    repo = tmp_path / "svc"
    repo.mkdir()
    (repo / "README.md").write_text("# svc\n")
    monkeypatch.chdir(ws)
    result = runner.invoke(app, ["init", "--path", str(ws), "--name", "demo"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["repo", "add", str(repo)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["repo", "list"])
    assert "svc" in result.output
