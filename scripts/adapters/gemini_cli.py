"""Gemini CLI adapter. Invokes `gemini -p "" --yolo` with the prompt piped to stdin.

`gemini` CLI help states: "-p/--prompt ... Appended to input on stdin (if any)."
We use empty -p to force non-interactive mode and feed the entire prompt via stdin.
The previous {prompt}-in-argv approach broke on Windows for prompts > ~32 KB
(ARG_MAX) — fixed once here via the shared stdin factory (#22 slice 3).
"""
from __future__ import annotations

from .stdin_cli import make_stdin_cli_adapter

send = make_stdin_cli_adapter("gemini-cli")
