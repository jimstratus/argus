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
        clients.append(client)
    return {"clients": clients}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the proposed config but don't write")
    ap.add_argument("--config-path", default=None, help="override aichat config location")
    ap.add_argument("--force", action="store_true", help="overwrite existing aichat config")
    args = ap.parse_args()

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

    if target.exists() and not args.force:
        existing = target.read_text(encoding="utf-8")
        if existing.strip() == yaml_text.strip():
            print(f"{target} already matches desired config — no changes.", file=sys.stderr)
        else:
            sibling = target.with_suffix(".argus.yaml")
            sibling.write_text(yaml_text, encoding="utf-8")
            print(f"{target} exists with different content. Wrote sibling: {sibling}", file=sys.stderr)
            print("Run with --force to overwrite the main config, or merge manually.", file=sys.stderr)
    else:
        target.write_text(yaml_text, encoding="utf-8")
        print(f"wrote {target}")

    print("\nReminder: API keys stay in env vars. Argus passes them to aichat via")
    print("AICHAT_<CLIENT>_API_KEY at dispatch time; nothing is written to disk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
