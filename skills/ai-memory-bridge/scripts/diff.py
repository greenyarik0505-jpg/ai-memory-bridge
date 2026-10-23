#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Memory Time-Travel Diff (diff.py).

Compares two revisions of project memory in `.ai-memory/history/` (or compares a historical
revision against the current `.ai-memory/memory.json`) to show exactly what an AI agent
added, completed, superseded, modified, or conflicted during a session.

Usage:
  python scripts/diff.py [--workspace .] [--from-rev N] [--to-rev M] [--json]
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
    MemoryBridgeError,
    get_memory_paths,
    load_memory,
)


def _list_history_snapshots(history_dir: Path) -> dict[int, Path]:
    """Return a map of {revision_number: snapshot_path} from .ai-memory/history/."""
    snapshots: dict[int, Path] = {}
    if not history_dir.exists() or history_dir.is_symlink():
        return snapshots
    for fpath in sorted(history_dir.glob("rev_*.json")):
        if fpath.is_symlink():
            continue
        try:
            parts = fpath.stem.split("_")
            rev_num = int(parts[1])
            snapshots[rev_num] = fpath
        except Exception:
            continue
    return snapshots


def _load_revision_data(workspace_root: Path, rev: int | None) -> dict[str, Any]:
    paths = get_memory_paths(workspace_root)
    current = load_memory(workspace_root)
    current_rev = int(current.get("revision", 1))
    if rev is None or rev == current_rev:
        return current

    snapshots = _list_history_snapshots(paths["history_dir"])
    if rev not in snapshots:
        available = sorted(set(list(snapshots.keys()) + [current_rev]))
        raise MemoryBridgeError(f"Revision {rev} not found in history. Available revisions: {available}")

    raw = json.loads(snapshots[rev].read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "memory" in raw and isinstance(raw["memory"], dict):
        return raw["memory"]
    return raw


def compute_memory_diff(
    workspace_root: Path,
    from_rev: int | None = None,
    to_rev: int | None = None,
) -> dict[str, Any]:
    """Compute structured differences between two revisions of project memory."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    if not paths["memory_json"].exists():
        raise MemoryBridgeError("Memory store is not initialized (.ai-memory/memory.json missing).")

    current = load_memory(workspace_root)
    current_rev = int(current.get("revision", 1))
    snapshots = _list_history_snapshots(paths["history_dir"])

    resolved_to = to_rev if to_rev is not None else current_rev
    if from_rev is not None:
        resolved_from = from_rev
    else:
        older_revs = [r for r in sorted(snapshots.keys()) if r < resolved_to]
        resolved_from = older_revs[-1] if older_revs else resolved_to

    old_data = _load_revision_data(workspace_root, resolved_from)
    new_data = _load_revision_data(workspace_root, resolved_to)

    old_entries = {e["id"]: e for e in old_data.get("entries", []) if isinstance(e, dict) and "id" in e}
    new_entries = {e["id"]: e for e in new_data.get("entries", []) if isinstance(e, dict) and "id" in e}

    added: list[dict[str, Any]] = []
    completed_tasks: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []
    modified: list[dict[str, Any]] = []

    for eid, n_entry in new_entries.items():
        if eid not in old_entries:
            added.append(n_entry)
            if n_entry.get("status") == "completed" or n_entry.get("type") == "task_done":
                completed_tasks.append(n_entry)
            if n_entry.get("status") == "superseded":
                superseded.append(n_entry)
            continue

        o_entry = old_entries[eid]
        if o_entry.get("status") != "completed" and (
            n_entry.get("status") == "completed" or n_entry.get("type") == "task_done"
        ):
            completed_tasks.append(n_entry)
        elif o_entry.get("status") != "superseded" and n_entry.get("status") == "superseded":
            superseded.append(n_entry)
        elif (
            o_entry.get("content_hash") != n_entry.get("content_hash")
            or o_entry.get("priority") != n_entry.get("priority")
            or o_entry.get("status") != n_entry.get("status")
        ):
            modified.append(
                {
                    "id": eid,
                    "title": n_entry.get("title", ""),
                    "old_status": o_entry.get("status"),
                    "new_status": n_entry.get("status"),
                    "old_priority": o_entry.get("priority"),
                    "new_priority": n_entry.get("priority"),
                }
            )

    old_conflicts = {c["id"]: c for c in old_data.get("conflicts", []) if isinstance(c, dict) and "id" in c}
    new_conflicts = {c["id"]: c for c in new_data.get("conflicts", []) if isinstance(c, dict) and "id" in c}

    added_conflicts = [c for cid, c in new_conflicts.items() if cid not in old_conflicts]
    resolved_conflicts = [
        c
        for cid, c in new_conflicts.items()
        if cid in old_conflicts
        and old_conflicts[cid].get("status") == "unresolved"
        and c.get("status") == "resolved"
    ]

    return {
        "status": "diff_computed",
        "from_revision": resolved_from,
        "to_revision": resolved_to,
        "summary": {
            "added_count": len(added),
            "completed_tasks_count": len(completed_tasks),
            "superseded_count": len(superseded),
            "modified_count": len(modified),
            "new_conflicts_count": len(added_conflicts),
            "resolved_conflicts_count": len(resolved_conflicts),
        },
        "added_entries": added,
        "completed_tasks": completed_tasks,
        "superseded_entries": superseded,
        "modified_entries": modified,
        "new_conflicts": added_conflicts,
        "resolved_conflicts": resolved_conflicts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two revisions of AI Memory Bridge project memory.")
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    parser.add_argument("--from-rev", type=int, default=None, help="Starting revision number (defaults to previous revision).")
    parser.add_argument("--to-rev", type=int, default=None, help="Target revision number (defaults to current revision).")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    args = parser.parse_args(argv)

    try:
        diff = compute_memory_diff(Path(args.workspace), from_rev=args.from_rev, to_rev=args.to_rev)
    except MemoryBridgeError as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(diff, indent=2))
    else:
        s = diff["summary"]
        print(
            f"=== Memory Diff: Revision #{diff['from_revision']} -> #{diff['to_revision']} ===\n"
            f"  + Added: {s['added_count']} | ✓ Completed Tasks: {s['completed_tasks_count']} | "
            f"↻ Superseded: {s['superseded_count']} | ~ Modified: {s['modified_count']} | "
            f"! New Conflicts: {s['new_conflicts_count']}"
        )
        for e in diff["added_entries"]:
            print(f"  [+] {e['id']} ({e['type']} / {e['priority']} by {e.get('source', 'agent')}): {e['title']}")
        for e in diff["completed_tasks"]:
            print(f"  [✓] {e['id']} (Task Completed): {e['title']}")
        for e in diff["superseded_entries"]:
            print(f"  [↻] {e['id']} (Superseded by {e.get('superseded_by')}): {e['title']}")
        for m in diff["modified_entries"]:
            print(
                f"  [~] {m['id']} ({m['title']}): status {m['old_status']}->{m['new_status']}, "
                f"priority {m['old_priority']}->{m['new_priority']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
