#!/usr/bin/env python3
"""PostToolUse(Write|Edit): refuse TODO/FIXME markers in code.

Dogma: discovered work goes through /intake or gets done now — it is never parked
in a comment where nothing will ever read it again.
"""

import json
import re
import sys

CODE_SUFFIXES = {"py", "ts", "js", "svelte", "rs", "sh", "sql", "yml", "yaml", "toml"}
MARKER = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if "." not in path or path.rsplit(".", 1)[-1] not in CODE_SUFFIXES:
        return 0

    written = (tool_input.get("content") or "") + (tool_input.get("new_string") or "")
    hits = [line.strip() for line in written.splitlines() if MARKER.search(line)]
    if not hits:
        return 0

    print(
        f"{path} introduces a parked-work marker:\n  "
        + "\n  ".join(hits[:5])
        + "\n\nThis repo has no TODOs (CLAUDE.md, wiki/dogmas.md). Either do the work "
        "now, or run /intake so it becomes a board line. Remove the marker.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
