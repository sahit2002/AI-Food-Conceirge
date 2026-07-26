#!/usr/bin/env python3
"""
Dry-run demo — no API keys or network access required.

Simulates the full Swiggy MCP response cycle to showcase the
concierge flow end-to-end.

    python scripts/demo.py
"""
import os
import sys
import time

# Make the src package importable when run from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from concierge import (
    IntakeAnswers,
    build_search_signals,
    compact_json,
    compress_restaurants,
    compress_search_results,
    signals_to_prompt_block,
)

# ──────────────────────────────────────────────────────────────
# Mock Swiggy MCP payloads
# ──────────────────────────────────────────────────────────────

MOCK_ADDRESSES = {
    "success": True,
    "data": [
        {"addressId": "addr_home_blr", "label": "Home", "displayText": "Koramangala 5th Block, Bengaluru"},
        {"addressId": "addr_work_blr", "label": "Work", "displayText": "Indiranagar, Bengaluru"},
    ],
}

MOCK_SEARCH_RESTAURANTS = {
    "success": True,
    "data": {
        "restaurants": [
            {
                "id": f"rest_{i + 1}",
                "name": ["Meghana Foods", "Truffles", "A2B", "Nagarjuna", "Biryani House", "Theobroma"][i % 6],
                "rating": round(4.2 + (i % 3) * 0.2, 1),
                "distance": f"{1.2 + i * 0.3:.1f} km",
                "availabilityStatus": "CLOSED" if i == 5 else "OPEN",
                "cuisines": ["North Indian", "Biryani", "South Indian"][: 1 + (i % 3)],
            }
            for i in range(12)
        ]
    },
}

MOCK_SEARCH_MENU = {
    "success": True,
    "data": {
        "items": [
            {"itemId": "item_1", "itemName": "Hyderabadi Chicken Biryani", "finalPrice": 349, "isVeg": False},
            {"itemId": "item_2", "itemName": "Paneer Butter Masala Meal",  "finalPrice": 279, "isVeg": True},
            {"itemId": "item_3", "itemName": "Masala Dosa Combo",          "finalPrice": 189, "isVeg": True},
            {"itemId": "item_4", "itemName": "Kolkata Roll (Egg)",         "finalPrice": 149, "isVeg": False},
            {"itemId": "item_5", "itemName": "Dal Khichdi Bowl",           "finalPrice": 199, "isVeg": True},
            {"itemId": "item_6", "itemName": "Butter Chicken Rice Bowl",   "finalPrice": 329, "isVeg": False},
        ]
    },
}


def _divider(title: str) -> None:
    print(f"\n{'─' * 58}")
    print(f"  {title}")
    print(f"{'─' * 58}\n")


def run() -> None:
    print("""
╔════════════════════════════════════════════════════════════╗
║      AI FOOD CONCIERGE — Demo (dry-run, no API keys)       ║
╚════════════════════════════════════════════════════════════╝
""")

    answers = IntakeAnswers(hunger="pretty_hungry", mood="comfort", preference="veg")

    _divider("STEP 1 · 3-Question Intake")
    print("  Q1  How hungry are you?      → Pretty hungry — a proper meal")
    print("  Q2  What's your mood?        → Comfort — familiar & satisfying")
    print("  Q3  Any dietary preference?  → Vegetarian\n")
    print(f"  hunger={answers.hunger!r}  mood={answers.mood!r}  preference={answers.preference!r}")

    _divider("STEP 2 · India-Specific Intelligence Signals")
    signals = build_search_signals(answers)
    print(signals_to_prompt_block(signals))
    print("\n  ✓ Late-night comfort boost active (10 PM–4 AM window)")
    print("  ✓ Veg-only filter propagated to compression layer")

    _divider("STEP 3 · Swiggy MCP Tool Calls (simulated)")
    t0 = time.monotonic()

    print("  → get_addresses()")
    time.sleep(0.1)
    print(f"     {MOCK_ADDRESSES['data'][0]['displayText']}")

    print("\n  → search_restaurants({ query: 'biryani', addressId: '...' })")
    time.sleep(0.2)
    raw_rest_size = len(compact_json(MOCK_SEARCH_RESTAURANTS))
    compressed_rest = compress_restaurants(MOCK_SEARCH_RESTAURANTS)
    print(f"     Raw: {raw_rest_size} chars, 12 restaurants")
    print(f"     After compression: {len(compressed_rest)} OPEN restaurants forwarded to LLM")

    print("\n  → search_menu({ query: 'comfort veg', addressId: '...' })")
    time.sleep(0.2)
    raw_menu_size = len(compact_json(MOCK_SEARCH_MENU))
    compressed_menu = compress_search_results(MOCK_SEARCH_MENU["data"])
    compressed_size = len(compact_json(compressed_menu))
    print(f"     Raw: {raw_menu_size} chars  →  Compressed: {compressed_size} chars")

    elapsed = time.monotonic() - t0
    print(f"\n  ⏱  Simulated MCP round-trips: {elapsed:.2f}s")

    _divider("STEP 4 · 3 Ranked Picks")
    picks = [
        {"rank": 1, "dish": "Paneer Butter Masala Meal", "price": 279,
         "rest": "Truffles", "reason": "Vegetarian comfort thali — satisfying without being heavy."},
        {"rank": 2, "dish": "Masala Dosa Combo", "price": 189,
         "rest": "A2B - Adyar Ananda Bhavan", "reason": "South Indian classic — crisp, light, and regional."},
        {"rank": 3, "dish": "Dal Khichdi Bowl", "price": 199,
         "rest": "Meghana Foods", "reason": "Easy on the stomach, perfect comfort pick."},
    ]
    for p in picks:
        print(f"  {p['rank']}. {p['dish']} — ₹{p['price']}")
        print(f"     {p['rest']}")
        print(f"     {p['reason']}\n")

    _divider("STEP 5 · Order Flow (on user selection)")
    print("  User selects: #1 Paneer Butter Masala Meal\n")
    print("  → search_menu()        resolve item variant")
    print("  → update_food_cart()   add to cart")
    print("  → get_food_cart()      total: ₹279 (under ₹1 000 cap ✓)")
    print("\n  ⚠  Demo halts here — real orders require Swiggy OAuth.")

    _divider("COMPLETE")
    print("  Start the Streamlit UI:   streamlit run app.py")
    print("  Run the interactive CLI:  python scripts/main.py\n")


if __name__ == "__main__":
    run()
