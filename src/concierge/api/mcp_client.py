import json
import time
import logging
import requests
from typing import Dict, Any, List, Optional

from ..config import settings

logger = logging.getLogger("concierge.api.mcp_client")


class SwiggyFoodMcpClient:
    """HTTP JSON-RPC 2.0 client for the Swiggy Food MCP server."""

    def __init__(self, access_token: Optional[str] = None):
        token = access_token or settings.swiggy_access_token
        if not token:
            raise ValueError(
                "SWIGGY_ACCESS_TOKEN is missing. "
                "Run 'python src/auth.py' to complete OAuth, then set it in .env."
            )

        self._access_token = token
        self._url = settings.swiggy_mcp_url
        self._timeout = settings.mcp_request_timeout
        self._max_retries = settings.mcp_max_retries
        self._request_id = 0

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
        )

        logger.info(
            "SwiggyFoodMcpClient ready → %s (timeout=%ds, retries=%d)",
            self._url,
            self._timeout,
            self._max_retries,
        )

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return available tools from the Swiggy Food MCP server."""
        data = self._rpc("tools/list", {})
        tools = data.get("tools", [])
        logger.info("Fetched %d tools from Swiggy Food MCP", len(tools))
        return [
            {
                "name": t["name"],
                "description": t.get("description", t["name"]),
                "inputSchema": t.get("inputSchema", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a named tool and return its result in a normalised envelope:
          {"success": True,  "data": <structured_data>, "text": <raw_text>}  — on success
          {"success": False, "error": {...}}                                  — on failure

        The Swiggy MCP server returns two useful fields per result:
          • content[].text   — human-readable text (for LLM context)
          • structuredContent — machine-readable JSON (preferred for parsing)

        We always prefer structuredContent as the primary "data" value so that
        callers get real typed dicts/lists instead of having to regex-parse text.
        The raw text is preserved in "text" for LLM prompts and display.
        """
        args = arguments or {}
        logger.info("→ MCP tool call: %s %s", name, json.dumps(args))

        result = self._rpc("tools/call", {"name": name, "arguments": args})

        content = result.get("content", [])
        text_parts = [c["text"] for c in content if c.get("type") == "text" and c.get("text")]
        raw_text = "\n".join(text_parts)
        logger.info("← MCP tool '%s' raw text (first 200 chars): %s", name, raw_text[:200])

        # structuredContent is the real machine-readable payload — prefer it
        structured = result.get("structuredContent")
        if structured is not None:
            logger.debug("← MCP tool '%s' has structuredContent keys: %s", name, list(structured.keys()) if isinstance(structured, dict) else type(structured).__name__)
            return {"success": True, "data": structured, "text": raw_text}

        # No structuredContent — fall back to parsing the text block
        if not text_parts:
            logger.warning("Tool '%s' returned empty content and no structuredContent", name)
            return {"success": False, "data": None, "text": "", "error": {"message": "Empty response from Swiggy MCP"}}

        try:
            parsed = json.loads(raw_text)
            return {"success": True, "data": parsed, "text": raw_text}
        except json.JSONDecodeError:
            # Plain text response (e.g. human-readable lists)
            return {"success": True, "data": raw_text, "text": raw_text}

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC 2.0 request with exponential-backoff retry."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                t0 = time.monotonic()
                response = self._session.post(
                    self._url, json=payload, timeout=self._timeout
                )
                response.raise_for_status()
                elapsed = time.monotonic() - t0
                logger.debug("RPC '%s' completed in %.2fs", method, elapsed)

                body = response.json()
                if "error" in body:
                    raise RuntimeError(f"MCP error {body['error']}")

                return body.get("result", {})

            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s …
                logger.warning(
                    "RPC '%s' attempt %d/%d failed: %s — retrying in %ds",
                    method,
                    attempt + 1,
                    self._max_retries,
                    exc,
                    wait,
                )
                # Recreate session to clear any stale TCP state
                self._session = requests.Session()
                self._session.headers.update(
                    {
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    }
                )
                time.sleep(wait)

        raise RuntimeError(
            f"Swiggy MCP '{method}' failed after {self._max_retries} retries: {last_exc}"
        )
