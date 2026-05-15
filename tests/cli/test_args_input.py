from __future__ import annotations

import io
from pathlib import Path

import pytest

from gumloop import GumloopError
from gumloop.cli.commands._args_input import resolve_json_args


def test_returns_empty_dict_when_no_input_provided() -> None:
    assert resolve_json_args(inline=None, file_path=None, stdin_marker=None) == {}


def test_parses_inline_json_string() -> None:
    assert resolve_json_args(inline='{"a": 1}', file_path=None, stdin_marker=None) == {"a": 1}


def test_reads_args_from_file(tmp_path: Path) -> None:
    path = tmp_path / "args.json"
    path.write_text('{"hello": "world"}')

    assert resolve_json_args(inline=None, file_path=str(path), stdin_marker=None) == {"hello": "world"}


def test_reads_args_from_stdin_when_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO('{"piped": true}'))

    assert resolve_json_args(inline=None, file_path=None, stdin_marker="-") == {"piped": True}


def test_rejects_combining_multiple_input_modes(tmp_path: Path) -> None:
    args_file = tmp_path / "a.json"
    args_file.write_text("{}")

    with pytest.raises(GumloopError, match="at most one"):
        resolve_json_args(inline="{}", file_path=str(args_file), stdin_marker=None)


def test_rejects_non_dash_stdin_marker() -> None:
    with pytest.raises(GumloopError, match="only accepts '-'"):
        resolve_json_args(inline=None, file_path=None, stdin_marker="foo")


def test_rejects_non_object_json() -> None:
    with pytest.raises(GumloopError, match="object at the top level"):
        resolve_json_args(inline="[1, 2, 3]", file_path=None, stdin_marker=None)


def test_rejects_invalid_json() -> None:
    with pytest.raises(GumloopError, match="parse JSON"):
        resolve_json_args(inline="{not json", file_path=None, stdin_marker=None)
