from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class IntakeAnswers:
    """3-Question intake preferences from the user."""
    hunger: str  # e.g., 'snack', 'pretty_hungry', 'starving'
    mood: str    # e.g., 'comfort', 'healthy', 'treat', 'spicy'
    preference: str = "none"  # e.g., 'veg', 'jain', 'non_veg', 'none'

@dataclass
class FoodPick:
    """Ranked food pick or restaurant returned by the Concierge agent."""
    rank: int
    dish_name: str
    restaurant_name: str
    price: Optional[float] = None
    reasoning: str = ""
    restaurant_id: Optional[str] = None
    item_id: Optional[str] = None
    veg: bool = False
    is_restaurant: bool = False
    cuisine: str = ""
    rating: str = ""
    delivery_time: str = ""
    price_for_two: str = ""

@dataclass
class ConciergeSession:
    """Session state holding active intake, address, and recommendations."""
    address_id: Optional[str] = None
    address_label: Optional[str] = None
    answers: Optional[IntakeAnswers] = None
    picks: List[FoodPick] = field(default_factory=list)
    raw_response: str = ""
