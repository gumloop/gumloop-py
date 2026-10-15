from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import typer

from gumloop import Gumloop
from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import ArtifactPasswordResponse
from gumloop.types import ItemAccessChangeResponse
from gumloop.types import ItemAccessResponse

_LINK_MODES = frozenset({"none", "anyone", "password"})


@dataclass(frozen=True)
class ParsedItemAccess:
    share: list[dict[str, str]] | None
    remove: list[dict[str, str]] | None
    link: dict[str, str] | None

    @property
    def is_empty(self) -> bool:
        return self.share is None and self.remove is None and self.link is None


def share_option() -> Any:
    return typer.Option("--share", help="Person to add or update, as email:role. Repeatable.")


def remove_option() -> Any:
    return typer.Option("--remove", help="Person to remove, by email. Repeatable.")


def share_team_option() -> Any:
    return typer.Option("--share-team", help="Team to add or update, as team_id:role. Repeatable.")


def remove_team_option() -> Any:
    return typer.Option("--remove-team", help="Team to remove, by team id. Repeatable.")


def organization_option() -> Any:
    return typer.Option("--organization", help="Organization role. none removes organization access.")


def link_option() -> Any:
    return typer.Option("--link", help="Link mode: none, anyone, or password.")


def link_role_option() -> Any:
    return typer.Option("--link-role", help="Role for the link. Uses the item default when omitted.")


def json_option() -> Any:
    return typer.Option("--json", help="Print the raw SDK response as JSON.")


def parse_item_access_flags(
    *,
    share: list[str] | None,
    remove: list[str] | None,
    share_team: list[str] | None,
    remove_team: list[str] | None,
    organization: str | None,
    link: str | None,
    link_role: str | None,
) -> ParsedItemAccess:
    share_parts: list[dict[str, str]] = []
    remove_parts: list[dict[str, str]] = []

    for value in share or []:
        email, role = _split_pair(value, flag="--share", kind="email")
        share_parts.append({"type": "person", "email": email, "role": role})
    for value in remove or []:
        email = value.strip()
        if not email:
            raise GumloopError("--remove needs an email.")
        remove_parts.append({"type": "person", "email": email})
    for value in share_team or []:
        team_id, role = _split_pair(value, flag="--share-team", kind="team_id")
        share_parts.append({"type": "team", "team_id": team_id, "role": role})
    for value in remove_team or []:
        team_id = value.strip()
        if not team_id:
            raise GumloopError("--remove-team needs a team id.")
        remove_parts.append({"type": "team", "team_id": team_id})

    if organization is not None:
        role = organization.strip()
        if not role:
            raise GumloopError("--organization needs a role, or none to remove it.")
        if role == "none":
            remove_parts.append({"type": "organization"})
        else:
            share_parts.append({"type": "organization", "role": role})

    link_body: dict[str, str] | None = None
    if link is not None:
        mode = link.strip()
        if mode not in _LINK_MODES:
            raise GumloopError("--link must be none, anyone, or password.")
        link_body = {"mode": mode}
        if link_role is not None:
            role = link_role.strip()
            if not role:
                raise GumloopError("--link-role needs a role.")
            link_body["role"] = role
    elif link_role is not None:
        raise GumloopError("--link-role needs --link.")

    return ParsedItemAccess(
        share=share_parts or None,
        remove=remove_parts or None,
        link=link_body,
    )


def read_password_stdin() -> str:
    password = sys.stdin.read()
    if password.endswith("\r\n"):
        password = password[:-2]
    elif password.endswith("\n"):
        password = password[:-1]
    return password


def show_item_access(
    ctx: typer.Context,
    *,
    json_output: bool,
    read: Callable[[Gumloop], ItemAccessResponse],
) -> None:
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(read)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_item_access(response)


def apply_item_access(
    ctx: typer.Context,
    *,
    share: list[str] | None,
    remove: list[str] | None,
    share_team: list[str] | None,
    remove_team: list[str] | None,
    organization: str | None,
    link: str | None,
    link_role: str | None,
    json_output: bool,
    update: Callable[[Gumloop, ParsedItemAccess], ItemAccessChangeResponse],
    set_password: Callable[[Gumloop], ArtifactPasswordResponse] | None = None,
) -> None:
    cli: CliContext = ctx.obj
    try:
        parsed = parse_item_access_flags(
            share=share,
            remove=remove,
            share_team=share_team,
            remove_team=remove_team,
            organization=organization,
            link=link,
            link_role=link_role,
        )
        if parsed.is_empty and set_password is None:
            raise GumloopError("Pass at least one access change.")

        def apply(client: Gumloop) -> ItemAccessChangeResponse | ArtifactPasswordResponse:
            password_response: ArtifactPasswordResponse | None = None
            if set_password is not None:
                password_response = set_password(client)
                if parsed.is_empty:
                    return password_response
            return update(client, parsed)

        response = cli.call_with_refresh(apply)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    if isinstance(response, ArtifactPasswordResponse):
        console.print("[green]Password set.[/green]")
        return
    console.print("[green]Access updated.[/green]")
    _print_item_access(response)


def _split_pair(value: str, *, flag: str, kind: str) -> tuple[str, str]:
    left, separator, role = value.partition(":")
    left = left.strip()
    role = role.strip()
    if separator == "" or left == "" or role == "":
        raise GumloopError(f"{flag} must be {kind}:role.")
    return left, role


def _print_item_access(response: ItemAccessResponse) -> None:
    access = response.access
    console.print(f"Visibility: {access.grants_visibility}", markup=False, highlight=False)
    if access.link_role:
        console.print(f"Link: {access.link} ({access.link_role})", markup=False, highlight=False)
    else:
        console.print(f"Link: {access.link}", markup=False, highlight=False)
    console.print(
        f"Password protected: {'yes' if access.password_protected else 'no'}",
        markup=False,
        highlight=False,
    )
    if access.organization_access is None:
        console.print("Organization: none", markup=False, highlight=False)
    else:
        console.print(f"Organization: {access.organization_access.role}", markup=False, highlight=False)

    if access.people:
        console.print("People:")
        for person in access.people:
            console.print(
                f"  {person.email}\t{person.name or ''}\t{person.role}",
                markup=False,
                highlight=False,
            )
    else:
        console.print("People: none")

    if access.teams:
        console.print("Teams:")
        for team in access.teams:
            console.print(f"  {team.team_id}\t{team.role}", markup=False, highlight=False)
    else:
        console.print("Teams: none")

    if access.hidden_by_role:
        console.print("Hidden by role:")
        for role, counts in access.hidden_by_role.items():
            console.print(f"  {role}: {counts.people} people, {counts.teams} teams", markup=False, highlight=False)

    if isinstance(response, ItemAccessChangeResponse) and response.notified:
        console.print("Notified: " + ", ".join(response.notified), markup=False, highlight=False)
