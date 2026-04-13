import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GRAPHQL_URL   = os.getenv("HOMEFY_GRAPHQL_URL", "http://localhost:4000/graphql")
REST_BASE_URL = os.getenv("HOMEFY_REST_BASE_URL", "http://localhost:4000")
DEFAULT_TOKEN = os.getenv("HOMEFY_AUTH_TOKEN", "")

TIMEOUT = 8  # seconds per request

class BaseAPIClient:
    """Executes Homefy GraphQL queries and REST calls and summarises results."""

    def __init__(self):
        self._query_cache = {}

    def _load_gql(self, filepath: str) -> str:
        """Helper to read .graphql files from disk."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_path = os.path.join(base_dir, filepath)
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def _headers(self, token: str, apartment_id: str = "") -> dict:
        t = token or DEFAULT_TOKEN
        h = {"Content-Type": "application/json"}
        if t:
            h["Authorization"] = f"Bearer {t}" if not t.startswith("Bearer") else t
        if apartment_id:
            h["apartment-id"] = apartment_id
        return h

    def execute_graphql(self, query: str, variables: dict, token: str = "", apartment_id: str = "") -> dict:
        """Send a GraphQL request and return parsed JSON data."""
        payload = {"query": query, "variables": variables or {}}
        try:
            resp = requests.post(
                GRAPHQL_URL,
                json=payload,
                headers=self._headers(token, apartment_id=apartment_id),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                print(f"[GRAPHQL ERRORS]: {result['errors']}")
                with open("last_graphql_error.txt", "w") as f:
                    f.write(json.dumps(result['errors'], indent=2))
                return {"error": result["errors"]}
            return result.get("data", {})
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_msg += f" - {e.response.json()}"
                except Exception:
                    error_msg = f"{e} - {e.response.text}"
            print(f"[GRAPHQL HTTP ERROR]: {error_msg}")
            with open("last_graphql_error.txt", "w") as f:
                f.write(error_msg)
            return {"error": error_msg}
        except Exception as e:
            print(f"[GRAPHQL EXCEPTION]: {e}")
            return {"error": str(e)}

    def execute_rest(self, method: str, path: str, token: str = "", **kwargs) -> dict:
        """Send a REST request and return parsed JSON."""
        url = REST_BASE_URL.rstrip("/") + path
        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers(token),
                timeout=TIMEOUT,
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def _fmt(self, data: dict, label: str) -> str:
        """Format a data dict as readable text for the AI prompt context."""
        if "error" in data:
            err_str = str(data['error']).lower()
            if "403" in err_str or "forbidden" in err_str or "unauthorized" in err_str:
                return f"[{label}]: No data registered for this account or access is restricted.\n"
            return f"[{label}]: unavailable ({data['error']})\n"
        return f"[{label}]:\n{json.dumps(data, indent=2, default=str)}\n"
