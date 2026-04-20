#!/usr/bin/env python3
"""Check OpenRouter account balance + key limits.

Usage:
  or_balance.py              # print current balance, exit 0
  or_balance.py --estimate N # compare estimate vs available, exit 2 if insufficient
  or_balance.py --json

Endpoints used (both free, GET with Bearer auth):
  /api/v1/auth/key  → per-key usage / limit / limit_remaining
  /api/v1/credits   → account-level total_credits / total_usage

If both return values, we use the stricter of the two as "available".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error


OR_BASE = "https://openrouter.ai/api/v1"


def _get(path: str, api_key: str, timeout: float = 10.0) -> dict | None:
    req = urllib.request.Request(
        f"{OR_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"OR GET {path} failed: HTTP {e.code}\n")
        return None
    except Exception as e:
        sys.stderr.write(f"OR GET {path} failed: {type(e).__name__}: {e}\n")
        return None


def probe(api_key: str) -> dict:
    """Return {limit_remaining, account_remaining, available, raw_key, raw_credits}.

    `available` is the stricter of:
      - per-key limit_remaining (if key is capped)
      - account-wide (total_credits - total_usage)
    """
    key_info = _get("/auth/key", api_key) or {}
    credits_info = _get("/credits", api_key) or {}

    kd = key_info.get("data", {}) if isinstance(key_info, dict) else {}
    cd = credits_info.get("data", {}) if isinstance(credits_info, dict) else {}

    key_remaining = kd.get("limit_remaining")  # None if uncapped
    account_total = cd.get("total_credits")
    account_usage = cd.get("total_usage")

    account_remaining = None
    if isinstance(account_total, (int, float)) and isinstance(account_usage, (int, float)):
        account_remaining = account_total - account_usage

    candidates = [v for v in (key_remaining, account_remaining) if isinstance(v, (int, float))]
    available = min(candidates) if candidates else None

    return {
        "key_limit_remaining": key_remaining,
        "key_usage": kd.get("usage"),
        "account_total_credits": account_total,
        "account_total_usage": account_usage,
        "account_remaining": account_remaining,
        "available_usd": available,
        "raw_key": kd,
        "raw_credits": cd,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", type=float, default=None, help="planned spend in USD; exit 2 if available < estimate × safety")
    ap.add_argument("--safety", type=float, default=2.0, help="safety factor: require available ≥ estimate × safety (default 2.0)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        sys.stderr.write("OPENROUTER_API_KEY not set — cannot query OR balance\n")
        return 3

    info = probe(api_key)
    available = info.get("available_usd")

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        kr = info.get("key_limit_remaining")
        ar = info.get("account_remaining")
        av = info.get("available_usd")
        print(f"OpenRouter balance check:")
        print(f"  per-key limit_remaining: {'uncapped' if kr is None else f'${kr:.4f}'}")
        print(f"  account remaining:       {'n/a' if ar is None else f'${ar:.4f}'}")
        print(f"  effective available:     {'unknown' if av is None else f'${av:.4f}'}")
        if args.estimate is not None:
            required = args.estimate * args.safety
            print(f"  planned spend:           ${args.estimate:.4f}")
            print(f"  required (×{args.safety}):          ${required:.4f}")

    if args.estimate is not None:
        if available is None:
            sys.stderr.write("WARN: could not determine available balance; continuing optimistically\n")
            return 1
        required = args.estimate * args.safety
        if available < required:
            sys.stderr.write(f"\nBLOCK: OR available ${available:.4f} < required ${required:.4f} "
                             f"({args.safety}× estimate ${args.estimate:.4f}). Top up or use --yes-cost to override.\n")
            return 2
        if available < args.estimate * 3:
            sys.stderr.write(f"\nWARN: OR available ${available:.4f} is tight relative to planned ${args.estimate:.4f}\n")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
