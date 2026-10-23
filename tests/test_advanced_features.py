#!/usr/bin/env python3
"""Tests for the 6 advanced AI Memory Bridge features:
1. Codebase Auto-Scanner (scan.py)
2. Stale File Reference & Drift Detection (check-stale / doctor.py)
3. BM25 + File-Affinity Relevance Search (capture.py search)
4. Automatic Git Commit & Diff Context Capture (capture.py auto-git)
5. Branch-Aware Memory & Tasks (branch filtering & priority sorting)
6. Offline Interactive HTML Dashboard (dashboard.py + XSS escaping)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ai-memory-bridge" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capture import add_memory_entry, capture_git_context  # noqa: E402
from dashboard import generate_dashboard  # noqa: E402
from doctor import run_diagnostics  # noqa: E402
from init import initialize_workspace  # noqa: E402
from memory_utils import (  # noqa: E402
    detect_stale_file_references,
    load_memory,
    search_memory_entries,
    sort_entries_by_priority,
)
from scan import scan_and_populate  # noqa: E402


class AdvancedFeaturesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)

    def test_01_codebase_auto_scanner_populates_stack_and_commands(self) -> None:
        (self.ws / "src").mkdir()
        (self.ws / "tests").mkdir()
        (self.ws / "package.json").write_text(
            json.dumps(
                {
                    "name": "fullstack-portal",
                    "dependencies": {"next": "15.0.0", "react": "19.0.0", "tailwindcss": "4.0.0"},
                    "devDependencies": {"typescript": "5.6.0", "vitest": "2.0.0"},
                    "scripts": {"dev": "next dev", "build": "next build", "test": "vitest run"},
                }
            ),
            encoding="utf-8",
        )
        (self.ws / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

        res = scan_and_populate(self.ws, apply_entries=True)
        self.assertEqual(res["status"], "scanned_and_applied")
        self.assertEqual(res["scan"]["project_name"], "fullstack-portal")
        self.assertIn("Next.js", res["scan"]["stacks"])
        self.assertIn("Node.js (pnpm)", res["scan"]["stacks"])
        self.assertGreaterEqual(len(res["saved_entry_ids"]), 2)

        data = load_memory(self.ws)
        titles = [e["title"] for e in data["entries"]]
        self.assertIn("Detected Technology Stack & Architecture Layout", titles)
        self.assertIn("Standard Build & Verification Commands", titles)

    def test_02_stale_file_reference_detection(self) -> None:
        initialize_workspace(self.ws, project_name="drift-test")
        src_dir = self.ws / "src"
        src_dir.mkdir()
        auth_file = src_dir / "auth_v1.py"
        auth_file.write_text("# auth v1\n", encoding="utf-8")

        add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Auth Module Location",
            content="Authentication middleware is implemented in `src/auth_v1.py`.",
            source="claude-code",
        )

        # While file exists, 0 stale references
        data = load_memory(self.ws)
        self.assertEqual(len(detect_stale_file_references(self.ws, data["entries"])), 0)

        # Delete the file to simulate codebase drift
        auth_file.unlink()
        stale = detect_stale_file_references(self.ws, data["entries"])
        self.assertEqual(len(stale), 1)
        self.assertIn("src/auth_v1.py", stale[0]["missing_files"])

        doc = run_diagnostics(self.ws)
        stale_check = [c for c in doc["checks"] if c["name"] == "Stale File Reference Check"][0]
        self.assertEqual(stale_check["status"], "WARN")

    def test_03_bm25_and_file_affinity_relevance_search(self) -> None:
        initialize_workspace(self.ws, project_name="search-test")
        add_memory_entry(
            self.ws,
            entry_type="decision",
            title="UI Color Palette",
            content="Use slate dark theme colors in `src/styles/theme.css`.",
            priority="low",
        )
        add_memory_entry(
            self.ws,
            entry_type="bug_fix",
            title="Stripe Webhook Retry Deadlock",
            content="Fixed exponential backoff deadlock in `src/payments/webhook_worker.py` by adding jitter.",
            priority="critical",
            tags=["payments", "retry", "webhooks"],
        )
        add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Database Connection Pool",
            content="Set max_overflow=20 in `src/db/session.py`.",
            priority="high",
        )

        data = load_memory(self.ws)
        results = search_memory_entries(
            data["entries"],
            query="exponential backoff deadlock",
            file_hint="src/payments/webhook_worker.py",
            top_k=2,
        )
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Stripe Webhook Retry Deadlock")
        self.assertGreater(results[0]["relevance_score"], 5.0)

    def test_04_auto_git_commit_and_diff_capture(self) -> None:
        initialize_workspace(self.ws, project_name="git-capture-test")
        subprocess.run(["git", "init", "-b", "feat/payments"], cwd=str(self.ws), capture_output=True, check=False)
        subprocess.run(["git", "config", "user.name", "Test Dev"], cwd=str(self.ws), capture_output=True, check=False)
        subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=str(self.ws), capture_output=True, check=False)

        (self.ws / "payment.py").write_text("def charge(): pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "payment.py"], cwd=str(self.ws), capture_output=True, check=False)
        subprocess.run(["git", "commit", "-m", "feat: add payment charger"], cwd=str(self.ws), capture_output=True, check=False)

        # Also modify a file in working tree
        (self.ws / "invoice.py").write_text("def render(): pass\n", encoding="utf-8")

        res = capture_git_context(self.ws, max_commits=3, source="codex")
        self.assertEqual(res["status"], "git_captured")
        self.assertIn("feat: add payment charger", res["entry"]["content"])
        self.assertIn("invoice.py", res["entry"]["content"])

    def test_05_branch_aware_task_prioritization(self) -> None:
        initialize_workspace(self.ws, project_name="branch-test")
        t_main = add_memory_entry(
            self.ws,
            entry_type="task_pending",
            title="Main Branch Cleanup",
            content="Clean up root README.",
            priority="high",
            branch="main",
        )["entry"]
        t_feat = add_memory_entry(
            self.ws,
            entry_type="task_pending",
            title="Feature OAuth Flow",
            content="Implement PKCE token exchange.",
            priority="medium",
            branch="feat/oauth",
        )["entry"]

        sorted_for_feat = sort_entries_by_priority([t_main, t_feat], preferred_branch="feat/oauth")
        self.assertEqual(sorted_for_feat[0]["id"], t_feat["id"])

    def test_06_html_dashboard_generation_and_xss_safety(self) -> None:
        initialize_workspace(self.ws, project_name="dashboard-test")
        add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Sanitization Check <script>alert('xss')</script>",
            content="Never render unescaped HTML tags like <img src=x onerror=alert(1)>.",
            priority="critical",
            source="antigravity",
        )
        res = generate_dashboard(self.ws)
        self.assertEqual(res["status"], "generated")
        dash_path = Path(res["dashboard_path"])
        self.assertTrue(dash_path.exists())

        html_text = dash_path.read_text(encoding="utf-8")
        self.assertIn("AI Memory Bridge", html_text)
        self.assertNotIn("<script>alert('xss')</script>", html_text)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", html_text)


if __name__ == "__main__":
    unittest.main()
