#!/usr/bin/env python3
"""End-to-end CLI and cross-platform (Windows/macOS/Linux) subprocess tests."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ai-memory-bridge" / "scripts"


class CliAndDoctorSubprocessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)

    def run_script(self, script_name: str, *args: str, expect_ok: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *args]
        proc = subprocess.run(
            cmd,
            cwd=str(self.ws),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        if expect_ok:
            self.assertEqual(proc.returncode, 0, f"Command failed: {cmd}\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
        else:
            self.assertNotEqual(proc.returncode, 0, f"Expected failure but got 0: {cmd}")
        return proc

    def test_full_cli_lifecycle_and_doctor(self) -> None:
        # 1. Init
        r_init = self.run_script(
            "init.py", "--workspace", str(self.ws), "--project-name", "cli-e2e", "--enable-hooks", "--agent", "claude-code", "--json"
        )
        init_data = json.loads(r_init.stdout)
        self.assertEqual(init_data["status"], "initialized")

        # 2. Capture Add
        r_add = self.run_script(
            "capture.py",
            "add",
            "--workspace",
            str(self.ws),
            "--type",
            "goal",
            "--title",
            "Cross-Platform CLI",
            "--content",
            "Ensure all scripts work identically on Windows, macOS, and Linux.",
            "--priority",
            "critical",
            "--source",
            "claude-code",
            "--json",
        )
        add_data = json.loads(r_add.stdout)
        self.assertEqual(add_data["status"], "added")

        # 3. Hook SessionStart and Stop auto-save execution
        r_hook = self.run_script("capture.py", "--workspace", str(self.ws), "--hook-event", "SessionStart")
        hook_payload = json.loads(r_hook.stdout)
        self.assertIn("injectSteps", hook_payload)

        # Initialize git in temp workspace and modify a file to verify Stop hook auto-captures workspace progress
        subprocess.run(["git", "init"], cwd=str(self.ws), capture_output=True, check=False)
        (self.ws / "feature.py").write_text("def hello(): return 'world'\n", encoding="utf-8")
        r_stop = self.run_script("capture.py", "--workspace", str(self.ws), "--hook-event", "Stop")
        self.assertEqual(json.loads(r_stop.stdout), {})
        r_list = self.run_script("capture.py", "list", "--workspace", str(self.ws), "--type", "session_summary", "--json")
        summaries = json.loads(r_list.stdout)["entries"]
        self.assertEqual(len(summaries), 1)
        self.assertIn("feature.py", summaries[0]["content"])

        # 4. Backup Create
        r_backup = self.run_script("backup.py", "create", "--workspace", str(self.ws), "--label", "e2e", "--json")
        backup_data = json.loads(r_backup.stdout)
        self.assertEqual(backup_data["status"], "created")

        # 5. Handoff to Cursor
        r_handoff = self.run_script(
            "handoff.py", "--workspace", str(self.ws), "--from", "claude-code", "--to", "cursor", "--json"
        )
        handoff_data = json.loads(r_handoff.stdout)
        self.assertEqual(handoff_data["status"], "handoff_ready")

        # 6. Sync all agents
        r_sync = self.run_script("sync.py", "--workspace", str(self.ws), "--targets", "all", "--json")
        sync_data = json.loads(r_sync.stdout)
        self.assertEqual(sync_data["status"], "synced")

        # 7. Doctor check (should pass with 0 failures)
        r_doc = self.run_script("doctor.py", "--workspace", str(self.ws), "--json")
        doc_data = json.loads(r_doc.stdout)
        self.assertTrue(doc_data["healthy"])
        self.assertEqual(doc_data["summary"]["fail"], 0)


if __name__ == "__main__":
    unittest.main()
