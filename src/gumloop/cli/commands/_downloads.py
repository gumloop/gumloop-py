"""Shared streamed-download helper for skills/artifacts download commands."""

from __future__ import annotations

import sys
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath
from typing import Any
from typing import Protocol
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import httpx

from gumloop import GumloopError


class _DownloadInfo(Protocol):
    """Subset of fields the helper reads off the SDK's download response.

    Declared as ``@property`` so concrete subtypes can narrow ``filename`` /
    ``media_type`` to ``str`` without tripping invariance on mutable attrs.
    """

    @property
    def download_url(self) -> str: ...
    @property
    def filename(self) -> str | None: ...
    @property
    def media_type(self) -> str | None: ...


_DOWNLOAD_CHUNK_BYTES = 64 * 1024
# No timeout=None: a stuck upstream could hang CI forever and drip-fill disk.
_DOWNLOAD_TIMEOUT = httpx.Timeout(connect=15.0, read=600.0, write=60.0, pool=15.0)

# Writing to these on Windows opens a device, not a file.
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
)


def _redact_signed_url(url: str) -> str:
    """Drop the query string before logging. Signed S3/GCS URLs carry the
    auth grant in ``?X-Amz-Signature=...``; logging it leaks a bearer."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<download url>"
    if not parts.scheme or not parts.netloc:
        return "<download url>"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _safe_server_basename(name: str | None) -> str | None:
    """Return ``name`` if safe to use as a basename, else ``None``.

    Server-provided filenames are untrusted: ``Path('/tmp/x') / '/etc/passwd'``
    resolves to ``/etc/passwd``, so an absolute or traversing filename
    would escape the user's chosen output directory.
    """
    if not isinstance(name, str):
        return None
    stripped = name.strip()
    if not stripped:
        return None
    if any(ch in stripped for ch in ("/", "\\", "\x00")):
        return None
    if stripped in (".", ".."):
        return None
    if PurePosixPath(stripped).is_absolute() or PureWindowsPath(stripped).is_absolute():
        return None
    # "C:" is anchored on Windows but not flagged as absolute on POSIX.
    if len(stripped) == 2 and stripped[1] == ":":
        return None
    head = stripped.split(".", 1)[0].upper()
    if head in _WINDOWS_RESERVED_NAMES:
        return None
    return stripped


def _resolve_output_path(output: str | None, server_filename: str | None, fallback: str) -> Path | None:
    """Return the destination Path or ``None`` if output should go to stdout."""
    if output == "-":
        return None

    safe_name = _safe_server_basename(server_filename)
    chosen_name = safe_name or fallback

    if output is None:
        return Path.cwd() / chosen_name

    target = Path(output).expanduser()
    if target.is_dir() or output.endswith(("/", "\\")):
        return target / chosen_name
    return target


def _stream_to_stdout(remote: httpx.Response) -> int:
    stdout = sys.stdout.buffer
    written = 0
    for chunk in remote.iter_bytes(_DOWNLOAD_CHUNK_BYTES):
        stdout.write(chunk)
        written += len(chunk)
    stdout.flush()
    return written


def _stream_to_file_atomically(remote: httpx.Response, destination: Path) -> int:
    """Stream into ``destination.part`` then rename. Ctrl-C or a mid-stream
    failure cleans up the partial file and leaves any existing target intact."""
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GumloopError(f"Cannot create output directory {destination.parent}: {exc}") from exc

    part_path = destination.with_name(destination.name + ".part")
    written = 0
    try:
        try:
            handle = part_path.open("wb")
        except OSError as exc:
            raise GumloopError(f"Cannot open {part_path} for writing: {exc}") from exc

        try:
            for chunk in remote.iter_bytes(_DOWNLOAD_CHUNK_BYTES):
                handle.write(chunk)
                written += len(chunk)
        finally:
            handle.close()

        try:
            part_path.replace(destination)
        except OSError as exc:
            raise GumloopError(f"Cannot move {part_path} to {destination}: {exc}") from exc
    except BaseException:
        # BaseException covers KeyboardInterrupt so Ctrl-C cleans up too.
        if part_path.exists():
            try:
                part_path.unlink()
            except OSError:
                pass
        raise

    return written


def download_response(response: _DownloadInfo, *, output: str | None, fallback_name: str) -> dict[str, Any]:
    """Stream a signed-URL download response to disk or stdout. Returns
    ``{path, bytes, filename, media_type}`` for the caller to render."""
    url = response.download_url
    if not url:
        raise GumloopError("Download response did not include a download_url.")

    server_filename = response.filename
    destination = _resolve_output_path(output, server_filename, fallback_name)

    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as remote:
            remote.raise_for_status()
            if destination is None:
                bytes_written = _stream_to_stdout(remote)
            else:
                bytes_written = _stream_to_file_atomically(remote, destination)
    except httpx.HTTPStatusError as error:
        # httpx.HTTPStatusError.__str__ embeds the full request URL, which
        # would leak the signed query string. Report the status only.
        raise GumloopError(
            f"Failed to download {_redact_signed_url(url)}: HTTP {error.response.status_code}"
        ) from error
    except httpx.HTTPError as error:
        raise GumloopError(f"Failed to download {_redact_signed_url(url)}: {error.__class__.__name__}") from error

    return {
        "path": None if destination is None else str(destination),
        "bytes": bytes_written,
        "filename": server_filename,
        "media_type": response.media_type,
    }
