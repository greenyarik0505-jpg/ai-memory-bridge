#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Synchronize project memory across .ai-memory/ views and multi-agent context files.

Supports non-destructive bounded updates to CLAUDE.md, AGENTS.md, GEMINI.md,
.cursor/rules/ai-memory-bridge.mdc, .agents/rules/ai-memory-bridge.md, and
.github/instructions/ai-memory-bridge.instructions.md, plus safe markdown import.

Usage:
  python scripts/sync.py [--workspace .] [--targets detected|all|claude-code,cursor,...] [--compact] [--dry-run] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from capture import add_memory_entry  # noqa: E402
from handoff import AGENT_PROFILES, apply_target_agent_rules  # noqa: E402
from memory_utils import (  # noqa: E402
    MARKER_END,
    MARKER_START,
    SUPPORTED_AGENTS,
    MemoryBridgeError,
    compact_memory,
    load_memory,
    safe_resolve_path,
    save_memory,
)

HEADING_TO_TYPE = {
    "goal": "goal",
    "goals": "goal",
    "project goals": "goal",
    "decision": "decision",
    "decisions": "decision",
    "architectural decisions": "decision",
    "architecture": "decision",
    "constraint": "constraint",
    "constraints": "constraint",
    "technical constraints": "constraint",
    "preference": "preference",
    "preferences": "preference",
    "user preferences": "preference",
    "bug": "bug_fix",
    "bugs": "bug_fix",
    "bug fixes": "bug_fix",
    "next step": "next_step",
    "next steps": "next_step",
    "pending tasks": "task_pending",
    "tasks": "task_pending",
    "completed tasks": "task_done",
}


def detect_workspace_agents(workspace_root: Path) -> list[str]:
    """Detect which AI coding agents are used in the workspace based on directories or config files."""
    detected: list[str] = []
    checks = [
        ("claude-code", (".claude", "CLAUDE.md")),
        ("codex", (".codex", "AGENTS.md")),
        ("cursor", (".cursor", ".cursorrules")),
        ("antigravity", (".agents", ".agent")),
        ("gemini-cli", (".gemini", "GEMINI.md")),
        ("opencode", (".opencode",)),
        ("github-copilot", (".github/copilot-instructions.md", ".github/instructions", ".github/skills")),
    ]
    for agent_name, markers in checks:
        for marker in markers:
            candidate = workspace_root / marker
            if candidate.exists() and not candidate.is_symlink():
                detected.append(agent_name)
                break
    return detected


def import_from_markdown_file(
    workspace_root: Path,
    md_rel_path: str,
    source_agent: str = "markdown-import",
    allow_redact_secrets: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Safely extract bullet items under recognized headings from an existing markdown file."""
    md_path = safe_resolve_path(workspace_root, md_rel_path)
    if not md_path.exists():
        raise MemoryBridgeError(f"Markdown file not found: {md_path}")

    raw_text = md_path.read_text(encoding="utf-8", errors="replace")
    # Strip any existing AI-MEMORY-BRIDGE managed block so we don't re-import our own generated summary
    if MARKER_START in raw_text and MARKER_END in raw_text:
        s_idx = raw_text.index(MARKER_START)
        e_idx = raw_text.index(MARKER_END) + len(MARKER_END)
        if s_idx < e_idx:
            raw_text = raw_text[:s_idx] + raw_text[e_idx:]

    current_type = "decision"
    imported_ids: list[str] = []
    dedup_ids: list[str] = []

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = re.match(r"^#{1,4}\s+(.+)$", line)
        if heading_match:
            h_text = heading_match.group(1).strip().lower()
            for key, mapped_type in HEADING_TO_TYPE.items():
                if key in h_text:
                    current_type = mapped_type
                    break
            continue

        bullet_match = re.match(r"^[-*]\s+(?:\[([ xX])\]\s+)?(.+)$", line)
        if bullet_match:
            checkbox, item_text = bullet_match.groups()
            entry_type = current_type
            if checkbox is not None:
                entry_type = "task_done" if checkbox.lower() == "x" else "task_pending"
            clean_item = item_text.strip()
            if len(clean_item) < 5:
                continue
            if ":" in clean_item:
                head, tail = clean_item.split(":", 1)
                title = re.sub(r"[*_`\[\]]", "", head).strip()[:72]
                content = tail.strip() or clean_item
            else:
                title = re.sub(r"[*_`\[\]]", "", clean_item)[:60].strip()
                content = clean_item

            res = add_memory_entry(
                workspace_root=workspace_root,
                entry_type=entry_type,
                title=title,
                content=content,
                source=source_agent,
                priority="medium",
                allow_redact_secrets=allow_redact_secrets,
                dry_run=dry_run,
            )
            if res["status"] == "deduplicated":
                dedup_ids.append(res["entry"]["id"])
            else:
                imported_ids.append(res["entry"].get("id", "dry-run"))

    return {
        "file": str(md_path),
        "imported_count": len(imported_ids),
        "deduplicated_count": len(dedup_ids),
    }


def sync_workspace_memory(
    workspace_root: Path,
    targets: list[str] | None = None,
    compact: bool = False,
    max_tokens: int = 2500,
    import_md: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Synchronize canonical memory with markdown views and target agent rule files."""
    workspace_root = workspace_root.resolve()

    import_result = None
    if import_md:
        import_result = import_from_markdown_file(
            workspace_root, import_md, source_agent="sync-import", dry_run=dry_run
        )

    data = load_memory(workspace_root)
    compaction_stats = None
    if compact:
        compaction_stats = compact_memory(data, max_tokens=max_tokens)

    if not dry_run:
        save_memory(
            workspace_root,
            data,
            action="sync",
            agent="sync",
            details={"compact": compact, "targets": targets or []},
            increment_revision=bool(compact),
        )
        try:
            from dashboard import generate_dashboard
            generate_dashboard(workspace_root)
        except Exception:
            pass

    if not targets or targets == ["detected"]:
        resolved_targets = detect_workspace_agents(workspace_root)
    elif targets == ["all"]:
        resolved_targets = [a for a in SUPPORTED_AGENTS if a != "generic"]
    else:
        resolved_targets = []
        for t in targets:
            t_norm = t.strip().lower()
            if t_norm not in SUPPORTED_AGENTS:
                raise MemoryBridgeError(f"Unsupported sync target '{t}'. Valid: {SUPPORTED_AGENTS}")
            if t_norm not in resolved_targets:
                resolved_targets.append(t_norm)

    synced_rules: list[dict[str, Any]] = []
    seen_rule_files: set[str] = set()
    for agent_name in resolved_targets:
        rule_rel = AGENT_PROFILES[agent_name]["rule_file"]
        if rule_rel in seen_rule_files:
            synced_rules.append(
                {
                    "agent": agent_name,
                    "relative_rule_file": rule_rel,
                    "action": "shared_with_previous_agent",
                    "dry_run": dry_run,
                }
            )
            continue
        seen_rule_files.add(rule_rel)
        res = apply_target_agent_rules(
            workspace_root=workspace_root,
            data=data,
            target_agent=agent_name,
            dry_run=dry_run,
        )
        synced_rules.append(res)

    return {
        "status": "synced",
        "dry_run": dry_run,
        "revision": data["revision"],
        "active_entries": len([e for e in data["entries"] if e.get("status") in ("active", "conflicted")]),
        "unresolved_conflicts": len([c for c in data.get("conflicts", []) if c.get("status") == "unresolved"]),
        "compaction": compaction_stats,
        "imported": import_result,
        "synced_targets": synced_rules,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize AI Memory Bridge views and agent rule files."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    parser.add_argument(
        "--targets",
        default="detected",
        help="Comma-separated agent targets (claude-code,codex,cursor,antigravity,gemini-cli,opencode,github-copilot), 'detected', or 'all'.",
    )
    parser.add_argument("--compact", action="store_true", help="Compact memory before syncing.")
    parser.add_argument("--max-tokens", type=int, default=2500, help="Token budget when --compact is enabled.")
    parser.add_argument("--import-markdown", default=None, help="Optional relative markdown file to import bullets from.")
    parser.add_argument("--dry-run", action="store_true", help="Preview sync without writing files.")
    parser.add_argument("--json", action="store_true", help="Output result as JSON.")
    args = parser.parse_args(argv)

    raw_targets = [t.strip() for t in args.targets.split(",") if t.strip()]

    try:
        res = sync_workspace_memory(
            workspace_root=Path(args.workspace),
            targets=raw_targets,
            compact=args.compact,
            max_tokens=args.max_tokens,
            import_md=args.import_markdown,
            dry_run=args.dry_run,
        )
    except MemoryBridgeError as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        prefix = "[DRY-RUN] " if res["dry_run"] else ""
        print(
            f"{prefix}Synchronized project memory (rev {res['revision']}, "
            f"{res['active_entries']} active entries, {res['unresolved_conflicts']} conflicts)"
        )
        if res["synced_targets"]:
            for t in res["synced_targets"]:
                print(f"  - {t['agent']}: {t['relative_rule_file']} ({t['action']})")
        else:
            print("  - Refreshed .ai-memory/context.md, decisions.md, and tasks.md (no external agent rule targets selected).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
