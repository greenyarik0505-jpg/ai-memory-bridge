#!/usr/bin/env python3
"""Reproducible Example 3: Session Recovery & Rollback."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ai-memory-bridge" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from backup import create_backup, verify_backup  # noqa: E402
from capture import add_memory_entry  # noqa: E402
from init import initialize_workspace  # noqa: E402
from memory_utils import load_memory  # noqa: E402
from restore import restore_memory  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="amb_ex03_") as tmp:
        ws = Path(tmp)
        initialize_workspace(ws, project_name="recovery-demo")

        add_memory_entry(
            ws,
            entry_type="goal",
            title="Stable Payment Service",
            content="Maintain 99.99% uptime on core checkout endpoints.",
            priority="critical",
            source="claude-code",
        )
        add_memory_entry(
            ws,
            entry_type="session_summary",
            title="Session 1: Checkout Validation",
            content="Completed idempotency keys and currency rounding tests.",
            priority="high",
            source="claude-code",
        )

        checkpoint = create_backup(ws, label="stable-checkpoint")
        verify_backup(ws, checkpoint["backup_id"])

        # Add an experimental entry that we will roll back
        add_memory_entry(
            ws,
            entry_type="decision",
            title="Experimental Rewrite",
            content="Drop all existing endpoints and rewrite in an untested framework.",
            priority="low",
            source="opencode",
        )
        assert len(load_memory(ws)["entries"]) == 3

        preview = restore_memory(ws, backup_id=checkpoint["backup_id"], dry_run=True)
        assert preview["dry_run"] is True
        assert len(preview["preview"]["entries_removed_by_rollback"]) == 1

        restored = restore_memory(ws, backup_id=checkpoint["backup_id"], confirm=True)
        final_data = load_memory(ws)
        assert len(final_data["entries"]) == 2

        print("=== Example 03: Session Recovery & Version Rollback (VERIFIED) ===")
        print(f"Checkpoint Created      : {checkpoint['backup_id']} (SHA-256: {checkpoint['sha256'][:16]}...)")
        print(f"Dry-Run Entries Removed : {len(preview['preview']['entries_removed_by_rollback'])}")
        print(f"Restored Revision       : {restored['new_revision']}")
        print(f"Auto Safety Backup      : {restored['pre_restore_backup']}")
        print(f"Active Entries Restored : {len(final_data['entries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
