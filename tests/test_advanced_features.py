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

from capture import (  # noqa: E402
    add_memory_entry,
    capture_git_context,
    complete_pending_task,
    run_and_watch_command,
    save_global_entry,
    sync_global_preferences_to_workspace,
)
from dashboard import generate_dashboard  # noqa: E402
from diff import compute_memory_diff  # noqa: E402
from doctor import run_diagnostics  # noqa: E402
from export import export_memory  # noqa: E402
from guard import run_guard  # noqa: E402
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
        self.assertIn("langSelect", html_text)
        self.assertIn("Русский", html_text)
        self.assertIn("Українська", html_text)
        self.assertIn("中文", html_text)
        self.assertNotIn("<script>alert('xss')</script>", html_text)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", html_text)

    def test_07_multilingual_search_dedup_and_conflict(self) -> None:
        initialize_workspace(self.ws, project_name="multilingual-test")

        # 1. Russian entry + deduplication
        r1 = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Кэширование сессий через Redis",
            content="Обязательно использовать Redis Cluster для хранения пользовательских сессий.",
            priority="high",
            source="claude-code",
        )
        self.assertEqual(r1["status"], "added")

        r1_dup = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Кэширование сессий через Redis",
            content="Обязательно использовать Redis Cluster для хранения пользовательских сессий.",
            priority="high",
            source="cursor",
        )
        self.assertEqual(r1_dup["status"], "deduplicated")

        # 2. Russian conflict detection (polarity inversion on same topic)
        r1_conflict = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Кэширование сессий через Redis",
            content="Запрещено использовать Redis Cluster для хранения пользовательских сессий.",
            priority="high",
            source="codex",
        )
        self.assertEqual(r1_conflict["status"], "added")
        self.assertEqual(r1_conflict["entry"]["status"], "conflicted")
        self.assertEqual(len(r1_conflict["conflicts_detected"]), 1)

        # 3. Ukrainian & Chinese entries + BM25 search
        add_memory_entry(
            self.ws,
            entry_type="goal",
            title="Безпека платіжного шлюзу",
            content="Забезпечити перевірку підписів вебхуків у модулі `src/payments/ukr_gateway.py`.",
            priority="critical",
            source="antigravity",
        )
        add_memory_entry(
            self.ws,
            entry_type="constraint",
            title="数据库连接池配置",
            content="生产环境必须使用 PostgreSQL 连接池，禁止使用单连接模式。",
            priority="high",
            source="gemini-cli",
        )

        data = load_memory(self.ws)
        uk_hits = search_memory_entries(data["entries"], query="перевірку підписів вебхуків", top_k=2)
        self.assertGreaterEqual(len(uk_hits), 1)
        self.assertEqual(uk_hits[0]["title"], "Безпека платіжного шлюзу")

        zh_hits = search_memory_entries(data["entries"], query="数据库连接池", top_k=2)
        self.assertGreaterEqual(len(zh_hits), 1)
        self.assertEqual(zh_hits[0]["title"], "数据库连接池配置")

    def test_08_architecture_and_constraint_guard(self) -> None:
        initialize_workspace(self.ws, project_name="guard-test")
        add_memory_entry(
            self.ws,
            entry_type="constraint",
            title="HTTP Client Policy",
            content="Use `httpx` for async requests; never use `requests` in application code.",
            priority="critical",
        )
        add_memory_entry(
            self.ws,
            entry_type="constraint",
            title="Запрет sqlite3",
            content="Запрещено использовать `sqlite3` в продакшене.",
            priority="high",
        )

        src_dir = self.ws / "src"
        src_dir.mkdir()
        app_py = src_dir / "client.py"
        app_py.write_text("import requests\nimport sqlite3\n\ndef fetch(): pass\n", encoding="utf-8")

        report = run_guard(self.ws)
        self.assertEqual(report["status"], "violation")
        self.assertEqual(report["violations_count"], 2)
        targets = {v["target"] for v in report["violations"]}
        self.assertIn("requests", targets)
        self.assertIn("sqlite3", targets)

        # Fix the code to comply with memory constraints
        app_py.write_text("import httpx\n\ndef fetch(): pass\n", encoding="utf-8")
        report_clean = run_guard(self.ws)
        self.assertEqual(report_clean["status"], "pass")
        self.assertEqual(report_clean["violations_count"], 0)

    def test_09_test_watcher_auto_captures_failure_and_resolution(self) -> None:
        initialize_workspace(self.ws, project_name="watcher-test")
        check_script = self.ws / "check_math.py"
        check_script.write_text("import sys\nprint('AssertionError in src/calc.py:42')\nsys.exit(1)\n", encoding="utf-8")

        # 1. Failing run -> creates high-priority task_pending
        fail_res = run_and_watch_command(
            self.ws,
            command=[sys.executable, "check_math.py"],
            source="claude-code",
        )
        self.assertEqual(fail_res["status"], "command_failed")
        self.assertEqual(fail_res["action_taken"], "created_pending_task")
        task_id = fail_res["entry"]["id"]

        # 2. Passing run -> auto-completes task_pending and records bug_fix
        check_script.write_text("import sys\nprint('OK')\nsys.exit(0)\n", encoding="utf-8")
        pass_res = run_and_watch_command(
            self.ws,
            command=[sys.executable, "check_math.py"],
            source="codex",
        )
        self.assertEqual(pass_res["status"], "command_passed_and_resolved")
        self.assertEqual(pass_res["resolved_task_id"], task_id)
        self.assertEqual(pass_res["bug_fix_entry"]["type"], "bug_fix")

    def test_10_global_developer_profile_sync(self) -> None:
        global_dir = self.ws / "global_profile"
        g_res = save_global_entry(
            entry_type="preference",
            title="Russian Language Communication",
            content="Always communicate with the user in Russian.",
            priority="critical",
            source="user",
            global_dir=global_dir,
        )
        self.assertEqual(g_res["status"], "added_global")

        project_ws = self.ws / "new_repo"
        project_ws.mkdir()
        initialize_workspace(project_ws, project_name="new-repo")

        sync_res = sync_global_preferences_to_workspace(project_ws, global_dir=global_dir)
        self.assertEqual(sync_res["status"], "global_synced")
        self.assertEqual(sync_res["imported_count"], 1)

        data = load_memory(project_ws)
        titles = [e["title"] for e in data["entries"]]
        self.assertIn("Russian Language Communication", titles)

    def test_11_memory_time_travel_diff(self) -> None:
        initialize_workspace(self.ws, project_name="diff-test")
        # Revision 1 is initial empty memory
        t_res = add_memory_entry(
            self.ws,
            entry_type="task_pending",
            title="Implement JWT Auth",
            content="Add token verification middleware.",
            priority="high",
            source="claude-code",
        )
        d1_res = add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Cache Backend",
            content="Use in-memory LRU cache.",
            priority="medium",
            source="claude-code",
        )
        complete_pending_task(self.ws, t_res["entry"]["id"], resolution_note="Done", source="codex")
        add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Cache Backend",
            content="Migrated to Redis 7 for multi-worker cache consistency.",
            priority="high",
            supersedes=d1_res["entry"]["id"],
            source="codex",
        )

        diff = compute_memory_diff(self.ws, from_rev=2)
        self.assertEqual(diff["status"], "diff_computed")
        self.assertGreaterEqual(diff["summary"]["completed_tasks_count"], 1)
        self.assertGreaterEqual(diff["summary"]["superseded_count"], 1)

    def test_12_export_pr_changelog_and_compact(self) -> None:
        initialize_workspace(self.ws, project_name="export-test")
        add_memory_entry(
            self.ws,
            entry_type="goal",
            title="Zero-Downtime Billing Migration",
            content="Migrate subscription webhooks without dropping events.",
            priority="critical",
        )
        t = add_memory_entry(
            self.ws,
            entry_type="task_pending",
            title="Idempotency Keys",
            content="Add idempotency key deduplication table.",
            priority="high",
        )
        complete_pending_task(self.ws, t["entry"]["id"], resolution_note="Verified", source="cursor")

        pr_res = export_memory(self.ws, export_format="pr", out_file="PR_SUMMARY.md")
        self.assertEqual(pr_res["status"], "exported")
        self.assertIn("Pull Request Summary", pr_res["content"])
        self.assertIn("Idempotency Keys", pr_res["content"])
        self.assertTrue((self.ws / "PR_SUMMARY.md").exists())

        cl_res = export_memory(self.ws, export_format="changelog")
        self.assertIn("## [Unreleased]", cl_res["content"])

        compact_res = export_memory(self.ws, export_format="compact")
        self.assertIn("Zero-Downtime Billing Migration", compact_res["content"])


if __name__ == "__main__":
    unittest.main()
