from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Mapping
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.errors import GumloopError
from gumloop.types import WorkbooksResponse
from gumloop.types import WorkflowFileDownload
from gumloop.types import WorkflowFilesUploaded
from gumloop.types import WorkflowFileUploaded
from gumloop.types import WorkflowInputsResponse
from gumloop.types import WorkflowRun
from gumloop.types import WorkflowRunCancelled
from gumloop.types import WorkflowRunStarted
from gumloop.types import WorkflowsResponse

DEFAULT_DOWNLOAD_MAX_BYTES = 64 * 1024 * 1024


class WorkflowExecutionError(GumloopError):
    def __init__(self, run: WorkflowRun) -> None:
        super().__init__(f"Workflow run {run.run_id} ended with state {run.state}.")
        self.run = run


def _start_body(workflow_id: str, inputs: Mapping[str, Any], project_id: str | None) -> dict[str, Any]:
    return {
        "saved_item_id": workflow_id,
        "pipeline_inputs": [{"input_name": key, "value": value} for key, value in inputs.items()],
        **({"project_id": project_id} if project_id else {}),
    }


def _poll_options(poll_interval: float, timeout: float | None) -> None:
    if poll_interval < 0 or (timeout is not None and timeout < 0):
        raise ValueError("poll_interval and timeout must be nonnegative")


class Workflows:
    """Saved workflow execution and files through the supported legacy public API.

    A workflow ID is a saved_item_id (workbook tab); workbook_id is a container ID.
    Personal keys/OAuth use personal scope unless project_id is supplied. Team keys use
    their authenticated project; project_id explicitly selects a workspace for personal keys.
    File writes in a project require project update access. Canvas authoring is not exposed.
    """

    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self, *, project_id: str | None = None) -> WorkflowsResponse:
        return WorkflowsResponse.model_validate(self._client.get("list_saved_items", params={"project_id": project_id}))

    def list_workbooks(self, *, project_id: str | None = None) -> WorkbooksResponse:
        return WorkbooksResponse.model_validate(self._client.get("list_workbooks", params={"project_id": project_id}))

    def inputs(self, workflow_id: str, *, project_id: str | None = None) -> WorkflowInputsResponse:
        return WorkflowInputsResponse.model_validate(
            self._client.get("get_inputs", params={"saved_item_id": workflow_id, "project_id": project_id})
        )

    def start(
        self, workflow_id: str, inputs: Mapping[str, Any] | None = None, *, project_id: str | None = None
    ) -> WorkflowRunStarted:
        result = self._client.post("start_pipeline", json=_start_body(workflow_id, inputs or {}, project_id))
        return WorkflowRunStarted.model_validate({"saved_item_id": workflow_id, **result})

    def get_run(self, run_id: str, *, project_id: str | None = None) -> WorkflowRun:
        result = self._client.get("get_pl_run", params={"run_id": run_id, "project_id": project_id})
        return WorkflowRun.model_validate({"run_id": run_id, **result})

    def cancel_run(self, run_id: str, *, project_id: str | None = None) -> WorkflowRunCancelled:
        return WorkflowRunCancelled.model_validate(
            self._client.post(
                "kill_pipeline", json={"run_id": run_id, **({"project_id": project_id} if project_id else {})}
            )
        )

    def wait(
        self, run_id: str, *, project_id: str | None = None, poll_interval: float = 1.0, timeout: float | None = None
    ) -> WorkflowRun:
        """Wait for DONE; raise WorkflowExecutionError on failure/termination. Timeout does not cancel."""
        _poll_options(poll_interval, timeout)
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Workflow run {run_id} timed out")
            result = self.get_run(run_id, project_id=project_id)
            if result.state == "DONE":
                return result
            if result.state in ("FAILED", "TERMINATING", "TERMINATED"):
                raise WorkflowExecutionError(result)
            delay = min(poll_interval, max(0, deadline - time.monotonic())) if deadline is not None else poll_interval
            time.sleep(delay)

    def run(
        self,
        workflow_id: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        project_id: str | None = None,
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> WorkflowRun:
        _poll_options(poll_interval, timeout)
        started = self.start(workflow_id, inputs, project_id=project_id)
        return self.wait(started.run_id, project_id=project_id, poll_interval=poll_interval, timeout=timeout)

    def upload_file(self, file_name: str, content: bytes, *, project_id: str | None = None) -> WorkflowFileUploaded:
        return WorkflowFileUploaded.model_validate(
            self._client.post(
                "upload_file",
                json={
                    "file_name": file_name,
                    "file_content": base64.b64encode(content).decode("ascii"),
                    **({"project_id": project_id} if project_id else {}),
                },
            )
        )

    def upload_files(self, files: Mapping[str, bytes], *, project_id: str | None = None) -> WorkflowFilesUploaded:
        return WorkflowFilesUploaded.model_validate(
            self._client.post(
                "upload_files",
                json={
                    "files": [
                        {"file_name": name, "file_content": base64.b64encode(content).decode("ascii")}
                        for name, content in files.items()
                    ],
                    **({"project_id": project_id} if project_id else {}),
                },
            )
        )

    def download_file(
        self,
        file_name: str,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        workflow_id: str | None = None,
        max_bytes: int = DEFAULT_DOWNLOAD_MAX_BYTES,
    ) -> WorkflowFileDownload:
        content, headers = self._client.post_bytes(
            "download_file",
            json={"file_name": file_name, "project_id": project_id, "run_id": run_id, "saved_item_id": workflow_id},
            max_bytes=max_bytes,
        )
        return WorkflowFileDownload(content=content, media_type=headers.get("Content-Type"))

    def download_files(
        self,
        file_names: list[str],
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        workflow_id: str | None = None,
        max_bytes: int = DEFAULT_DOWNLOAD_MAX_BYTES,
    ) -> WorkflowFileDownload:
        content, headers = self._client.post_bytes(
            "download_files",
            json={"file_names": file_names, "project_id": project_id, "run_id": run_id, "saved_item_id": workflow_id},
            max_bytes=max_bytes,
        )
        return WorkflowFileDownload(content=content, media_type=headers.get("Content-Type"))


class AsyncWorkflows:
    """Saved workflow execution and files through the supported legacy public API.

    A workflow ID is a saved_item_id (workbook tab); workbook_id is a container ID.
    Personal keys/OAuth use personal scope unless project_id is supplied. Team keys use
    their authenticated project; project_id explicitly selects a workspace for personal keys.
    File writes in a project require project update access. Canvas authoring is not exposed.
    """

    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self, *, project_id: str | None = None) -> WorkflowsResponse:
        return WorkflowsResponse.model_validate(
            await self._client.get("list_saved_items", params={"project_id": project_id})
        )

    async def list_workbooks(self, *, project_id: str | None = None) -> WorkbooksResponse:
        return WorkbooksResponse.model_validate(
            await self._client.get("list_workbooks", params={"project_id": project_id})
        )

    async def inputs(self, workflow_id: str, *, project_id: str | None = None) -> WorkflowInputsResponse:
        return WorkflowInputsResponse.model_validate(
            await self._client.get("get_inputs", params={"saved_item_id": workflow_id, "project_id": project_id})
        )

    async def start(
        self, workflow_id: str, inputs: Mapping[str, Any] | None = None, *, project_id: str | None = None
    ) -> WorkflowRunStarted:
        result = await self._client.post("start_pipeline", json=_start_body(workflow_id, inputs or {}, project_id))
        return WorkflowRunStarted.model_validate({"saved_item_id": workflow_id, **result})

    async def get_run(self, run_id: str, *, project_id: str | None = None) -> WorkflowRun:
        result = await self._client.get("get_pl_run", params={"run_id": run_id, "project_id": project_id})
        return WorkflowRun.model_validate({"run_id": run_id, **result})

    async def cancel_run(self, run_id: str, *, project_id: str | None = None) -> WorkflowRunCancelled:
        return WorkflowRunCancelled.model_validate(
            await self._client.post(
                "kill_pipeline", json={"run_id": run_id, **({"project_id": project_id} if project_id else {})}
            )
        )

    async def wait(
        self, run_id: str, *, project_id: str | None = None, poll_interval: float = 1.0, timeout: float | None = None
    ) -> WorkflowRun:
        """Wait for DONE; raise WorkflowExecutionError on failure/termination. Timeout does not cancel."""
        _poll_options(poll_interval, timeout)
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Workflow run {run_id} timed out")
            result = await self.get_run(run_id, project_id=project_id)
            if result.state == "DONE":
                return result
            if result.state in ("FAILED", "TERMINATING", "TERMINATED"):
                raise WorkflowExecutionError(result)
            delay = min(poll_interval, max(0, deadline - time.monotonic())) if deadline is not None else poll_interval
            await asyncio.sleep(delay)

    async def run(
        self,
        workflow_id: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        project_id: str | None = None,
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> WorkflowRun:
        _poll_options(poll_interval, timeout)
        started = await self.start(workflow_id, inputs, project_id=project_id)
        return await self.wait(started.run_id, project_id=project_id, poll_interval=poll_interval, timeout=timeout)

    async def upload_file(
        self, file_name: str, content: bytes, *, project_id: str | None = None
    ) -> WorkflowFileUploaded:
        return WorkflowFileUploaded.model_validate(
            await self._client.post(
                "upload_file",
                json={
                    "file_name": file_name,
                    "file_content": base64.b64encode(content).decode("ascii"),
                    **({"project_id": project_id} if project_id else {}),
                },
            )
        )

    async def upload_files(self, files: Mapping[str, bytes], *, project_id: str | None = None) -> WorkflowFilesUploaded:
        return WorkflowFilesUploaded.model_validate(
            await self._client.post(
                "upload_files",
                json={
                    "files": [
                        {"file_name": name, "file_content": base64.b64encode(content).decode("ascii")}
                        for name, content in files.items()
                    ],
                    **({"project_id": project_id} if project_id else {}),
                },
            )
        )

    async def download_file(
        self,
        file_name: str,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        workflow_id: str | None = None,
        max_bytes: int = DEFAULT_DOWNLOAD_MAX_BYTES,
    ) -> WorkflowFileDownload:
        content, headers = await self._client.post_bytes(
            "download_file",
            json={"file_name": file_name, "project_id": project_id, "run_id": run_id, "saved_item_id": workflow_id},
            max_bytes=max_bytes,
        )
        return WorkflowFileDownload(content=content, media_type=headers.get("Content-Type"))

    async def download_files(
        self,
        file_names: list[str],
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        workflow_id: str | None = None,
        max_bytes: int = DEFAULT_DOWNLOAD_MAX_BYTES,
    ) -> WorkflowFileDownload:
        content, headers = await self._client.post_bytes(
            "download_files",
            json={"file_names": file_names, "project_id": project_id, "run_id": run_id, "saved_item_id": workflow_id},
            max_bytes=max_bytes,
        )
        return WorkflowFileDownload(content=content, media_type=headers.get("Content-Type"))
