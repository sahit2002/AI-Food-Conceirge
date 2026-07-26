# 🍲 AI Food Concierge

> **Stop scrolling through 200-item menus.** Tell the AI what you feel like eating, and it finds 3 great options on Swiggy — ready to order in under 30 seconds.

---

## What does it do?

The concierge asks you **3 quick questions**, then searches Swiggy live and returns **3 ranked picks** with a reason for each one. You can order directly from the app with one tap (Cash on Delivery).

| Question | Example answers |
|---|---|
| 🍽 **How hungry are you?** | Snack · Proper meal · Full feast |
| 😋 **What's your mood?** | Comfort food · Spicy · Healthy · Sweet treat |
| 🥗 **Any dietary needs?** | No restriction · Vegetarian · Jain · Non-veg |

**Output:** 3 dish picks, each with the restaurant name, price, and a plain-English reason why it suits you right now.

---

## What makes it special for India?

- 🌙 **Late-night (10 PM – 4 AM)** — automatically weights biryani, rolls, and comfort food
- 🟢 **Veg / Jain mode** — enforced end-to-end, not just a filter label
- 🍛 **Mood → cuisine** — "comfort" maps to North/South Indian, "healthy" to salad bowls, etc.
- 📦 **Payload compression** — Swiggy menus can be huge; the agent trims them before sending to the AI so responses stay fast

---

## How to run it

### What you need first

- **Python 3.10 or newer** — check with `python --version`
- **A Swiggy account** — to connect to Swiggy's ordering API
- **One AI API key** — Gemini (free tier available), Anthropic Claude, or OpenAI GPT-4o

---

### Step 1 — Download and install

```bash
# Clone the repo
git clone <your-repo-url>
cd AI_Food_Concierge

# Create a Python virtual environment (keeps dependencies isolated)
python -m venv .venv
source .venv/bin/activate        # Mac / Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Copy the environment file template
cp .env.example .env
```

---

### Step 2 — Connect your Swiggy account

```bash
python scripts/auth.py
```

This opens a browser tab. Log in with your Swiggy phone number + OTP. The access token is saved to your `.env` file automatically — **you only need to do this once**.

---

### Step 3 — Add an AI key

Open `.env` in any text editor and add your key. Pick **one** provider:

```bash
# Google Gemini (recommended — has a free tier)
GEMINI_API_KEY=your-key-here

# OR Anthropic Claude
# ANTHROPIC_API_KEY=your-key-here

# OR OpenAI GPT-4o
# OPENAI_API_KEY=your-key-here
```

Get a free Gemini key at [aistudio.google.com](https://aistudio.google.com/apikey).

---

### Step 4 — Launch

```bash
streamlit run app.py
```

Opens at `http://localhost:8501` in your browser. Type what you're craving and hit Enter.

---

## Other ways to run it

| Mode | Command | When to use |
|---|---|---|
| 🌐 **Web UI** | `streamlit run app.py` | Normal use — best experience |
| 💻 **Terminal CLI** | `python scripts/main.py` | If you prefer the command line |
| 🧪 **Dry-run demo** | `python scripts/demo.py` | Try it out **without** any API keys |
| ✅ **Tests** | `python -m unittest discover tests` | Verify everything works after changes |

---

## Project layout

```
AI_Food_Concierge/
│
├── app.py                   ← Start here — the Streamlit web app
│
├── src/concierge/           ← Core library
│   ├── agent/
│   │   ├── core.py          ← AI orchestrator (talks to Gemini / Claude / GPT-4o)
│   │   └── prompts.py       ← Instructions given to the AI
│   ├── api/
│   │   └── mcp_client.py    ← Connects to Swiggy's ordering API
│   ├── middleware/
│   │   ├── compression.py   ← Trims large Swiggy responses before sending to AI
│   │   └── intelligence.py  ← India-specific logic (late-night, veg filter, etc.)
│   ├── models/
│   │   └── schema.py        ← Data shapes: IntakeAnswers, FoodPick, Session
│   └── config.py            ← All settings, read from .env
│
├── scripts/
│   ├── auth.py              ← Run once to connect your Swiggy account
│   ├── main.py              ← Terminal version of the app
│   └── demo.py              ← No-API-key demo / walkthrough
│
├── tests/                   ← Automated tests
├── assets/                  ← Architecture diagram, proposal doc
│
├── .env.example             ← Template — copy to .env and fill in your keys
├── .streamlit/config.toml   ← UI dark theme settings
├── requirements.txt         ← Python dependencies
└── pyproject.toml           ← Package metadata
```

---

## How it works under the hood

```
You type:  "spicy chicken biryani under ₹300"
                        │
              ┌─────────▼──────────┐
              │   Streamlit UI     │  app.py
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │   AI Agent         │  Gemini / Claude / GPT-4o
              │   (up to 4 turns)  │
              └──┬──────────────┬──┘
    tool call ↙               ↘ tool call
  ┌────────────┐             ┌──────────────┐
  │ search_    │             │ search_menu  │
  │ restaurants│             │              │
  └─────┬──────┘             └──────┬───────┘
        │                           │
        └──────────┬────────────────┘
                   │  Swiggy MCP responses
              ┌────▼──────────────────┐
              │  Compression layer    │  Trims payload → faster AI
              └────┬──────────────────┘
                   │
              ┌────▼──────────────────┐
              │  India intelligence   │  Late-night? Veg filter? Portion?
              └────┬──────────────────┘
                   │
              3 ranked picks displayed
                   │
        You tap "Order" → cart → COD checkout
```

---

## Environment variables

Copy `.env.example` to `.env` and fill in the required values.

| Variable | Required? | What it does |
|---|---|---|
| `SWIGGY_ACCESS_TOKEN` | ✅ Yes | Your Swiggy OAuth token (from `scripts/auth.py`) |
| `GEMINI_API_KEY` | ✅ Pick one | Google Gemini AI key |
| `ANTHROPIC_API_KEY` | ✅ Pick one | Anthropic Claude key |
| `OPENAI_API_KEY` | ✅ Pick one | OpenAI GPT-4o key |
| `LLM_MODEL` | Optional | Override the default AI model name |
| `AGENT_MAX_TURNS` | Optional | How many AI ↔ Swiggy back-and-forths (default: 4) |
| `MCP_REQUEST_TIMEOUT` | Optional | Swiggy API timeout in seconds (default: 30) |
| `MCP_MAX_RETRIES` | Optional | How many times to retry on failure (default: 4) |
| `CART_MAX_CAP_INR` | Optional | Maximum cart value in ₹ (default: ₹1000) |

---

## ⚠️ Important — real orders

- Clicking **Place Order** places a **real Cash-on-Delivery order** on your Swiggy account
- Always check the cart total before confirming
- Use `python scripts/demo.py` for demos and presentations — it never calls the real API

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `SWIGGY_ACCESS_TOKEN missing` | Run `python scripts/auth.py` and log in again |
| `No LLM API key found` | Add `GEMINI_API_KEY=...` (or Anthropic / OpenAI) to `.env` |
| Streamlit shows a blank page | Make sure your `.venv` is activated and `pip install -r requirements.txt` was run |
| Token expired after a few days | Re-run `python scripts/auth.py` to get a fresh token |

---

## Swiggy MCP — tools used

The app talks to Swiggy through their official [MCP (Model Context Protocol)](https://mcp.swiggy.com/builders/) API. Here are the tools it calls:

| Stage | API calls |
|---|---|
| Find food | `get_addresses`, `search_restaurants`, `search_menu`, `get_restaurant_menu` |
| Build cart | `update_food_cart`, `get_food_cart`, `flush_food_cart` |
| Checkout | `fetch_food_coupons`, `apply_food_coupon`, `place_food_order` |
| Track order | `get_food_orders`, `track_food_order`, `get_food_order_details` |

---

## Submitting to Swiggy Builders Club

Apply at **[mcp.swiggy.com/access](https://mcp.swiggy.com/access)** or email **builders@swiggy.in**.

Attach your GitHub link, a 2–3 minute demo video, and the proposal doc at [`assets/proposal.docx`](assets/proposal.docx).

---

## Useful links

- [Swiggy MCP Developer Quickstart](https://mcp.swiggy.com/builders/docs/start/developer/)
- [Order Food with MCP — recipe](https://mcp.swiggy.com/builders/docs/build/recipes/order-food.md)
- [All Food API tools](https://mcp.swiggy.com/builders/docs/reference/food/)
- [How to get a Swiggy token](https://mcp.swiggy.com/builders/docs/start/authenticate.md)
- [Get a free Gemini API key](https://aistudio.google.com/apikey)

---

## License

MIT — free to use, modify, and distribute.
