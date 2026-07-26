#!/usr/bin/env python3
"""
Interactive CLI — 3-question intake → 3 curated picks → optional COD order.

    python scripts/main.py
"""
import logging
import os
import sys

from dotenv import load_dotenv

# Make the src package importable when run from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from concierge import (
    FoodConciergeAgent,
    FoodPick,
    IntakeAnswers,
    SwiggyFoodMcpClient,
)

_BANNER = """
╔══════════════════════════════════════════════════════════╗
║       AI FOOD CONCIERGE · Swiggy MCP                     ║
║   3 questions → 3 curated picks → order in seconds       ║
╚══════════════════════════════════════════════════════════╝
"""

_HUNGER = [
    ("1", "snack",        "Snack — something small"),
    ("2", "pretty_hungry","Pretty hungry — a proper meal"),
    ("3", "starving",     "Extremely hungry — big feast"),
]

_MOOD = [
    ("1", "comfort", "Comfort — familiar & satisfying"),
    ("2", "spicy",   "Spicy — heat it up"),
    ("3", "healthy", "Healthy — light and clean"),
    ("4", "treat",   "Treat — something indulgent"),
]

_PREF = [
    ("1", "none",    "No restriction"),
    ("2", "veg",     "Vegetarian"),
    ("3", "jain",    "Jain"),
    ("4", "non_veg", "Non-vegetarian"),
]


def _ask(title: str, options: list[tuple[str, str, str]]) -> str:
    print(f"\n{title}")
    for key, _, label in options:
        print(f"  {key}. {label}")
    valid = {o[0] for o in options}
    while True:
        try:
            choice = input(f"Your choice (1-{len(options)}): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if choice in valid:
            return next(o[1] for o in options if o[0] == choice)
        print(f"  Please enter one of: {sorted(valid)}")


def _print_picks(picks: list[FoodPick]) -> None:
    print("\n── Your 3 picks ────────────────────────────────────\n")
    for p in picks:
        price = f" · ₹{int(p.price)}" if p.price is not None else ""
        tag = "🟢 Veg" if p.veg else "🔴 Non-Veg"
        print(f"  {p.rank}. {p.dish_name}{price}  [{tag}]")
        print(f"     {p.restaurant_name}")
        print(f"     {p.reasoning}\n")


def main() -> None:
    print(_BANNER)

    if not os.getenv("SWIGGY_ACCESS_TOKEN"):
        print("SWIGGY_ACCESS_TOKEN missing — run 'python scripts/auth.py' first.")
        sys.exit(1)

    try:
        client = SwiggyFoodMcpClient()
        tools = client.list_tools()
        print(f"Connected to Swiggy Food MCP — {len(tools)} tools available.\n")

        agent = FoodConciergeAgent(client)
        answers = IntakeAnswers(
            hunger=_ask("Q1 · How hungry are you?", _HUNGER),
            mood=_ask("Q2 · What's your mood?", _MOOD),
            preference=_ask("Q3 · Dietary preference?", _PREF),
        )

        print(f"\nHunger: {answers.hunger}  Mood: {answers.mood}  Pref: {answers.preference}")
        print("\nSearching Swiggy … (Swiggy MCP + LLM)\n")

        picks, raw = agent.recommend(answers, log_callback=lambda m: print(f"  {m}"))

        if not picks:
            print("\nNo structured picks returned. Raw agent response:\n")
            print(raw)
            return

        _print_picks(picks)

        try:
            choice = input("Select a pick (1-3) or q to quit: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return

        if choice == "q":
            return

        idx = int(choice) - 1
        if 0 <= idx < len(picks):
            selected = picks[idx]
            print(f"\nBuilding cart for: {selected.dish_name} …\n")
            result = agent.order_selected_pick(selected, log_callback=lambda m: print(f"  {m}"))
            print(f"\n{result}")
        else:
            print("Invalid selection.")

    except Exception as exc:
        print(f"Fatal error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
