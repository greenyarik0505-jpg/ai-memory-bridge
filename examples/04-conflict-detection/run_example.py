#!/usr/bin/env python3
"""Reproducible Example 4: Conflict Detection & Resolution."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ai-memory-bridge" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capture import add_memory_entry, resolve_memory_conflict  # noqa: E402
from init import initialize_workspace  # noqa: E402
from memory_utils import load_memory  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="amb_ex04_") as tmp:
        ws = Path(tmp)
        initialize_workspace(ws, project_name="conflict-demo")

        res_a = add_memory_entry(
            ws,
            entry_type="decision",
            title="Primary Database Architecture",
            content="Use PostgreSQL 16 with strict ACID transactions for billing records.",
            priority="high",
            source="claude-code",
        )
        res_b = add_memory_entry(
            ws,
            entry_type="decision",
            title="Primary Database Architecture",
            content="Use MongoDB document store for primary storage of billing records.",
            priority="high",
            source="cursor",
        )

        conflicts = res_b["conflicts_detected"]
        assert len(conflicts) == 1, "Expected 1 conflict to be detected automatically"
        conflict = conflicts[0]

        decisions_md_before = (ws / ".ai-memory" / "decisions.md").read_text(encoding="utf-8")
        assert "Active Decision Conflicts" in decisions_md_before

        resolved = resolve_memory_conflict(
            ws,
            conflict_id=conflict["id"],
            keep_entry_id=res_a["entry"]["id"],
            note="Confirmed ACID requirement with engineering lead.",
            source="claude-code",
        )

        data_after = load_memory(ws)
        by_id = {e["id"]: e for e in data_after["entries"]}
        assert by_id[res_a["entry"]["id"]]["status"] == "active"
        assert by_id[res_b["entry"]["id"]]["status"] == "superseded"
        assert data_after["conflicts"][0]["status"] == "resolved"

        print("=== Example 04: Conflict Detection & Resolution (VERIFIED) ===")
        print(f"Entry A (claude-code) : {res_a['entry']['id']} -> PostgreSQL 16")
        print(f"Entry B (cursor)      : {res_b['entry']['id']} -> MongoDB")
        print(f"Conflict Detected     : {conflict['id']}")
        print(f"Conflict Reason       : {conflict['reason']}")
        print(f"Resolution Status     : {resolved['conflict']['status']} (kept {res_a['entry']['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
