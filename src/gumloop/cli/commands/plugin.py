from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.errors import exit_with_error
from gumloop.sync.targets import detect_targets

if TYPE_CHECKING:
    from importlib.abc import Traversable

plugin_app = typer.Typer(
    help="Install official Gumloop agent plugins.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@plugin_app.command(
    "install",
    epilog=(
        "Examples:\n"
        "  gumloop plugin install gumloop\n"
        "  gumloop plugin install gumloop --force\n"
        "  gumloop plugin install gumloop --dir ~/.agents/plugins"
    ),
)
def install_plugin(
    name: Annotated[
        str,
        typer.Argument(help="Name of the plugin to install. `gumloop` teaches coding agents the Gumloop CLI."),
    ],
    directory: Annotated[
        Path | None,
        typer.Option(
            "--dir",
            help="Write the full plugin package (plugin.json + skills/) into this directory "
            "instead of installing skills into detected agent skill directories.",
            file_okay=False,
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace files that already exist at the destination."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the install summary as JSON."),
    ] = False,
) -> None:
    """Install an official Gumloop plugin's skills for coding agents (Claude Code, Cursor, Codex)."""
    try:
        bundled = _bundled_plugin_root(name)
        if directory is not None:
            results = [_install_tree(bundled, directory.expanduser() / name, force=force)]
        else:
            results = _install_skills_into_detected_targets(name, bundled, force=force)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(
            {
                "plugin": name,
                "installed": [str(path) for action, path in results if action == "installed"],
                "skipped": [str(path) for action, path in results if action == "skipped"],
            }
        )
        return

    for action, path in results:
        if action == "installed":
            console.print(f"[green]Installed[/green] {path}", markup=True, highlight=False)
        else:
            console.print(f"[yellow]Skipped[/yellow] {path} (already exists; use --force to replace)")
    if any(action == "installed" for action, _ in results):
        console.print("\nRestart your coding agent (or start a new session) to pick up the Gumloop CLI skill.")


def _bundled_plugin_names() -> list[str]:
    assets = resources.files("gumloop.cli").joinpath("plugin_assets")
    if not assets.is_dir():
        return []
    return sorted(entry.name for entry in assets.iterdir() if entry.is_dir())


def _bundled_plugin_root(name: str) -> Traversable:
    # Chained joinpath: Traversable only accepts multiple segments from 3.11.
    root = resources.files("gumloop.cli").joinpath("plugin_assets").joinpath(name)
    if name not in _bundled_plugin_names() or not root.is_dir():
        available = ", ".join(_bundled_plugin_names()) or "none"
        raise GumloopError(f"Unknown plugin: {name}. Available plugins: {available}.")
    return root


def _install_skills_into_detected_targets(
    name: str,
    bundled: Traversable,
    *,
    force: bool,
) -> list[tuple[str, Path]]:
    targets = detect_targets()
    if not targets:
        raise GumloopError(
            "No supported coding agent was detected (looked for Claude Code, Cursor, Codex, and ~/.agents). "
            f"Use `gumloop plugin install {name} --dir <path>` to write the plugin package somewhere explicit."
        )
    skills = [entry for entry in bundled.joinpath("skills").iterdir() if entry.is_dir()]
    # No .gumloop.json ownership marker is written on purpose: these skills
    # belong to the CLI install, and `gumloop sync` must never adopt,
    # overwrite, or remove them during org-skill reconciliation.
    results: list[tuple[str, Path]] = []
    for target in targets:
        for skill in skills:
            results.append(_install_tree(skill, target.skills_root / skill.name, force=force))
    return results


def _install_tree(source: Traversable, destination: Path, *, force: bool) -> tuple[str, Path]:
    if destination.exists() or destination.is_symlink():
        if not force:
            return ("skipped", destination)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".{destination.name}.gumloop-plugin-tmp"
        _remove_path(staging)
        _copy_traversable(source, staging)
        _remove_path(destination)
        staging.rename(destination)
    except OSError as error:
        raise GumloopError(f"Could not install to {destination}: {error.strerror or error}") from error
    return ("installed", destination)


def _copy_traversable(source: Traversable, destination: Path) -> None:
    # Walk the Traversable instead of assuming a filesystem path so the copy
    # also works when the package is loaded from a non-directory importer.
    destination.mkdir(parents=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            _copy_traversable(entry, target)
        else:
            target.write_bytes(entry.read_bytes())


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)
