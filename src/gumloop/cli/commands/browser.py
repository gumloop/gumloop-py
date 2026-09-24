from __future__ import annotations

import sys
from typing import Annotated
from typing import Any

import questionary
import typer
from rich.markup import escape as escape_markup

from gumloop import GumloopError
from gumloop.browser_logins import BrowserKind
from gumloop.browser_logins import ExtractResult
from gumloop.browser_logins import LocalProfile
from gumloop.browser_logins import discover_profiles
from gumloop.browser_logins import extract_profile_cookies
from gumloop.browser_logins import extract_site_cookies
from gumloop.browser_logins import site_of_url
from gumloop.browser_logins.chromium_cookies import KeychainAccessError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.resources.browser_profiles import DEFAULT_PROFILE
from gumloop.types import BrowserProfile
from gumloop.types import BrowserProfileImportResponse
from gumloop.types import BrowserProfileImportSummary

browser_app = typer.Typer(
    help="Bring your browser sign-ins to Gumloop agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
profiles_app = typer.Typer(help="List browser profiles.", no_args_is_help=True, rich_markup_mode="rich")
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
            f"No {where}browser profile was found on this machine. "
            "Supported: Chrome, Chromium, Brave, Edge, Arc and Firefox on macOS and Linux."
        )

    if len(candidates) == 1 or non_interactive:
        return candidates[0]

    choice = questionary.select(
        "Which browser profile do you want to import?",
        choices=[questionary.Choice(candidate.label, value=index) for index, candidate in enumerate(candidates)],
    ).ask()
    if choice is None:
        raise typer.Exit(1)

    return candidates[choice]


def _resolve_target(cli: CliContext, into: str | None, team_id: str | None) -> str:
    if not into or into == DEFAULT_PROFILE:
        return DEFAULT_PROFILE

    listed = cli.call_with_refresh(lambda client: client.browser_profiles.list(team_id=team_id))
    for profile in listed.profiles:
        if profile.profile_id == into or profile.name.casefold() == into.casefold():
            return profile.profile_id

    raise GumloopError(f"No browser profile named or identified by '{into}'. Run `gumloop browser profiles list`.")


def _print_profile_rows(profiles: list[BrowserProfile]) -> None:
    if not profiles:
        console.print("No browser profiles yet. Import one with `gumloop browser import-logins`.")
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


_IMPORT_CHUNK = 5000
_PREVIEW_SITES = 25


@browser_app.command(
    "import-logins",
    epilog=(
        "Examples:\n"
        "  gumloop browser import-logins\n"
        "  gumloop browser import-logins --browser brave --exclude-domain doubleclick.net\n"
        "  gumloop browser import-logins --include-domain github.com --include-domain linear.app\n"
        "  gumloop browser import-logins --url https://mail.google.com --team <team_id> --into 'Ops inbox' --yes"
    ),
)
def import_logins(
    ctx: typer.Context,
    url: Annotated[
        str | None,
        typer.Option("--url", help="Import only this site, e.g. https://github.com. Default: every site."),
    ] = None,
    include_domain: Annotated[
        list[str] | None,
        typer.Option("--include-domain", help="Only these domains and their subdomains. Repeat for several."),
    ] = None,
    exclude_domain: Annotated[
        list[str] | None,
        typer.Option("--exclude-domain", help="Skip these domains and their subdomains. Repeat for several."),
    ] = None,
    into: Annotated[
        str | None,
        typer.Option("--into", help="Target browser profile id or name. Default: your personal default profile."),
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
    """Copy this machine's browser cookies into a Gumloop browser profile.

    Takes every site's cookies from the local browser profile you pick (narrow it with
    --include-domain / --exclude-domain), or one site with --url. Cookies only: local storage
    and IndexedDB stay on this machine. Only counts are ever printed. On macOS the system asks
    for Keychain access to the browser's cookie key; that prompt is the consent step.
    """
    cli: CliContext = ctx.obj
    if browser and browser not in {kind.value for kind in BrowserKind}:
        exit_with_error(
            GumloopError(f"Unknown browser '{browser}'. Use one of: " + ", ".join(k.value for k in BrowserKind)),
            json_output=json_output,
        )

    if url and (include_domain or exclude_domain):
        exit_with_error(
            GumloopError("Use --url for one site, or --include-domain / --exclude-domain for a whole profile."),
            json_output=json_output,
        )

    try:
        site = site_of_url(url) if url else None
        local = _pick_local_profile(browser, browser_profile, non_interactive=yes or json_output)
        if sys.platform == "darwin" and local.browser is not BrowserKind.FIREFOX and not json_output:
            console.print(
                f"[dim]macOS will ask for Keychain access to '{local.browser.safe_storage_service}' "
                "so the cookies can be read. Allow it to continue.[/dim]"
            )

        if url:
            extracted = extract_site_cookies(local, url)
        else:
            extracted = extract_profile_cookies(local, include=include_domain or (), exclude=exclude_domain or ())
    except (GumloopError, KeychainAccessError, ValueError, FileNotFoundError, typer.Exit) as error:
        if isinstance(error, typer.Exit):
            raise

        exit_with_error(GumloopError(str(error)), json_output=json_output)

    if not extracted.cookies:
        hint = (
            " Some cookies could not be decrypted; open that browser and try again." if extracted.undecryptable else ""
        )
        if site:
            message = f"No sign-ins for {site} were found in {local.label}. Sign in there in that browser first.{hint}"
        else:
            message = f"No sign-ins were found in {local.label}.{hint}"
        exit_with_error(GumloopError(message), json_output=json_output)

    if not json_output:
        _print_import_preview(extracted, local)
        if not yes:
            prompt = (
                "Import this site into your Gumloop browser profile?"
                if extracted.site
                else "Import these sites into your Gumloop browser profile?"
            )
            confirmed = questionary.confirm(prompt, default=True).ask()
            if not confirmed:
                console.print("Cancelled; nothing was sent.")
                raise typer.Exit(1)

    try:
        response = _upload_cookies(cli, _resolve_target(cli, into, team), url, extracted.cookies, team)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    imported = response.imported
    target = f"'{escape_markup(response.profile.name)}' (profile {response.profile.profile_id})"
    if imported.site:
        console.print(f"Imported {imported.cookie_count} cookie(s) for {escape_markup(imported.site)} into {target}.")
    else:
        console.print(f"Imported {imported.cookie_count} cookie(s) across {len(imported.sites)} site(s) into {target}.")

    if imported.skipped:
        console.print(f"[dim]{imported.skipped} cookie(s) were skipped as expired or unusable.[/dim]")

    console.print(
        "[dim]Agents using this profile start signed in on their next browser call. Sites that keep the session "
        "in local storage, or bind it to your device or network, may still ask the agent to sign in.[/dim]"
    )


def _print_import_preview(extracted: ExtractResult, local: LocalProfile) -> None:
    label = escape_markup(local.label)
    if extracted.site:
        console.print(
            f"Found {len(extracted.cookies)} cookie(s) for [bold]{escape_markup(extracted.site)}[/bold] in {label}:"
        )
        rows = extracted.per_domain
    else:
        rows = extracted.per_site
        console.print(f"Found {len(extracted.cookies)} cookie(s) across {len(rows)} site(s) in {label}:")

    for domain, count in list(rows.items())[:_PREVIEW_SITES]:
        console.print(f"  {escape_markup(domain)}\t{count}")

    if len(rows) > _PREVIEW_SITES:
        console.print(f"  [dim]…and {len(rows) - _PREVIEW_SITES} more site(s)[/dim]")

    if extracted.undecryptable:
        console.print(f"  [dim]{extracted.undecryptable} cookie(s) could not be decrypted and were skipped.[/dim]")


def _upload_cookies(
    cli: CliContext,
    target: str,
    url: str | None,
    cookies: list[dict[str, Any]],
    team: str | None,
) -> BrowserProfileImportResponse:
    responses: list[BrowserProfileImportResponse] = []
    for start in range(0, len(cookies), _IMPORT_CHUNK):
        chunk = cookies[start : start + _IMPORT_CHUNK]
        profile_id = responses[-1].profile.profile_id if responses else target
        responses.append(
            cli.call_with_refresh(
                lambda client, profile_id=profile_id, chunk=chunk: client.browser_profiles.import_cookies(
                    profile_id,
                    url=url,
                    cookies=chunk,
                    team_id=team,
                )
            )
        )

    if len(responses) == 1:
        return responses[0]

    return BrowserProfileImportResponse(
        profile=responses[-1].profile,
        imported=BrowserProfileImportSummary(
            site=responses[-1].imported.site,
            cookie_count=sum(r.imported.cookie_count for r in responses),
            skipped=sum(r.imported.skipped for r in responses),
            sites=sorted({s for r in responses for s in r.imported.sites}),
        ),
    )


@profiles_app.command(
    "list", epilog="Examples:\n  gumloop browser profiles list\n  gumloop browser profiles list --team <team_id>"
)
def list_profiles(
    ctx: typer.Context,
    team: Annotated[str | None, typer.Option("--team", help="List a team's profiles instead of your own.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw SDK response as JSON.")] = False,
) -> None:
    """List browser profiles and the sites they hold."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.browser_profiles.list(team_id=team))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    _print_profile_rows(response.profiles)
    console.print("[dim]Rename, remove sites from, or delete profiles on the Secrets page in Gumloop.[/dim]")
