import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from concierge.middleware import compress_restaurants, compress_search_results, compact_json


class TestContextCompression(unittest.TestCase):

    def test_compress_restaurants(self):
        raw = {
            "data": {
                "restaurants": [
                    {"id": "r1", "name": "Rest 1", "rating": 4.5, "availabilityStatus": "OPEN"},
                    {"id": "r2", "name": "Rest 2", "rating": 4.0, "availabilityStatus": "CLOSED"},
                ]
            }
        }
        compressed = compress_restaurants(raw)
        self.assertEqual(len(compressed), 1)
        self.assertEqual(compressed[0]["id"], "r1")
        self.assertEqual(compressed[0]["name"], "Rest 1")

    def test_compress_search_results(self):
        raw = {
            "data": {
                "items": [
                    {"itemId": "i1", "itemName": "Paneer Tikka", "finalPrice": 250, "isVeg": True},
                    {"itemId": "i2", "itemName": "Chicken Roll",  "finalPrice": 180, "isVeg": False},
                ]
            }
        }
        compressed = compress_search_results(raw)
        self.assertEqual(len(compressed), 2)
        self.assertEqual(compressed[0]["itemName"], "Paneer Tikka")
        self.assertTrue(compressed[0]["isVeg"])

    def test_compact_json(self):
        data = {"key": "val", "arr": [1, 2]}
        self.assertEqual(compact_json(data), '{"key":"val","arr":[1,2]}')


if __name__ == "__main__":
    unittest.main()
