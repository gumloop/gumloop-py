"""Shared render helpers for command modules."""

from __future__ import annotations

from rich.markup import escape as escape_markup
from rich.table import Table
from rich.text import Text

from gumloop.cli.console import console
from gumloop.types import Session


def render_session(session: Session) -> None:
    """Pretty-print a Session for `sessions create / get / send`."""
    # Header uses markup=True framing -> escape the server-supplied id.
    # Data rows use markup=False. Table cells default to markup=True so
    # message bodies go through rich.text.Text.
    console.print(f"[bold]Session {escape_markup(session.id)}[/bold]", markup=True, highlight=False)
    for field in ("agent_id", "agent_name", "state", "created_at"):
        value = getattr(session, field, None)
        if value not in (None, ""):
            console.print(f"  {field}: {value}", markup=False, highlight=False)
    if session.messages:
        console.print(f"  messages: {len(session.messages)}")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Role")
        table.add_column("Content", overflow="fold")
        for m in session.messages[-5:]:
            content = m.content if isinstance(m.content, str) else str(m.content or "")
            table.add_row(Text(m.role or ""), Text(content[:200]))
        console.print(table)
