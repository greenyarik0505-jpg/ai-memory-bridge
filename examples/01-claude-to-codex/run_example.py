#!/usr/bin/env python3
"""Reproducible Example 1: Claude Code -> OpenAI Codex Handoff."""
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

from capture import import_entries_from_json  # noqa: E402
from handoff import create_handoff  # noqa: E402
from init import initialize_workspace  # noqa: E402
from memory_utils import load_memory  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="amb_ex01_") as tmp:
        ws = Path(tmp)
        # Pre-populate an existing AGENTS.md to verify non-destructive update
        (ws / "AGENTS.md").write_text("# Repository Guidelines\n\n- Run pytest before every commit.\n", encoding="utf-8")
        shutil.copy2(EXAMPLE_DIR / "sample_entries.json", ws / "sample_entries.json")

        init_res = initialize_workspace(ws, project_name="webhook-service")
        imp_res = import_entries_from_json(ws, Path("sample_entries.json"), default_source="claude-code")
        handoff_res = create_handoff(
            ws,
            target_agent="codex",
            source_agent="claude-code",
            focus_note="HMAC middleware is done; implement the PostgreSQL outbox worker next.",
            apply_rules=True,
        )

        data = load_memory(ws)
        handoff_md = (ws / ".ai-memory" / "handoffs" / "handoff-codex.md").read_text(encoding="utf-8")
        agents_md = (ws / "AGENTS.md").read_text(encoding="utf-8")

        assert len(data["entries"]) == 4, "Expected 4 imported entries"
        assert "Agent Handoff Packet: claude-code -> OpenAI Codex" in handoff_md
        assert "Implement Outbox Worker & Retry Backoff" in handoff_md
        assert "Run pytest before every commit." in agents_md
        assert "<!-- AI-MEMORY-BRIDGE:START -->" in agents_md

        print("=== Example 01: Claude Code -> OpenAI Codex (VERIFIED) ===")
        print(f"Project        : {init_res['project_name']}")
        print(f"Entries Saved  : {imp_res['added_count']} (from claude-code)")
        print(f"Handoff Packet : {handoff_res['relative_handoff_file']} (~{handoff_res['estimated_tokens']} tokens)")
        print(f"Rule Updated   : {handoff_res['rule_sync']['relative_rule_file']} ({handoff_res['rule_sync']['action']})")
        print("\n--- Preview of Generated .ai-memory/handoffs/handoff-codex.md ---")
        print("\n".join(handoff_md.splitlines()[:28]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
