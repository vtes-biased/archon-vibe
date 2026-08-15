#!/usr/bin/env python3
"""PostToolUse(Write|Edit): flag a touched test file for reviewer attention.

Weakening or deleting a test is a rejection unless the wiki-declared behavior
changed — so the change has to be able to say which claim moved.
"""

import json
import sys


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        "/tests/" in path
        or name.startswith("test_")
        or ".spec." in name
        or "conftest" in name
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path or not is_test(path):
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"Test file touched: {path}. Before shipping, be able to name "
                        "the wiki claim this test traces to. If the change weakens or "
                        "removes an assertion, the reviewer treats that as blocking "
                        "unless a wiki-declared behavior changed in the same diff."
                    ),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
