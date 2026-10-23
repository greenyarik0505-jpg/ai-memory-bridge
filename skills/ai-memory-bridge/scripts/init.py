#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Initialize AI Memory Bridge local store (.ai-memory/) in a project workspace.

Usage:
  python scripts/init.py [--workspace .] [--project-name NAME] [--enable-hooks --agent AGENT] [--dry-run] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from memory_utils import (  # noqa: E402
    MEMORY_DIR_NAME,
    MemoryBridgeError,
     atomic_write_json,
    atomic_write_text,
    create_empty_memory,
    get_memory_paths,
    load_memory,
     safe_resolve_path,
    save_memory,
)


def ensure_gitignore(workspace_root: Path, dry_run: bool = False) -> dict[str, Any]:
    """Ensure .ai-memory/ is listed in workspace .gitignore to prevent accidental secret/context leaks."""
    gitignore_path = safe_resolve_path(workspace_root, ".gitignore")
    entry_line = f"{MEMORY_DIR_NAME}/"
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8", errors="replace")
        lines = [line.strip() for line in existing.splitlines()]
        if entry_line in lines or MEMORY_DIR_NAME in lines or f"/{MEMORY_DIR_NAME}/" in lines:
            return {"updated": False, "path": str(gitignore_path), "reason": "already_ignored"}
        new_content = existing.rstrip() + f"\n\n# AI Memory Bridge local context store\n{entry_line}\n"
    else:
        new_content = f"# AI Memory Bridge local context store\n{entry_line}\n"

    if not dry_run:
        atomic_write_text(gitignore_path, new_content)
    return {"updated": True, "path": str(gitignore_path), "reason": "added_to_gitignore"}


def configure_opt_in_hooks(
    workspace_root: Path,
    agent: str,
    skill_scripts_dir: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Configure optional lifecycle hooks ONLY when explicitly requested by user consent."""
    agent_norm = agent.strip().lower()
    capture_script = skill_scripts_dir / "capture.py"
    cmd_start = f'python "{capture_script}" --workspace "." --hook-event SessionStart'
    cmd_stop = f'python "{capture_script}" --workspace "." --hook-event Stop'

    if agent_norm == "claude-code":
        settings_path = safe_resolve_path(workspace_root, ".claude/settings.json")
        existing: dict[str, Any] = {}
        if settings_path.exists():
            try:
                existing = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise MemoryBridgeError(f"Invalid JSON in existing {settings_path}: {exc}") from exc
        hooks = existing.setdefault("hooks", {})
        for event_name, cmd in (("SessionStart", cmd_start), ("Stop", cmd_stop)):
            event_list = hooks.setdefault(event_name, [])
            already_present = any(
                "ai-memory-bridge" in json.dumps(item) or "capture.py" in json.dumps(item)
                for item in event_list
            )
            if not already_present:
                event_list.append(
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": cmd,
                            }
                        ]
                    }
                )
        if not dry_run:
            atomic_write_json(settings_path, existing)
        return {"configured": True, "agent": "claude-code", "config_path": str(settings_path)}

    if agent_norm == "antigravity":
        hooks_path = safe_resolve_path(workspace_root, ".agents/hooks.json")
        existing = {}
        if hooks_path.exists():
            try:
                existing = json.loads(hooks_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise MemoryBridgeError(f"Invalid JSON in existing {hooks_path}: {exc}") from exc
        existing["ai-memory-bridge"] = {
            "enabled": True,
            "SessionStart": [{"type": "command", "command": cmd_start, "timeout": 15}],
            "Stop": [{"type": "command", "command": cmd_stop, "timeout": 15}],
        }
        if not dry_run:
            atomic_write_json(hooks_path, existing)
        return {"configured": True, "agent": "antigravity", "config_path": str(hooks_path)}

    return {
        "configured": False,
        "agent": agent_norm,
        "reason": (
            f"Agent '{agent_norm}' does not support standardized local lifecycle hooks or requires manual capture. "
            "Use conversational capture or sync.py instead."
        ),
    }


def initialize_workspace(
    workspace_root: Path,
    project_name: str | None = None,
    update_gitignore: bool = True,
    enable_hooks: bool = False,
    hook_agent: str = "claude-code",
    force: bool = False,
    confirm: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Initialize or verify .ai-memory/ directory structure in workspace_root."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    resolved_name = (project_name or workspace_root.name or "project").strip()

    already_exists = paths["memory_json"].exists()
    if already_exists and force and not confirm and not dry_run:
        raise MemoryBridgeError(
            "Re-initializing with --force will overwrite existing memory. Pass --confirm to proceed or --dry-run to preview."
        )

    if already_exists and not force:
        data = load_memory(workspace_root)
        if enable_hooks:
            data["metadata"]["auto_capture_enabled"] = True
            if not dry_run:
                save_memory(
                    workspace_root,
                    data,
                    action="enable_hooks",
                    agent=hook_agent,
                    details={"auto_capture_enabled": True},
                )
        status = "already_initialized"
    else:
        data = create_empty_memory(project_name=resolved_name, root_hint=".")
        if enable_hooks:
            data["metadata"]["auto_capture_enabled"] = True
        if not dry_run:
            save_memory(
                workspace_root,
                data,
                action="init",
                agent="init",
                details={"project_name": resolved_name, "forced": force},
                increment_revision=False,
            )
        status = "reinitialized" if already_exists else "initialized"

    gitignore_result = (
        ensure_gitignore(workspace_root, dry_run=dry_run)
        if update_gitignore
        else {"updated": False, "reason": "skipped"}
    )

    hook_result = (
        configure_opt_in_hooks(workspace_root, hook_agent, SCRIPT_DIR, dry_run=dry_run)
        if enable_hooks
        else {"configured": False, "reason": "opt_in_not_requested"}
    )

    return {
        "status": status,
        "dry_run": dry_run,
        "workspace": str(workspace_root),
        "memory_dir": str(paths["memory_dir"]),
        "project_name": data["project"]["name"],
        "schema_version": data["schema_version"],
        "revision": data["revision"],
        "gitignore": gitignore_result,
        "hooks": hook_result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize AI Memory Bridge local storage (.ai-memory/) in a workspace."
    )
    parser.add_argument("--workspace", default=".", help="Target workspace root directory (default: current directory).")
    parser.add_argument("--project-name", default=None, help="Explicit project name (default: workspace folder name).")
    parser.add_argument("--no-gitignore", action="store_true", help="Do not automatically add .ai-memory/ to .gitignore.")
    parser.add_argument(
        "--enable-hooks",
        action="store_true",
        help="Opt-in to automatic session lifecycle hooks for supported agents.",
    )
    parser.add_argument(
        "--agent",
        default="claude-code",
        help="Target agent when configuring opt-in hooks (e.g., claude-code, antigravity).",
    )
    parser.add_argument("--force", action="store_true", help="Re-initialize even if .ai-memory/memory.json exists.")
    parser.add_argument("--confirm", action="store_true", help="Confirm destructive --force re-initialization.")
    parser.add_argument("--dry-run", action="store_true", help="Preview initialization actions without writing files.")
    parser.add_argument("--json", action="store_true", help="Output result as JSON.")
    args = parser.parse_args(argv)

    try:
        result = initialize_workspace(
            workspace_root=Path(args.workspace),
            project_name=args.project_name,
            update_gitignore=not args.no_gitignore,
            enable_hooks=args.enable_hooks,
            hook_agent=args.agent,
            force=args.force,
            confirm=args.confirm,
            dry_run=args.dry_run,
        )
    except MemoryBridgeError as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        prefix = "[DRY-RUN] " if result["dry_run"] else ""
        print(f"{prefix}AI Memory Bridge: {result['status']} at {result['memory_dir']}")
        print(f"  Project Name   : {result['project_name']}")
        print(f"  Schema Version : {result['schema_version']} (revision {result['revision']})")
        print(f"  Gitignore      : {result['gitignore']['reason']}")
        if args.enable_hooks:
            print(f"  Hooks          : {result['hooks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
