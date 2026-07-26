import json
import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("concierge.middleware.compression")

# ──────────────────────────────────────────────────────────────────────────────
# Swiggy MCP structuredContent field mappings
#
# Real field names discovered from live structuredContent responses:
#
# search_menu SC:
#   { "items": [{ "name", "price", "isVeg", "menu_item_id", "inStock",
#                 "imageUrl", "restaurant_id", "restaurant_name", "rating",
#                 "hasAddons" }], "total", "query" }
#
# search_restaurants SC:
#   { "restaurants": [{ "id", "name", "cuisines", "avgRating", "totalRatings",
#                       "costForTwo", "areaName", "distanceKm",
#                       "deliveryTimeMinutes", "deliveryTimeRange",
#                       "offer", "imageUrl", "availabilityStatus" }] }
#
# get_restaurant_menu SC:
#   { "restaurant": {...}, "categories": [{ "title", "items": [{ "id", "name",
#       "description", "price", "inStock", "isVeg", "isBestseller", "rating",
#       "imageUrl", "hasVariants", "hasAddons" }] }] }
#
# get_food_orders SC:
#   { "orders": [{ "orderId", "restaurantId", "restaurantName", "orderTotal",
#                  "orderStatus", "orderDeliveryStatus", "orderedItems",
#                  "orderedTime", "isActiveOrder", "actions": [...] }] }
#
# update_food_cart SC:
#   { "successful", "statusCode", "statusMessage", "errorCodes", ... }
#
# get_food_cart SC:
#   { "successful", "statusCode", "statusMessage", "addressId", ... }
#   (Swiggy renders the cart in a UI widget — actual line items are NOT in SC)
# ──────────────────────────────────────────────────────────────────────────────


def _first(d: dict, *keys: str, default=None):
    """Return the first non-None value found in d for any of the given keys."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


def _unwrap_list(raw_data: Any, *list_keys: str) -> List[dict]:
    """
    Given a raw MCP tool response (dict, list, or nested), dig out the
    innermost list of item/restaurant dicts.
    """
    if isinstance(raw_data, list):
        return [r for r in raw_data if isinstance(r, dict)]

    if not isinstance(raw_data, dict):
        return []

    # Try data → <list_key>
    data_block = raw_data.get("data", raw_data)
    if isinstance(data_block, list):
        return [r for r in data_block if isinstance(r, dict)]

    if isinstance(data_block, dict):
        for key in list_keys:
            val = data_block.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
        # Try the same at top level
        for key in list_keys:
            val = raw_data.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]

    return []


def compress_restaurants(raw_data: Any) -> List[Dict[str, Any]]:
    """
    Compress a Swiggy restaurant search response down to essential decision fields.
    Handles both structuredContent format (preferred) and legacy formats.
    Only OPEN restaurants are kept.
    """
    if not raw_data:
        return []

    # structuredContent shape: {"restaurants": [...]}
    if isinstance(raw_data, dict) and "restaurants" in raw_data:
        restaurants = raw_data["restaurants"]
    else:
        restaurants = _unwrap_list(raw_data, "restaurants", "data", "items")

    if not isinstance(restaurants, list):
        return []

    compressed: List[Dict[str, Any]] = []
    for r in restaurants:
        if not isinstance(r, dict):
            continue
        # Filter out closed restaurants
        status = _first(r, "availabilityStatus", "status", default="OPEN")
        if isinstance(status, str) and status.upper() not in ("OPEN", "AVAILABLE", ""):
            continue

        restaurant_id = _first(r, "id", "restaurantId", "restaurant_id")
        name = _first(r, "name", "restaurantName", "title")
        if not restaurant_id or not name:
            continue

        rating = _first(r, "avgRating", "rating", "avgRatingString")
        delivery_range = _first(r, "deliveryTimeRange", "slaString", "deliveryTime")
        delivery_mins = _first(r, "deliveryTimeMinutes", "deliverySla")
        cuisines = _first(r, "cuisines", "cuisine", default=[])
        cost_for_two = _first(r, "costForTwo", "costForTwoMessage", "priceForTwo")
        offer = r.get("offer", "")

        compressed.append({
            "id": str(restaurant_id),
            "name": name,
            "rating": rating,
            "sla": delivery_range or (f"{delivery_mins} min" if delivery_mins else ""),
            "cuisines": (cuisines[:3] if isinstance(cuisines, list) else [str(cuisines)]),
            "costForTwo": cost_for_two,
            "offer": offer,
        })

    logger.debug(
        "Compressed %d raw restaurants to %d open restaurants",
        len(restaurants), len(compressed),
    )
    return compressed


def compress_search_results(raw_data: Any, veg_only: bool = False) -> List[Dict[str, Any]]:
    """
    Compress a Swiggy menu/dish search response down to key fields.
    Handles both structuredContent (search_menu) and get_restaurant_menu formats.
    Strips non-veg items when veg_only=True.
    """
    if not raw_data:
        return []

    non_veg_keywords = {"chicken", "mutton", "fish", "egg", "prawns", "kebab", "meat", "pork", "lamb"}

    # ── structuredContent from search_menu: {"items": [...], "total", "query"} ──
    if isinstance(raw_data, dict) and "items" in raw_data and isinstance(raw_data["items"], list):
        items = raw_data["items"]
        compressed: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if not item.get("inStock", 1):
                continue  # skip out-of-stock

            item_name_lower = str(item.get("name", "")).lower()
            is_veg = bool(item.get("isVeg", True))
            has_non_veg_name = any(kw in item_name_lower for kw in non_veg_keywords)

            if veg_only and (not is_veg or has_non_veg_name):
                continue

            # search_menu uses "menu_item_id", get_restaurant_menu categories use "id"
            item_id = item.get("menu_item_id") or item.get("id")
            if not item_id:
                continue

            compressed.append({
                "itemId": str(item_id),
                "itemName": item.get("name", "Item"),
                "price": item.get("price"),
                "isVeg": is_veg and not has_non_veg_name,
                "restaurantName": item.get("restaurant_name"),
                "restaurantId": str(item["restaurant_id"]) if item.get("restaurant_id") else None,
                "rating": item.get("rating"),
                "imageUrl": item.get("imageUrl"),
            })

        logger.debug("Compressed %d search_menu SC items to %d", len(items), len(compressed))
        return compressed

    # ── structuredContent from get_restaurant_menu: {"restaurant", "categories"} ──
    if isinstance(raw_data, dict) and "categories" in raw_data:
        restaurant = raw_data.get("restaurant", {})
        rest_id = str(restaurant.get("id", ""))
        rest_name = restaurant.get("name", "")
        compressed = []
        for cat in raw_data.get("categories", []):
            for item in cat.get("items", []):
                if not isinstance(item, dict):
                    continue
                if not item.get("inStock", 1):
                    continue

                item_name_lower = str(item.get("name", "")).lower()
                is_veg = bool(item.get("isVeg", True))
                has_non_veg_name = any(kw in item_name_lower for kw in non_veg_keywords)

                if veg_only and (not is_veg or has_non_veg_name):
                    continue

                item_id = item.get("id")
                if not item_id:
                    continue

                compressed.append({
                    "itemId": str(item_id),
                    "itemName": item.get("name", "Item"),
                    "price": item.get("price"),
                    "isVeg": is_veg and not has_non_veg_name,
                    "restaurantName": rest_name,
                    "restaurantId": rest_id,
                    "rating": item.get("rating"),
                    "category": cat.get("title", ""),
                    "imageUrl": item.get("imageUrl"),
                })
        logger.debug("Compressed restaurant_menu to %d items", len(compressed))
        return compressed

    # ── Legacy fallback: raw dict/list formats ──
    items = _unwrap_list(raw_data, "items", "menuItems", "dishes", "data")
    if not items:
        return []

    compressed = []
    for item in items:
        item_name = str(_first(item, "itemName", "name", "title", default="")).lower()
        is_veg_flag = _first(item, "isVeg", "veg", "vegetarian", default=True)
        if isinstance(is_veg_flag, str):
            is_veg = is_veg_flag.lower() in ("true", "1", "yes", "veg")
        else:
            is_veg = bool(is_veg_flag)

        has_non_veg_name = any(kw in item_name for kw in non_veg_keywords)

        if veg_only and (not is_veg or has_non_veg_name):
            continue

        item_id = _first(item, "menu_item_id", "itemId", "id", "dishId")
        display_name = _first(item, "itemName", "name", "title", default="Item")
        price = _first(item, "finalPrice", "price", "defaultPrice", "discountedPrice")
        restaurant_name = _first(item, "restaurantName", "restaurant_name", "restaurant", "restName")
        restaurant_id = _first(item, "restaurantId", "restaurant_id", "restId")

        if not item_id or not display_name:
            continue

        compressed.append({
            "itemId": str(item_id),
            "itemName": display_name,
            "price": price,
            "isVeg": is_veg and not has_non_veg_name,
            "restaurantName": restaurant_name,
            "restaurantId": str(restaurant_id) if restaurant_id else None,
        })

    logger.debug("Compressed %d legacy items to %d", len(items), len(compressed))
    return compressed


def compact_json(data: Any) -> str:
    """Format data as minimal 1-line JSON string without whitespace."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def extract_cart_summary(cart_response: Any) -> Optional[Dict[str, Any]]:
    """
    Parse a get_food_cart MCP response.

    The Swiggy MCP cart API renders items in a UI widget and does NOT return
    line-item JSON via the MCP protocol. The structuredContent only contains
    status metadata (successful=True, addressId, etc.).

    We return a minimal summary so the checkout flow knows the cart call
    succeeded, even when we can't extract individual item prices.
    Returns None only if the call outright failed.
    """
    if not isinstance(cart_response, dict):
        return None

    sc = cart_response.get("data") or cart_response
    text = cart_response.get("text", "")

    # structuredContent from get_food_cart — check for explicit failure
    if isinstance(sc, dict):
        successful = sc.get("successful")
        status_msg = sc.get("statusMessage", "")

        # Explicit failure
        if successful is False:
            return None

        # Cart is empty
        if "empty" in text.lower() or "empty" in status_msg.lower():
            return {"items": [], "subtotal": None, "deliveryFee": None,
                    "taxes": None, "grandTotal": None, "discount": None, "empty": True}

        # Cart exists — line items are in the widget (not available via MCP text)
        # Return a placeholder that tells the UI the cart was confirmed
        return {"items": [], "subtotal": None, "deliveryFee": None,
                "taxes": None, "grandTotal": None, "discount": None,
                "confirmed": True, "statusMessage": status_msg}

    # Legacy: plain text "Cart is empty"
    if isinstance(sc, str) and "empty" in sc.lower():
        return {"items": [], "subtotal": None, "deliveryFee": None,
                "taxes": None, "grandTotal": None, "discount": None, "empty": True}

    return None


def extract_order_id(place_order_response: Any) -> Optional[str]:
    """
    Extract orderId from a place_food_order MCP response.
    Checks structuredContent, data dict, and raw text.
    """
    if not isinstance(place_order_response, dict):
        return None

    # structuredContent or data dict
    for payload in (place_order_response.get("data"), place_order_response):
        if isinstance(payload, dict):
            oid = _first(payload, "orderId", "order_id", "id")
            if oid:
                return str(oid)

    # Plain text / raw text
    text = place_order_response.get("text", "") or str(place_order_response.get("data", ""))
    if text:
        m = re.search(r'"?orderId"?\s*[:=]\s*"?([0-9A-Za-z\-_]{6,})"?', text)
        if m:
            return m.group(1)
        # "Order 243604461064327 placed"
        m = re.search(r'Order\s+([0-9]{10,})', text)
        if m:
            return m.group(1)
    return None
