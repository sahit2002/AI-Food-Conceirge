import json
import re
import time
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from ..api.mcp_client import SwiggyFoodMcpClient
from ..config import settings
from ..middleware.compression import compress_restaurants, compress_search_results
from ..models.schema import FoodPick, IntakeAnswers
from .prompts import (
    CONCIERGE_SYSTEM_PROMPT,
    ORDER_CONFIRMATION_PROMPT,
    build_recommendation_prompt,
)

logger = logging.getLogger("concierge.agent.core")

# Tools whose output benefits from compression before being fed to the LLM
_COMPRESS_TOOLS = frozenset({"search_restaurants", "search_menu", "get_restaurant_menu"})

# Non-veg ingredient keywords used for post-filter enforcement
_NON_VEG_TERMS = frozenset(
    {"chicken", "mutton", "egg", "fish", "prawns", "prawn", "kebab", "meat", "lamb", "pork"}
)


def _json_schema_to_gemini_schema(schema: Dict[str, Any]) -> Any:
    """Recursively convert a JSON Schema dict into a Google GenAI gtypes.Schema object."""
    from google.genai import types as gtypes

    type_map = {
        "string": gtypes.Type.STRING,
        "integer": gtypes.Type.INTEGER,
        "number": gtypes.Type.NUMBER,
        "boolean": gtypes.Type.BOOLEAN,
        "array": gtypes.Type.ARRAY,
        "object": gtypes.Type.OBJECT,
    }

    stype = schema.get("type", "object").lower() if isinstance(schema.get("type"), str) else "object"
    gtype = type_map.get(stype, gtypes.Type.OBJECT)

    props = {}
    if "properties" in schema and isinstance(schema["properties"], dict):
        for prop_name, prop_spec in schema["properties"].items():
            if isinstance(prop_spec, dict):
                props[prop_name] = _json_schema_to_gemini_schema(prop_spec)

    items_schema = None
    if "items" in schema and isinstance(schema["items"], dict):
        items_schema = _json_schema_to_gemini_schema(schema["items"])
    elif gtype == gtypes.Type.ARRAY:
        items_schema = gtypes.Schema(type=gtypes.Type.STRING)

    return gtypes.Schema(
        type=gtype,
        description=schema.get("description"),
        properties=props if props else None,
        required=schema.get("required"),
        items=items_schema,
    )


class FoodConciergeAgent:
    """Multi-LLM orchestrator that queries Swiggy MCP tools and ranks food picks."""

    def __init__(self, mcp_client: SwiggyFoodMcpClient):
        self.mcp = mcp_client
        self._provider = settings.active_llm_provider
        self._cached_address_id: Optional[str] = None

        logger.info("FoodConciergeAgent ready — provider=%s", self._provider.upper())

    # ──────────────────────────────────────────────────────────────────
    # Address resolution
    # ──────────────────────────────────────────────────────────────────

    def _get_address_id(self) -> str:
        """Fetch or return cached address ID from user saved addresses."""
        if self._cached_address_id:
            return self._cached_address_id
        try:
            res = self.mcp.call_tool("get_addresses", {})
            addr_id = _extract_address_id(res)
            if addr_id:
                self._cached_address_id = addr_id
                return self._cached_address_id
        except Exception as exc:
            logger.warning("Failed to fetch address ID: %s", exc)

        # Hard fallback — should only happen in tests or if MCP is unreachable
        logger.warning("Falling back to hardcoded address ID")
        self._cached_address_id = "d4722bhjqdcnkdef8450"
        return self._cached_address_id

    def invalidate_address_cache(self) -> None:
        """Force re-fetch of address on next call."""
        self._cached_address_id = None

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def recommend(
        self,
        query_or_answers: Union[IntakeAnswers, str],
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[List[FoodPick], str]:
        """Return (picks, raw_llm_text) for an intake form or a freeform query."""
        veg_only, user_prompt, search_term = self._build_prompt(query_or_answers)

        raw = ""
        try:
            raw = self._run_loop(user_prompt, log_callback)
        except Exception as err:
            logger.warning("LLM provider loop failed: %s — falling back to direct MCP search", err)

        picks = extract_picks(raw, veg_only=veg_only)

        # If LLM didn't return parseable picks, run a direct live MCP search
        if not picks:
            _log(log_callback, f"🔍 Querying Swiggy MCP directly for: '{search_term}'…")
            picks = self._direct_mcp_search(search_term, veg_only=veg_only)
            raw = f"Fetched {len(picks)} live options directly from Swiggy for '{search_term}'."

        picks = self._enforce_veg(picks, veg_only)
        logger.info(
            "Recommendation complete — %d picks (veg_only=%s, provider=%s)",
            len(picks), veg_only, self._provider,
        )
        return picks, raw

    def order_selected_pick(
        self,
        pick: FoodPick,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Run the full cart-build → coupon → checkout loop for a user-selected pick."""
        logger.info("Building cart — dish='%s', restaurant='%s'", pick.dish_name, pick.restaurant_name)
        prompt = (
            f"{ORDER_CONFIRMATION_PROMPT}\n\n"
            f"User selected:\n"
            f"- Dish: {pick.dish_name}\n"
            f"- Restaurant: {pick.restaurant_name}\n"
            f"- Restaurant ID: {pick.restaurant_id or 'unknown'}\n"
            f"- Item ID: {pick.item_id or 'unknown'}\n\n"
            "Complete the full checkout flow as described above."
        )
        return self._run_loop(prompt, log_callback)

    def get_cart(self) -> Dict[str, Any]:
        """Return the current cart state from Swiggy MCP."""
        addr_id = self._get_address_id()
        return self.mcp.call_tool("get_food_cart", {"addressId": addr_id})

    def flush_cart(self) -> Dict[str, Any]:
        """Empty the cart via Swiggy MCP. flush_food_cart takes NO arguments."""
        return self.mcp.call_tool("flush_food_cart", {})

    def get_coupons(self, restaurant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return available coupons from Swiggy MCP.
        fetch_food_coupons requires restaurantId to return applicable coupons."""
        addr_id = self._get_address_id()
        args: Dict[str, Any] = {"addressId": addr_id}
        if restaurant_id:
            args["restaurantId"] = restaurant_id
        res = self.mcp.call_tool("fetch_food_coupons", args)
        return _extract_list(res, ("coupons", "data"))

    def apply_coupon(self, coupon_code: str) -> Dict[str, Any]:
        """Apply a coupon code and return updated cart totals."""
        addr_id = self._get_address_id()
        return self.mcp.call_tool("apply_food_coupon", {"couponCode": coupon_code, "addressId": addr_id})

    def add_to_cart(
        self,
        item_id: str,
        restaurant_id: str,
        quantity: int = 1,
        restaurant_name: str = "",
    ) -> Dict[str, Any]:
        """Add an item to the cart.
        Swiggy MCP uses 'cartItems' (not 'items') and requires restaurantId at top level."""
        addr_id = self._get_address_id()
        args: Dict[str, Any] = {
            "addressId": addr_id,
            "restaurantId": restaurant_id,
            "cartItems": [{"itemId": item_id, "quantity": quantity}],
        }
        if restaurant_name:
            args["restaurantName"] = restaurant_name
        return self.mcp.call_tool("update_food_cart", args)

    def place_order(self, address_id: Optional[str] = None) -> Dict[str, Any]:
        """Place a Cash on Delivery order and return the full response including orderId.
        Swiggy MCP requires paymentMethod='Cash' (not 'COD')."""
        addr_id = address_id or self._get_address_id()
        return self.mcp.call_tool(
            "place_food_order", {"addressId": addr_id, "paymentMethod": "Cash"}
        )

    def track_order(self, order_id: str) -> Dict[str, Any]:
        """Return live tracking information for an order."""
        return self.mcp.call_tool("track_food_order", {"orderId": order_id})

    def get_order_history(self) -> List[Dict[str, Any]]:
        """Return the user's recent order history."""
        res = self.mcp.call_tool("get_food_orders", {})
        return _extract_list(res, ("orders", "data"))

    def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Return full details for a specific order."""
        return self.mcp.call_tool("get_food_order_details", {"orderId": order_id})

    # ──────────────────────────────────────────────────────────────────
    # Direct Swiggy MCP Fallback (no LLM)
    # ──────────────────────────────────────────────────────────────────

    def _direct_mcp_search(self, query: str, veg_only: bool = False) -> List[FoodPick]:
        """Directly query Swiggy Food MCP search tools and extract live options.

        Uses structuredContent (via call_tool's new "data" field) for reliable
        structured extraction, falling back to plain-text parsing.
        """
        addr_id = self._get_address_id()
        clean_query = query.strip() or "food"

        # 1. Try search_menu — structuredContent gives {"items": [...]}
        try:
            res = self.mcp.call_tool("search_menu", {"query": clean_query, "addressId": addr_id})
            if res.get("success") and res.get("data"):
                data = res["data"]
                compressed = compress_search_results(data, veg_only=veg_only)
                if compressed:
                    picks = [
                        _dict_to_pick(item, rank_override=idx + 1)
                        for idx, item in enumerate(compressed[:3])
                    ]
                    if picks:
                        return picks
                # Fall back to text parsing if structuredContent had no items
                text = res.get("text", str(data))
                picks = parse_swiggy_mcp_text(text, veg_only=veg_only)
                if picks:
                    return picks
        except Exception as exc:
            logger.warning("Direct search_menu failed: %s", exc)

        # 2. Try search_restaurants fallback
        try:
            res = self.mcp.call_tool("search_restaurants", {"query": clean_query, "addressId": addr_id})
            if res.get("success") and res.get("data"):
                data = res["data"]
                compressed = compress_restaurants(data)
                if compressed:
                    picks = []
                    for idx, r in enumerate(compressed[:3]):
                        picks.append(FoodPick(
                            rank=idx + 1,
                            dish_name=f"Top dish at {r['name']}",
                            restaurant_name=r["name"],
                            price=None,
                            reasoning=f"{', '.join(r.get('cuisines', []))} · {r.get('sla', '')}",
                            restaurant_id=r["id"],
                            item_id=None,
                            veg=veg_only,
                            is_restaurant=True,
                            cuisine=", ".join(r.get("cuisines", [])),
                            rating=str(r.get("rating", "")),
                            delivery_time=r.get("sla", ""),
                        ))
                    if picks:
                        return picks
                text = res.get("text", str(data))
                picks = parse_swiggy_mcp_text(text, veg_only=veg_only)
                if picks:
                    return picks
        except Exception as exc:
            logger.warning("Direct search_restaurants failed: %s", exc)

        return []

    # ──────────────────────────────────────────────────────────────────
    # Internal routing
    # ──────────────────────────────────────────────────────────────────

    def _build_prompt(self, query_or_answers: Union[IntakeAnswers, str]) -> Tuple[bool, str, str]:
        """Return (veg_only, prompt_string, search_term).

        search_term is the CLEAN query for MCP tool calls — it must never contain
        preference labels like '(Hunger: 😋 Proper Meal, Mood: 🍲 Comfort)'.
        """
        if isinstance(query_or_answers, IntakeAnswers):
            veg_only = query_or_answers.preference.lower() in ("veg", "vegetarian", "jain")
            search_term = f"{query_or_answers.mood} {query_or_answers.hunger}"
            prompt = build_recommendation_prompt(query_or_answers)
            return veg_only, prompt, search_term

        query_str = str(query_or_answers)

        # Strip any appended preference context "(Hunger: …, Mood: …, Dietary: …)"
        # that app.py appends before passing the query — keep only the clean user text.
        clean_query = re.sub(r"\s*\([^)]*(?:Hunger|Mood|Dietary|Diet)[^)]*\)", "", query_str, flags=re.IGNORECASE).strip()
        clean_query = clean_query.strip(" ,")

        veg_only = any(t in query_str.lower() for t in ("veg", "vegetarian", "pure veg", "jain"))
        constraint = (
            "STRICT REQUIREMENT: Provide ONLY 100% VEGETARIAN options. "
            "Do NOT suggest chicken, mutton, egg, fish, or any meat."
            if veg_only
            else ""
        )
        prompt = (
            f"User Food Request: {clean_query}\n"
            f"{constraint}\n\n"
            "INSTRUCTIONS:\n"
            "1. Call get_addresses() to get the delivery addressId.\n"
            f"2. Call search_menu(query=\"{clean_query}\", addressId=<from step 1>).\n"
            "3. If fewer than 3 menu items are returned, also call "
            f"search_restaurants(query=\"{clean_query}\", addressId=<from step 1>).\n"
            "4. Output the top 3 picks as the standard JSON block using ONLY real MCP data."
        )
        # search_term is the CLEAN query — used by _direct_mcp_search and Ollama pre-fetch
        return veg_only, prompt, clean_query

    def _run_loop(
        self,
        user_prompt: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        dispatch = {
            "ollama": self._run_ollama,
            "gemini": self._run_gemini,
            "anthropic": self._run_anthropic,
            "openai": self._run_openai,
        }
        return dispatch[self._provider](user_prompt, log_callback)

    # ──────────────────────────────────────────────────────────────────
    # Ollama (local) — pre-fetch live data, then single-shot generation
    # ──────────────────────────────────────────────────────────────────

    def _run_ollama(
        self,
        user_prompt: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Run the full multi-turn tool-call loop via Ollama's OpenAI-compatible API.

        llama3.1:8b (and later) supports the OpenAI tool-call format natively when
        served through 'ollama serve'.  We use the same loop as _run_openai, just
        pointed at localhost.

        If tool-call support is absent (older models / unexpected response format),
        we fall back to a single-shot generation with pre-fetched live Swiggy data
        injected into the prompt.
        """
        import openai as _openai

        client = _openai.OpenAI(base_url=settings.ollama_base_url, api_key="ollama")
        model_name = settings.llm_model or settings.ollama_model or "llama3.1:8b"

        # Only send the 3 discovery tools — sending all 18 overflows llama3.1:8b's
        # effective context for tool schemas and causes it to ignore tool_choice.
        _OLLAMA_TOOLS = {"get_addresses", "search_menu", "search_restaurants"}
        all_tools = self.mcp.list_tools()
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            for t in all_tools
            if t["name"] in _OLLAMA_TOOLS
        ]

        # Concise system prompt — llama3.1:8b ignores long system prompts and writes
        # prose when the system message is multi-paragraph.
        OLLAMA_SYSTEM = (
            "You are a Swiggy food assistant. Use tools to answer. "
            "Step 1: call get_addresses. "
            "Step 2: call search_menu with the user's query and the addressId from step 1. "
            'Step 3: reply with ONLY valid JSON: {"picks":[{"rank":1,"dishName":"...",'
            '"restaurantName":"...","price":0,"veg":true,"restaurantId":"...","itemId":"...",'
            '"reasoning":"..."}]} — 3 items, real data only, no extra text.'
        )

        # Strip the INSTRUCTIONS block from the user prompt — for Ollama the system
        # prompt carries all instructions; the user message must be the bare query.
        bare_query = re.sub(
            r"\n+INSTRUCTIONS:.*",
            "",
            user_prompt,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        # Also strip the "User Food Request:" prefix if present
        bare_query = re.sub(r"^user food request:\s*", "", bare_query, flags=re.IGNORECASE).strip()

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": OLLAMA_SYSTEM},
            {"role": "user", "content": bare_query},
        ]

        # Fixed turn sequence for llama3.1:8b:
        # Turn 0 → force get_addresses (pin the tool so model can't batch calls)
        # Turn 1 → force search_menu   (now it has the real addressId)
        # Turn 2+ → auto               (model decides when to return final JSON)
        _TURN_TOOL: Dict[int, Any] = {
            0: {"type": "function", "name": "get_addresses"},
            1: {"type": "function", "name": "search_menu"},
        }

        for turn in range(settings.agent_max_turns):
            _log(log_callback, f"Turn {turn + 1} — Ollama ({model_name})")

            tool_choice: Any = _TURN_TOOL.get(turn, "auto")

            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice=tool_choice,
                )
            except Exception as err:
                logger.warning("Ollama tool-call request failed (turn %d): %s", turn + 1, err)
                return self._run_ollama_fallback(user_prompt, log_callback)

            msg = response.choices[0].message
            logger.info(
                "Ollama turn %d — tool_calls=%s content_preview=%s",
                turn + 1,
                [tc.function.name for tc in (msg.tool_calls or [])],
                (msg.content or "")[:120],
            )

            # No tool calls → model produced a final answer
            if not msg.tool_calls:
                content = msg.content or ""
                if content.strip():
                    return content
                logger.warning("Ollama returned empty content with no tool calls on turn %d", turn + 1)
                return self._run_ollama_fallback(user_prompt, log_callback)

            # Last turn — return whatever text we have
            if turn == settings.agent_max_turns - 1:
                return msg.content or ""

            # Execute ONLY the first tool call each turn.
            # llama3.1:8b sometimes emits multiple calls in one turn; we execute
            # only the expected one to keep the address → search chain strict.
            messages.append(msg)
            tc = msg.tool_calls[0]
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            # If Turn 1 produced search_menu but the addressId looks fake, replace it
            # with the real one we already have cached.
            if name == "search_menu":
                real_addr = self._get_address_id()
                if args.get("addressId") in (None, "", "address from get_addresses",
                                             "address_id_from_get_addresses", "<addressId>"):
                    args["addressId"] = real_addr
                    logger.info("Replaced hallucinated addressId with real: %s", real_addr)

            _log(log_callback, f"🛠 {name}({json.dumps(args)})")
            result = self._execute_tool(name, args)

            # After get_addresses completes, cache the real address and inject it
            # into the search_menu call on the next turn via the system.
            if name == "get_addresses":
                addr_id = _extract_address_id(result)
                if addr_id:
                    self._cached_address_id = addr_id
                    logger.info("Cached real addressId from turn %d: %s", turn + 1, addr_id)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })

        return ""

    def _run_ollama_fallback(
        self,
        user_prompt: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Single-shot fallback for Ollama models that don't support tool calls.
        Pre-fetches live Swiggy data and injects it directly into the prompt.
        """
        import openai as _openai

        client = _openai.OpenAI(base_url=settings.ollama_base_url, api_key="ollama")
        model_name = settings.llm_model or settings.ollama_model or "llama3.1:8b"

        # Extract the clean search query from the first meaningful line of the prompt
        clean_query = "food"
        for line in user_prompt.splitlines():
            line = line.strip()
            if line and not line.upper().startswith("INSTRUCTION") and not line.startswith("-"):
                clean_query = re.sub(r"^user food request:\s*", "", line, flags=re.IGNORECASE).strip()
                if clean_query:
                    break

        swiggy_data_str = ""
        try:
            addr_id = self._get_address_id()
            res = self.mcp.call_tool("search_menu", {"query": clean_query, "addressId": addr_id})
            if res.get("success") and res.get("data"):
                compressed = compress_search_results(res["data"])
                swiggy_data_str = json.dumps(compressed[:10], ensure_ascii=False)
        except Exception as exc:
            logger.warning("Ollama fallback live search failed: %s", exc)

        if swiggy_data_str:
            enhanced_prompt = (
                f"{user_prompt}\n\n"
                f"LIVE SWIGGY MENU DATA (from Swiggy API):\n{swiggy_data_str}\n\n"
                "INSTRUCTION: Use the live Swiggy data above. Select and rank the top 3 best "
                "matching dishes. Use the EXACT itemName→dishName, restaurantName, "
                "price (numeric), isVeg→veg, restaurantId, itemId fields from the data. "
                "Output a JSON object with a top-level 'picks' array."
            )
        else:
            enhanced_prompt = user_prompt

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": CONCIERGE_SYSTEM_PROMPT},
            {"role": "user", "content": enhanced_prompt},
        ]

        _log(log_callback, f"Turn 1 (fallback) — Ollama ({model_name})")
        try:
            res = client.chat.completions.create(
                model=model_name, messages=messages, response_format={"type": "json_object"}
            )
            return res.choices[0].message.content or ""
        except Exception as err:
            logger.warning("Ollama fallback structured output failed: %s — trying plain text", err)
            try:
                res = client.chat.completions.create(model=model_name, messages=messages)
                return res.choices[0].message.content or ""
            except Exception as err2:
                logger.warning("Ollama fallback execution failed: %s", err2)
                return ""

    # ──────────────────────────────────────────────────────────────────
    # Veg enforcement
    # ──────────────────────────────────────────────────────────────────

    def _enforce_veg(self, picks: List[FoodPick], veg_only: bool) -> List[FoodPick]:
        """Remove non-veg items when veg_only=True."""
        if not veg_only:
            return picks

        clean: List[FoodPick] = []
        for p in picks:
            name_lower = p.dish_name.lower()
            if not p.veg or any(t in name_lower for t in _NON_VEG_TERMS):
                logger.warning("Filtered non-veg pick under veg-only mode: '%s'", p.dish_name)
                continue
            clean.append(p)
        return clean

    # ──────────────────────────────────────────────────────────────────
    # Gemini — full multi-turn tool-call loop
    # ──────────────────────────────────────────────────────────────────

    def _run_gemini(
        self,
        user_prompt: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        from google import genai
        from google.genai import types as gtypes

        client = genai.Client(api_key=settings.gemini_api_key)
        tools = self.mcp.list_tools()

        candidate_models = [settings.llm_model, "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        model_name = next((m for m in candidate_models if m), "gemini-2.0-flash")

        func_declarations = [
            gtypes.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=_json_schema_to_gemini_schema(t.get("inputSchema", {})),
            )
            for t in tools
        ]

        contents: List[Any] = [user_prompt]
        max_turns = settings.agent_max_turns

        for turn in range(max_turns):
            _log(log_callback, f"Turn {turn + 1}/{max_turns} — Gemini ({model_name})")

            response = None
            for retry in range(3):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=gtypes.GenerateContentConfig(
                            system_instruction=CONCIERGE_SYSTEM_PROMPT,
                            tools=[gtypes.Tool(function_declarations=func_declarations)],
                        ),
                    )
                    break
                except Exception as err:
                    err_s = str(err).lower()
                    if any(t in err_s for t in ("429", "resource_exhausted", "503", "502", "connection")):
                        wait = (retry + 1) * 3
                        _log(log_callback, f"⏳ Gemini rate-limit/network — retry in {wait}s…")
                        logger.warning("Gemini transient error (retry %d/3): %s", retry + 1, err)
                        time.sleep(wait)
                    else:
                        raise

            if not response or not response.candidates:
                logger.warning("Gemini returned no candidates on turn %d", turn + 1)
                break

            contents.append(response.candidates[0].content)
            calls = response.function_calls

            if not calls or turn == max_turns - 1:
                return response.text or ""

            parts = []
            for call in calls:
                name, args = call.name, dict(call.args or {})
                _log(log_callback, f"🛠 {name}({json.dumps(args)})")
                result = self._execute_tool(name, args)
                parts.append(gtypes.Part.from_function_response(name=name, response=result))

            contents.append(gtypes.Content(role="user", parts=parts))

        return ""

    # ──────────────────────────────────────────────────────────────────
    # OpenAI — full multi-turn tool-call loop
    # ──────────────────────────────────────────────────────────────────

    def _run_openai(
        self,
        user_prompt: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        import openai as _openai

        client = _openai.OpenAI(api_key=settings.openai_api_key)
        tools = self.mcp.list_tools()
        model_name = settings.llm_model or "gpt-4o"

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": CONCIERGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        for turn in range(settings.agent_max_turns):
            _log(log_callback, f"Turn {turn + 1} — OpenAI ({model_name})")
            res = client.chat.completions.create(
                model=model_name, messages=messages, tools=openai_tools
            )
            msg = res.choices[0].message
            messages.append(msg)

            if not msg.tool_calls or turn == settings.agent_max_turns - 1:
                return msg.content or ""

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")
                _log(log_callback, f"🛠 {name}({json.dumps(args)})")
                result = self._execute_tool(name, args)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}
                )

        return ""

    # ──────────────────────────────────────────────────────────────────
    # Anthropic — full multi-turn tool-call loop
    # ──────────────────────────────────────────────────────────────────

    def _run_anthropic(
        self,
        user_prompt: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        import anthropic as _anthropic

        client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
        tools = self.mcp.list_tools()
        model_name = settings.llm_model or "claude-3-5-sonnet-latest"

        ant_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t.get("inputSchema", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]

        messages: List[Dict[str, Any]] = [{"role": "user", "content": user_prompt}]

        for turn in range(settings.agent_max_turns):
            _log(log_callback, f"Turn {turn + 1} — Anthropic ({model_name})")
            res = client.messages.create(
                model=model_name,
                max_tokens=4096,
                system=CONCIERGE_SYSTEM_PROMPT,
                tools=ant_tools,
                messages=messages,
            )

            tool_uses = [b for b in res.content if b.type == "tool_use"]
            text_blocks = [b.text for b in res.content if b.type == "text"]

            if res.stop_reason == "end_turn" or not tool_uses or turn == settings.agent_max_turns - 1:
                return "\n".join(text_blocks)

            messages.append({"role": "assistant", "content": res.content})

            tool_results = []
            for tu in tool_uses:
                name, args = tu.name, tu.input or {}
                _log(log_callback, f"🛠 {name}({json.dumps(args)})")
                result = self._execute_tool(name, args)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(result)}
                )

            messages.append({"role": "user", "content": tool_results})

        return ""

    # ──────────────────────────────────────────────────────────────────
    # Tool execution with optional compression
    # ──────────────────────────────────────────────────────────────────

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Swiggy MCP tool and compress results for large-payload tools."""
        result = self.mcp.call_tool(name, args)
        if name in _COMPRESS_TOOLS:
            data = result.get("data")
            if data is not None:
                if name == "search_restaurants":
                    compressed = compress_restaurants(data)
                else:
                    # search_menu and get_restaurant_menu
                    compressed = compress_search_results(data)
                result["data"] = compressed
                logger.debug("Compressed tool output for '%s' → %d items", name, len(compressed))
        return result


# ──────────────────────────────────────────────────────────────────────────────
# Helpers — address extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_address_id(res: Dict[str, Any]) -> Optional[str]:
    """
    Robustly extract the FIRST real addressId from a get_addresses MCP response.

    After the call_tool normalisation, the envelope is always:
      {"success": True, "data": <str | list | dict>}

    The Swiggy MCP returns plain text like:
      "Found 7 saved addresses (page 1 of 1, showing 7):\n
       1. [KT PG] SAHIT SSVK: kamakshi gents pg, … (ID: d4722bhjqdcnkdef8450)\n
       2. …"

    We search ALL address IDs and return the first one found.
    """
    if not isinstance(res, dict):
        return None

    data = res.get("data")

    # Structured list — {"data": [{"addressId": "...", ...}, ...]}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                addr_id = item.get("addressId") or item.get("id")
                if addr_id:
                    return str(addr_id)

    # Structured dict wrapping a list — {"data": {"addresses": [...]}}
    if isinstance(data, dict):
        for key in ("addresses", "savedAddresses", "data"):
            lst = data.get(key)
            if isinstance(lst, list):
                for item in lst:
                    if isinstance(item, dict):
                        addr_id = item.get("addressId") or item.get("id")
                        if addr_id:
                            return str(addr_id)

    # Plain-text response — search for every "(ID: <value>)" occurrence and
    # return the FIRST match.  The Swiggy MCP format is:
    #   "… Karnataka 560017, India (ID: d4722bhjqdcnkdef8450)"
    text = data if isinstance(data, str) else ""
    if text:
        # Match "(ID: <alphanumeric>)" — greedy match for the full ID value
        m = re.search(r"\(ID:\s*([a-zA-Z0-9_\-]+)\)", text)
        if m:
            logger.info("Extracted addressId from text: %s", m.group(1))
            return m.group(1)
        # Fallback: "addressId: <value>" or "ID: <value>" without parentheses
        m = re.search(r"(?:addressId|ID):\s*([a-zA-Z0-9_\-]{8,})", text, re.IGNORECASE)
        if m:
            logger.info("Extracted addressId (fallback regex): %s", m.group(1))
            return m.group(1)

    return None


def _extract_list(res: Dict[str, Any], keys: tuple) -> List[Dict[str, Any]]:
    """Extract a list from a nested MCP response trying multiple key paths."""
    if not isinstance(res, dict):
        return []
    for key in keys:
        val = res.get(key)
        if isinstance(val, list):
            return val
    data = res.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


def _log(callback: Optional[Callable[[str], None]], msg: str) -> None:
    logger.info(msg)
    if callback:
        callback(msg)


def _dict_to_pick(d: Dict[str, Any], rank_override: Optional[int] = None) -> FoodPick:
    """Convert a dict (from LLM JSON, structuredContent, or compressed data) to a FoodPick.

    Handles field names from:
      - LLM output:           dishName, restaurantName, restaurantId, itemId
      - search_menu SC:       name, restaurant_name, restaurant_id, menu_item_id, price, isVeg
      - compressed results:   itemName, restaurantName, restaurantId, itemId
    """
    raw_price = d.get("price") or d.get("finalPrice")
    parsed_price = None
    if raw_price is not None:
        if isinstance(raw_price, (int, float)):
            parsed_price = float(raw_price)
        elif isinstance(raw_price, str):
            cleaned = re.sub(r"[^\d\.]", "", raw_price).strip()
            if cleaned:
                try:
                    parsed_price = float(cleaned)
                except ValueError:
                    parsed_price = None

    return FoodPick(
        rank=rank_override if rank_override is not None else d.get("rank", 1),
        dish_name=(
            d.get("dishName") or d.get("dish_name")
            or d.get("itemName") or d.get("name") or "Dish"
        ),
        restaurant_name=(
            d.get("restaurantName") or d.get("restaurant_name") or "Restaurant"
        ),
        price=parsed_price,
        reasoning=d.get("reasoning", ""),
        restaurant_id=(
            d.get("restaurantId") or d.get("restaurant_id")
        ),
        item_id=(
            d.get("itemId") or d.get("item_id")
            or d.get("menu_item_id") or d.get("id")
        ),
        veg=bool(d.get("veg") or d.get("isVeg", False)),
    )


def parse_swiggy_mcp_text(text: str, veg_only: bool = False) -> List[FoodPick]:
    """Extract structured FoodPick items from Swiggy MCP plain-text responses.

    Handles the real text format returned by search_menu:
      "1. Palak Paneer — ₹267 | Veg | 4.5★ | ITC Aashirvaad Soul Creations (restaurantId: 640763) (ID: 146277265) [has addons]"

    And search_restaurants:
      "1. Domino's Pizza (Ad) — Pizzas, Italian | 4.4★ | 20 min | ₹400 for two (ID: 38957)"
    """
    picks: List[FoodPick] = []
    lines = text.splitlines()

    # 1. Parse menu search items
    # Format: "N. Dish Name — ₹PRICE | Veg/Non-Veg | RATING★ | Restaurant Name (restaurantId: X) (ID: Y) [...]"
    for line in lines:
        line_str = line.strip()
        if not line_str or not re.match(r"^\d+\.", line_str) or "— ₹" not in line_str:
            continue

        parts = line_str.split("— ₹", 1)
        dish_name = re.sub(r"^\d+\.\s*", "", parts[0]).strip()
        meta = parts[1]

        # Split on "|" — segments: [price, veg_flag, rating_or_restaurant, restaurant_or_id...]
        segments = [s.strip() for s in meta.split("|")]

        price_str = re.sub(r"[^\d\.]", "", segments[0]).strip()
        try:
            price_val = float(price_str)
        except ValueError:
            price_val = 250.0

        # Veg detection — segment containing "Veg" but not "Non-Veg"
        is_veg = any(
            re.search(r"\bveg\b", s, re.IGNORECASE) and not re.search(r"\bnon.?veg\b", s, re.IGNORECASE)
            for s in segments
        )
        if veg_only and not is_veg:
            continue

        # Extract restaurantId and item ID from anywhere in the line
        rest_id_match = re.search(r"\(restaurantId:\s*([a-zA-Z0-9_\-]+)\)", line_str)
        item_id_match = re.search(r"\(ID:\s*([a-zA-Z0-9_\-]+)\)", line_str)
        rest_id = rest_id_match.group(1) if rest_id_match else None
        item_id = item_id_match.group(1) if item_id_match else None

        # Restaurant name is the last text segment before "(restaurantId:..."
        # Strip the IDs and addons annotations from the last segment
        last_seg = segments[-1]
        rest_name_raw = re.sub(r"\s*\(restaurantId:.*$", "", last_seg)
        rest_name_raw = re.sub(r"\s*\(ID:.*$", "", rest_name_raw)
        rest_name_raw = re.sub(r"\s*\[.*?\]", "", rest_name_raw)
        # Also strip a rating token like "4.5★" that may appear in this segment
        rest_name_raw = re.sub(r"\b\d+\.\d+★\s*", "", rest_name_raw).strip()
        rest_name_clean = rest_name_raw or "Swiggy Restaurant"

        picks.append(
            FoodPick(
                rank=len(picks) + 1,
                dish_name=dish_name,
                restaurant_name=rest_name_clean,
                price=price_val,
                reasoning=f"Fresh {dish_name} from {rest_name_clean}.",
                restaurant_id=rest_id,
                item_id=item_id,
                veg=is_veg,
            )
        )
        if len(picks) >= 3:
            break

    # 2. Parse restaurant search items if menu items not found
    # Format: "N. Restaurant Name (Ad) — cuisines | RATING★ | TIME min | ₹PRICE for two (ID: X)"
    if not picks:
        for line in lines:
            # Match: number. Name — cuisines | rating | time | ₹price for two (ID: X)
            m = re.match(
                r"^\d+\.\s+(.*?)(?:\s*\(Ad\))?\s*—\s*([^|]+?)\s*\|\s*[\d\.]+★\s*\|\s*[\d\-]+ min\s*\|\s*₹(\d+)\s*for two(?:\s*\(ID:\s*([a-zA-Z0-9_\-]+)\))?",
                line.strip(),
            )
            if m:
                rest_name, cuisines_str, price_for_two, rest_id = m.groups()
                rest_clean = rest_name.strip()
                cuisine_first = cuisines_str.split(",")[0].strip()
                is_veg = "veg" in cuisines_str.lower() and "non" not in cuisines_str.lower()
                if veg_only and not is_veg:
                    continue

                picks.append(
                    FoodPick(
                        rank=len(picks) + 1,
                        dish_name=f"Chef's Special {cuisine_first}",
                        restaurant_name=rest_clean,
                        price=float(price_for_two) / 2,
                        reasoning=f"Top-rated {cuisines_str.strip()} at {rest_clean}.",
                        restaurant_id=rest_id,
                        item_id=None,
                        veg=is_veg,
                        is_restaurant=True,
                        cuisine=cuisines_str.strip(),
                    )
                )
                if len(picks) >= 3:
                    break

    return picks


def extract_picks(text: str, veg_only: bool = False) -> List[FoodPick]:
    """Parse a structured FoodPick list from the agent's text output or Swiggy MCP response."""
    raw_list: List[Dict[str, Any]] = []

    # 1 — JSON code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if m:
        raw_list = _try_parse_picks(m.group(1))

    # 2 — bare JSON object in the full text
    if not raw_list:
        raw_list = _try_parse_picks(text)

    # 3 — top-level JSON array
    if not raw_list:
        arr_m = re.search(r"\[\s*\{[\s\S]*?\}\s*\]", text)
        if arr_m:
            try:
                arr = json.loads(arr_m.group(0))
                if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                    raw_list = arr
            except Exception:
                pass

    picks: List[FoodPick] = []

    if raw_list:
        for item in raw_list:
            if isinstance(item, dict):
                is_veg = item.get("veg") or item.get("isVeg", False)
                picks.append(_dict_to_pick({**item, "veg": is_veg}, rank_override=len(picks) + 1))
    else:
        # 4 — Swiggy MCP text parser fallback
        picks = parse_swiggy_mcp_text(text, veg_only=veg_only)

        # 5 — regex fallback for numbered lists in prose
        if not picks:
            pattern = r"(?:^|\n)(?:#|\d+\.|\*)\s*([^\n—\-]+)[—\-]\s*(?:₹|INR)?\s*(\d+)?\s*(?:from|at)?\s*([^\n]+)?"
            for idx, (dish, price_str, rest) in enumerate(re.findall(pattern, text)[:3]):
                picks.append(
                    FoodPick(
                        rank=idx + 1,
                        dish_name=dish.strip(),
                        restaurant_name=rest.strip() if rest else "Recommended Restaurant",
                        price=float(price_str) if price_str else None,
                        reasoning="Curated option matching your food preference.",
                        restaurant_id=None,
                        item_id=None,
                        veg=True if veg_only else ("veg" in text.lower()),
                    )
                )

    return picks


def _try_parse_picks(text: str) -> List[Dict[str, Any]]:
    """Try to extract the 'picks' list from a JSON string. Returns [] on failure."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            candidates = parsed.get("picks") or parsed.get("recommendations") or []
            if isinstance(candidates, list):
                return candidates
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed
    except Exception:
        pass
    return []
