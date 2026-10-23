#!/usr/bin/env python3
"""Tests for backup creation, checksum verification, and safe version restoration."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ai-memory-bridge" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from backup import create_backup, list_backups, verify_backup  # noqa: E402
from capture import add_memory_entry  # noqa: E402
from init import initialize_workspace  # noqa: E402
from memory_utils import MemoryBridgeError, load_memory  # noqa: E402
from restore import restore_memory  # noqa: E402


class BackupAndRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        initialize_workspace(self.ws, project_name="backup-test")

    def test_create_list_verify_and_restore_backup(self) -> None:
        add_memory_entry(
            self.ws,
            entry_type="goal",
            title="Initial Goal",
            content="Build v1 release.",
            source="claude-code",
        )
        b1 = create_backup(self.ws, label="v1-milestone")
        self.assertEqual(b1["status"], "created")
        self.assertEqual(b1["entry_count"], 1)

        verified = verify_backup(self.ws, b1["backup_id"])
        self.assertEqual(verified["status"], "verified")

        # Add a second entry that we will roll back
        add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Temporary Experiment",
            content="Experimental architecture to roll back.",
            source="cursor",
        )
        self.assertEqual(len(load_memory(self.ws)["entries"]), 2)

        # Dry-run preview first
        preview = restore_memory(self.ws, backup_id=b1["backup_id"], dry_run=True)
        self.assertTrue(preview["dry_run"])
        self.assertEqual(len(preview["preview"]["entries_removed_by_rollback"]), 1)
        self.assertEqual(len(load_memory(self.ws)["entries"]), 2)

        # Restore without --confirm must fail
        with self.assertRaises(MemoryBridgeError):
            restore_memory(self.ws, backup_id=b1["backup_id"], dry_run=False, confirm=False)

        # Confirmed restore succeeds and creates a pre-restore safety backup
        restored = restore_memory(self.ws, backup_id=b1["backup_id"], dry_run=False, confirm=True)
        self.assertEqual(restored["status"], "restored")
        self.assertTrue(restored["pre_restore_backup"].startswith("backup_"))
        self.assertEqual(len(load_memory(self.ws)["entries"]), 1)

        all_backups = list_backups(self.ws)
        self.assertGreaterEqual(len(all_backups), 2)

    def test_restore_by_history_revision(self) -> None:
        add_memory_entry(
            self.ws,
            entry_type="constraint",
            title="Constraint R2",
            content="Must work offline.",
        )
        rev_after_first = load_memory(self.ws)["revision"]

        add_memory_entry(
            self.ws,
            entry_type="constraint",
            title="Constraint R3",
            content="Extra constraint added in next revision.",
        )
        self.assertEqual(len(load_memory(self.ws)["entries"]), 2)

        res = restore_memory(self.ws, revision=rev_after_first, confirm=True)
        self.assertEqual(res["status"], "restored")
        self.assertEqual(len(load_memory(self.ws)["entries"]), 1)

    def test_tampered_backup_checksum_is_rejected(self) -> None:
        b = create_backup(self.ws, label="tamper-check")
        b_path = Path(b["path"])
        bundle = json.loads(b_path.read_text(encoding="utf-8"))
        bundle["memory"]["project"]["name"] = "tampered-name"
        b_path.write_text(json.dumps(bundle), encoding="utf-8")

        with self.assertRaises(MemoryBridgeError):
            verify_backup(self.ws, b["backup_id"])


if __name__ == "__main__":
    unittest.main()
