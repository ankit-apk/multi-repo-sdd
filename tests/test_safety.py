from pathlib import Path

import pytest

from multi_repo_sdd.errors import PathSafetyError
from multi_repo_sdd.safety import assert_within, redact_text, sanitize_mapping


def test_assert_within_rejects_traversal(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outsider = tmp_path / "secret"
    outsider.mkdir()
    with pytest.raises(PathSafetyError):
        assert_within(outsider / "file.txt", allowed)


def test_redacts_secrets() -> None:
    text = "API_KEY=abcd1234 TOKEN=xyz"
    result = redact_text(text)
    assert "abcd1234" not in result
    assert "[REDACTED]" in result


def test_sanitize_mapping_redacts_password_keys() -> None:
    clean = sanitize_mapping({"database_password": "super-secret", "host": "localhost"})
    assert clean["database_password"] == "[REDACTED]"
    assert clean["host"] == "localhost"
