"""Resource classes, imported on first attribute access (PEP 562) so ``import gumloop`` stays cheap."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gumloop.resources.agents import Agents
    from gumloop.resources.agents import AsyncAgents
    from gumloop.resources.agents import AsyncModels
    from gumloop.resources.agents import Models
    from gumloop.resources.artifacts import Artifacts
    from gumloop.resources.artifacts import AsyncArtifacts
    from gumloop.resources.brain import AsyncBrain
    from gumloop.resources.brain import Brain
    from gumloop.resources.browser_profiles import AsyncBrowserProfiles
    from gumloop.resources.browser_profiles import BrowserProfiles
    from gumloop.resources.chat import AsyncChat
    from gumloop.resources.chat import Chat
    from gumloop.resources.decisions import AsyncDecisions
    from gumloop.resources.decisions import Decisions
    from gumloop.resources.evaluations import AsyncEvaluations
    from gumloop.resources.evaluations import Evaluations
    from gumloop.resources.mcp import MCP
    from gumloop.resources.mcp import AsyncMCP
    from gumloop.resources.organizations import AsyncOrganizations
    from gumloop.resources.organizations import Organizations
    from gumloop.resources.sessions import AsyncSessions
    from gumloop.resources.sessions import Sessions
    from gumloop.resources.skills import AsyncSkills
    from gumloop.resources.skills import Skills
    from gumloop.resources.sync import Sync
    from gumloop.resources.teams import AsyncTeams
    from gumloop.resources.teams import Teams
    from gumloop.resources.voice import AsyncVoice
    from gumloop.resources.voice import Voice
    from gumloop.resources.wiki import AsyncWiki
    from gumloop.resources.wiki import Wiki

_RESOURCE_MODULES: dict[str, str] = {
    "Agents": "agents",
    "AsyncAgents": "agents",
    "AsyncModels": "agents",
    "Models": "agents",
    "Artifacts": "artifacts",
    "AsyncArtifacts": "artifacts",
    "AsyncBrain": "brain",
    "Brain": "brain",
    "AsyncBrowserProfiles": "browser_profiles",
    "BrowserProfiles": "browser_profiles",
    "AsyncChat": "chat",
    "Chat": "chat",
    "AsyncDecisions": "decisions",
    "Decisions": "decisions",
    "AsyncEvaluations": "evaluations",
    "Evaluations": "evaluations",
    "MCP": "mcp",
    "AsyncMCP": "mcp",
    "AsyncOrganizations": "organizations",
    "Organizations": "organizations",
    "AsyncSessions": "sessions",
    "Sessions": "sessions",
    "AsyncSkills": "skills",
    "Skills": "skills",
    "Sync": "sync",
    "AsyncTeams": "teams",
    "Teams": "teams",
    "AsyncVoice": "voice",
    "Voice": "voice",
    "AsyncWiki": "wiki",
    "Wiki": "wiki",
}

__all__ = [
    "MCP",
    "Agents",
    "Artifacts",
    "AsyncAgents",
    "AsyncArtifacts",
    "AsyncBrain",
    "AsyncBrowserProfiles",
    "AsyncChat",
    "AsyncDecisions",
    "AsyncEvaluations",
    "AsyncMCP",
    "AsyncModels",
    "AsyncOrganizations",
    "AsyncSessions",
    "AsyncSkills",
    "AsyncTeams",
    "Brain",
    "BrowserProfiles",
    "Chat",
    "Decisions",
    "Evaluations",
    "Models",
    "Organizations",
    "Sessions",
    "Skills",
    "Sync",
    "Teams",
    "AsyncWiki",
    "Wiki",
    "AsyncVoice",
    "Voice",
]


def __getattr__(name: str) -> object:
    module_name = _RESOURCE_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
