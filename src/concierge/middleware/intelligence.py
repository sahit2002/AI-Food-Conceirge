from datetime import datetime
import logging
from typing import Dict, Any, List, Optional
from ..models.schema import IntakeAnswers

logger = logging.getLogger("concierge.middleware.intelligence")

def is_late_night(dt: Optional[datetime] = None) -> bool:
    """Detect late-night hours in IST (10 PM to 4 AM)."""
    now = dt or datetime.now()
    hour = now.hour
    return hour >= 22 or hour < 4

def build_search_signals(answers: IntakeAnswers, current_time: Optional[datetime] = None) -> Dict[str, Any]:
    """Build India-specific culinary signals based on intake answers and time of day."""
    late_night = is_late_night(current_time)
    
    hunger_portions = {
        "snack": "small",
        "pretty_hungry": "medium",
        "starving": "large"
    }
    portion_target = hunger_portions.get(answers.hunger, "medium")

    signals: Dict[str, Any] = {
        "is_late_night": late_night,
        "portion_size": portion_target,
        "veg_only": answers.preference.lower() in ("veg", "vegetarian"),
        "jain": answers.preference.lower() == "jain",
        "queries": [],
        "cuisines": []
    }

    if late_night:
        signals["queries"].extend(["biryani", "rolls", "paratha", "maggi", "burgers"])
    elif answers.mood == "comfort":
        signals["queries"].extend(["biryani", "dal khichdi", "paratha", "paneer butter masala"])
        signals["cuisines"].extend(["north indian", "south indian", "mughlai"])
    elif answers.mood == "healthy":
        signals["queries"].extend(["salad", "khichdi", "soup", "bowl"])
        signals["cuisines"].extend(["healthy food", "salads"])
    elif answers.mood == "treat":
        signals["queries"].extend(["pizza", "dessert", "pasta", "cake"])
    else:
        signals["queries"].extend(["thali", "combo", "meal"])

    logger.debug("Built India search signals: %s", signals)
    return signals

def signals_to_prompt_block(signals: Dict[str, Any]) -> str:
    """Format search signals as system prompt injection block."""
    lines = ["India-Specific Intelligence Context:"]
    if signals.get("is_late_night"):
        lines.append("- Time: LATE-NIGHT (10 PM–4 AM). Prioritize late-night comfort like biryani, rolls, and quick comfort items.")
    else:
        lines.append("- Time: Regular meal hours.")

    lines.append(f"- Portion Target: {signals.get('portion_size', 'medium').upper()}")

    if signals.get("veg_only"):
        lines.append("- Constraint: VEGETARIAN ONLY (no meat, fish, or egg). Filter strictly.")
    if signals.get("jain"):
        lines.append("- Constraint: JAIN VEGETARIAN (no onion, garlic, or root vegetables).")

    if signals.get("queries"):
        lines.append(f"- Recommended search terms: {', '.join(signals['queries'][:4])}")

    return "\n".join(lines)
