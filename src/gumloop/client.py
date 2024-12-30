import requests
import time
from typing import Dict, List, Optional, Union

class GumloopClient:
    def __init__(self, api_key: str, user_id: str, project_id: Optional[str] = None):
        """Initialize Gumloop client.
        
        Args:
            api_key: Your Gumloop API key
            user_id: Your Gumloop user ID
            project_id: Optional project ID for scoping operations
        """
        self.api_key = api_key
        self.user_id = user_id
        self.project_id = project_id
        self.base_url = "https://api.gumloop.com/api/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def run_flow(
        self, 
        flow_id: str, 
        inputs: Dict[str, any],
        poll_interval: float = 1.0,
        timeout: Optional[float] = None
    ) -> Dict:
        """Run a Gumloop flow and wait for results.
        
        Args:
            flow_id: The saved_item_id of your flow
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
        pipeline_inputs = [
            {"input_name": k, "value": v} 
            for k, v in inputs.items()
        ]
        
        # Start the flow
        request_body = {
            "user_id": self.user_id,
            "saved_item_id": flow_id,
            "pipeline_inputs": pipeline_inputs
        }
        if self.project_id:
            request_body["project_id"] = self.project_id
            
        response = requests.post(
            f"{self.base_url}/start_pipeline",
            headers=self.headers,
            json=request_body
        )
        response.raise_for_status()
        run_id = response.json()["run_id"]
        
        # Poll until completion
        start_time = time.time()
        while True:
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError("Flow execution timed out")
                
            status = self.get_run_status(run_id)
            
            if status["state"] == "DONE":
                return status["outputs"]
            elif status["state"] == "FAILED":
                raise RuntimeError(
                    f"Flow execution failed: {status.get('log', [])}"
                )
            elif status["state"] in ["TERMINATING", "TERMINATED"]:
                raise RuntimeError(
                    f"Flow execution was terminated: {status.get('log', [])}"
                )
            
            time.sleep(poll_interval)

    def get_run_status(self, run_id: str) -> Dict:
        """Get the status of a flow run.
        
        Args:
            run_id: The ID of the flow run
            
        Returns:
            Dict containing run status information
        """
        params = {"run_id": run_id, "user_id": self.user_id}
        if self.project_id:
            params["project_id"] = self.project_id
            
        response = requests.get(
            f"{self.base_url}/get_pl_run",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
