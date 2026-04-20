#!/usr/bin/env python3
"""Generate / merge the aichat client config at ~/.config/aichat/config.yaml.

Reads the `aichat_clients:` block from Argus config.yaml and writes matching
openai-compatible client definitions. API keys are NEVER embedded — keys live
in env vars (e.g., ZAI_API_KEY) and are passed through to subprocesses by
scripts/_common.build_aichat_env().

Usage:
  python scripts/install_aichat.py [--dry-run] [--config-path PATH]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_config

try:
    import yaml
except ImportError:
    sys.stderr.write("pyyaml required\n")
    sys.exit(2)


def _default_config_path() -> Path:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "aichat" / "config.yaml"
    return Path.home() / ".config" / "aichat" / "config.yaml"


def build_aichat_config(argus_cfg: dict) -> dict:
    clients = []
    for name, spec in argus_cfg["aichat_clients"].items():
        client = {
            "type": spec["type"],
            "name": name,
            "api_base": spec["api_base"],
            # aichat reads AICHAT_<NAME>_API_KEY from env when api_key is null
            "api_key": None,
            # models are resolved per-call via -m client:model so we leave this minimal
            "models": [],
        }
        # Pass through optional client-level pass-through fields (verified in
        # aichat 0.30: `patch`, `extra`, `proxy`, `connect_timeout`, `timeout`).
        for optional in ("patch", "extra", "proxy", "connect_timeout", "timeout"):
            if optional in spec:
                client[optional] = spec[optional]
        clients.append(client)
    return {"clients": clients}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the proposed config but don't write")
    ap.add_argument("--config-path", default=None, help="override aichat config location")
    ap.add_argument("--force", action="store_true", help="overwrite existing aichat config entirely")
    ap.add_argument("--merge", action="store_true", help="merge Argus clients into existing aichat config, preserving user's other clients and non-clients sections")
    args = ap.parse_args()
    if args.force and args.merge:
        sys.stderr.write("--force and --merge are mutually exclusive\n")
        return 2

    argus_cfg = load_config()
    out_cfg = build_aichat_config(argus_cfg)

    target = Path(args.config_path) if args.config_path else _default_config_path()

    # Check for env vars
    print("env var presence:", file=sys.stderr)
    for name, spec in argus_cfg["aichat_clients"].items():
        var = spec["api_key_env"]
        present = "SET" if os.environ.get(var) else "MISSING"
        print(f"  {name:12s} ← ${var}: {present}", file=sys.stderr)

    yaml_text = yaml.safe_dump(out_cfg, sort_keys=False)

    if args.dry_run:
        print(f"# Would write to: {target}\n")
        print(yaml_text)
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and not args.force and not args.merge:
        existing = target.read_text(encoding="utf-8")
        if existing.strip() == yaml_text.strip():
            print(f"{target} already matches desired config — no changes.", file=sys.stderr)
        else:
            sibling = target.with_suffix(".argus.yaml")
            sibling.write_text(yaml_text, encoding="utf-8")
            print(f"{target} exists with different content. Wrote sibling: {sibling}", file=sys.stderr)
            print("Run with --force to overwrite the main config, or --merge to merge Argus clients into it.", file=sys.stderr)
    elif target.exists() and args.merge:
        existing_cfg = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        existing_clients = existing_cfg.get("clients") or []
        argus_client_names = {c["name"] for c in out_cfg["clients"]}
        # Keep user's non-Argus clients; replace Argus clients with fresh versions.
        kept = [c for c in existing_clients if c.get("name") not in argus_client_names]
        merged_cfg = dict(existing_cfg)
        merged_cfg["clients"] = kept + out_cfg["clients"]
        target.write_text(yaml.safe_dump(merged_cfg, sort_keys=False), encoding="utf-8")
        print(f"merged {len(out_cfg['clients'])} Argus clients into {target}", file=sys.stderr)
        print(f"  kept user clients: {[c.get('name') for c in kept]}", file=sys.stderr)
        print(f"  (re)wrote Argus clients: {sorted(argus_client_names)}", file=sys.stderr)
    else:
        target.write_text(yaml_text, encoding="utf-8")
        print(f"wrote {target}")

    print("\nReminder: API keys stay in env vars. Argus passes them to aichat via")
    print("AICHAT_<CLIENT>_API_KEY at dispatch time; nothing is written to disk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
