"""Tests for local env-file loading (no dependency, real environment wins)."""

from __future__ import annotations

from src.lifesci.envfile import load_env_file, parse_env


def test_parse_supports_comments_quotes_and_export():
    parsed = parse_env(
        "\ufeff# leading comment\n"
        "\n"
        "PLAIN=value\n"
        "export EXPORTED=from-export\n"
        "SINGLE='keep $HOME and # hash'\n"
        'DOUBLE="line\\nbreak and \\"quote\\""\n'
        "EMPTY=\n"
        "WITH_COMMENT=kept#not-a-comment  # trailing comment\n"
        "INVALID KEY=ignored\n"
        "NO_EQUALS\n"
        "  SPACED  =  trimmed  \n"
    )
    assert parsed["PLAIN"] == "value"
    assert parsed["EXPORTED"] == "from-export"
    assert parsed["SINGLE"] == "keep $HOME and # hash"
    assert parsed["DOUBLE"] == 'line\nbreak and "quote"'
    assert parsed["EMPTY"] == ""
    assert parsed["WITH_COMMENT"] == "kept#not-a-comment"
    assert parsed["SPACED"] == "trimmed"
    assert "INVALID KEY" not in parsed and "NO_EQUALS" not in parsed


def test_load_does_not_override_the_real_environment(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("LIFESCI_DATABASE_URL=sqlite:///from-file\nNEW_SETTING=file\n")
    environ = {"LIFESCI_DATABASE_URL": "sqlite:///from-environment"}
    applied = load_env_file(env_file, environ)
    assert environ["LIFESCI_DATABASE_URL"] == "sqlite:///from-environment"
    assert environ["NEW_SETTING"] == "file"
    assert applied == ["NEW_SETTING"]


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "missing") == []


def test_override_is_opt_in(tmp_path):
    env_file = tmp_path / "values"
    env_file.write_text("A=file\n")
    environ = {"A": "environment"}
    assert load_env_file(env_file, environ, override=True) == ["A"]
    assert environ["A"] == "file"
