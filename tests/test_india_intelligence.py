import sys
import os
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from concierge.models import IntakeAnswers
from concierge.middleware import build_search_signals, signals_to_prompt_block


class TestIndiaIntelligence(unittest.TestCase):

    def test_veg_comfort_signals(self):
        answers = IntakeAnswers(hunger="pretty_hungry", mood="comfort", preference="veg")
        dt = datetime(2026, 7, 26, 14, 0, 0)
        signals = build_search_signals(answers, current_time=dt)

        self.assertFalse(signals["is_late_night"])
        self.assertTrue(signals["veg_only"])
        self.assertEqual(signals["portion_size"], "medium")
        self.assertIn("biryani", signals["queries"])

    def test_late_night_signals(self):
        answers = IntakeAnswers(hunger="snack", mood="comfort", preference="none")
        dt = datetime(2026, 7, 26, 23, 30, 0)
        signals = build_search_signals(answers, current_time=dt)

        self.assertTrue(signals["is_late_night"])
        self.assertFalse(signals["veg_only"])
        self.assertEqual(signals["portion_size"], "small")

    def test_signals_to_prompt_block(self):
        signals = {
            "is_late_night": True,
            "portion_size": "large",
            "veg_only": True,
            "jain": False,
            "queries": ["biryani", "paneer"],
            "cuisines": ["north indian"],
        }
        block = signals_to_prompt_block(signals)
        self.assertIn("late-night", block)
        self.assertIn("vegetarian only", block.lower())


if __name__ == "__main__":
    unittest.main()
