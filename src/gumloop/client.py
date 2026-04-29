from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class GumloopClient:
    def __init__(self, api_key: str, user_id: str, project_id: str | None = None):
        self.api_key = api_key
        self.user_id = user_id
        self.project_id = project_id
        self.base_url = "https://api.gumloop.com/api/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def run_flow(
        self,
        flow_id: str,
        inputs: dict[str, Any],
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> dict:
        """Run a Gumloop flow and block until it reaches a terminal state.

        Raises:
            TimeoutError: ``timeout`` elapsed before completion.
            RuntimeError: flow finished in FAILED, TERMINATING, or TERMINATED state.
        """
        pipeline_inputs = [{"input_name": k, "value": v} for k, v in inputs.items()]

        request_body = {
            "user_id": self.user_id,
            "saved_item_id": flow_id,
            "pipeline_inputs": pipeline_inputs,
        }
        if self.project_id:
            request_body["project_id"] = self.project_id

        response = httpx.post(
            f"{self.base_url}/start_pipeline",
            headers=self.headers,
            json=request_body,
        )
        response.raise_for_status()
        response_data = response.json()
        run_id = response_data["run_id"]

        logger.info("Started automation run: %s", response_data["url"])

        start_time = time.time()
        while True:
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError("Flow execution timed out")

            status = self.get_run_status(run_id)

            if status["state"] == "DONE":
                return status["outputs"]
            elif status["state"] == "FAILED":
                raise RuntimeError(f"Flow execution failed: {status.get('log', [])}")
            elif status["state"] in ["TERMINATING", "TERMINATED"]:
                raise RuntimeError(f"Flow execution was terminated: {status.get('log', [])}")

            time.sleep(poll_interval)

    def get_run_status(self, run_id: str) -> dict:
        """Fetch the status payload for a run."""
        params = {"run_id": run_id, "user_id": self.user_id}
        if self.project_id:
            params["project_id"] = self.project_id

        response = httpx.get(
            f"{self.base_url}/get_pl_run",
            headers=self.headers,
            params=params,
        )
        response.raise_for_status()
        return response.json()
