#!/usr/bin/env python3
"""Tests for entry capture, deduplication, superseding, conflict detection, and compaction."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ai-memory-bridge" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capture import (  # noqa: E402
    add_memory_entry,
    complete_pending_task,
    resolve_memory_conflict,
)
from init import initialize_workspace  # noqa: E402
from memory_utils import (  # noqa: E402
    VALID_ENTRY_TYPES,
    compact_memory,
    load_memory,
    save_memory,
)


class CaptureAndSmartMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        initialize_workspace(self.ws, project_name="smart-mem-test")

    def test_capture_all_nine_entry_types(self) -> None:
        for idx, etype in enumerate(VALID_ENTRY_TYPES):
            res = add_memory_entry(
                workspace_root=self.ws,
                entry_type=etype,
                title=f"Sample {etype} #{idx}",
                content=f"Detailed verified content for {etype} entry number {idx}.",
                source="claude-code",
                priority="high" if idx % 2 == 0 else "medium",
            )
            self.assertEqual(res["status"], "added")

        data = load_memory(self.ws)
        self.assertEqual(len(data["entries"]), len(VALID_ENTRY_TYPES))
        context_md = (self.ws / ".ai-memory" / "context.md").read_text(encoding="utf-8")
        decisions_md = (self.ws / ".ai-memory" / "decisions.md").read_text(encoding="utf-8")
        tasks_md = (self.ws / ".ai-memory" / "tasks.md").read_text(encoding="utf-8")
        self.assertIn("Project Goals", context_md)
        self.assertIn("Sample decision", decisions_md)
        self.assertIn("Sample task_pending", tasks_md)

    def test_exact_and_fuzzy_deduplication_boosts_priority(self) -> None:
        r1 = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="API Protocol",
            content="Use REST endpoints with OpenAPI 3.1 schema validation.",
            source="claude-code",
            priority="medium",
        )
        self.assertEqual(r1["status"], "added")

        # Duplicate with higher priority
        r2 = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="API Protocol",
            content="Use REST endpoints with OpenAPI 3.1 schema validation!",
            source="cursor",
            priority="critical",
        )
        self.assertEqual(r2["status"], "deduplicated")
        self.assertEqual(r2["entry"]["id"], r1["entry"]["id"])
        self.assertEqual(r2["entry"]["priority"], "critical")
        self.assertEqual(len(load_memory(self.ws)["entries"]), 1)

    def test_supersede_outdated_entry(self) -> None:
        r1 = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Primary Database",
            content="Use SQLite for local prototype storage.",
            source="claude-code",
        )
        old_id = r1["entry"]["id"]

        r2 = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Primary Database",
            content="Migrate to PostgreSQL 16 for production multi-user concurrency.",
            source="codex",
            supersedes=old_id,
            priority="high",
        )
        self.assertEqual(r2["status"], "added")
        self.assertEqual(len(r2["conflicts_detected"]), 0)

        data = load_memory(self.ws)
        by_id = {e["id"]: e for e in data["entries"]}
        self.assertEqual(by_id[old_id]["status"], "superseded")
        self.assertEqual(by_id[old_id]["superseded_by"], r2["entry"]["id"])
        self.assertEqual(by_id[r2["entry"]["id"]]["supersedes"], old_id)

    def test_conflict_detection_and_resolution(self) -> None:
        e1 = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Database Storage Engine",
            content="We must use PostgreSQL 16 for all primary application data storage.",
            source="claude-code",
            priority="high",
        )
        e2 = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Database Storage Engine",
            content="We must use MongoDB for all primary application data storage.",
            source="cursor",
            priority="high",
        )
        self.assertEqual(len(e2["conflicts_detected"]), 1)
        conflict_id = e2["conflicts_detected"][0]["id"]

        data = load_memory(self.ws)
        self.assertEqual(len(data["conflicts"]), 1)
        self.assertEqual(data["conflicts"][0]["status"], "unresolved")

        resolved = resolve_memory_conflict(
            self.ws,
            conflict_id=conflict_id,
            keep_entry_id=e1["entry"]["id"],
            note="PostgreSQL confirmed as canonical database",
            source="antigravity",
        )
        self.assertEqual(resolved["status"], "resolved")

        updated = load_memory(self.ws)
        by_id = {e["id"]: e for e in updated["entries"]}
        self.assertEqual(by_id[e1["entry"]["id"]]["status"], "active")
        self.assertEqual(by_id[e2["entry"]["id"]]["status"], "superseded")
        self.assertEqual(updated["conflicts"][0]["status"], "resolved")

    def test_complete_pending_task(self) -> None:
        t = add_memory_entry(
            self.ws,
            entry_type="task_pending",
            title="Write unit tests",
            content="Cover all security edge cases.",
            source="claude-code",
        )
        tid = t["entry"]["id"]
        done = complete_pending_task(self.ws, tid, resolution_note="All 25 tests passing", source="codex")
        self.assertEqual(done["entry"]["type"], "task_done")
        self.assertEqual(done["entry"]["status"], "completed")
        self.assertIn("All 25 tests passing", done["entry"]["content"])

    def test_context_compaction_rolls_up_summaries_and_preserves_critical(self) -> None:
        add_memory_entry(
            self.ws,
            entry_type="goal",
            title="Critical Security Goal",
            content="Zero cloud dependencies and strict secret scanning.",
            priority="critical",
        )
        for i in range(5):
            add_memory_entry(
                self.ws,
                entry_type="session_summary",
                title=f"Session #{i + 1} Summary",
                content=f"Completed milestone batch #{i + 1} with module updates.",
                priority="low",
            )
        data = load_memory(self.ws)
        stats = compact_memory(data, max_active_entries=4, max_tokens=500)
        save_memory(self.ws, data, action="compact", agent="test")
        self.assertGreater(stats["archived_count"], 0)

        reloaded = load_memory(self.ws)
        critical_active = [
            e for e in reloaded["entries"] if e["priority"] == "critical" and e["status"] == "active"
        ]
        self.assertEqual(len(critical_active), 1)


if __name__ == "__main__":
    unittest.main()
