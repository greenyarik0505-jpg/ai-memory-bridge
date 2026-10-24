#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Zero-Prompt Autopilot Engine (autopilot.py).

Enables 100% hands-free, zero-prompt memory loading, saving, and cross-agent synchronization
so the user never has to manually tell an AI agent to load context or prepare a handoff:

1. Always-On Agent Rule Injection:
   Writes/updates `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursor/rules/ai-memory-bridge.mdc`
   (`alwaysApply: true`), `.agents/rules/ai-memory-bridge.md` (`trigger: always_on`), and
   `.github/instructions/ai-memory-bridge.instructions.md` (`applyTo: "**"`). Every agent
   loads the latest memory automatically on startup without being asked.
2. Real-Time Save Propagation:
   Sets `metadata.auto_capture_enabled = true` so every `capture.py` write immediately
   propagates to all active agent rule files and refreshes `.ai-memory/dashboard.html`.
3. Automatic Git Hooks (`post-commit`, `post-checkout`, `post-merge`):
   Whenever code is committed or branches are switched, Git automatically triggers
   `autopilot.py tick` in the background to capture commit history and sync all agents.
4. Agent Lifecycle Hooks (`SessionStart` / `Stop`):
   Configures `.claude/settings.json` and `.agents/hooks.json` so sessions auto-save on exit.

Usage:
  python scripts/autopilot.py enable [--workspace .] [--targets all|detected] [--no-git-hooks] [--json]
  python scripts/autopilot.py tick [--workspace .] [--json]
  python scripts/autopilot.py status [--workspace .] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from capture import capture_git_context, sync_global_preferences_to_workspace  # noqa: E402
from dashboard import generate_dashboard  # noqa: E402
from handoff import AGENT_PROFILES  # noqa: E402
from init import configure_opt_in_hooks, initialize_workspace  # noqa: E402
from memory_utils import (  # noqa: E402
    MARKER_START,
    MemoryBridgeError,
    atomic_write_text,
    get_memory_paths,
    load_memory,
    save_memory,
)
from scan import scan_and_populate  # noqa: E402
from sync import detect_workspace_agents, sync_workspace_memory  # noqa: E402

GIT_HOOK_NAMES = ("post-commit", "post-checkout", "post-merge")
GIT_HOOK_MARKER = "# AI-MEMORY-BRIDGE-AUTOPILOT-HOOK"


def install_git_autopilot_hooks(workspace_root: Path, dry_run: bool = False) -> dict[str, Any]:
    """Install non-destructive Git hooks (post-commit, post-checkout, post-merge) if .git/hooks exists."""
    git_dir = workspace_root / ".git"
    hooks_dir = git_dir / "hooks"
    if not git_dir.is_dir() or git_dir.is_symlink():
        return {"installed": False, "reason": "not_a_git_repository", "hooks": []}

    hooks_dir.mkdir(parents=True, exist_ok=True)
    autopilot_script = (SCRIPT_DIR / "autopilot.py").resolve().as_posix()
    ws_posix = workspace_root.resolve().as_posix()
    hook_cmd_line = (
        f'{GIT_HOOK_MARKER}\n'
        f'python "{autopilot_script}" tick --workspace "{ws_posix}" >/dev/null 2>&1 || true\n'
    )

    installed_hooks: list[str] = []
    for hname in GIT_HOOK_NAMES:
        hpath = hooks_dir / hname
        if hpath.exists() and hpath.is_symlink():
            continue
        if hpath.exists():
            existing = hpath.read_text(encoding="utf-8", errors="replace")
            if GIT_HOOK_MARKER in existing:
                installed_hooks.append(hname)
                continue
            new_text = existing.rstrip() + "\n\n" + hook_cmd_line
        else:
            new_text = "#!/bin/sh\n" + hook_cmd_line

        if not dry_run:
            atomic_write_text(hpath, new_text)
            try:
                mode = os.stat(hpath).st_mode
                os.chmod(hpath, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except Exception:
                pass
        installed_hooks.append(hname)

    return {"installed": True, "hooks": installed_hooks, "hooks_dir": str(hooks_dir)}


def enable_autopilot(
    workspace_root: Path,
    targets: str = "all",
    enable_git_hooks: bool = True,
    enable_agent_hooks: bool = True,
    auto_scan_if_empty: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Enable full zero-prompt autopilot for a workspace."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    if not paths["memory_json"].exists() and not dry_run:
        initialize_workspace(workspace_root, enable_hooks=True)

    data = load_memory(workspace_root)
    data["metadata"]["auto_capture_enabled"] = True
    if not dry_run:
        save_memory(
            workspace_root,
            data,
            action="autopilot_enable",
            agent="autopilot",
            details={"targets": targets, "git_hooks": enable_git_hooks},
            increment_revision=False,
        )

    # Pull global developer preferences if ~/.ai-memory-global/ exists
    global_sync = sync_global_preferences_to_workspace(workspace_root, dry_run=dry_run)

    # Optional auto-scan only when explicitly requested
    scan_res = None
    if auto_scan_if_empty and len(data.get("entries", [])) == 0:
        scan_res = scan_and_populate(workspace_root, apply_entries=not dry_run)

    target_list = [t.strip() for t in targets.split(",") if t.strip()]
    sync_res = sync_workspace_memory(
        workspace_root=workspace_root,
        targets=target_list,
        dry_run=dry_run,
    )

    git_hooks_res = {"installed": False, "hooks": []}
    if enable_git_hooks:
        git_hooks_res = install_git_autopilot_hooks(workspace_root, dry_run=dry_run)

    agent_hooks_res: list[dict[str, Any]] = []
    if enable_agent_hooks:
        for ag in ("claude-code", "antigravity"):
            agent_hooks_res.append(
                configure_opt_in_hooks(workspace_root, agent=ag, skill_scripts_dir=SCRIPT_DIR, dry_run=dry_run)
            )

    if not dry_run:
        generate_dashboard(workspace_root)

    return {
        "status": "autopilot_enabled",
        "workspace": str(workspace_root),
        "auto_capture_enabled": True,
        "global_preferences_synced": global_sync.get("imported_count", 0),
        "auto_scan": scan_res["status"] if scan_res else "skipped",
        "synced_agent_rules": [item["relative_rule_file"] for item in sync_res.get("synced_targets", [])],
        "git_hooks": git_hooks_res,
        "agent_hooks": agent_hooks_res,
    }


def run_autopilot_tick(workspace_root: Path, dry_run: bool = False) -> dict[str, Any]:
    """Perform a background autopilot tick: capture latest Git state, sync detected agent rules, refresh dashboard."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    if not paths["memory_json"].exists():
        return {"status": "skipped_uninitialized"}

    git_captured = False
    try:
        capture_git_context(workspace_root, max_commits=5, source="autopilot-git", dry_run=dry_run)
        git_captured = True
    except Exception:
        pass

    detected = detect_workspace_agents(workspace_root)
    targets = detected if detected else ["claude-code", "codex", "cursor", "antigravity"]
    sync_res = sync_workspace_memory(workspace_root, targets=targets, dry_run=dry_run)
    if not dry_run:
        generate_dashboard(workspace_root)

    return {
        "status": "tick_completed",
        "git_captured": git_captured,
        "synced_targets": [t["relative_rule_file"] for t in sync_res.get("synced_targets", [])],
        "revision": sync_res.get("revision", 1),
    }


def get_autopilot_status(workspace_root: Path) -> dict[str, Any]:
    """Inspect current Zero-Prompt Autopilot status in workspace_root."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    if not paths["memory_json"].exists():
        return {"initialized": False, "auto_capture_enabled": False}

    data = load_memory(workspace_root)
    active_rule_files: list[str] = []
    seen: set[str] = set()
    for ag, prof in AGENT_PROFILES.items():
        if ag == "generic":
            continue
        rfile = prof["rule_file"]
        if rfile in seen:
            continue
        seen.add(rfile)
        fpath = workspace_root / rfile
        if fpath.is_file() and not fpath.is_symlink():
            txt = fpath.read_text(encoding="utf-8", errors="replace")
            if MARKER_START in txt or "AI Memory Bridge" in txt:
                active_rule_files.append(rfile)

    git_hooks_installed: list[str] = []
    for hname in GIT_HOOK_NAMES:
        hpath = workspace_root / ".git" / "hooks" / hname
        if hpath.is_file() and GIT_HOOK_MARKER in hpath.read_text(encoding="utf-8", errors="replace"):
            git_hooks_installed.append(hname)

    return {
        "initialized": True,
        "auto_capture_enabled": bool(data.get("metadata", {}).get("auto_capture_enabled", False)),
        "revision": data.get("revision", 1),
        "active_entries": len([e for e in data.get("entries", []) if e.get("status") in ("active", "conflicted")]),
        "always_on_rule_files": active_rule_files,
        "git_hooks_installed": git_hooks_installed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configure and run Zero-Prompt Autopilot for AI Memory Bridge."
    )
    subparsers = parser.add_subparsers(dest="command")

    p_en = subparsers.add_parser("enable", help="Enable zero-prompt auto-load, auto-save, and cross-agent rule sync.")
    p_en.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_en.add_argument(
        "--targets",
        default="all",
        help="Agent rule files to keep always-on ('all', 'detected', or comma-separated agent names).",
    )
    p_en.add_argument("--no-git-hooks", action="store_true", help="Skip installing Git post-commit/checkout hooks.")
    p_en.add_argument("--no-agent-hooks", action="store_true", help="Skip installing Claude/Antigravity lifecycle hooks.")
    p_en.add_argument("--scan", action="store_true", help="Also run codebase auto-scanner if memory is empty.")
    p_en.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    p_en.add_argument("--json", action="store_true", help="Output JSON.")

    p_tick = subparsers.add_parser("tick", help="Run a background autopilot sync tick.")
    p_tick.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_tick.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    p_tick.add_argument("--json", action="store_true", help="Output JSON.")

    p_stat = subparsers.add_parser("status", help="Show current Zero-Prompt Autopilot status.")
    p_stat.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_stat.add_argument("--json", action="store_true", help="Output JSON.")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    try:
        ws = Path(getattr(args, "workspace", "."))
        if args.command == "enable":
            res = enable_autopilot(
                workspace_root=ws,
                targets=args.targets,
                enable_git_hooks=not args.no_git_hooks,
                enable_agent_hooks=not args.no_agent_hooks,
                auto_scan_if_empty=args.scan,
                dry_run=args.dry_run,
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print("=== AI Memory Bridge: Zero-Prompt Autopilot ENABLED ===")
                print(f"  Workspace          : {res['workspace']}")
                print(f"  Always-On Rules    : {', '.join(res['synced_agent_rules'])}")
                print(f"  Git Auto-Hooks     : {', '.join(res['git_hooks'].get('hooks', [])) or 'none'}")
                print("  Result             : Agents now load and sync memory automatically without manual prompts.")
        elif args.command == "tick":
            res = run_autopilot_tick(ws, dry_run=args.dry_run)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"[AUTOPILOT TICK] {res['status']} (rev #{res.get('revision', 1)})")
        elif args.command == "status":
            res = get_autopilot_status(ws)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Autopilot Active   : {res.get('auto_capture_enabled')}")
                print(f"Always-On Rules    : {', '.join(res.get('always_on_rule_files', [])) or 'none'}")
                print(f"Git Hooks Installed: {', '.join(res.get('git_hooks_installed', [])) or 'none'}")
    except MemoryBridgeError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
