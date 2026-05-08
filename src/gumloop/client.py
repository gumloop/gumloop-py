from __future__ import annotations

import time
import warnings
from typing import Any

import httpx


class GumloopClient:
    def __init__(self, api_key: str, user_id: str, project_id: str | None = None):
        """Initialize Gumloop client.

        Args:
            api_key: Your Gumloop API key
            user_id: Your Gumloop user ID
            project_id: Optional project ID for running automations under a workspace
        """
        warnings.warn(
            "GumloopClient is the legacy flows client. Use gumloop.Gumloop for new agents and sessions APIs.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.api_key = api_key
        self.user_id = user_id
        self.project_id = project_id
        self.base_url = "https://api.gumloop.com/api/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # Persistent client so the polling loop reuses one TCP connection
        # across start_pipeline + get_pl_run instead of handshaking per call.
        self._client = httpx.Client(headers=self.headers)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GumloopClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def run_flow(
        self,
        flow_id: str,
        inputs: dict[str, Any],
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> dict:
        """Run a Gumloop flow and wait for results.

        Args:
            flow_id: The id of your flow
            inputs: Dictionary of input names to values
            poll_interval: How often to check for completion (seconds)
            timeout: Maximum time to wait for completion (seconds)

        Returns:
            Dict containing the flow outputs

        Raises:
            TimeoutError: If the flow doesn't complete within timeout
            RuntimeError: If the flow fails
        """
        # Convert inputs to pipeline_inputs format
        pipeline_inputs = [{"input_name": k, "value": v} for k, v in inputs.items()]

        # Start the flow
        request_body = {
            "user_id": self.user_id,
            "saved_item_id": flow_id,
            "pipeline_inputs": pipeline_inputs,
        }
        if self.project_id:
            request_body["project_id"] = self.project_id

        response = self._client.post(
            f"{self.base_url}/start_pipeline",
            json=request_body,
        )
        response.raise_for_status()
        response_data = response.json()
        run_id = response_data["run_id"]

        start_time = time.time()
        while True:
            # `is not None` so timeout=0 raises immediately rather than
            # being treated as "no deadline" by truthiness.
            if timeout is not None and (time.time() - start_time) > timeout:
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
        """Get the status of a flow run.

        Args:
            run_id: The ID of the flow run

        Returns:
            Dict containing run status information
        """
        params = {"run_id": run_id, "user_id": self.user_id}
        if self.project_id:
            params["project_id"] = self.project_id

        response = self._client.get(
            f"{self.base_url}/get_pl_run",
            params=params,
        )
        response.raise_for_status()
        return response.json()
