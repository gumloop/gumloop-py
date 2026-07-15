from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from gumloop._http import HttpClient
from gumloop._http import ResponseSizeExceededError
from gumloop._version import __version__
from gumloop.sync.errors import SyncError
from gumloop.sync.wire import BUNDLE_CONTENT_TYPE
from gumloop.sync.wire import CLI_VERSION_HEADER
from gumloop.sync.wire import V1_LIMITS
from gumloop.types import CliSyncPlanResponse

# Public aliases kept for callers/tests that monkeypatch transfer limits.
SYNC_BUNDLE_CONTENT_TYPE = BUNDLE_CONTENT_TYPE
SYNC_CLI_VERSION_HEADER = CLI_VERSION_HEADER
SYNC_BUNDLE_MAX_BYTES = V1_LIMITS.bundle_transfer_bytes


@dataclass(frozen=True)
class SyncBundleDownload:
    content: bytes
    content_type: str


class Sync:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def plan(
        self,
        *,
        organization_id: str | None = None,
    ) -> CliSyncPlanResponse:
        try:
            payload = self._client.post(
                "skills/sync/plan",
                json=self._request_body(organization_id=organization_id),
                extra_headers=self._request_headers(),
            )
        except ValueError as error:
            raise SyncError(
                "invalid_desired_state",
                "The sync plan response is not valid JSON.",
            ) from error
        try:
            return CliSyncPlanResponse.model_validate(payload)
        except ValidationError as error:
            raise SyncError(
                "invalid_desired_state",
                "The sync plan response is invalid.",
            ) from error

    def download(
        self,
        *,
        organization_id: str | None = None,
    ) -> SyncBundleDownload:
        try:
            content, headers = self._client.post_bytes(
                "skills/sync/download",
                json=self._request_body(organization_id=organization_id),
                extra_headers=self._request_headers(),
                max_bytes=SYNC_BUNDLE_MAX_BYTES,
            )
        except ResponseSizeExceededError as error:
            raise SyncError(
                "download_failed",
                "The sync bundle exceeds the client transfer limit.",
            ) from error

        value = headers.get("Content-Type")
        if value is None:
            raise SyncError("download_failed", "The sync bundle is missing a content type.")
        media_type = value.split(";", 1)[0].strip()
        if media_type != SYNC_BUNDLE_CONTENT_TYPE:
            raise SyncError("download_failed", "The sync bundle has an invalid content type.")

        return SyncBundleDownload(
            content=content,
            content_type=media_type,
        )

    def _request_headers(self) -> dict[str, str]:
        return {
            SYNC_CLI_VERSION_HEADER: __version__,
        }

    def _request_body(self, *, organization_id: str | None) -> dict[str, str]:
        if organization_id is None:
            return {}
        return {"organization_id": organization_id}
