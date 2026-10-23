#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Capture, update, query, deduplicate, and resolve conflicts in project memory.

Usage examples:
  python scripts/capture.py add --type decision --title "Database" --content "Use PostgreSQL 16" --source claude-code
  python scripts/capture.py import --from-json entries.json --source cursor
  python scripts/capture.py complete-task --id mem_20261023_abcd1234 --note "Implemented and tested"
  python scripts/capture.py resolve-conflict --conflict-id conflict_... --keep mem_... --note "Chose PostgreSQL"
  python scripts/capture.py list [--type decision] [--status active]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from init import initialize_workspace  # noqa: E402
from memory_utils import (  # noqa: E402
    PRIORITY_WEIGHTS,
    SecurityViolationError,
    VALID_ENTRY_TYPES,
    VALID_PRIORITIES,
    VALID_STATUSES,
    MemoryBridgeError,
    compact_memory,
    compute_content_hash,
    detect_conflicts_for_entry,
    detect_stale_file_references,
    extract_file_references,
    find_duplicate_entry,
    generate_entry_id,
    get_current_git_branch,
    get_memory_paths,
    load_memory,
    redact_secrets,
    safe_resolve_path,
    sanitize_text_for_markdown,
    save_memory,
    scan_for_prompt_injection,
    scan_for_secrets,
    search_memory_entries,
    sort_entries_by_priority,
    utc_now_iso,
)


def _validate_and_clean_content(
    title: str,
    content: str,
    allow_redact_secrets: bool = False,
) -> tuple[str, str, list[dict[str, str]]]:
    clean_title = sanitize_text_for_markdown(title.strip())
    clean_content = sanitize_text_for_markdown(content.strip())
    if not clean_content:
        raise MemoryBridgeError("Memory entry content cannot be empty.")
    if not clean_title:
        clean_title = clean_content.splitlines()[0][:72]

    combined = f"{clean_title}\n{clean_content}"
    injections = scan_for_prompt_injection(combined)
    if injections:
        kinds = ", ".join(f"{item['type']} ('{item['snippet']}')" for item in injections)
        raise SecurityViolationError(
            f"Prompt injection or unsafe directive blocked: {kinds}"
        )

    secret_hits = scan_for_secrets(combined)
    if secret_hits:
        if not allow_redact_secrets:
            labels = ", ".join(sorted({h["type"] for h in secret_hits}))
            raise SecurityViolationError(
                f"Potential secret(s) detected in memory entry ({labels}). "
                "Never store API keys, passwords, or private tokens in project memory. "
                "Remove the secret or pass --redact-secrets to mask it automatically."
            )
        clean_title, _ = redact_secrets(clean_title)
        clean_content, _ = redact_secrets(clean_content)

    return clean_title, clean_content, secret_hits


def add_memory_entry(
    workspace_root: Path,
    entry_type: str,
    title: str,
    content: str,
    source: str = "manual",
    priority: str = "medium",
    tags: list[str] | None = None,
    supersedes: str | None = None,
    branch: str | None = None,
    files: list[str] | None = None,
    allow_redact_secrets: bool = False,
    auto_init: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add or deduplicate/update a single entry in .ai-memory/memory.json."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    if not paths["memory_json"].exists():
        if auto_init and not dry_run:
            initialize_workspace(workspace_root)
        elif not auto_init:
            raise MemoryBridgeError("Memory store is not initialized. Run init.py first.")

    if entry_type not in VALID_ENTRY_TYPES:
        raise MemoryBridgeError(f"Invalid entry type '{entry_type}'. Valid types: {VALID_ENTRY_TYPES}")
    if priority not in VALID_PRIORITIES:
        raise MemoryBridgeError(f"Invalid priority '{priority}'. Valid priorities: {VALID_PRIORITIES}")

    clean_title, clean_content, redacted_secrets = _validate_and_clean_content(
        title, content, allow_redact_secrets=allow_redact_secrets
    )
    resolved_branch = (branch or get_current_git_branch(workspace_root)).strip() or "main"
    auto_files = extract_file_references(f"{clean_title}\n{clean_content}")
    merged_files = sorted(set((files or []) + auto_files))

    if dry_run and not paths["memory_json"].exists():
        return {
            "status": "dry_run",
            "action": "add",
            "entry": {
                "type": entry_type,
                "title": clean_title,
                "content": clean_content,
                "priority": priority,
                "source": source,
                "branch": resolved_branch,
                "files": merged_files,
            },
        }

    data = load_memory(workspace_root)
    entries = data["entries"]
    now = utc_now_iso()

    # Check if duplicate already exists
    dup = find_duplicate_entry(entries, entry_type, clean_title, clean_content)
    if dup is not None and not supersedes:
        old_prio = dup.get("priority", "medium")
        if PRIORITY_WEIGHTS.get(priority, 2) > PRIORITY_WEIGHTS.get(old_prio, 2):
            dup["priority"] = priority
        dup["updated_at"] = now
        dup["source"] = source
        if tags:
            existing_tags = set(dup.get("tags", []))
            dup["tags"] = sorted(existing_tags | set(tags))
        if not dry_run:
            save_memory(
                workspace_root,
                data,
                action="deduplicate_update",
                agent=source,
                details={"entry_id": dup["id"], "title": clean_title},
            )
        return {
            "status": "deduplicated",
            "dry_run": dry_run,
            "entry": dup,
            "redacted_secrets_count": len(redacted_secrets),
            "conflicts_detected": [],
        }

    new_id = generate_entry_id("mem")
    superseded_target: dict[str, Any] | None = None
    if supersedes:
        for item in entries:
            if item["id"] == supersedes:
                superseded_target = item
                break
        if superseded_target is None:
            raise MemoryBridgeError(f"Supersedes target ID '{supersedes}' not found in memory.")
        superseded_target["status"] = "superseded"
        superseded_target["superseded_by"] = new_id
        superseded_target["updated_at"] = now

    new_entry: dict[str, Any] = {
        "id": new_id,
        "type": entry_type,
        "title": clean_title,
        "content": clean_content,
        "source": source.strip() or "manual",
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "priority": priority,
        "tags": sorted(set(tags or [])),
        "branch": resolved_branch,
        "files": merged_files,
        "supersedes": supersedes,
        "superseded_by": None,
        "content_hash": compute_content_hash(entry_type, clean_title, clean_content),
    }

    conflicts = detect_conflicts_for_entry(entries, new_entry)
    if conflicts:
        new_entry["status"] = "conflicted"
        conflicted_ids = {cid for c in conflicts for cid in c["entry_ids"]}
        for item in entries:
            if item["id"] in conflicted_ids and item["status"] == "active":
                item["status"] = "conflicted"
        data["conflicts"].extend(conflicts)

    entries.append(new_entry)

    if not dry_run:
        save_memory(
            workspace_root,
            data,
            action="capture_add",
            agent=source,
            details={
                "entry_id": new_id,
                "type": entry_type,
                "title": clean_title,
                "supersedes": supersedes,
                "conflicts": [c["id"] for c in conflicts],
            },
        )

    return {
        "status": "added",
        "dry_run": dry_run,
        "entry": new_entry,
        "redacted_secrets_count": len(redacted_secrets),
        "conflicts_detected": conflicts,
    }


def import_entries_from_json(
    workspace_root: Path,
    json_file: Path,
    default_source: str = "import",
    allow_redact_secrets: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Safely validate and import multiple memory entries from a JSON file."""
    workspace_root = workspace_root.resolve()
    resolved_json = safe_resolve_path(workspace_root, json_file, allow_outside=False)
    if not resolved_json.exists():
        raise MemoryBridgeError(f"Import file not found: {resolved_json}")

    try:
        payload = json.loads(resolved_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MemoryBridgeError(f"Invalid JSON in import file: {exc}") from exc

    raw_items = payload.get("entries", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise MemoryBridgeError("Import JSON must be a list of entry objects or an object with 'entries' list.")

    added = []
    deduplicated = []
    all_conflicts = []

    for idx, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise MemoryBridgeError(f"Import item #{idx} is not a JSON object.")
        res = add_memory_entry(
            workspace_root=workspace_root,
            entry_type=str(item.get("type", "decision")),
            title=str(item.get("title", "")),
            content=str(item.get("content", "")),
            source=str(item.get("source", default_source)),
            priority=str(item.get("priority", "medium")),
            tags=item.get("tags", []),
            supersedes=item.get("supersedes"),
            allow_redact_secrets=allow_redact_secrets,
            dry_run=dry_run,
        )
        if res["status"] == "deduplicated":
            deduplicated.append(res["entry"]["id"])
        else:
            added.append(res["entry"].get("id", f"dry_run_{idx}"))
        all_conflicts.extend(res.get("conflicts_detected", []))

    return {
        "status": "imported",
        "dry_run": dry_run,
        "added_count": len(added),
        "deduplicated_count": len(deduplicated),
        "added_ids": added,
        "deduplicated_ids": deduplicated,
        "conflicts_detected": all_conflicts,
    }


def complete_pending_task(
    workspace_root: Path,
    task_id: str,
    resolution_note: str = "",
    source: str = "manual",
) -> dict[str, Any]:
    """Transition a pending task (task_pending) to completed (task_done)."""
    workspace_root = workspace_root.resolve()
    data = load_memory(workspace_root)
    now = utc_now_iso()

    target = None
    for entry in data["entries"]:
        if entry["id"] == task_id:
            target = entry
            break
    if target is None:
        raise MemoryBridgeError(f"Task ID '{task_id}' not found.")

    target["type"] = "task_done"
    target["status"] = "completed"
    target["updated_at"] = now
    if resolution_note.strip():
        clean_note = sanitize_text_for_markdown(resolution_note.strip())
        if scan_for_secrets(clean_note) or scan_for_prompt_injection(clean_note):
            raise SecurityViolationError("Task completion note contains secrets or unsafe instructions.")
        target["content"] = f"{target['content']} (Completed: {clean_note})"
        target["content_hash"] = compute_content_hash(target["type"], target["title"], target["content"])

    save_memory(
        workspace_root,
        data,
        action="complete_task",
        agent=source,
        details={"task_id": task_id, "note": resolution_note},
    )
    return {"status": "completed", "entry": target}


def resolve_memory_conflict(
    workspace_root: Path,
    conflict_id: str,
    keep_entry_id: str,
    note: str = "",
    source: str = "manual",
) -> dict[str, Any]:
    """Resolve an active conflict by keeping one entry and superseding the other(s)."""
    workspace_root = workspace_root.resolve()
    data = load_memory(workspace_root)
    now = utc_now_iso()

    conflict_obj = None
    for c in data.get("conflicts", []):
        if c.get("id") == conflict_id:
            conflict_obj = c
            break
    if conflict_obj is None:
        raise MemoryBridgeError(f"Conflict ID '{conflict_id}' not found.")

    involved_ids = conflict_obj.get("entry_ids", [])
    if keep_entry_id not in involved_ids:
        raise MemoryBridgeError(
            f"Entry '{keep_entry_id}' is not part of conflict '{conflict_id}' ({involved_ids})."
        )

    for entry in data["entries"]:
        if entry["id"] == keep_entry_id:
            entry["status"] = "active"
            entry["updated_at"] = now
        elif entry["id"] in involved_ids:
            entry["status"] = "superseded"
            entry["superseded_by"] = keep_entry_id
            entry["updated_at"] = now

    conflict_obj["status"] = "resolved"
    conflict_obj["resolved_at"] = now
    conflict_obj["kept_entry_id"] = keep_entry_id
    conflict_obj["resolution_note"] = sanitize_text_for_markdown(note or f"Kept {keep_entry_id}")

    save_memory(
        workspace_root,
        data,
        action="resolve_conflict",
        agent=source,
        details={"conflict_id": conflict_id, "kept_entry_id": keep_entry_id},
    )
    return {"status": "resolved", "conflict": conflict_obj}


def _collect_git_progress_summary(workspace_root: Path) -> str:
    """Inspect workspace git status for modified/created files to include in auto-saved turn progress."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        if proc.returncode != 0:
            return ""
        changed_files: list[str] = []
        for raw_line in proc.stdout.splitlines():
            line = raw_line.strip()
            if not line or ".ai-memory" in line:
                continue
            parts = line.split(maxsplit=1)
            rel_file = parts[1] if len(parts) > 1 else parts[0]
            changed_files.append(rel_file)
        if not changed_files:
            return ""
        preview = ", ".join(changed_files[:8])
        more = f" (+{len(changed_files) - 8} more)" if len(changed_files) > 8 else ""
        return f"Workspace files modified/staged in session: {preview}{more}."
    except Exception:
        return ""


def capture_git_context(
    workspace_root: Path,
    max_commits: int = 5,
    source: str = "git-auto",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Automatically extract branch, recent commits, and working tree status from Git into project memory."""
    workspace_root = workspace_root.resolve()
    branch = get_current_git_branch(workspace_root)

    commits: list[str] = []
    try:
        proc_log = subprocess.run(
            ["git", "log", f"-n{max(1, int(max_commits))}", "--oneline"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if proc_log.returncode == 0:
            commits = [line.strip() for line in proc_log.stdout.splitlines() if line.strip()]
    except Exception:
        pass

    working_changes = _collect_git_progress_summary(workspace_root)
    if not commits and not working_changes:
        raise MemoryBridgeError("No Git commits or working tree modifications found in workspace.")

    parts = [f"Active Git branch: `{branch}`."]
    if commits:
        parts.append("Recent commits: " + "; ".join(commits) + ".")
    if working_changes:
        parts.append(working_changes)

    summary_content = " ".join(parts)
    res = add_memory_entry(
        workspace_root=workspace_root,
        entry_type="session_summary",
        title=f"Git Progress Snapshot ({branch})",
        content=summary_content,
        source=source,
        priority="medium",
        tags=["git-auto", branch],
        branch=branch,
        allow_redact_secrets=True,
        dry_run=dry_run,
    )
    return {
        "status": "git_captured",
        "branch": branch,
        "commits_included": len(commits),
        "working_tree_dirty": bool(working_changes),
        "entry": res["entry"],
    }


def handle_hook_event(workspace_root: Path, event_name: str) -> dict[str, Any]:
    """Handle lifecycle hook events (SessionStart / PostToolUse / Stop) with automatic progress saving."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    if not paths["memory_json"].exists():
        return {}

    data = load_memory(workspace_root)
    if not data.get("metadata", {}).get("auto_capture_enabled", False):
        return {}

    if event_name == "SessionStart":
        active_entries = [e for e in data["entries"] if e.get("status") in ("active", "conflicted")]
        pending_tasks = [e["title"] for e in active_entries if e.get("type") in ("task_pending", "next_step")][:4]
        unresolved = len([c for c in data.get("conflicts", []) if c.get("status") == "unresolved"])
        tasks_hint = f" Next tasks: {'; '.join(pending_tasks)}." if pending_tasks else ""
        msg = (
            f"[AI Memory Bridge] Loaded project memory '{data['project']['name']}' "
            f"(rev {data['revision']}, {len(active_entries)} active entries, {unresolved} unresolved conflicts).{tasks_hint} "
            f"Auto-save is active: record any new architectural decisions or completed tasks via capture.py."
        )
        return {
            "injectSteps": [
                {
                    "systemMessage": {
                        "systemMessage": msg,
                    }
                }
            ]
        }

    if event_name in ("Stop", "PostToolUse"):
        git_summary = _collect_git_progress_summary(workspace_root)
        now = utc_now_iso()
        increment_rev = False
        if git_summary and not scan_for_secrets(git_summary) and not scan_for_prompt_injection(git_summary):
            auto_title = "Auto-Saved Workspace Progress"
            existing_auto = None
            for item in data["entries"]:
                if item.get("type") == "session_summary" and item.get("title") == auto_title and item.get("status") == "active":
                    existing_auto = item
                    break
            if existing_auto is not None:
                if existing_auto.get("content") != git_summary:
                    existing_auto["content"] = git_summary
                    existing_auto["updated_at"] = now
                    existing_auto["content_hash"] = compute_content_hash("session_summary", auto_title, git_summary)
                    increment_rev = True
            else:
                data["entries"].append(
                    {
                        "id": generate_entry_id("mem"),
                        "type": "session_summary",
                        "title": auto_title,
                        "content": git_summary,
                        "source": "auto-hook",
                        "created_at": now,
                        "updated_at": now,
                        "status": "active",
                        "priority": "medium",
                        "tags": ["auto-capture"],
                        "supersedes": None,
                        "superseded_by": None,
                        "content_hash": compute_content_hash("session_summary", auto_title, git_summary),
                    }
                )
                increment_rev = True

        save_memory(
            workspace_root,
            data,
            action=f"hook_{event_name.lower()}_autosave",
            agent=data.get("metadata", {}).get("last_agent", "auto-hook"),
            details={"event": event_name, "git_summary_captured": bool(git_summary)},
            increment_revision=increment_rev,
        )

        # Also refresh any detected agent rule files automatically
        try:
            from sync import sync_workspace_memory
            sync_workspace_memory(workspace_root, targets=["detected"], dry_run=False)
        except Exception:
            pass
        return {}

    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture, query, and manage AI Memory Bridge entries.")
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    parser.add_argument(
        "--hook-event",
        choices=("SessionStart", "PostToolUse", "Stop"),
        default=None,
        help="Internal lifecycle hook handler mode.",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_add = subparsers.add_parser("add", help="Add or update a memory entry.")
    p_add.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_add.add_argument("--type", required=True, choices=VALID_ENTRY_TYPES, help="Memory entry category.")
    p_add.add_argument("--title", required=True, help="Short topic or title of the entry.")
    p_add.add_argument("--content", required=True, help="Detailed memory entry content.")
    p_add.add_argument("--source", default="manual", help="Agent or source recording this entry.")
    p_add.add_argument("--priority", default="medium", choices=VALID_PRIORITIES, help="Priority level.")
    p_add.add_argument("--tags", default="", help="Comma-separated list of tags.")
    p_add.add_argument("--branch", default=None, help="Git branch name (auto-detected if omitted).")
    p_add.add_argument("--files", default="", help="Comma-separated relative file paths related to this entry.")
    p_add.add_argument("--supersedes", default=None, help="Entry ID that this entry replaces/updates.")
    p_add.add_argument("--redact-secrets", action="store_true", help="Automatically mask detected secrets instead of failing.")
    p_add.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    p_add.add_argument("--json", action="store_true", help="Output JSON.")

    p_import = subparsers.add_parser("import", help="Import multiple entries from a JSON file.")
    p_import.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_import.add_argument("--from-json", required=True, help="Path to JSON file inside workspace.")
    p_import.add_argument("--source", default="import", help="Default source agent label.")
    p_import.add_argument("--redact-secrets", action="store_true", help="Mask detected secrets.")
    p_import.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    p_import.add_argument("--json", action="store_true", help="Output JSON.")

    p_complete = subparsers.add_parser("complete-task", help="Mark a pending task as completed.")
    p_complete.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_complete.add_argument("--id", required=True, help="Task entry ID to mark completed.")
    p_complete.add_argument("--note", default="", help="Completion summary note.")
    p_complete.add_argument("--source", default="manual", help="Agent completing the task.")
    p_complete.add_argument("--json", action="store_true", help="Output JSON.")

    p_resolve = subparsers.add_parser("resolve-conflict", help="Resolve an architectural or constraint conflict.")
    p_resolve.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_resolve.add_argument("--conflict-id", required=True, help="Conflict ID to resolve.")
    p_resolve.add_argument("--keep", required=True, help="Entry ID to keep active.")
    p_resolve.add_argument("--note", default="", help="Explanation for resolution.")
    p_resolve.add_argument("--source", default="manual", help="Agent resolving the conflict.")
    p_resolve.add_argument("--json", action="store_true", help="Output JSON.")

    p_list = subparsers.add_parser("list", help="List or filter memory entries.")
    p_list.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_list.add_argument("--type", choices=VALID_ENTRY_TYPES, default=None, help="Filter by entry type.")
    p_list.add_argument("--status", choices=VALID_STATUSES, default=None, help="Filter by status.")
    p_list.add_argument("--branch", default=None, help="Filter by Git branch.")
    p_list.add_argument("--query", default=None, help="Substring search query.")
    p_list.add_argument("--json", action="store_true", help="Output JSON.")

    p_search = subparsers.add_parser("search", help="BM25 & file-affinity relevance search across memory.")
    p_search.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_search.add_argument("--query", default="", help="Keywords or natural language search query.")
    p_search.add_argument("--file", default="", help="Relative file path to boost entries relevant to this file.")
    p_search.add_argument("--branch", default="", help="Optional Git branch filter/boost.")
    p_search.add_argument("--top", type=int, default=5, help="Max top-ranked entries to return (default: 5).")
    p_search.add_argument("--json", action="store_true", help="Output JSON.")

    p_autogit = subparsers.add_parser("auto-git", help="Automatically capture Git branch, recent commits, and diff status.")
    p_autogit.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_autogit.add_argument("--commits", type=int, default=5, help="Number of recent Git commits to summarize.")
    p_autogit.add_argument("--source", default="git-auto", help="Source label.")
    p_autogit.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    p_autogit.add_argument("--json", action="store_true", help="Output JSON.")

    p_stale = subparsers.add_parser("check-stale", help="Detect active entries referencing deleted or moved files.")
    p_stale.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_stale.add_argument("--json", action="store_true", help="Output JSON.")

    p_compact = subparsers.add_parser("compact", help="Compact memory to fit token/entry budget.")
    p_compact.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_compact.add_argument("--max-entries", type=int, default=40, help="Max active entries to retain.")
    p_compact.add_argument("--max-tokens", type=int, default=2500, help="Max active token budget.")
    p_compact.add_argument("--json", action="store_true", help="Output JSON.")

    args = parser.parse_args(argv)

    if args.hook_event:
        try:
            hook_out = handle_hook_event(Path(args.workspace), args.hook_event)
            print(json.dumps(hook_out))
            return 0
        except Exception:
            print("{}")
            return 0

    if not args.command:
        parser.print_help()
        return 1

    try:
        ws = Path(getattr(args, "workspace", "."))
        if args.command == "add":
            tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
            file_list = [f.strip() for f in args.files.split(",") if f.strip()]
            res = add_memory_entry(
                workspace_root=ws,
                entry_type=args.type,
                title=args.title,
                content=args.content,
                source=args.source,
                priority=args.priority,
                tags=tag_list,
                supersedes=args.supersedes,
                branch=args.branch,
                files=file_list,
                allow_redact_secrets=args.redact_secrets,
                dry_run=args.dry_run,
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                e = res["entry"]
                print(f"[{res['status'].upper()}] {e.get('id', 'dry-run')} ({e['type']} / {e['priority']}): {e['title']}")
                if res.get("conflicts_detected"):
                    print(f"  [WARNING] {len(res['conflicts_detected'])} conflict(s) detected!")
                    for c in res["conflicts_detected"]:
                        print(f"    - {c['id']}: {c['reason']}")

        elif args.command == "import":
            res = import_entries_from_json(
                workspace_root=ws,
                json_file=Path(args.from_json),
                default_source=args.source,
                allow_redact_secrets=args.redact_secrets,
                dry_run=args.dry_run,
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(
                    f"Import finished: {res['added_count']} added, "
                    f"{res['deduplicated_count']} deduplicated, "
                    f"{len(res['conflicts_detected'])} conflicts."
                )

        elif args.command == "complete-task":
            res = complete_pending_task(ws, args.id, resolution_note=args.note, source=args.source)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Task marked completed: {res['entry']['id']} ({res['entry']['title']})")

        elif args.command == "resolve-conflict":
            res = resolve_memory_conflict(
                ws, args.conflict_id, args.keep, note=args.note, source=args.source
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Conflict {args.conflict_id} resolved (kept {args.keep}).")

        elif args.command == "list":
            data = load_memory(ws)
            items = data.get("entries", [])
            if args.type:
                items = [e for e in items if e.get("type") == args.type]
            if args.status:
                items = [e for e in items if e.get("status") == args.status]
            if args.branch:
                items = [e for e in items if e.get("branch", "main") == args.branch]
            if args.query:
                q = args.query.lower()
                items = [
                    e
                    for e in items
                    if q in e.get("title", "").lower() or q in e.get("content", "").lower()
                ]
            items = sort_entries_by_priority(items, preferred_branch=args.branch)
            if args.json:
                print(json.dumps({"entries": items, "conflicts": data.get("conflicts", [])}, indent=2))
            else:
                print(f"Found {len(items)} memory entries:")
                for item in items:
                    print(
                        f"- {item['id']} [{item['status']}] ({item['type']} | {item['priority']} | "
                        f"branch:{item.get('branch', 'main')} | {item['source']}): {item['title']}"
                    )

        elif args.command == "search":
            data = load_memory(ws)
            ranked = search_memory_entries(
                data.get("entries", []),
                query=args.query,
                file_hint=args.file,
                branch=args.branch,
                top_k=args.top,
            )
            if args.json:
                print(json.dumps({"results": ranked, "count": len(ranked)}, indent=2))
            else:
                print(f"Top {len(ranked)} relevant memory entries:")
                for item in ranked:
                    print(
                        f"- [score:{item['relevance_score']}] {item['id']} ({item['type']} | {item['priority']}): "
                        f"{item['title']}"
                    )

        elif args.command == "auto-git":
            res = capture_git_context(
                workspace_root=ws,
                max_commits=args.commits,
                source=args.source,
                dry_run=args.dry_run,
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(
                    f"[GIT-CAPTURED] Branch '{res['branch']}' ({res['commits_included']} commits, "
                    f"dirty={res['working_tree_dirty']}) -> {res['entry'].get('id', 'dry-run')}"
                )

        elif args.command == "check-stale":
            data = load_memory(ws)
            stale = detect_stale_file_references(ws, data.get("entries", []))
            if args.json:
                print(json.dumps({"stale_entries": stale, "count": len(stale)}, indent=2))
            else:
                if not stale:
                    print("No stale file references detected in active memory entries.")
                else:
                    print(f"Detected {len(stale)} entry/entries with missing file references:")
                    for s in stale:
                        print(f"- {s['entry_id']} ({s['title']}): missing {s['missing_files']}")

        elif args.command == "compact":
            data = load_memory(ws)
            stats = compact_memory(data, max_active_entries=args.max_entries, max_tokens=args.max_tokens)
            save_memory(ws, data, action="compact", agent="compactor", details=stats)
            if args.json:
                print(json.dumps({"status": "compacted", **stats}, indent=2))
            else:
                print(
                    f"Compacted memory: archived {stats['archived_count']} entries, "
                    f"{stats['active_remaining']} active remaining (~{stats['estimated_active_tokens']} tokens)."
                )

    except MemoryBridgeError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
