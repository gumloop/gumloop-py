from __future__ import annotations

import json
from typing import Any

import httpx

API_BASE = "https://api.gumloop.com/api/v1"
OAUTH_BASE = "https://api.gumloop.com"


def auth_header(request: httpx.Request) -> str:
    return request.headers["Authorization"]


def request_json(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)
