"""
AI Food Concierge — Streamlit Web UI
Production entry point. Run with: streamlit run app.py
"""
from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from typing import Optional  # noqa: E402 — must come after sys.path patch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("concierge.app")

from concierge import (  # noqa: E402
    FoodConciergeAgent,
    FoodPick,
    IntakeAnswers,
    SwiggyFoodMcpClient,
)
from concierge.middleware.compression import extract_cart_summary, extract_order_id  # noqa: E402

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Food Concierge",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# CSS — Premium Dark & Vibrant Food Concierge Theme
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
}

/* ── App background & layout dimensions ── */
.stApp {
    background: #0d1117 !important;
    color: #f0f6fc !important;
}

.block-container {
    padding: 1.5rem 2rem 6rem 2rem !important;
    max-width: 1080px !important;
    margin: 0 auto !important;
}

/* Header styling — transparent header background, visible styled sidebar toggle icon */
header[data-testid="stHeader"] {
    background: transparent !important;
    height: 3.5rem !important;
    pointer-events: none !important;
}

header[data-testid="stHeader"] * {
    pointer-events: auto !important;
}

[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarToggle"],
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    background: #161b22 !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 10px !important;
    color: #FC8019 !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
    transition: all 0.2s ease !important;
}

[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarToggle"] button,
[data-testid="collapsedControl"] button {
    color: #FC8019 !important;
}

[data-testid="stSidebarCollapseButton"]:hover,
[data-testid="stSidebarToggle"]:hover,
[data-testid="collapsedControl"]:hover {
    background: #21262d !important;
    border-color: #FC8019 !important;
    transform: scale(1.05);
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #161b22 !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    min-width: 280px !important;
    max-width: 280px !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
}

[data-testid="stSidebarContent"] {
    padding: 1.25rem 1rem !important;
}

/* ── Sidebar Brand ── */
.brand-section {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 6px 16px 6px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 16px;
}

.brand-icon {
    width: 44px;
    height: 44px;
    background: linear-gradient(135deg, #FC8019 0%, #E65100 100%);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    box-shadow: 0 4px 12px rgba(252, 128, 25, 0.3);
    flex-shrink: 0;
}

.brand-name {
    font-size: 16px;
    font-weight: 800;
    color: #ffffff;
    margin: 0;
    line-height: 1.2;
    letter-spacing: -0.3px;
}

.brand-tagline {
    font-size: 11.5px;
    color: #8b949e;
    margin: 2px 0 0 0;
}

.nav-header-label {
    font-size: 11px;
    font-weight: 700;
    color: #8b949e;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin: 14px 4px 8px 4px;
}

/* Sidebar nav buttons styling */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: 1px solid transparent !important;
    color: #c9d1d9 !important;
    text-align: left !important;
    justify-content: flex-start !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 8px 12px !important;
    border-radius: 10px !important;
    transition: all 0.15s ease !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255, 255, 255, 0.06) !important;
    color: #ffffff !important;
    border-color: rgba(255, 255, 255, 0.1) !important;
}

[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: rgba(252, 128, 25, 0.15) !important;
    border: 1px solid rgba(252, 128, 25, 0.4) !important;
    color: #FC8019 !important;
    font-weight: 700 !important;
}

/* ── Sidebar Preferences Card ── */
.pref-card {
    background: #0d1117;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 12px 14px;
    margin: 12px 0;
}

.pref-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 12.5px;
}

.pref-label {
    color: #8b949e;
    display: flex;
    align-items: center;
    gap: 6px;
}

.pref-value {
    color: #f0f6fc;
    font-weight: 600;
}

/* ── Ingredient Upload Card ── */
.upload-card {
    background: linear-gradient(180deg, rgba(16, 185, 129, 0.08) 0%, rgba(13, 17, 23, 0) 100%);
    border: 1px dashed rgba(16, 185, 129, 0.3);
    border-radius: 12px;
    padding: 14px;
    margin: 14px 0 8px 0;
    text-align: center;
}

.upload-card-title {
    font-size: 13px;
    font-weight: 700;
    color: #10b981;
    margin-bottom: 4px;
}

.upload-card-sub {
    font-size: 11.5px;
    color: #8b949e;
    line-height: 1.4;
    margin-bottom: 8px;
}

/* ── Top Header Bar ── */
.top-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0 20px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 20px;
}

.header-title {
    font-size: 24px;
    font-weight: 800;
    color: #ffffff;
    margin: 0 0 4px 0;
    letter-spacing: -0.5px;
}

.header-subtitle {
    font-size: 13.5px;
    color: #8b949e;
    margin: 0;
}

.mcp-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: #34d399;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 20px;
}

/* ── Welcome Empty State ── */
.welcome-container {
    background: #161b22;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 32px 24px;
    text-align: center;
    margin-bottom: 24px;
}

.welcome-icon {
    font-size: 48px;
    margin-bottom: 12px;
}

.welcome-title {
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 8px;
}

.welcome-sub {
    font-size: 14px;
    color: #8b949e;
    max-width: 500px;
    margin: 0 auto 20px auto;
    line-height: 1.5;
}

/* ── Recommendation Cards Grid ── */
[data-testid="stVerticalBlock"] > div:has(div.card-hero) {
    height: 100%;
}

.card-hero {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}

.card-hero-icon {
    width: 42px;
    height: 42px;
    background: rgba(252, 128, 25, 0.12);
    border: 1px solid rgba(252, 128, 25, 0.25);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
}

.card-rank-badge {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #FC8019;
    font-size: 12px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 20px;
}

.card-title-text {
    font-size: 15px;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 4px;
    line-height: 1.3;
}

.card-sub-text {
    font-size: 12px;
    color: #8b949e;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
}

.tag-badge {
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 6px;
}

.tag-badge-nonveg {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 6px;
}

.card-reasoning {
    font-size: 12px;
    color: #9ca3af;
    line-height: 1.45;
    margin-bottom: 12px;
    font-style: italic;
    min-height: 34px;
}

/* ── Checkout Card ── */
.checkout-card {
    background: #161b22;
    border: 1px solid rgba(252, 128, 25, 0.4);
    border-radius: 16px;
    padding: 20px;
    margin: 16px 0;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}

.checkout-header {
    font-size: 12px;
    font-weight: 700;
    color: #FC8019;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    margin-bottom: 8px;
}

.checkout-item {
    font-size: 18px;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 4px;
}

.checkout-meta {
    font-size: 13px;
    color: #8b949e;
    margin-bottom: 16px;
}

.order-success-box {
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.4);
    border-radius: 16px;
    padding: 24px;
    text-align: center;
    margin: 16px 0;
}

.order-success-title {
    font-size: 22px;
    font-weight: 800;
    color: #34d399;
    margin-bottom: 6px;
}

/* ── Setup & Error Banners ── */
.setup-card {
    background: rgba(245, 158, 11, 0.1);
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: 14px;
    padding: 24px;
    text-align: center;
    margin: 20px 0;
}

.setup-title {
    font-size: 18px;
    font-weight: 700;
    color: #fbbf24;
    margin-bottom: 10px;
}

.setup-step {
    background: #161b22;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 10px 14px;
    margin: 6px 0;
    font-size: 13px;
    color: #c9d1d9;
    text-align: left;
}

.setup-step code {
    background: rgba(255, 255, 255, 0.1);
    color: #fbbf24;
    padding: 2px 6px;
    border-radius: 4px;
}

/* ── Streamlit Widget Overrides ── */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.15s ease !important;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #FC8019 0%, #E65100 100%) !important;
    border: none !important;
    color: #ffffff !important;
    box-shadow: 0 4px 12px rgba(252, 128, 25, 0.25) !important;
}

.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 16px rgba(252, 128, 25, 0.4) !important;
    transform: translateY(-1px);
}

[data-testid="stChatInput"] {
    max-width: 1080px !important;
    margin: 0 auto !important;
}

[data-testid="stChatInput"] > div {
    background: #161b22 !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 14px !important;
}

[data-testid="stChatInput"] textarea {
    color: #f0f6fc !important;
    font-size: 14px !important;
}

[data-testid="stChatInput"] textarea::placeholder {
    color: #8b949e !important;
}

[data-testid="stChatInput"] button {
    background: #FC8019 !important;
    border-radius: 10px !important;
}

.input-disclaimer {
    text-align: center;
    font-size: 11.5px;
    color: #6e7681;
    margin-top: 10px;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
_NAV_ITEMS = [
    ("🏠", "Home"),
    ("⭐", "Recommendations"),
    ("📅", "Meal Planner"),
    ("📍", "Find Restaurants"),
    ("📖", "Food Knowledge"),
    ("☆", "Favorites"),
]

_WELCOME_SUGGESTIONS = [
    ("🥗", "Healthy High-Protein", "High protein meal under 600 calories"),
    ("🌶️", "Spicy Vegetarian", "Spicy paneer or curry options"),
    ("🍕", "Snack under ₹200", "Quick budget bite delivered fast"),
    ("🍲", "Comfort Food", "Warm, soothing bowls & thalis"),
    ("🌱", "Gluten-Free Lunch", "Wholesome gluten-free options"),
    ("🍰", "Sweet Treat", "Best desserts near me"),
]

_QUICK_REPLY_SUGGESTIONS = [
    "More vegetarian options",
    "Low-carb high protein meals",
    "Quick breakfast ideas",
    "Nearby healthy restaurants",
]

_HUNGER_OPTS = ["snack", "pretty_hungry", "starving"]
_HUNGER_LABELS = {"snack": "🥨 Quick Snack", "pretty_hungry": "😋 Proper Meal", "starving": "🔥 Full Feast"}
_MOOD_OPTS = ["comfort", "spicy", "healthy", "treat"]
_MOOD_LABELS = {"comfort": "🍲 Comfort", "spicy": "🌶 Spicy", "healthy": "🥗 Healthy", "treat": "🍰 Sweet"}
_PREF_OPTS = ["none", "veg", "jain", "non_veg"]
_PREF_LABELS = {"none": "⚪ Any", "veg": "🟢 Veg", "jain": "🟡 Jain", "non_veg": "🔴 Non-Veg"}
_PREF_DISPLAY = {"none": "Any", "veg": "Vegetarian", "jain": "Jain", "non_veg": "Non-Veg"}

# ──────────────────────────────────────────────────────────────────────────────
# Session-state initialisation
# ──────────────────────────────────────────────────────────────────────────────
def _init_state() -> None:
    if "mcp_client" not in st.session_state:
        try:
            st.session_state.mcp_client = SwiggyFoodMcpClient()
            st.session_state.mcp_connected = True
            st.session_state.mcp_error = None
        except Exception as err:
            st.session_state.mcp_client = None
            st.session_state.mcp_connected = False
            st.session_state.mcp_error = str(err)
            logger.warning("MCP client init failed: %s", err)

    if "agent" not in st.session_state:
        if st.session_state.get("mcp_connected"):
            try:
                st.session_state.agent = FoodConciergeAgent(st.session_state.mcp_client)
                st.session_state.agent_error = None
            except Exception as err:
                st.session_state.agent = None
                st.session_state.agent_error = str(err)
                logger.warning("Agent init failed: %s", err)
        else:
            st.session_state.agent = None
            st.session_state.agent_error = None

    defaults = {
        "messages": [],
        "active_nav": "Home",
        "filter_hunger": "pretty_hungry",
        "filter_mood": "comfort",
        "filter_pref": "none",
        "edit_prefs": False,
        "checkout_pick": None,
        "saved_addresses": [],
        "selected_address": None,
        "cart_built": False,
        "cart_summary": None,      # real cart data from get_food_cart
        "available_coupons": [],   # coupons from fetch_food_coupons
        "applied_coupon": None,    # applied coupon code
        "order_placed": False,
        "order_result": None,
        "order_id": None,          # real orderId from place_food_order
        "order_tracking": None,    # live tracking data from track_food_order
        "show_filters": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _parse_addresses(raw: Any) -> list:
    """Parse the Swiggy MCP get_addresses response into a list of address dicts.

    The MCP returns plain text via structuredContent-less responses:
      "Found 7 saved addresses (page 1 of 1, showing 7):\n
       1. [Label] Name: street, area, city (ID: abc123)\n
       2. ..."

    We extract the real addressId with the "(ID: ...)" regex.
    """
    if not isinstance(raw, dict):
        return []

    # Prefer structured data if available
    data = raw.get("data")

    # If data is a list of address dicts (future SC format)
    if isinstance(data, list):
        result = []
        for a in data:
            if isinstance(a, dict) and (a.get("addressId") or a.get("id")):
                addr_id = a.get("addressId") or str(a.get("id", ""))
                label = a.get("label") or a.get("displayText") or a.get("alias") or ""
                area = a.get("area") or a.get("city") or ""
                display = f"{label} — {area}" if label and area else (label or area or addr_id)
                result.append({"addressId": addr_id, "displayText": display})
        if result:
            return result

    # Plain text format (most common)
    text = raw.get("text", "") or (data if isinstance(data, str) else "")
    if not text:
        return []

    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Found"):
            continue
        # Match: "N. [Label] Name: ...street..., City (ID: addressId)"
        id_match = re.search(r"\(ID:\s*([a-zA-Z0-9_\-]+)\)", line)
        if not id_match:
            continue
        addr_id = id_match.group(1)
        # Strip the leading "N. " and the "(ID: ...)" suffix for display
        display = re.sub(r"^\d+\.\s*", "", line)
        display = re.sub(r"\s*\(ID:.*$", "", display).strip()
        result.append({"addressId": addr_id, "displayText": display})

    return result


def _parse_price_val(price_val: Any) -> Optional[float]:
    if price_val is None:
        return None
    if isinstance(price_val, (int, float)):
        return float(price_val)
    if isinstance(price_val, str):
        cleaned = re.sub(r"[^\d\.]", "", price_val).strip()
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                pass
    return None


def _price_display(pick: FoodPick) -> str:
    val = _parse_price_val(pick.price)
    if val is not None:
        return f"₹{int(val)}"
    return "~₹250"


def _default_addresses() -> list:
    return [{"addressId": "d4722bhjqdcnkdef8450", "displayText": "Home — Bengaluru"}]


def _reset_chat() -> None:
    st.session_state.messages = []
    st.session_state.checkout_pick = None
    st.session_state.cart_built = False
    st.session_state.cart_summary = None
    st.session_state.available_coupons = []
    st.session_state.applied_coupon = None
    st.session_state.order_placed = False
    st.session_state.order_result = None
    st.session_state.order_id = None
    st.session_state.order_tracking = None
    st.session_state.show_filters = False


def _clean_assistant_text(raw_text: str, picks: list[FoodPick] = None) -> str:
    """Remove raw JSON codeblocks and return engaging, clean markdown explanation."""
    if not raw_text:
        raw_text = ""
    clean = re.sub(r"```json[\s\S]*?```", "", raw_text, flags=re.IGNORECASE).strip()
    clean = re.sub(r"```[\s\S]*?```", "", clean).strip()

    if not clean and picks:
        lines = ["Here are the top live options found on Swiggy for your query:\n"]
        for p in picks:
            price_str = _price_display(p)
            reason = p.reasoning or "Top choice matching your preferences."
            lines.append(f"• **{p.dish_name}** from *{p.restaurant_name}* ({price_str}) — {reason}")
        clean = "\n".join(lines)
    return clean


def _run_query(query: str) -> None:
    """
    Append user message, call agent with active sidebar preferences as IntakeAnswers
    when the query is a food request (not a specific restaurant lookup or general chat),
    then append the authentic assistant answer and rerun.
    """
    hunger = st.session_state.get("filter_hunger", "pretty_hungry")
    mood = st.session_state.get("filter_mood", "comfort")
    pref = st.session_state.get("filter_pref", "none")

    # Decide whether to pass structured IntakeAnswers or a raw string query.
    # Use IntakeAnswers for welcome-prompt triggers; use raw string for typed chat.
    query_lower = query.lower()
    _welcome_triggers = {q.lower() for _, _, q in _WELCOME_SUGGESTIONS}
    use_intake = query_lower in _welcome_triggers and st.session_state.get("active_nav") == "Home"

    if use_intake:
        query_obj: Any = IntakeAnswers(hunger=hunger, mood=mood, preference=pref)
    else:
        # Append preference context to the free-text query
        pref_context = []
        hunger_label = _HUNGER_LABELS.get(hunger, "")
        mood_label = _MOOD_LABELS.get(mood, "")
        pref_label = _PREF_DISPLAY.get(pref, "")
        if hunger_label:
            pref_context.append(f"Hunger: {hunger_label}")
        if mood_label:
            pref_context.append(f"Mood: {mood_label}")
        if pref_label and pref_label != "Any":
            pref_context.append(f"Dietary: {pref_label}")
        query_obj = f"{query} ({', '.join(pref_context)})" if pref_context else query

    st.session_state.messages.append({"role": "user", "content": query, "picks": []})
    with st.spinner("Thinking & finding answers for you…"):
        try:
            picks, raw = st.session_state.agent.recommend(query_obj)
            clean_text = _clean_assistant_text(raw, picks=picks)

            if not clean_text:
                clean_text = (
                    f"I searched Swiggy for *\"{query}\"*, but couldn't find exact matches right now. "
                    "Try rephrasing or asking another food question!"
                )

            st.session_state.messages.append(
                {"role": "assistant", "content": clean_text, "picks": picks}
            )
        except Exception as err:
            st.session_state.messages.append(
                {"role": "assistant", "content": f"⚠️ Processing error: {err}", "picks": []}
            )
    st.rerun()


def _render_food_cards(picks: list[FoodPick], msg_idx: int) -> None:
    """Render a responsive grid of food or restaurant cards."""
    if not picks:
        return

    num_cards = min(len(picks), 3)
    cols = st.columns(num_cards)

    for i, pick in enumerate(picks[:num_cards]):
        with cols[i]:
            with st.container(border=True):
                if pick.is_restaurant:
                    rating_badge = f"#{pick.rank} &nbsp;·&nbsp; ⭐ {pick.rating or '4.3★'}"
                    st.markdown(f"""
<div class="card-hero">
    <div class="card-hero-icon">🏪</div>
    <div class="card-rank-badge">{rating_badge}</div>
</div>
<div class="card-title-text">{pick.restaurant_name}</div>
<div class="card-sub-text">📍 {pick.cuisine} &nbsp;•&nbsp; ⏱ {pick.delivery_time}</div>
<div class="card-reasoning">{pick.reasoning}</div>
""", unsafe_allow_html=True)
                    if st.button(
                        "📖 Explore Menu",
                        key=f"card_rest_{msg_idx}_{pick.rank}_{i}",
                        type="primary",
                        use_container_width=True,
                    ):
                        _run_query(f"View menu items for {pick.restaurant_name} restaurantId: {pick.restaurant_id}")
                else:
                    veg_tag = (
                        "<span class='tag-badge'>🌱 Veg</span>"
                        if pick.veg
                        else "<span class='tag-badge-nonveg'>🔴 Non-Veg</span>"
                    )
                    price = _price_display(pick)
                    icon = "🥗" if pick.veg else "🍗"

                    st.markdown(f"""
<div class="card-hero">
    <div class="card-hero-icon">{icon}</div>
    <div class="card-rank-badge">#{pick.rank} &nbsp;·&nbsp; {price}</div>
</div>
<div class="card-title-text">{pick.dish_name}</div>
<div class="card-sub-text">📍 {pick.restaurant_name} &nbsp;•&nbsp; {veg_tag}</div>
<div class="card-reasoning">{pick.reasoning}</div>
""", unsafe_allow_html=True)

                    if st.button(
                        f"🛒 Order — {price}",
                        key=f"card_order_{msg_idx}_{pick.rank}_{i}",
                        type="primary",
                        use_container_width=True,
                    ):
                        st.session_state.checkout_pick = pick
                        st.session_state.cart_built = False
                        st.session_state.order_placed = False
                        with st.spinner("Fetching delivery addresses…"):
                            try:
                                raw = st.session_state.mcp_client.call_tool("get_addresses")
                                addrs = _parse_addresses(raw)
                                if not addrs:
                                    addrs = _default_addresses()
                            except Exception as exc:
                                logger.warning("get_addresses failed: %s", exc)
                                addrs = _default_addresses()
                        st.session_state.saved_addresses = addrs
                        st.session_state.selected_address = addrs[0] if addrs else None
                        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    # Brand Header
    st.markdown("""
<div class="brand-section">
    <div class="brand-icon">🍽️</div>
    <div>
        <p class="brand-name">AI Food Concierge</p>
        <p class="brand-tagline">Powered by Swiggy MCP</p>
    </div>
</div>""", unsafe_allow_html=True)

    # New Chat Primary Action
    if st.button("💬  New Chat", use_container_width=True, key="new_chat_btn", type="primary"):
        _reset_chat()
        st.session_state.active_nav = "Home"
        st.rerun()

    # Navigation Section
    st.markdown("<div class='nav-header-label'>NAVIGATE</div>", unsafe_allow_html=True)
    _nav_query_map = {
        "Recommendations": "Give me today's top food recommendations",
        "Meal Planner": "Help me plan my meals for the week",
        "Find Restaurants": "Find the best restaurants near me",
        "Food Knowledge": "Tell me interesting food facts and nutrition tips",
        "Favorites": "Show my favorite dishes",
    }

    for icon, label in _NAV_ITEMS:
        is_active = st.session_state.active_nav == label
        btn_type = "primary" if is_active else "secondary"
        if st.button(
            f"{icon}  {label}",
            key=f"nav_btn_{label}",
            use_container_width=True,
            type=btn_type,
        ):
            st.session_state.active_nav = label
            if label in _nav_query_map and st.session_state.mcp_connected:
                _reset_chat()
                _run_query(_nav_query_map[label])
            elif label == "Home":
                _reset_chat()
                st.rerun()

    # Preferences Panel
    st.markdown("<div class='nav-header-label'>PREFERENCES</div>", unsafe_allow_html=True)
    
    if st.session_state.edit_prefs:
        st.session_state.filter_hunger = st.selectbox(
            "Hunger level",
            _HUNGER_OPTS,
            index=_HUNGER_OPTS.index(st.session_state.filter_hunger),
            format_func=lambda x: _HUNGER_LABELS[x],
            key="pref_hunger_sel",
        )
        st.session_state.filter_mood = st.selectbox(
            "Mood",
            _MOOD_OPTS,
            index=_MOOD_OPTS.index(st.session_state.filter_mood),
            format_func=lambda x: _MOOD_LABELS[x],
            key="pref_mood_sel",
        )
        st.session_state.filter_pref = st.selectbox(
            "Dietary preference",
            _PREF_OPTS,
            index=_PREF_OPTS.index(st.session_state.filter_pref),
            format_func=lambda x: _PREF_LABELS[x],
            key="pref_diet_sel",
        )
        if st.button("✅ Save Preferences", use_container_width=True, key="save_prefs", type="primary"):
            st.session_state.edit_prefs = False
            st.rerun()
    else:
        pref_hunger = st.session_state.filter_hunger
        pref_mood = st.session_state.filter_mood
        pref_diet = st.session_state.filter_pref
        
        st.markdown(f"""
<div class="pref-card">
    <div class="pref-row">
        <span class="pref-label"><span>🍽️</span> Hunger</span>
        <span class="pref-value">{_HUNGER_LABELS[pref_hunger]}</span>
    </div>
    <div class="pref-row">
        <span class="pref-label"><span>😊</span> Mood</span>
        <span class="pref-value">{_MOOD_LABELS[pref_mood]}</span>
    </div>
    <div class="pref-row">
        <span class="pref-label"><span>🥗</span> Diet</span>
        <span class="pref-value">{_PREF_LABELS[pref_diet]}</span>
    </div>
</div>""", unsafe_allow_html=True)
        
        if st.button("✏️ Edit Preferences", use_container_width=True, key="edit_prefs_btn"):
            st.session_state.edit_prefs = True
            st.rerun()

    # Ingredient Upload Card
    st.markdown("""
<div class="upload-card">
    <div style="font-size:24px;margin-bottom:4px;">🧺</div>
    <div class="upload-card-title">Upload Kitchen Ingredients</div>
    <div class="upload-card-sub">Get personalized recipes based on ingredients you have.</div>
</div>""", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Upload a photo or list",
        type=["jpg", "jpeg", "png", "txt"],
        label_visibility="collapsed",
        key="ingredient_upload",
    )
    if uploaded is not None:
        if st.button("🔍 Suggest Recipes", type="primary", use_container_width=True, key="upload_search"):
            _run_query("I uploaded my ingredients. Please suggest healthy recipes I can make.")

    # Status & Footer
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    if st.session_state.mcp_connected:
        st.markdown("<div class='mcp-badge' style='width:100%; justify-content:center;'>🟢 Swiggy MCP Ready</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='mcp-badge' style='width:100%; justify-content:center; background:rgba(239,68,68,0.15); border-color:rgba(239,68,68,0.3); color:#f87171;'>🔴 MCP Setup Required</div>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Main Area — Top Header Bar
# ──────────────────────────────────────────────────────────────────────────────
col_title, col_actions = st.columns([5, 1], vertical_alignment="center")
with col_title:
    st.markdown("""
<div class="top-header" style="border-bottom:none; margin-bottom:0; padding-bottom:0;">
    <div>
        <div class="header-title">👋 Hello! I'm your AI Food Concierge</div>
        <div class="header-subtitle">Discover dishes, plan meals, find restaurants &amp; order via Swiggy MCP</div>
    </div>
</div>""", unsafe_allow_html=True)

with col_actions:
    if st.button("🗑 Clear", key="clear_chat_top", use_container_width=True):
        _reset_chat()
        st.rerun()

st.markdown("<div style='border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 20px; padding-bottom: 12px;'></div>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Setup / Error Banners
# ──────────────────────────────────────────────────────────────────────────────
if not st.session_state.mcp_connected:
    st.markdown(f"""
<div class="setup-card">
    <div class="setup-title">⚙️ Setup Required — Swiggy MCP</div>
    <p style="color:#c9d1d9;font-size:14px;margin-bottom:16px;">
        Complete the one-time authentication to start ordering.
    </p>
    <div class="setup-step">1. Run <code>python src/auth.py</code> in your terminal</div>
    <div class="setup-step">2. Complete Phone + OTP login in the browser tab</div>
    <div class="setup-step">3. Token auto-saves to <code>.env</code> — restart the application</div>
    <p style="color:#8b949e;font-size:12px;margin-top:14px;">
        Error: {st.session_state.mcp_error or 'ACCESS_TOKEN not set'}
    </p>
</div>
""", unsafe_allow_html=True)
    st.stop()

if st.session_state.get("agent_error"):
    st.markdown(
        f'<div style="background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); border-radius:10px; padding:12px 16px; color:#f87171; font-size:13px; margin:8px 0;">⚠️ <strong>LLM Agent Error:</strong> {st.session_state.agent_error}</div>',
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Empty State — Welcome Hero & Quick Suggestions
# ──────────────────────────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown("""
<div class="welcome-container">
    <div class="welcome-icon">🍽️</div>
    <div class="welcome-title">What are you craving today?</div>
    <div class="welcome-sub">
        Ask me about specific dishes, restaurants, dietary meal plans, or nutrition — or select a prompt below to get started immediately.
    </div>
</div>""", unsafe_allow_html=True)

    # Suggestion Grid — 3 columns x 2 rows
    cols = st.columns(3)
    for i, (icon, title, query) in enumerate(_WELCOME_SUGGESTIONS):
        with cols[i % 3]:
            st.markdown(f"""
<div style="background:#161b22; border:1px solid rgba(255,255,255,0.08); border-radius:12px 12px 0 0; padding:14px 14px 10px 14px; min-height:85px;">
    <div style="font-size:20px; margin-bottom:4px;">{icon}</div>
    <div style="font-weight:700; color:#ffffff; font-size:13.5px; margin-bottom:2px;">{title}</div>
    <div style="color:#8b949e; font-size:11.5px; line-height:1.3;">{query}</div>
</div>""", unsafe_allow_html=True)
            if st.button("Explore →", key=f"welcome_sug_{i}", use_container_width=True):
                _run_query(query)
            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)



# ──────────────────────────────────────────────────────────────────────────────
# Chat Message Stream
# ──────────────────────────────────────────────────────────────────────────────
for msg_idx, msg in enumerate(st.session_state.messages):
    role = msg["role"]
    content = msg["content"]
    picks: list[FoodPick] = msg.get("picks", [])

    with st.chat_message(role, avatar="👤" if role == "user" else "🤖"):
        st.markdown(content)

        if picks:
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            _render_food_cards(picks, msg_idx)

        # Quick-reply chips after the last assistant message
        if msg_idx == len(st.session_state.messages) - 1 and picks:
            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
            chip_cols = st.columns(len(_QUICK_REPLY_SUGGESTIONS))
            for ci, chip_text in enumerate(_QUICK_REPLY_SUGGESTIONS):
                with chip_cols[ci]:
                    if st.button(chip_text, key=f"chip_{msg_idx}_{ci}"):
                        _run_query(chip_text)

# ──────────────────────────────────────────────────────────────────────────────
# Checkout Flow Card
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.checkout_pick and not st.session_state.order_placed:
    pick: FoodPick = st.session_state.checkout_pick
    price_str = _price_display(pick)

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(f"""
<div class="checkout-header">🛒 Checkout Details</div>
<div class="checkout-item">{pick.dish_name}</div>
<div class="checkout-meta">📍 {pick.restaurant_name} &nbsp;•&nbsp; Total: <strong style="color:#FC8019;">{price_str}</strong></div>
""", unsafe_allow_html=True)

        st.markdown("**Select Delivery Address:**")
        if st.session_state.saved_addresses:
            addr_labels = [
                a.get("displayText") or a.get("label") or a.get("addressId", f"Address {i+1}")
                for i, a in enumerate(st.session_state.saved_addresses)
            ]
            selected_idx = st.radio(
                "address",
                range(len(addr_labels)),
                format_func=lambda i: f"📍 {addr_labels[i]}",
                label_visibility="collapsed",
            )
            st.session_state.selected_address = st.session_state.saved_addresses[selected_idx]
            addr_id = st.session_state.selected_address.get("addressId", "d4722bhjqdcnkdef8450")
        else:
            addr_id = "d4722bhjqdcnkdef8450"

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        if not st.session_state.cart_built:
            if st.button("🛒 Verify Cart", type="primary", use_container_width=True, key="verify_cart"):
                if not pick.item_id or not pick.restaurant_id:
                    st.error(
                        "⚠️ This item is missing a real Swiggy item ID or restaurant ID. "
                        "Please choose a different recommendation."
                    )
                else:
                    with st.spinner("Adding to cart…"):
                        try:
                            # Step 1: add item to cart
                            st.session_state.mcp_client.call_tool(
                                "update_food_cart",
                                {
                                    "addressId": addr_id,
                                    "items": [
                                        {
                                            "itemId": pick.item_id,
                                            "quantity": 1,
                                            "restaurantId": pick.restaurant_id,
                                        }
                                    ],
                                },
                            )
                            # Step 2: fetch real cart to confirm
                            cart_res = st.session_state.mcp_client.call_tool(
                                "get_food_cart", {"addressId": addr_id}
                            )
                            st.session_state.cart_summary = extract_cart_summary(cart_res)
                            st.session_state.cart_built = True

                            # Step 3: pre-fetch coupons in background
                            try:
                                coupon_res = st.session_state.mcp_client.call_tool(
                                    "fetch_food_coupons", {"addressId": addr_id}
                                )
                                from concierge.agent.core import _extract_list
                                st.session_state.available_coupons = _extract_list(
                                    coupon_res, ("coupons", "data")
                                )
                            except Exception:
                                st.session_state.available_coupons = []

                            st.rerun()
                        except Exception as err:
                            st.error(f"Cart verification failed: {err}")
        else:
            # ── Cart verified — show real cart summary ────────────────────
            cart_summary = st.session_state.cart_summary
            if cart_summary:
                st.markdown("**🛒 Cart Summary:**")
                for ci in cart_summary.get("items", []):
                    qty = ci.get("quantity", 1)
                    prc = ci.get("price")
                    prc_str = f"₹{int(prc)}" if prc is not None else ""
                    st.markdown(
                        f"- {ci.get('name', 'Item')} × {qty} &nbsp; {prc_str}",
                        unsafe_allow_html=True,
                    )
                grand = cart_summary.get("grandTotal")
                delivery = cart_summary.get("deliveryFee")
                discount = cart_summary.get("discount")
                if delivery is not None:
                    st.markdown(f"🚴 Delivery fee: **₹{int(delivery)}**")
                if discount:
                    st.markdown(f"🏷️ Discount: **-₹{int(discount)}**")
                if grand is not None:
                    st.markdown(f"**💰 Grand Total: ₹{int(grand)}**")
            else:
                st.success("✅ Cart verified — ready to place order!")

            # ── Coupon picker ──────────────────────────────────────────────
            coupons = st.session_state.available_coupons
            if coupons and not st.session_state.applied_coupon:
                st.markdown("**🎟️ Available Coupons:**")
                coupon_opts = ["No coupon"] + [
                    c.get("code", c.get("couponCode", "COUPON"))
                    for c in coupons
                    if isinstance(c, dict)
                ]
                chosen_coupon = st.selectbox(
                    "Apply a coupon", coupon_opts, key="coupon_sel", label_visibility="collapsed"
                )
                if chosen_coupon and chosen_coupon != "No coupon":
                    if st.button("Apply Coupon", key="apply_coupon_btn"):
                        with st.spinner("Applying coupon…"):
                            try:
                                coupon_res = st.session_state.mcp_client.call_tool(
                                    "apply_food_coupon",
                                    {"addressId": addr_id, "couponCode": chosen_coupon},
                                )
                                st.session_state.applied_coupon = chosen_coupon
                                # Refresh cart summary after coupon
                                cart_res = st.session_state.mcp_client.call_tool(
                                    "get_food_cart", {"addressId": addr_id}
                                )
                                st.session_state.cart_summary = extract_cart_summary(cart_res)
                                st.rerun()
                            except Exception as err:
                                st.error(f"Coupon failed: {err}")
            elif st.session_state.applied_coupon:
                st.success(f"✅ Coupon **{st.session_state.applied_coupon}** applied!")

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

            col_a, col_b = st.columns([2, 1])
            with col_a:
                if st.button("🚀 Place COD Order", type="primary", use_container_width=True, key="place_order"):
                    with st.spinner("Placing your order…"):
                        try:
                            result = st.session_state.mcp_client.call_tool(
                                "place_food_order", {"addressId": addr_id, "paymentMethod": "COD"}
                            )
                            order_id = extract_order_id(result)
                            st.session_state.order_placed = True
                            st.session_state.order_result = result
                            st.session_state.order_id = order_id

                            # Fetch real tracking immediately
                            if order_id:
                                try:
                                    tracking = st.session_state.mcp_client.call_tool(
                                        "track_food_order", {"orderId": order_id}
                                    )
                                    st.session_state.order_tracking = tracking
                                except Exception:
                                    st.session_state.order_tracking = None

                            st.rerun()
                        except Exception as err:
                            st.error(f"Order failed: {err}")
            with col_b:
                if st.button("✕ Cancel", use_container_width=True, key="cancel_order"):
                    # Flush the cart on cancellation
                    try:
                        st.session_state.mcp_client.call_tool(
                            "flush_food_cart", {"addressId": addr_id}
                        )
                    except Exception:
                        pass
                    st.session_state.checkout_pick = None
                    st.session_state.cart_built = False
                    st.session_state.cart_summary = None
                    st.session_state.applied_coupon = None
                    st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# Order Confirmation Banner
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.order_placed and st.session_state.checkout_pick:
    pick = st.session_state.checkout_pick
    price_str = _price_display(pick)
    addr_label = (
        st.session_state.selected_address.get("displayText", "Your address")
        if st.session_state.selected_address
        else "Your address"
    )

    # Build real ETA from tracking data
    tracking = st.session_state.get("order_tracking")
    order_id = st.session_state.get("order_id", "")
    if tracking and isinstance(tracking, dict):
        track_data = tracking.get("data", tracking)
        if not isinstance(track_data, dict):
            track_data = {}
        eta = (
            track_data.get("estimatedDeliveryTime")
            or track_data.get("eta")
            or track_data.get("deliveryEta")
            or track_data.get("slaString")
        )
        driver_name = track_data.get("driverName") or track_data.get("agentName")
        eta_line = f"⏱️ Estimated delivery: <strong>{eta}</strong>" if eta else "⏱️ Estimated delivery: tracking…"
        driver_line = f"🛵 Driver: {driver_name}" if driver_name else ""
    else:
        eta_line = "⏱️ Tracking your order…"
        driver_line = ""

    order_id_html = f"<p style='color:#8b949e; font-size:12px; margin-top:4px;'>Order ID: <code>{order_id}</code></p>" if order_id else ""
    driver_html = f"<p style='color:#8b949e; font-size:13px; margin:2px 0;'>{driver_line}</p>" if driver_line else ""

    st.balloons()
    st.markdown(
        f"<div class='order-success-box'>"
        f"<div class='order-success-title'>🎉 Order Placed Successfully!</div>"
        f"<p style='color:#ffffff; font-weight:700; font-size:15px; margin:6px 0 2px;'>{pick.dish_name} from {pick.restaurant_name}</p>"
        f"<p style='color:#8b949e; font-size:13px; margin:0;'>📍 {addr_label} &nbsp;•&nbsp; 💳 Cash on Delivery ({price_str})</p>"
        f"{order_id_html}"
        f"<p style='color:#34d399; font-size:13px; margin-top:6px; font-weight:600;'>{eta_line}</p>"
        f"{driver_html}"
        f"</div>",
        unsafe_allow_html=True,
    )

    success_msg = (
        f"✅ **Order confirmed!** Your *{pick.dish_name}* from {pick.restaurant_name} "
        f"({price_str}) is on its way to {addr_label}. Payment: Cash on Delivery."
    )
    if order_id:
        success_msg += f" Order ID: `{order_id}`."
    if not any(m.get("content", "").startswith("✅ **Order confirmed!") for m in st.session_state.messages):
        st.session_state.messages.append({"role": "assistant", "content": success_msg, "picks": []})



# ──────────────────────────────────────────────────────────────────────────────
# Chat Input & Disclaimer
# ──────────────────────────────────────────────────────────────────────────────
if user_input := st.chat_input("Ask me anything about food, dishes, restaurants, or recipes…"):
    _run_query(user_input)

st.markdown(
    "<div class='input-disclaimer'>AI-generated recommendations. Please verify ingredients for dietary restrictions and allergies.</div>",
    unsafe_allow_html=True,
)
