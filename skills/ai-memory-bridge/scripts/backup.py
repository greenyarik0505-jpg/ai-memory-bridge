#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Create, list, and verify local snapshots in .ai-memory/backups/.

Usage:
  python scripts/backup.py create [--workspace .] [--label LABEL] [--json]
  python scripts/backup.py list [--workspace .] [--json]
  python scripts/backup.py verify --id BACKUP_ID [--workspace .] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from memory_utils import (  # noqa: E402
    BACKUPS_DIR_NAME,
    MEMORY_DIR_NAME,
    MemoryBridgeError,
    atomic_write_json,
    get_memory_paths,
    load_memory,
    safe_resolve_path,
    utc_now_iso,
    validate_memory_data,
)


def _compute_payload_sha256(memory_data: dict[str, Any]) -> str:
    canonical = json.dumps(memory_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def create_backup(
    workspace_root: Path,
    label: str = "manual",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a verifiable JSON snapshot backup in .ai-memory/backups/."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    memory_data = load_memory(workspace_root)

    safe_label = re.sub(r"[^a-zA-Z0-9_\-]", "-", label.strip())[:32] or "snapshot"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    rev = int(memory_data.get("revision", 1))
    backup_id = f"backup_{stamp}_rev{rev:04d}_{safe_label}"
    backup_filename = f"{backup_id}.json"
    backup_path = safe_resolve_path(
        workspace_root, f"{MEMORY_DIR_NAME}/{BACKUPS_DIR_NAME}/{backup_filename}"
    )

    checksum = _compute_payload_sha256(memory_data)
    bundle = {
        "backup_id": backup_id,
        "created_at": utc_now_iso(),
        "label": safe_label,
        "revision": rev,
        "schema_version": memory_data.get("schema_version"),
        "sha256": checksum,
        "entry_count": len(memory_data.get("entries", [])),
        "memory": memory_data,
    }

    if not dry_run:
        paths["backups_dir"].mkdir(parents=True, exist_ok=True)
        atomic_write_json(backup_path, bundle)

    return {
        "status": "created",
        "dry_run": dry_run,
        "backup_id": backup_id,
        "path": str(backup_path),
        "revision": rev,
        "entry_count": len(memory_data.get("entries", [])),
        "sha256": checksum,
    }


def list_backups(workspace_root: Path) -> list[dict[str, Any]]:
    """List all backup snapshots in .ai-memory/backups/ sorted newest first."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    backups_dir = paths["backups_dir"]
    if not backups_dir.exists():
        return []

    items: list[dict[str, Any]] = []
    for file_path in sorted(backups_dir.glob("backup_*.json"), reverse=True):
        if file_path.is_symlink():
            continue
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            items.append(
                {
                    "backup_id": raw.get("backup_id", file_path.stem),
                    "created_at": raw.get("created_at", ""),
                    "label": raw.get("label", ""),
                    "revision": raw.get("revision", 0),
                    "entry_count": raw.get("entry_count", 0),
                    "sha256": raw.get("sha256", ""),
                    "path": str(file_path),
                }
            )
        except Exception:
            items.append(
                {
                    "backup_id": file_path.stem,
                    "created_at": "",
                    "label": "corrupted",
                    "revision": -1,
                    "entry_count": -1,
                    "sha256": "",
                    "path": str(file_path),
                }
            )
    return items


def verify_backup(workspace_root: Path, backup_id_or_file: str) -> dict[str, Any]:
    """Verify integrity and schema validity of a backup snapshot."""
    workspace_root = workspace_root.resolve()
    filename = backup_id_or_file if backup_id_or_file.endswith(".json") else f"{backup_id_or_file}.json"
    if "/" in filename or "\\" in filename:
        raise MemoryBridgeError("Backup identifier must be a backup ID or filename, not a path.")
    backup_path = safe_resolve_path(
        workspace_root, f"{MEMORY_DIR_NAME}/{BACKUPS_DIR_NAME}/{filename}"
    )
    if not backup_path.exists():
        raise MemoryBridgeError(f"Backup not found: {backup_id_or_file}")

    try:
        bundle = json.loads(backup_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MemoryBridgeError(f"Backup JSON is corrupted: {exc}") from exc

    memory_data = bundle.get("memory")
    if not isinstance(memory_data, dict):
        raise MemoryBridgeError("Backup bundle is missing 'memory' object.")

    validate_memory_data(memory_data)
    actual_sha = _compute_payload_sha256(memory_data)
    expected_sha = bundle.get("sha256", "")
    if expected_sha and actual_sha != expected_sha:
        raise MemoryBridgeError(
            f"Backup checksum mismatch! Expected {expected_sha}, computed {actual_sha}."
        )

    return {
        "status": "verified",
        "backup_id": bundle.get("backup_id", backup_path.stem),
        "revision": bundle.get("revision"),
        "entry_count": len(memory_data.get("entries", [])),
        "sha256": actual_sha,
        "path": str(backup_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage local backups in .ai-memory/backups/.")
    subparsers = parser.add_subparsers(dest="command")

    p_create = subparsers.add_parser("create", help="Create a new backup snapshot.")
    p_create.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_create.add_argument("--label", default="manual", help="Short label for the backup.")
    p_create.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    p_create.add_argument("--json", action="store_true", help="Output JSON.")

    p_list = subparsers.add_parser("list", help="List available backups.")
    p_list.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_list.add_argument("--json", action="store_true", help="Output JSON.")

    p_verify = subparsers.add_parser("verify", help="Verify checksum and schema of a backup.")
    p_verify.add_argument("--workspace", default=".", help="Workspace root directory.")
    p_verify.add_argument("--id", required=True, help="Backup ID or filename to verify.")
    p_verify.add_argument("--json", action="store_true", help="Output JSON.")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "create":
            res = create_backup(Path(args.workspace), label=args.label, dry_run=args.dry_run)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Backup created: {res['backup_id']} (rev {res['revision']}, {res['entry_count']} entries)")
        elif args.command == "list":
            items = list_backups(Path(args.workspace))
            if args.json:
                print(json.dumps({"backups": items}, indent=2))
            else:
                if not items:
                    print("No backups found.")
                for b in items:
                    print(
                        f"- {b['backup_id']} | rev {b['revision']} | entries: {b['entry_count']} | {b['created_at']}"
                    )
        elif args.command == "verify":
            res = verify_backup(Path(args.workspace), args.id)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Backup verified: {res['backup_id']} (SHA-256: {res['sha256'][:16]}...)")
    except MemoryBridgeError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
