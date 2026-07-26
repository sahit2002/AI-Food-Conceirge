"""
AI Food Concierge — Swiggy Builders Club Production Package
Modular architecture divided into:
- api/          : Swiggy Food MCP HTTP Client
- agent/        : Multi-LLM Orchestrator & System Prompts
- middleware/   : Payload Compression & India-Intelligence Signals
- models/       : Dataclasses & Data Schemas
- config.py     : Application Configurations
"""

from .models import IntakeAnswers, FoodPick, ConciergeSession
from .api import SwiggyFoodMcpClient
from .middleware import (
    compress_restaurants,
    compress_search_results,
    compact_json,
    extract_cart_summary,
    extract_order_id,
    build_search_signals,
    signals_to_prompt_block,
    is_late_night,
)
from .agent import FoodConciergeAgent, extract_picks
from .config import settings, Settings

__all__ = [
    "IntakeAnswers",
    "FoodPick",
    "ConciergeSession",
    "SwiggyFoodMcpClient",
    "compress_restaurants",
    "compress_search_results",
    "compact_json",
    "extract_cart_summary",
    "extract_order_id",
    "build_search_signals",
    "signals_to_prompt_block",
    "is_late_night",
    "FoodConciergeAgent",
    "extract_picks",
    "settings",
    "Settings",
]
