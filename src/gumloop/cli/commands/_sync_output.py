from __future__ import annotations

from collections import Counter
from types import TracebackType

from rich.markup import escape as escape_markup
from rich.status import Status
from rich.table import Table
from rich.text import Text

from gumloop.cli.console import console
from gumloop.cli.console import error_console
from gumloop.sync.results import SyncExecution
from gumloop.sync.results import SyncProgress
from gumloop.sync.results import TargetOutcome
from gumloop.sync.targets import PhysicalTarget
from gumloop.types import CliSyncPlanResponse

_ACTION_LABELS = {
    "adopted": "adopted",
    "failed": "failed",
    "installed": "installed",
    "overwritten_collision": "replaced",
    "overwritten_local_edit": "replaced local edit",
    "removed": "removed",
    "unchanged": "unchanged",
    "updated": "updated",
}

_CRITICAL_ACTIONS = frozenset(
    {
        "failed",
        "overwritten_collision",
        "overwritten_local_edit",
        "removed",
    }
)

# Human labels match Homecrew/crew adapter names (hyphenated).
_AGENT_LABELS = {
    "agent_skills": "agent-skills",
    "claude_code": "claude-code",
    "codex": "codex",
    "cursor": "cursor",
}


class SyncOutput:
    def __init__(self) -> None:
        self._status: Status | None = None
        self._already_current = False

    def __enter__(self) -> SyncOutput:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self._stop()

    def __call__(self, progress: SyncProgress) -> None:
        if progress.stage == "resolving_plan":
            if progress.attempt == 1:
                message = "Resolving managed Skills…"
            else:
                max_attempts = progress.max_attempts
                retry_label = (
                    f"{progress.attempt}/{max_attempts}" if max_attempts is not None else str(progress.attempt)
                )
                message = f"Desired state changed; retrying ({retry_label})…"
            self._start(message)
            return
        if progress.stage == "plan_resolved":
            self._stop()
            skill_count = progress.skill_count or 0
            agent_count = progress.agent_count or 0
            console.print(
                "[green]✓[/green] "
                f"Found {skill_count} {self._pluralize('Skill', skill_count)} "
                f"for {agent_count} {self._pluralize('agent', agent_count)}"
            )
            return
        if progress.stage == "downloading_bundle":
            self._start("Downloading and verifying Skill bundle…")
            return
        if progress.stage == "bundle_verified":
            self._stop()
            console.print("[green]✓[/green] Downloaded and verified Skill bundle")
            return
        if progress.stage == "reconciling_target" and progress.target is not None:
            agents = escape_markup(self._format_agents(progress.target))
            self._start(f"Syncing {agents}…")
            return
        if progress.stage == "target_complete" and progress.outcome is not None:
            self._stop()
            self._print_target_outcome(progress.outcome)
            return
        if progress.stage == "already_current":
            self._stop()
            self._already_current = True
            skill_count = progress.skill_count or 0
            agent_count = progress.agent_count or 0
            console.print(
                "[green]✓[/green] "
                f"All {skill_count} {self._pluralize('Skill', skill_count)} are already current "
                f"across {agent_count} {self._pluralize('agent', agent_count)}"
            )

    def print_enrollment(
        self,
        *,
        plan: CliSyncPlanResponse,
        targets: tuple[PhysicalTarget, ...],
    ) -> None:
        table = Table(show_lines=False)
        table.add_column("Skills path", style="dim")
        table.add_column("Coding agents")

        console.print()
        console.print(
            f"Enrolled in [cyan]{escape_markup(plan.organization.organization_name)}[/cyan]"
        )
        if not targets:
            table.add_row(
                Text("—"),
                Text("No coding agents found"),
            )
            console.print(table)
            return

        for target in targets:
            table.add_row(
                Text(str(target.skills_root)),
                Text(self._format_agents(target)),
            )
        console.print(table)

    def print_background_status(self, status: str) -> None:
        console.print(f"[green]✓[/green] Background sync {status} [dim](every 4 hours)[/dim]")

    def print_result(self, execution: SyncExecution, *, verbose: bool) -> None:
        if execution.status == "blocked":
            reason = execution.result.get("blocked_reason") or "unknown"
            console.print(
                f"\nSync blocked: {reason}. Installed Skills were preserved.",
                markup=False,
                highlight=False,
            )
            self._print_changes(execution, verbose=verbose)
            return

        skill_counts = self._unique_skill_counts(execution)
        failed_count = self._failed_count_for_summary(execution, skill_counts)
        action_parts = [
            label
            for count, label in (
                (skill_counts.get("installed", 0), f"{skill_counts.get('installed', 0)} installed"),
                (skill_counts.get("adopted", 0), f"{skill_counts.get('adopted', 0)} adopted"),
                (skill_counts.get("overwritten", 0), f"{skill_counts.get('overwritten', 0)} replaced"),
                (skill_counts.get("updated", 0), f"{skill_counts.get('updated', 0)} updated"),
                (skill_counts.get("removed", 0), f"{skill_counts.get('removed', 0)} removed"),
            )
            if count
        ]
        agent_count = self._detected_agent_count(execution)
        agents = f"{agent_count} {self._pluralize('agent', agent_count)}"

        if not action_parts and failed_count == 0:
            # Fast-path already printed "already current"; avoid a redundant summary.
            if not self._already_current:
                console.print(f"\nSync complete: already up to date across {agents}.")
        else:
            status = "complete" if execution.status == "ok" else execution.status
            parts = [*action_parts, f"{failed_count} failed"]
            console.print(f"\nSync {status}: {', '.join(parts)} across {agents}.")

        self._print_changes(execution, verbose=verbose)

    def _start(self, message: str) -> None:
        if self._status is None:
            self._status = Status(
                message,
                console=console,
                spinner="dots",
            )
            self._status.start()
        else:
            self._status.update(message)

    def _stop(self) -> None:
        status = self._status
        self._status = None
        if status is None:
            return
        try:
            status.stop()
        except Exception:
            pass

    def _unique_skill_counts(self, execution: SyncExecution) -> dict[str, int]:
        """Count each Skill once, even when the same change is written for multiple agents."""
        by_skill: dict[str, set[str]] = {}
        changes = execution.result.get("changes")
        if isinstance(changes, list):
            for change in changes:
                if not isinstance(change, dict):
                    continue
                action = change.get("action")
                if not isinstance(action, str) or action == "unchanged":
                    continue
                if action in ("overwritten_collision", "overwritten_local_edit"):
                    bucket = "overwritten"
                else:
                    bucket = action
                skill_key = change.get("skill_id") or change.get("name")
                if not isinstance(skill_key, str) or not skill_key:
                    skill_key = str(change.get("physical_path") or id(change))
                by_skill.setdefault(skill_key, set()).add(bucket)

        counts = Counter(bucket for actions in by_skill.values() for bucket in actions)
        return dict(counts)

    def _detected_agent_count(self, execution: SyncExecution) -> int:
        detected = execution.result.get("detected_targets")
        if isinstance(detected, list):
            return len(detected)
        return 0

    def _failed_count_for_summary(
        self,
        execution: SyncExecution,
        skill_counts: dict[str, int],
    ) -> int:
        """Prefer unique Skill failures; raise to target-level when partial under-reports."""
        change_failed = skill_counts.get("failed", 0)
        if execution.status != "partial":
            return change_failed
        physical_targets = execution.result.get("physical_targets")
        if not isinstance(physical_targets, list):
            return change_failed
        target_failed = sum(
            1 for target in physical_targets if isinstance(target, dict) and target.get("error") is not None
        )
        return max(change_failed, target_failed)

    def _print_target_outcome(self, outcome: TargetOutcome) -> None:
        agents = self._format_agents(outcome.target)
        if outcome.error is not None:
            error_console.print(f"✗ {agents} — {outcome.error}", markup=False, highlight=False)
            return

        counts = Counter(change.action for change in outcome.changes)
        replaced = counts["overwritten_collision"] + counts["overwritten_local_edit"]
        parts = [
            label
            for count, label in (
                (counts["installed"], f"{counts['installed']} installed"),
                (counts["adopted"], f"{counts['adopted']} adopted"),
                (replaced, f"{replaced} replaced"),
                (counts["updated"], f"{counts['updated']} updated"),
                (counts["removed"], f"{counts['removed']} removed"),
                (counts["failed"], f"{counts['failed']} failed"),
            )
            if count
        ]
        detail = ", ".join(parts) if parts else "up to date"
        # One line per physical write; list every agent that shares that path.
        console.print(f"[green]✓[/green] {escape_markup(agents)} — {detail}")

    def _print_changes(self, execution: SyncExecution, *, verbose: bool) -> None:
        changes = execution.result.get("changes")
        if not isinstance(changes, list):
            return

        visible = [
            change
            for change in changes
            if isinstance(change, dict)
            and self._change_is_visible(change, verbose=verbose)
        ]
        if not visible:
            return

        console.print("\nChanges:")
        for change in visible:
            action = str(change.get("action", "changed"))
            label = _ACTION_LABELS.get(action, action.replace("_", " "))
            agents = self._format_agent_names(change.get("targets"))
            line = f"  {label}: {change.get('name')}"
            if agents:
                line += f" ({agents})"
            if change.get("backup_path"):
                line += f" backup: {change['backup_path']}"
            if change.get("error"):
                line += f" error: {change['error']}"
                error_console.print(line, markup=False, highlight=False)
            else:
                console.print(line, markup=False, highlight=False)

    def _change_is_visible(self, change: dict[str, object], *, verbose: bool) -> bool:
        action = change.get("action")
        if change.get("error"):
            return True
        if action == "unchanged":
            return False
        if verbose:
            return True
        if change.get("backup_path"):
            return True
        return action in _CRITICAL_ACTIONS

    def _format_agents(self, target: PhysicalTarget) -> str:
        return self._format_agent_names(target.logical_targets)

    def _format_agent_names(self, names: object) -> str:
        if not isinstance(names, (list, tuple)):
            return ""
        labels = [self._agent_label(str(name)) for name in names]
        return ", ".join(labels)

    def _agent_label(self, name: str) -> str:
        return _AGENT_LABELS.get(name, name.replace("_", "-"))

    def _pluralize(self, word: str, count: int) -> str:
        return word if count == 1 else f"{word}s"
