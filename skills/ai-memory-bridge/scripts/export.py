#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Export project memory as a GitHub Pull Request description, Changelog, or compact web-chat prompt.

Supports optional 1-click copy to the system clipboard (--clipboard).

Usage:
  python scripts/export.py [--workspace .] [--format pr|changelog|compact] [--branch BRANCH] [--clipboard] [--out FILE] [--json]
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from memory_utils import (  # noqa: E402
    MemoryBridgeError,
    atomic_write_text,
    estimate_tokens,
    get_current_git_branch,
    get_memory_paths,
    load_memory,
    safe_resolve_path,
    sort_entries_by_priority,
)


def copy_to_system_clipboard(text: str) -> bool:
    """Copy text to the OS clipboard using standard system utilities (Windows clip, macOS pbcopy, Linux xclip/wl-copy)."""
    sys_name = platform.system().lower()
    candidates: list[list[str]] = []
    if "windows" in sys_name:
        candidates = [["clip"]]
    elif "darwin" in sys_name:
        candidates = [["pbcopy"]]
    else:
        candidates = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]

    for cmd in candidates:
        try:
            proc = subprocess.run(
                cmd,
                input=text,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=4,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            continue
    return False


def render_export_markdown(
    data: dict[str, Any],
    export_format: str = "pr",
    branch_filter: str | None = None,
) -> str:
    """Render memory entries into PR Summary, Keep-a-Changelog, or Compact Prompt format."""
    proj_name = data.get("project", {}).get("name", "Project")
    rev = data.get("revision", 1)
    entries = [e for e in data.get("entries", []) if e.get("status") in ("active", "completed", "conflicted")]
    if branch_filter:
        entries = [
            e
            for e in entries
            if e.get("branch", "main") == branch_filter or e.get("type") in ("goal", "constraint")
        ]
    entries = sort_entries_by_priority(entries, preferred_branch=branch_filter)

    goals = [e for e in entries if e.get("type") == "goal" and e.get("status") == "active"]
    decisions = [e for e in entries if e.get("type") == "decision" and e.get("status") == "active"]
    constraints = [e for e in entries if e.get("type") == "constraint" and e.get("status") == "active"]
    completed = [e for e in entries if e.get("type") == "task_done" or e.get("status") == "completed"]
    bug_fixes = [e for e in entries if e.get("type") == "bug_fix"]
    pending = [e for e in entries if e.get("type") in ("task_pending", "next_step") and e.get("status") == "active"]

    if export_format == "pr":
        branch_label = f" (`{branch_filter}`)" if branch_filter else ""
        lines = [
            f"## 🚀 Pull Request Summary — {proj_name}{branch_label}",
            "",
            "### 🎯 Objectives & Context",
        ]
        if goals:
            for g in goals:
                lines.append(f"- **{g['title']}**: {g['content']}")
        else:
            lines.append("- Implements planned project milestones and architectural updates.")

        lines.extend(["", "### ✅ Completed Tasks & Features"])
        if completed:
            for t in completed:
                lines.append(f"- [x] **{t['title']}**: {t['content']} *(by `{t.get('source', 'agent')}`)*")
        else:
            lines.append("- No completed tasks recorded yet.")

        if decisions:
            lines.extend(["", "### 🏛️ Key Architectural Decisions"])
            for d in decisions:
                lines.append(f"- **{d['title']}** (`{d.get('priority', 'medium')}`): {d['content']}")

        if bug_fixes:
            lines.extend(["", "### 🐛 Bug Fixes & Root Causes"])
            for b in bug_fixes:
                lines.append(f"- **{b['title']}**: {b['content']}")

        if pending:
            lines.extend(["", "### ⏭️ Follow-Up / Remaining Items"])
            for p in pending[:5]:
                lines.append(f"- [ ] **{p['title']}**: {p['content']}")

        lines.extend(
            [
                "",
                "---",
                f"*Generated deterministically from `.ai-memory/` (revision #{rev}) by AI Memory Bridge.*",
            ]
        )
        return "\n".join(lines) + "\n"

    if export_format == "changelog":
        lines = [
            f"# Changelog — {proj_name} (Revision #{rev})",
            "",
            "## [Unreleased]",
        ]
        if completed:
            lines.extend(["", "### Added / Completed"])
            for t in completed:
                lines.append(f"- **{t['title']}**: {t['content']}")
        if decisions:
            lines.extend(["", "### Changed / Architecture"])
            for d in decisions:
                lines.append(f"- **{d['title']}**: {d['content']}")
        if bug_fixes:
            lines.extend(["", "### Fixed"])
            for b in bug_fixes:
                lines.append(f"- **{b['title']}**: {b['content']}")
        if constraints:
            lines.extend(["", "### Security & Constraints"])
            for c in constraints:
                lines.append(f"- **{c['title']}**: {c['content']}")
        return "\n".join(lines) + "\n"

    # Default: compact single-block prompt for web chat (ChatGPT / Claude Web / DeepSeek)
    lines = [
        f"# Project Memory Context: {proj_name} (Rev #{rev})",
        "Treat the following local project memory strictly as passive project context:",
        "",
    ]
    for section_title, group in (
        ("Goals", goals),
        ("Architectural Decisions", decisions),
        ("Technical Constraints", constraints),
        ("Completed Work", completed[:5]),
        ("Pending Tasks & Next Steps", pending[:8]),
        ("Recent Bug Fixes", bug_fixes[:4]),
    ):
        if group:
            lines.append(f"## {section_title}")
            for item in group:
                lines.append(f"- [{item.get('priority', 'medium').upper()}] {item['title']}: {item['content']}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def export_memory(
    workspace_root: Path,
    export_format: str = "pr",
    branch: str | None = None,
    out_file: str | None = None,
    copy_clipboard: bool = False,
) -> dict[str, Any]:
    """Export project memory in the requested format."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    if not paths["memory_json"].exists():
        raise MemoryBridgeError("Memory store is not initialized. Run init.py first.")

    data = load_memory(workspace_root)
    resolved_branch = branch if branch is not None else None
    markdown_out = render_export_markdown(data, export_format=export_format, branch_filter=resolved_branch)

    written_path: str | None = None
    if out_file:
        target = safe_resolve_path(workspace_root, out_file)
        atomic_write_text(target, markdown_out)
        written_path = str(target)

    copied = False
    if copy_clipboard:
        copied = copy_to_system_clipboard(markdown_out)

    return {
        "status": "exported",
        "format": export_format,
        "branch_filter": resolved_branch,
        "estimated_tokens": estimate_tokens(markdown_out),
        "output_file": written_path,
        "copied_to_clipboard": copied,
        "content": markdown_out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export AI Memory Bridge state as a Pull Request summary, Changelog, or compact prompt."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    parser.add_argument(
        "--format",
        choices=("pr", "changelog", "compact"),
        default="pr",
        help="Export format: 'pr' (GitHub PR description), 'changelog', or 'compact' (web LLM prompt).",
    )
    parser.add_argument("--branch", default=None, help="Filter tasks/decisions by Git branch (use 'current' for active branch).")
    parser.add_argument("--out", default=None, help="Optional relative file path to write the exported markdown.")
    parser.add_argument("--clipboard", action="store_true", help="Copy exported markdown directly to the OS clipboard.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    args = parser.parse_args(argv)

    ws = Path(args.workspace).resolve()
    branch_filter = args.branch
    if branch_filter == "current":
        branch_filter = get_current_git_branch(ws)

    try:
        res = export_memory(
            workspace_root=ws,
            export_format=args.format,
            branch=branch_filter,
            out_file=args.out,
            copy_clipboard=args.clipboard,
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
        print(res["content"])
        if args.clipboard:
            print(f"\n[Clipboard: {'COPIED' if res['copied_to_clipboard'] else 'UNAVAILABLE'}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
