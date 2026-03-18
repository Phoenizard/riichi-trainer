#!/usr/bin/env python3
"""
Test script for MJAPI (Mortal online API) connectivity.
Based on MahjongCopilot's MJAPI client implementation.
"""

import requests
import json
import sys
import random
import string

# Known MJAPI endpoints (may change - check MahjongCopilot updates)
MJAPI_URLS = [
    "https://cdt-authentication-consultation-significance.trycloudflare.com",
]


class MjapiTestClient:
    """Minimal MJAPI client for testing."""

    def __init__(self, base_url: str, timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {}
        self.token = None

    def _post(self, path, data=None):
        url = f"{self.base_url}{path}"
        resp = requests.post(url, json=data, headers=self.headers, timeout=self.timeout)
        return resp

    def _get(self, path):
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        return resp

    def register(self, name: str):
        resp = self._post("/user/register", {"name": name})
        print(f"  Register: {resp.status_code} - {resp.text[:200]}")
        if resp.ok:
            return resp.json()
        return None

    def login(self, name: str, secret: str):
        resp = self._post("/user/login", {"name": name, "secret": secret})
        print(f"  Login: {resp.status_code} - {resp.text[:200]}")
        if resp.ok:
            data = resp.json()
            if "id" in data:
                self.token = data["id"]
                self.headers["Authorization"] = f"Bearer {self.token}"
            return data
        return None

    def list_models(self):
        resp = self._get("/mjai/list")
        print(f"  List models: {resp.status_code} - {resp.text[:200]}")
        if resp.ok:
            return resp.json()
        return None

    def get_usage(self):
        resp = self._get("/mjai/usage")
        print(f"  Usage: {resp.status_code} - {resp.text[:200]}")
        if resp.ok:
            return resp.json()
        return None

    def start_bot(self, seat: int, bound: int, model: str):
        resp = self._post("/mjai/start", {"id": seat, "bound": bound, "model": model})
        print(f"  Start bot: {resp.status_code} - {resp.text[:200]}")
        if resp.ok:
            return resp.json() if resp.content else True
        return None

    def act(self, seq: int, data: dict):
        resp = self._post("/mjai/act", {"seq": seq, "data": data})
        if resp.ok and resp.content:
            return resp.json()
        return None

    def stop_bot(self):
        resp = self._post("/mjai/stop")
        print(f"  Stop bot: {resp.status_code}")
        return resp.ok

    def logout(self):
        resp = self._post("/user/logout")
        return resp.ok


def test_connectivity(url: str) -> bool:
    """Test basic connectivity to MJAPI endpoint."""
    print(f"\n{'='*60}")
    print(f"Testing MJAPI: {url}")
    print(f"{'='*60}")

    client = MjapiTestClient(url)
    rand_name = "test_" + "".join(random.choices(string.ascii_lowercase, k=6))

    # Step 1: Register
    print("\n[1] Register...")
    reg_result = client.register(rand_name)
    if not reg_result:
        print("  FAILED: Cannot register")
        return False
    secret = reg_result.get("secret", "")

    # Step 2: Login
    print("\n[2] Login...")
    login_result = client.login(rand_name, secret)
    if not login_result or not client.token:
        print("  FAILED: Cannot login")
        return False

    # Step 3: List models
    print("\n[3] List available models...")
    models = client.list_models()
    if not models:
        print("  FAILED: Cannot list models")
        return False
    model_list = models.get("models", [])
    print(f"  Available models: {model_list}")

    # Step 4: Get usage
    print("\n[4] Check usage...")
    client.get_usage()

    # Step 5: Start bot and test one action
    if model_list:
        model = model_list[0]
        print(f"\n[5] Start bot with model: {model}")
        start_result = client.start_bot(seat=0, bound=256, model=model)

        if start_result is not None:
            print("\n[6] Test mjai interaction...")

            # Send start_game
            seq = 0
            start_game_msg = {"type": "start_game", "id": 0, "names": ["player", "ai1", "ai2", "ai3"]}
            result = client.act(seq, start_game_msg)
            print(f"  start_game response: {json.dumps(result, ensure_ascii=False)[:200] if result else 'None'}")

            # Send start_kyoku with a sample hand
            seq += 1
            start_kyoku_msg = {
                "type": "start_kyoku",
                "bakaze": "E",
                "dora_marker": "3s",
                "kyoku": 1,
                "honba": 0,
                "kyotaku": 0,
                "oya": 0,
                "scores": [25000, 25000, 25000, 25000],
                "tehais": [
                    ["1m", "2m", "3m", "5p", "6p", "7p", "2s", "3s", "4s", "E", "E", "P", "P"],
                    ["?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?"],
                    ["?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?"],
                    ["?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?"],
                ]
            }
            result = client.act(seq, start_kyoku_msg)
            print(f"  start_kyoku response: {json.dumps(result, ensure_ascii=False)[:200] if result else 'None'}")

            # Send tsumo (player 0 draws a tile)
            seq += 1
            tsumo_msg = {"type": "tsumo", "actor": 0, "pai": "9s"}
            result = client.act(seq, tsumo_msg)
            print(f"  tsumo response: {json.dumps(result, ensure_ascii=False)[:300] if result else 'None'}")

            if result and "act" in result:
                act = result["act"]
                print(f"\n  >>> Mortal recommends: {act.get('type')} - {act.get('pai', '')}")
                if "meta" in act:
                    meta = act["meta"]
                    print(f"  >>> q_values: {meta.get('q_values', [])[:5]}...")
                    print(f"  >>> shanten: {meta.get('shanten', 'N/A')}")
                    print(f"  >>> is_greedy: {meta.get('is_greedy', 'N/A')}")

            # Stop bot
            print("\n[7] Stop bot...")
            client.stop_bot()

    # Logout
    print("\n[8] Logout...")
    client.logout()

    print(f"\n{'='*60}")
    print("TEST COMPLETE - API is functional!")
    print(f"{'='*60}")
    return True


if __name__ == "__main__":
    success = False
    for url in MJAPI_URLS:
        try:
            if test_connectivity(url):
                success = True
                break
        except requests.exceptions.ConnectionError as e:
            print(f"  Connection failed: {e}")
        except requests.exceptions.Timeout:
            print(f"  Timeout connecting to {url}")
        except Exception as e:
            print(f"  Error: {e}")

    if not success:
        print("\nAll MJAPI endpoints failed.")
        print("The temporary Cloudflare URL may have changed.")
        print("Check MahjongCopilot releases for updated MJAPI URL.")
        sys.exit(1)
