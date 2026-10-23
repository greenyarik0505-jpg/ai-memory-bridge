#!/usr/bin/env python3
"""Reproducible Example 2: Cursor -> Google Antigravity Handoff."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ai-memory-bridge" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capture import complete_pending_task, import_entries_from_json  # noqa: E402
from handoff import create_handoff  # noqa: E402
from init import initialize_workspace  # noqa: E402
from memory_utils import load_memory  # noqa: E402
from sync import sync_workspace_memory  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="amb_ex02_") as tmp:
        ws = Path(tmp)
        shutil.copy2(EXAMPLE_DIR / "sample_entries.json", ws / "sample_entries.json")

        initialize_workspace(ws, project_name="cross-platform-cli")
        import_entries_from_json(ws, Path("sample_entries.json"), default_source="cursor")

        handoff_res = create_handoff(
            ws,
            target_agent="antigravity",
            source_agent="cursor",
            focus_note="Complete the atomic persistence task while respecting stdlib-only constraint.",
            apply_rules=True,
        )

        # Simulate Antigravity picking up the pending task and marking it completed
        data = load_memory(ws)
        pending_tasks = [e for e in data["entries"] if e["type"] == "task_pending"]
        assert len(pending_tasks) == 1
        completed = complete_pending_task(
            ws,
            pending_tasks[0]["id"],
            resolution_note="Implemented atomic_write_text with tempfile and os.replace",
            source="antigravity",
        )
        sync_workspace_memory(ws, targets=["cursor", "antigravity"])

        agy_rule = (ws / ".agents" / "rules" / "ai-memory-bridge.md").read_text(encoding="utf-8")
        cursor_rule = (ws / ".cursor" / "rules" / "ai-memory-bridge.mdc").read_text(encoding="utf-8")

        assert "Zero External Runtime Dependencies" in agy_rule
        assert "alwaysApply: true" in cursor_rule
        assert completed["entry"]["status"] == "completed"

        print("=== Example 02: Cursor -> Google Antigravity (VERIFIED) ===")
        print(f"Handoff Packet   : {handoff_res['relative_handoff_file']}")
        print(f"Antigravity Rule : .agents/rules/ai-memory-bridge.md")
        print(f"Cursor Rule      : .cursor/rules/ai-memory-bridge.mdc")
        print(f"Completed Task   : {completed['entry']['title']} -> {completed['entry']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
