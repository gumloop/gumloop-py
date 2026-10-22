from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import BinaryIO

import pytest

from gumloop.cli.commands import _downloads


class _WindowsLinkError(OSError):
    winerror: int


def _outputs(directory: Path) -> list[Path]:
    return [path for path in directory.iterdir() if path.name != "home"]


@pytest.mark.parametrize("umask", [0o477, 0o277, 0o777])
def test_fallback_preserves_restrictive_umask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, umask: int) -> None:
    def unsupported_link(source: Path, destination: Path) -> None:
        raise OSError(errno.EOPNOTSUPP, "hard links unavailable")

    monkeypatch.setattr(_downloads.os, "link", unsupported_link)
    target = tmp_path / "download.bin"
    error = None
    previous = os.umask(umask)
    try:
        _downloads.write_download_bytes(b"complete download", target)
    except OSError as failure:
        error = failure
    finally:
        os.umask(previous)
    assert error is None
    assert stat.S_IMODE(target.stat().st_mode) == 0o666 & ~umask
    target.chmod(0o600)
    assert target.read_bytes() == b"complete download"
    assert _outputs(tmp_path) == [target]


@pytest.mark.parametrize("winerror", [1, 50])
def test_download_supports_windows_unsupported_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winerror: int
) -> None:
    def unsupported_link(source: Path, destination: Path) -> None:
        failure = _WindowsLinkError(errno.EINVAL, "Windows hard links unavailable")
        failure.winerror = winerror
        raise failure

    monkeypatch.setattr(_downloads.os, "link", unsupported_link)
    target = tmp_path / "download.bin"
    error = None
    try:
        _downloads.write_download_bytes(b"download", target)
    except OSError as failure:
        error = failure
    assert error is None
    assert target.read_bytes() == b"download"


@pytest.mark.parametrize("link_errno", [errno.EINVAL, errno.EIO, errno.EACCES])
def test_download_preserves_other_link_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_errno: int) -> None:
    def failed_link(source: Path, destination: Path) -> None:
        raise OSError(link_errno, "not an unsupported-link failure")

    monkeypatch.setattr(_downloads.os, "link", failed_link)
    target = tmp_path / "download.bin"
    with pytest.raises(OSError) as failure:
        _downloads.write_download_bytes(b"download", target)
    assert failure.value.errno == link_errno
    assert _outputs(tmp_path) == []


@pytest.mark.parametrize("link_errno", [errno.EPERM, errno.EOPNOTSUPP])
def test_download_supports_volumes_without_hard_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_errno: int
) -> None:
    def unsupported_link(source: Path, destination: Path) -> None:
        raise OSError(link_errno, "hard links unavailable")

    monkeypatch.setattr(_downloads.os, "link", unsupported_link)
    target = tmp_path / "download.bin"
    error = None
    try:
        _downloads.write_download_bytes(b"complete download", target)
    except OSError as failure:
        error = failure
    assert error is None
    assert target.read_bytes() == b"complete download"
    assert _outputs(tmp_path) == [target]


@pytest.mark.parametrize("mode", [0o644, 0o755])
def test_forced_download_preserves_regular_permissions(tmp_path: Path, mode: int) -> None:
    target = tmp_path / "download.bin"
    target.write_bytes(b"original")
    target.chmod(mode | stat.S_ISUID | stat.S_ISGID)
    _downloads.write_download_bytes(b"replacement", target, force=True)
    assert stat.S_IMODE(target.stat().st_mode) == mode
    assert target.read_bytes() == b"replacement"


@pytest.mark.parametrize("force", [False, True])
def test_new_download_obeys_process_umask(tmp_path: Path, force: bool) -> None:
    target = tmp_path / "download.bin"
    previous = os.umask(0o027)
    try:
        _downloads.write_download_bytes(b"download", target, force=force)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.parametrize("force", [False, True])
def test_download_accepts_valid_maximum_basename(tmp_path: Path, force: bool) -> None:
    target = tmp_path / ("x" * os.pathconf(tmp_path, "PC_NAME_MAX"))
    error = None
    try:
        _downloads.write_download_bytes(b"download", target, force=force)
    except OSError as failure:
        error = failure
    assert error is None
    assert target.read_bytes() == b"download"
    assert _outputs(tmp_path) == [target]


def test_fallback_refuses_a_racing_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "download.bin"

    def racing_link(source: Path, destination: Path) -> None:
        destination.write_bytes(b"racing writer")
        raise OSError(errno.EOPNOTSUPP, "hard links unavailable")

    monkeypatch.setattr(_downloads.os, "link", racing_link)
    with pytest.raises(FileExistsError):
        _downloads.write_download_bytes(b"download", target)
    assert target.read_bytes() == b"racing writer"
    assert _outputs(tmp_path) == [target]


@pytest.mark.parametrize("replace_during_failure", [False, True])
def test_failed_fallback_only_removes_its_own_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replace_during_failure: bool
) -> None:
    target = tmp_path / "download.bin"

    def unsupported_link(source: Path, destination: Path) -> None:
        raise OSError(errno.EOPNOTSUPP, "hard links unavailable")

    def failed_copy(source: BinaryIO, destination: BinaryIO, length: int = 0) -> None:
        destination.write(b"partial")
        if replace_during_failure:
            target.unlink()
            target.write_bytes(b"racing replacement")
        raise OSError("test disk full")

    monkeypatch.setattr(_downloads.os, "link", unsupported_link)
    monkeypatch.setattr(_downloads.shutil, "copyfileobj", failed_copy)
    with pytest.raises(OSError, match="test disk full"):
        _downloads.write_download_bytes(b"download", target)
    if replace_during_failure:
        assert target.exists()
        assert target.read_bytes() == b"racing replacement"
        assert _outputs(tmp_path) == [target]
    else:
        assert _outputs(tmp_path) == []


@pytest.mark.parametrize("force", [False, True])
def test_download_never_writes_through_existing_symlink(tmp_path: Path, force: bool) -> None:
    existing = tmp_path / "original.bin"
    existing.write_bytes(b"original")
    target = tmp_path / "download.bin"
    target.symlink_to(existing)
    if force:
        _downloads.write_download_bytes(b"download", target, force=True)
        assert not target.is_symlink()
        assert target.read_bytes() == b"download"
    else:
        with pytest.raises(FileExistsError):
            _downloads.write_download_bytes(b"download", target)
        assert target.is_symlink()
    assert existing.read_bytes() == b"original"
