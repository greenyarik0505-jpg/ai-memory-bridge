#!/usr/bin/env python3
"""Tests for cross-agent handoff packets and non-destructive rule synchronization."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ai-memory-bridge" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capture import add_memory_entry  # noqa: E402
from handoff import create_handoff  # noqa: E402
from init import initialize_workspace  # noqa: E402
from memory_utils import load_memory  # noqa: E402
from sync import detect_workspace_agents, sync_workspace_memory  # noqa: E402


class HandoffAndSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        initialize_workspace(self.ws, project_name="bridge-demo")
        add_memory_entry(
            self.ws,
            entry_type="goal",
            title="Seamless Handoff",
            content="Allow switching from Claude Code to Codex and Cursor without losing state.",
            source="claude-code",
            priority="critical",
        )
        add_memory_entry(
            self.ws,
            entry_type="decision",
            title="Storage Format",
            content="Store canonical memory in .ai-memory/memory.json with atomic writes.",
            source="claude-code",
            priority="high",
        )
        add_memory_entry(
            self.ws,
            entry_type="next_step",
            title="Implement Sync CLI",
            content="Add bounded marker updates for CLAUDE.md and AGENTS.md.",
            source="claude-code",
            priority="high",
        )

    def test_handoff_preserves_existing_user_rules_in_agents_md(self) -> None:
        agents_md = self.ws / "AGENTS.md"
        original_custom_rule = "# Custom Project Rules\n\nAlways run ruff before committing.\n"
        agents_md.write_text(original_custom_rule, encoding="utf-8")

        res = create_handoff(
            self.ws,
            target_agent="codex",
            source_agent="claude-code",
            focus_note="Continue with the sync CLI task.",
            apply_rules=True,
        )
        self.assertEqual(res["status"], "handoff_ready")
        self.assertTrue((self.ws / ".ai-memory" / "handoffs" / "handoff-codex.md").exists())

        updated_agents_md = agents_md.read_text(encoding="utf-8")
        self.assertIn("Always run ruff before committing.", updated_agents_md)
        self.assertIn("<!-- AI-MEMORY-BRIDGE:START -->", updated_agents_md)
        self.assertIn("Seamless Handoff", updated_agents_md)

    def test_cursor_and_antigravity_and_copilot_dedicated_rule_files(self) -> None:
        # Create another user cursor rule to ensure it is untouched
        cursor_rules_dir = self.ws / ".cursor" / "rules"
        cursor_rules_dir.mkdir(parents=True, exist_ok=True)
        user_mdc = cursor_rules_dir / "style.mdc"
        user_mdc.write_text("---\ndescription: User style\n---\nUse 2 spaces.\n", encoding="utf-8")

        res = sync_workspace_memory(
            self.ws,
            targets=["cursor", "antigravity", "github-copilot", "gemini-cli"],
        )
        self.assertEqual(res["status"], "synced")
        self.assertTrue((cursor_rules_dir / "ai-memory-bridge.mdc").exists())
        self.assertEqual(user_mdc.read_text(encoding="utf-8"), "---\ndescription: User style\n---\nUse 2 spaces.\n")
        self.assertTrue((self.ws / ".agents" / "rules" / "ai-memory-bridge.md").exists())
        self.assertTrue((self.ws / ".github" / "instructions" / "ai-memory-bridge.instructions.md").exists())
        self.assertTrue((self.ws / "GEMINI.md").exists())

    def test_detect_workspace_agents_and_import_markdown(self) -> None:
        (self.ws / "CLAUDE.md").write_text(
            "# Notes\n\n## Architectural Decisions\n- Caching Layer: Use in-memory LRU cache for lookup tables.\n",
            encoding="utf-8",
        )
        detected = detect_workspace_agents(self.ws)
        self.assertIn("claude-code", detected)

        sync_res = sync_workspace_memory(
            self.ws,
            targets=["detected"],
            import_md="CLAUDE.md",
        )
        self.assertEqual(sync_res["imported"]["imported_count"], 1)
        data = load_memory(self.ws)
        titles = [e["title"] for e in data["entries"]]
        self.assertIn("Caching Layer", titles)


if __name__ == "__main__":
    unittest.main()
