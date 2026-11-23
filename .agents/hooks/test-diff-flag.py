#!/usr/bin/env python3
"""PostToolUse + PostInvocation: flag touched test files for reviewer attention.

Antigravity mirror of .claude/hooks/test-diff-flag.py. PostToolUse records
touched test paths per conversation; PostInvocation injects the systemMessage
because Antigravity PostToolUse output is ignored.
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        "/tests/" in path
        or name.startswith("test_")
        or ".spec." in name
        or "conftest" in name
    )


def state_file(conversation_id: str) -> Path:
    digest = hashlib.sha256(conversation_id.encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"agy-test-diff-flag-{digest}.txt"


def handle_post_tool_use(payload: dict) -> dict:
    if payload.get("error"):
        return {}
    conv_id = payload.get("conversationId") or ""
    args = (payload.get("toolCall") or {}).get("args") or {}
    path = args.get("Path") or args.get("TargetFile") or args.get("AbsolutePath") or ""
    if not conv_id or not path or not is_test(path):
        return {}
    marker = state_file(conv_id)
    with marker.open("a", encoding="utf-8") as fh:
        fh.write(path + "\n")
    return {}


def handle_post_invocation(payload: dict) -> dict:
    conv_id = payload.get("conversationId") or ""
    if not conv_id:
        return {}
    marker = state_file(conv_id)
    try:
        raw = marker.read_text(encoding="utf-8")
        marker.unlink(missing_ok=True)
    except FileNotFoundError:
        return {}
    paths = list(dict.fromkeys(line for line in raw.splitlines() if line))
    if not paths:
        return {}
    joined = ", ".join(paths)
    return {
        "injectSteps": [
            {
                "systemMessage": {
                    "systemMessage": (
                        f"Test file touched: {joined}. Before shipping, be able to name "
                        "the docs claim this test traces to. If the change weakens or "
                        "removes an assertion, the reviewer treats that as blocking "
                        "unless a docs-declared behavior changed in the same diff."
                    )
                }
            }
        ]
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("{}")
        return 0

    event = payload.get("hookEventName") or ""
    if event == "PostToolUse":
        out = handle_post_tool_use(payload)
    elif event == "PostInvocation":
        out = handle_post_invocation(payload)
    else:
        out = {}

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
