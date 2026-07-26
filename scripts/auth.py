#!/usr/bin/env python3
"""
Swiggy Food MCP — OAuth 2.1 PKCE token retriever.

Run once to authorise and save SWIGGY_ACCESS_TOKEN to .env:
    python scripts/auth.py
"""
import base64
import hashlib
import os
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests

PORT = 3000
REDIRECT_URI = f"http://localhost:{PORT}/callback"
AUTH_BASE_URL = "https://mcp.swiggy.com"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _register_client() -> str:
    try:
        res = requests.post(
            f"{AUTH_BASE_URL}/auth/register",
            json={"client_name": "AI Food Concierge", "redirect_uris": [REDIRECT_URI]},
            timeout=5,
        )
        if res.status_code == 200:
            return res.json().get("client_id", "swiggy-mcp")
    except Exception:
        pass
    return "swiggy-mcp"


def _save_token(token: str) -> None:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_path = os.path.normpath(env_path)
    content = ""
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

    import re
    if "SWIGGY_ACCESS_TOKEN=" in content:
        content = re.sub(
            r"^SWIGGY_ACCESS_TOKEN=.*$",
            f"SWIGGY_ACCESS_TOKEN={token}",
            content,
            flags=re.MULTILINE,
        )
    else:
        content += f"\nSWIGGY_ACCESS_TOKEN={token}\n"

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅  SWIGGY_ACCESS_TOKEN saved to {env_path}")


def run() -> None:
    print("┌─────────────────────────────────────────────────────┐")
    print("│   Swiggy Food MCP — OAuth 2.1 PKCE Token Fetcher   │")
    print("└─────────────────────────────────────────────────────┘\n")

    client_id = _register_client()
    code_verifier = _b64url(secrets.token_bytes(32))
    code_challenge = _b64url(hashlib.sha256(code_verifier.encode()).digest())
    state = _b64url(secrets.token_bytes(16))

    auth_url = (
        f"{AUTH_BASE_URL}/auth/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&state={state}"
        f"&scope=mcp:tools+mcp:resources+mcp:prompts"
    )

    received_code: list[str] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            recv_state = params.get("state", [None])[0]

            if not code or recv_state != state:
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Invalid state or missing code</h1>")
                return

            received_code.append(code)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                b"<h2>Swiggy OAuth complete!</h2>"
                b"<p>Token saved to .env — return to your terminal.</p>"
                b"</body></html>"
            )

        def log_message(self, *_: object) -> None:  # silence access log
            pass

    server = HTTPServer(("localhost", PORT), _Handler)
    print(f"Local callback listener → {REDIRECT_URI}")
    print("\nOpening browser for Swiggy Phone + OTP login …\n")
    print(f"  {auth_url}\n")

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    server.handle_request()

    if not received_code:
        print("❌  No authorisation code received.")
        sys.exit(1)

    print("Exchanging authorisation code for access token …")
    res = requests.post(
        f"{AUTH_BASE_URL}/auth/token",
        json={
            "grant_type": "authorization_code",
            "code": received_code[0],
            "code_verifier": code_verifier,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
        },
        timeout=10,
    )

    if res.status_code != 200:
        print(f"❌  Token exchange failed: {res.status_code} {res.text}")
        sys.exit(1)

    data = res.json()
    token = data["access_token"]
    expires = data.get("expires_in", 432000)
    print(f"🎉  Token received (expires in {expires}s / ~{round(expires / 86400)} days)")
    _save_token(token)


if __name__ == "__main__":
    run()
