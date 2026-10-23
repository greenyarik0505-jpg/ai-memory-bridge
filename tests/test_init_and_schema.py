#!/usr/bin/env python3
"""Tests for workspace initialization, schema validation, and schema migration."""
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

import init as init_mod  # noqa: E402
from memory_utils import (  # noqa: E402
    MemoryBridgeError,
    SchemaValidationError,
    create_empty_memory,
    load_memory,
    migrate_schema,
    validate_memory_data,
)


class InitAndSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)

    def test_initialize_creates_all_artifacts_and_gitignore(self) -> None:
        res = init_mod.initialize_workspace(self.ws, project_name="demo-app")
        self.assertEqual(res["status"], "initialized")
        self.assertEqual(res["project_name"], "demo-app")
        self.assertTrue((self.ws / ".ai-memory" / "memory.json").exists())
        self.assertTrue((self.ws / ".ai-memory" / "context.md").exists())
        self.assertTrue((self.ws / ".ai-memory" / "decisions.md").exists())
        self.assertTrue((self.ws / ".ai-memory" / "tasks.md").exists())
        self.assertTrue((self.ws / ".ai-memory" / "handoffs").is_dir())
        self.assertTrue((self.ws / ".ai-memory" / "backups").is_dir())
        self.assertTrue((self.ws / ".ai-memory" / "history" / "events.jsonl").exists())
        self.assertTrue((self.ws / ".ai-memory" / "history" / "rev_00001.json").exists())

        gitignore = (self.ws / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".ai-memory/", gitignore)

    def test_idempotent_reinit_preserves_existing_data(self) -> None:
        init_mod.initialize_workspace(self.ws, project_name="first-name")
        res2 = init_mod.initialize_workspace(self.ws, project_name="second-name")
        self.assertEqual(res2["status"], "already_initialized")
        data = load_memory(self.ws)
        self.assertEqual(data["project"]["name"], "first-name")

    def test_force_reinit_requires_confirmation(self) -> None:
        init_mod.initialize_workspace(self.ws, project_name="first-name")
        with self.assertRaises(MemoryBridgeError):
            init_mod.initialize_workspace(self.ws, project_name="new-name", force=True, confirm=False)

        res = init_mod.initialize_workspace(self.ws, project_name="new-name", force=True, confirm=True)
        self.assertEqual(res["status"], "reinitialized")
        self.assertEqual(load_memory(self.ws)["project"]["name"], "new-name")

    def test_opt_in_hooks_claude_and_antigravity(self) -> None:
        res_claude = init_mod.initialize_workspace(
            self.ws, project_name="hook-test", enable_hooks=True, hook_agent="claude-code"
        )
        self.assertTrue(res_claude["hooks"]["configured"])
        claude_settings = json.loads((self.ws / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("SessionStart", claude_settings["hooks"])
        self.assertIn("Stop", claude_settings["hooks"])

        res_agy = init_mod.initialize_workspace(
            self.ws, project_name="hook-test", enable_hooks=True, hook_agent="antigravity"
        )
        self.assertTrue(res_agy["hooks"]["configured"])
        agy_hooks = json.loads((self.ws / ".agents" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("ai-memory-bridge", agy_hooks)
        self.assertTrue(agy_hooks["ai-memory-bridge"]["enabled"])

    def test_schema_validation_rejects_invalid_structures(self) -> None:
        valid = create_empty_memory("valid-proj")
        validate_memory_data(valid)

        bad_version = dict(valid, schema_version="9.9.9")
        with self.assertRaises(SchemaValidationError):
            validate_memory_data(bad_version)

        bad_type = create_empty_memory("valid-proj")
        bad_type["entries"] = [
            {
                "id": "mem_1",
                "type": "invalid_type",
                "title": "T",
                "content": "C",
                "source": "manual",
                "created_at": "2026-10-23T00:00:00Z",
                "updated_at": "2026-10-23T00:00:00Z",
                "status": "active",
                "priority": "high",
            }
        ]
        with self.assertRaises(SchemaValidationError):
            validate_memory_data(bad_type)

    def test_schema_migration_from_v0_1_0(self) -> None:
        legacy = {
            "schema_version": "0.1.0",
            "project_name": "legacy-service",
            "entries": [
                {
                    "type": "task",
                    "content": "Implement Redis rate limiter",
                    "status": "active",
                },
                {
                    "type": "task",
                    "content": "Setup repository structure",
                    "status": "completed",
                },
            ],
        }
        migrated = migrate_schema(legacy)
        validate_memory_data(migrated)
        self.assertEqual(migrated["schema_version"], "1.0.0")
        self.assertEqual(migrated["project"]["name"], "legacy-service")
        self.assertEqual(migrated["entries"][0]["type"], "task_pending")
        self.assertEqual(migrated["entries"][1]["type"], "task_done")
        self.assertEqual(len(migrated["entries"][0]["content_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
