#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Restore project memory from a backup snapshot or historical revision.

Includes automatic pre-restore safety backup, dry-run diff preview, and confirmation gate.

Usage:
  python scripts/restore.py --backup BACKUP_ID [--workspace .] [--dry-run | --confirm] [--json]
  python scripts/restore.py --revision REV_NUM [--workspace .] [--dry-run | --confirm] [--json]
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

from backup import create_backup, verify_backup  # noqa: E402
from memory_utils import (  # noqa: E402
    BACKUPS_DIR_NAME,
    HISTORY_DIR_NAME,
    MEMORY_DIR_NAME,
    MemoryBridgeError,
    load_memory,
    migrate_schema,
    safe_resolve_path,
    save_memory,
    validate_memory_data,
)


def _load_target_state(
    workspace_root: Path,
    backup_id: str | None = None,
    revision: int | None = None,
) -> tuple[dict[str, Any], str]:
    if backup_id:
        verified = verify_backup(workspace_root, backup_id)
        backup_path = Path(verified["path"])
        bundle = json.loads(backup_path.read_text(encoding="utf-8"))
        target_data = migrate_schema(bundle["memory"])
        validate_memory_data(target_data)
        return target_data, f"backup:{verified['backup_id']}"

    if revision is not None:
        if revision < 1:
            raise MemoryBridgeError("Revision number must be >= 1.")
        rev_path = safe_resolve_path(
            workspace_root,
            f"{MEMORY_DIR_NAME}/{HISTORY_DIR_NAME}/rev_{revision:05d}.json",
        )
        if not rev_path.exists():
            raise MemoryBridgeError(f"Revision snapshot rev_{revision:05d}.json not found in history.")
        raw = json.loads(rev_path.read_text(encoding="utf-8"))
        target_data = migrate_schema(raw)
        validate_memory_data(target_data)
        return target_data, f"revision:{revision}"

    raise MemoryBridgeError("Specify either --backup <BACKUP_ID> or --revision <REV_NUM>.")


def restore_memory(
    workspace_root: Path,
    backup_id: str | None = None,
    revision: int | None = None,
    dry_run: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Restore memory state with pre-restore backup and confirmation check."""
    workspace_root = workspace_root.resolve()
    current_data = load_memory(workspace_root)
    target_data, source_label = _load_target_state(workspace_root, backup_id=backup_id, revision=revision)

    current_ids = {e["id"] for e in current_data.get("entries", [])}
    target_ids = {e["id"] for e in target_data.get("entries", [])}

    added_ids = sorted(target_ids - current_ids)
    removed_ids = sorted(current_ids - target_ids)

    preview = {
        "source": source_label,
        "current_revision": current_data.get("revision"),
        "target_revision": target_data.get("revision"),
        "current_entry_count": len(current_data.get("entries", [])),
        "target_entry_count": len(target_data.get("entries", [])),
        "entries_restored_or_added": added_ids,
        "entries_removed_by_rollback": removed_ids,
    }

    if dry_run:
        return {
            "status": "dry_run",
            "dry_run": True,
            "preview": preview,
        }

    if not confirm:
        raise MemoryBridgeError(
            "Restore overwrites active memory state. Run with --dry-run to preview changes, "
            "or pass --confirm to execute the restore."
        )

    pre_backup = create_backup(workspace_root, label="pre-restore-auto", dry_run=False)
    restored_copy = dict(target_data)
    restored_copy["revision"] = int(current_data.get("revision", 1))
    saved = save_memory(
        workspace_root,
        restored_copy,
        action="restore",
        agent="restore",
        details={"source": source_label, "pre_restore_backup": pre_backup["backup_id"]},
        increment_revision=True,
    )

    return {
        "status": "restored",
        "dry_run": False,
        "source": source_label,
        "new_revision": saved["revision"],
        "pre_restore_backup": pre_backup["backup_id"],
        "preview": preview,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Restore project memory from a backup or historical revision."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backup", default=None, help="Backup ID or filename in .ai-memory/backups/.")
    group.add_argument("--revision", type=int, default=None, help="Historical revision number (e.g., 2).")
    parser.add_argument("--dry-run", action="store_true", help="Preview restore diff without modifying files.")
    parser.add_argument("--confirm", action="store_true", help="Confirm and execute the restore operation.")
    parser.add_argument("--json", action="store_true", help="Output result as JSON.")
    args = parser.parse_args(argv)

    try:
        res = restore_memory(
            workspace_root=Path(args.workspace),
            backup_id=args.backup,
            revision=args.revision,
            dry_run=args.dry_run,
            confirm=args.confirm,
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
        p = res["preview"]
        if res["dry_run"]:
            print(f"[DRY-RUN] Restore preview from {p['source']}:")
            print(f"  Current Revision : {p['current_revision']} ({p['current_entry_count']} entries)")
            print(f"  Target Revision  : {p['target_revision']} ({p['target_entry_count']} entries)")
            print(f"  Entries Added    : {len(p['entries_restored_or_added'])}")
            print(f"  Entries Removed  : {len(p['entries_removed_by_rollback'])}")
        else:
            print(f"Restored memory from {res['source']} -> new revision {res['new_revision']}")
            print(f"  Pre-restore safety backup: {res['pre_restore_backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
