"""``gumloop browser``: move logins from this machine's browser into a Gumloop login profile."""

from __future__ import annotations

import sys
from typing import Annotated

import questionary
import typer
from rich.markup import escape as escape_markup

from gumloop import GumloopError
from gumloop.browser_logins import BrowserKind
from gumloop.browser_logins import LocalProfile
from gumloop.browser_logins import discover_profiles
from gumloop.browser_logins import extract_site_cookies
from gumloop.browser_logins import site_of_url
from gumloop.browser_logins.chromium_cookies import KeychainAccessError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.resources.browser_profiles import DEFAULT_PROFILE
from gumloop.types import BrowserProfile

browser_app = typer.Typer(
    help="Bring your browser logins to Gumloop agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
profiles_app = typer.Typer(help="Manage browser login profiles.", no_args_is_help=True, rich_markup_mode="rich")
browser_app.add_typer(profiles_app, name="profiles")


def _pick_local_profile(browser: str | None, browser_profile: str | None, *, non_interactive: bool) -> LocalProfile:
    kinds = [BrowserKind(browser)] if browser else None
    candidates = discover_profiles(browsers=kinds)
    if browser_profile:
        candidates = [
            p
            for p in candidates
            if p.name.lower() == browser_profile.lower() or p.display_name.lower() == browser_profile.lower()
        ]
    if not candidates:
        where = f"{BrowserKind(browser).display_name} " if browser else ""
        raise GumloopError(
            f"No {where}browser profile with saved cookies was found on this machine. "
            "Supported: Chrome, Chromium, Brave, Edge, Arc and Firefox on macOS and Linux."
        )
    if len(candidates) == 1 or non_interactive:
        return candidates[0]
    choice = questionary.select(
        "Which browser profile holds the login?",
        choices=[questionary.Choice(candidate.label, value=index) for index, candidate in enumerate(candidates)],
    ).ask()
    if choice is None:
        raise typer.Exit(1)
    return candidates[choice]


def _resolve_target(cli: CliContext, into: str | None, team_id: str | None) -> str:
    """A profile id passes through; a name is looked up under the owner scope."""
    if not into or into == DEFAULT_PROFILE:
        return DEFAULT_PROFILE
    listed = cli.call_with_refresh(lambda client: client.browser_profiles.list(project_id=team_id))
    for profile in listed.profiles:
        if profile.profile_id == into or profile.name.casefold() == into.casefold():
            return profile.profile_id
    raise GumloopError(
        f"No browser login profile named or identified by '{into}'. Run `gumloop browser profiles list`."
    )


def _print_profile_rows(profiles: list[BrowserProfile]) -> None:
    if not profiles:
        console.print("No browser login profiles yet. Import one with `gumloop browser import-logins --url <site>`.")
        return
    console.print("ID", "NAME", "SCOPE", "DEFAULT", "SITES", "UPDATED", sep="\t", soft_wrap=True)
    for profile in profiles:
        console.print(
            profile.profile_id,
            escape_markup(profile.name),
            profile.owner_scope,
            "yes" if profile.is_default else "",
            ", ".join(site.domain for site in profile.sites) or "-",
            profile.updated_ts or "",
            sep="\t",
            soft_wrap=True,
        )


@browser_app.command(
    "import-logins",
    epilog=(
        "Examples:\n"
        "  gumloop browser import-logins --url https://github.com\n"
        "  gumloop browser import-logins --url https://app.linear.app --browser brave --into 'Work'\n"
        "  gumloop browser import-logins --url https://mail.google.com --team <team_id> --into 'Ops inbox' --yes"
    ),
)
def import_logins(
    ctx: typer.Context,
    url: Annotated[str, typer.Option("--url", help="The site whose login to import, e.g. https://github.com.")],
    into: Annotated[
        str | None,
        typer.Option("--into", help="Target login profile id or name. Default: your personal default profile."),
    ] = None,
    team: Annotated[
        str | None,
        typer.Option("--team", help="Team id when the target profile belongs to a team."),
    ] = None,
    browser: Annotated[
        str | None,
        typer.Option("--browser", help="chrome, chromium, brave, edge, arc or firefox. Default: ask."),
    ] = None,
    browser_profile: Annotated[
        str | None,
        typer.Option("--browser-profile", help="Local browser profile name (e.g. 'Default', 'Profile 1', 'Work')."),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print the result as JSON.")] = False,
) -> None:
    """Copy this machine's cookies for one site into a Gumloop browser login profile.

    Only cookies for the site you name leave this machine, and only counts are ever printed.
    On macOS the system asks for Keychain access to the browser's cookie key; that prompt is
    the consent step.
    """
    cli: CliContext = ctx.obj
    if browser and browser not in {kind.value for kind in BrowserKind}:
        exit_with_error(
            GumloopError(f"Unknown browser '{browser}'. Use one of: " + ", ".join(k.value for k in BrowserKind)),
            json_output=json_output,
        )
    try:
        site = site_of_url(url)
        local = _pick_local_profile(browser, browser_profile, non_interactive=yes or json_output)
        if sys.platform == "darwin" and local.browser is not BrowserKind.FIREFOX and not json_output:
            console.print(
                f"[dim]macOS will ask for Keychain access to '{local.browser.safe_storage_service}' "
                "so the cookies can be read. Allow it to continue.[/dim]"
            )
        extracted = extract_site_cookies(local, url)
    except (GumloopError, KeychainAccessError, ValueError, FileNotFoundError, typer.Exit) as error:
        if isinstance(error, typer.Exit):
            raise
        exit_with_error(GumloopError(str(error)), json_output=json_output)

    if not extracted.cookies:
        hint = (
            " Some cookies could not be decrypted; open the site in that browser and try again."
            if extracted.undecryptable
            else ""
        )
        exit_with_error(
            GumloopError(
                f"No logins for {site} were found in {local.label}. Log in to the site in that browser first.{hint}"
            ),
            json_output=json_output,
        )

    if not json_output:
        console.print(
            f"Found {len(extracted.cookies)} cookie(s) for [bold]{escape_markup(site)}[/bold] "
            f"in {escape_markup(local.label)}:"
        )
        for domain, count in extracted.per_domain.items():
            console.print(f"  {escape_markup(domain)}\t{count}")
        if extracted.undecryptable:
            console.print(f"  [dim]{extracted.undecryptable} cookie(s) could not be decrypted and were skipped.[/dim]")
        if not yes:
            confirmed = questionary.confirm("Send these cookies to your Gumloop login profile?", default=True).ask()
            if not confirmed:
                console.print("Cancelled; nothing was sent.")
                raise typer.Exit(1)

    try:
        target = _resolve_target(cli, into, team)
        response = cli.call_with_refresh(
            lambda client: client.browser_profiles.import_cookies(
                target,
                url=url,
                cookies=extracted.cookies,
                project_id=team,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    imported = response.imported
    console.print(
        f"Imported {imported.cookie_count} cookie(s) for {escape_markup(imported.site)} into "
        f"'{escape_markup(response.profile.name)}' (profile {response.profile.profile_id})."
    )
    if imported.skipped:
        console.print(f"[dim]{imported.skipped} cookie(s) were skipped as expired or not for this site.[/dim]")
    console.print(
        "[dim]Agents using this profile start logged in on their next browser call. Sites that bind a session "
        "to your device or network may still ask you to sign in.[/dim]"
    )


@profiles_app.command(
    "list", epilog="Examples:\n  gumloop browser profiles list\n  gumloop browser profiles list --team <team_id>"
)
def list_profiles(
    ctx: typer.Context,
    team: Annotated[str | None, typer.Option("--team", help="List a team's profiles instead of your own.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw SDK response as JSON.")] = False,
) -> None:
    """List browser login profiles and the sites they hold."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.browser_profiles.list(project_id=team))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    if json_output:
        print_json(response)
        return
    _print_profile_rows(response.profiles)


@profiles_app.command("delete", epilog="Examples:\n  gumloop browser profiles delete <profile_id>")
def delete_profile(
    ctx: typer.Context,
    profile_id: Annotated[str, typer.Argument(help="Profile id, or 'default' for your personal default.")],
    team: Annotated[str | None, typer.Option("--team", help="Team id when the profile belongs to a team.")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print the result as JSON.")] = False,
) -> None:
    """Delete a login profile and every login it holds."""
    cli: CliContext = ctx.obj
    if not yes and not json_output:
        if not questionary.confirm(
            f"Delete browser login profile {profile_id} and all of its logins?", default=False
        ).ask():
            raise typer.Exit(1)
    try:
        cli.call_with_refresh(lambda client: client.browser_profiles.delete(profile_id, project_id=team))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    if json_output:
        print_json({"deleted": True, "profile_id": profile_id})
        return
    console.print(f"Deleted browser login profile {profile_id}.")


@profiles_app.command("remove-site", epilog="Examples:\n  gumloop browser profiles remove-site <profile_id> github.com")
def remove_site(
    ctx: typer.Context,
    profile_id: Annotated[str, typer.Argument(help="Profile id, or 'default' for your personal default.")],
    site: Annotated[str, typer.Argument(help="Site to forget, e.g. github.com.")],
    team: Annotated[str | None, typer.Option("--team", help="Team id when the profile belongs to a team.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw SDK response as JSON.")] = False,
) -> None:
    """Remove one site's logins from a profile."""
    cli: CliContext = ctx.obj
    try:
        profile = cli.call_with_refresh(
            lambda client: client.browser_profiles.remove_site(profile_id, site, project_id=team)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    if json_output:
        print_json(profile)
        return
    console.print(f"Removed {escape_markup(site)} from '{escape_markup(profile.name)}'.")
    _print_profile_rows([profile])
