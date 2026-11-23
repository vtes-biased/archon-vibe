#!/usr/bin/env python3
"""PreToolUse(write_file|edit_file|...): refuse TODO/FIXME markers in code.

Antigravity mirror of .claude/hooks/todo-lint.py. Runs on PreToolUse because
Antigravity PostToolUse cannot block or return feedback to the model.
"""

import json
import re
import sys

CODE_SUFFIXES = {"py", "ts", "js", "svelte", "rs", "sh", "sql", "yml", "yaml", "toml"}
MARKER = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")


def extract_written(args: dict) -> str:
    parts = [
        args.get("Content") or "",
        args.get("Replacement") or "",
        args.get("CodeContent") or "",
        args.get("ReplacementContent") or "",
    ]
    for chunk in args.get("ReplacementChunks") or []:
        if isinstance(chunk, dict):
            parts.append(chunk.get("ReplacementContent") or "")
    return "\n".join(parts)


def allow() -> int:
    print(json.dumps({"decision": "allow"}))
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return allow()

    args = (payload.get("toolCall") or {}).get("args") or {}
    path = args.get("Path") or args.get("TargetFile") or args.get("AbsolutePath") or ""
    if "." not in path or path.rsplit(".", 1)[-1] not in CODE_SUFFIXES:
        return allow()

    written = extract_written(args)
    hits = [line.strip() for line in written.splitlines() if MARKER.search(line)]
    if not hits:
        return allow()

    reason = (
        f"{path} introduces a parked-work marker:\n  "
        + "\n  ".join(hits[:5])
        + "\n\nThis repo has no TODOs (CLAUDE.md, docs/principles.md). Either do the work "
        "now, or run /intake so it becomes a board line. Remove the marker."
    )
    print(json.dumps({"decision": "deny", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
