#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Run health, schema, security, backup, and agent compatibility diagnostics for AI Memory Bridge.

Usage:
  python scripts/doctor.py [--workspace .] [--json]

Exit codes:
  0 = no failed checks (warnings may remain)
  1 = at least one failed check
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from backup import list_backups, verify_backup  # noqa: E402
from memory_utils import (  # noqa: E402
    MEMORY_DIR_NAME,
    MemoryBridgeError,
    check_no_symlinks_in_chain,
    detect_stale_file_references,
    get_memory_paths,
    load_memory,
    scan_for_prompt_injection,
    scan_for_secrets,
)
from sync import detect_workspace_agents  # noqa: E402


def _make_check(name: str, status: str, detail: str, fix: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def run_diagnostics(workspace_root: Path) -> dict[str, Any]:
    """Run offline diagnostic checks on the workspace and AI Memory Bridge installation."""
    checks: list[dict[str, str]] = []
    workspace_root = workspace_root.resolve()

    # 1. Python runtime check
    py_ok = sys.version_info >= (3, 10)
    checks.append(
        _make_check(
            "Python Runtime",
            "PASS" if py_ok else "FAIL",
            f"Python {platform.python_version()} on {platform.system()}",
            "" if py_ok else "Install Python 3.10 or newer.",
        )
    )

    # 2. Skill bundle integrity check
    skill_root = SCRIPT_DIR.parent
    skill_md = skill_root / "SKILL.md"
    required_scripts = (
        "init.py",
        "capture.py",
        "sync.py",
        "handoff.py",
        "restore.py",
        "doctor.py",
        "backup.py",
        "scan.py",
        "dashboard.py",
        "memory_utils.py",
    )
    missing_scripts = [s for s in required_scripts if not (SCRIPT_DIR / s).exists()]
    if skill_md.exists() and not missing_scripts:
        checks.append(
            _make_check(
                "Skill Bundle Integrity",
                "PASS",
                f"SKILL.md and all {len(required_scripts)} scripts verified at {skill_root}",
            )
        )
    else:
        checks.append(
            _make_check(
                "Skill Bundle Integrity",
                "FAIL",
                f"Missing SKILL.md={not skill_md.exists()}, missing scripts={missing_scripts}",
                "Reinstall the ai-memory-bridge skill bundle.",
            )
        )

    # 3. Symlink & workspace write permission check
    try:
        check_no_symlinks_in_chain(workspace_root, workspace_root)
        fd, probe_tmp = tempfile.mkstemp(prefix=".ai_mem_probe_", dir=str(workspace_root))
        os.close(fd)
        Path(probe_tmp).unlink(missing_ok=True)
        checks.append(
            _make_check("Workspace Write & Symlink Safety", "PASS", f"Writable directory: {workspace_root}")
        )
    except Exception as exc:
        checks.append(
            _make_check(
                "Workspace Write & Symlink Safety",
                "FAIL",
                str(exc),
                "Ensure workspace directory is writable and not a symbolic link.",
            )
        )

    # 4. Gitignore privacy check
    gitignore_path = workspace_root / ".gitignore"
    if gitignore_path.exists():
        gi_text = gitignore_path.read_text(encoding="utf-8", errors="replace")
        gi_lines = [line.strip() for line in gi_text.splitlines()]
        ignored = any(x in gi_lines for x in (f"{MEMORY_DIR_NAME}/", MEMORY_DIR_NAME, f"/{MEMORY_DIR_NAME}/"))
        checks.append(
            _make_check(
                "Gitignore Privacy Protection",
                "PASS" if ignored else "WARN",
                ".ai-memory/ is ignored in .gitignore" if ignored else ".ai-memory/ is not listed in .gitignore",
                "" if ignored else "Run `python scripts/init.py` to add `.ai-memory/` to `.gitignore`.",
            )
        )
    else:
        checks.append(
            _make_check(
                "Gitignore Privacy Protection",
                "WARN",
                "No .gitignore file found in workspace root.",
                "Run `python scripts/init.py` to create `.gitignore` with `.ai-memory/`.",
            )
        )

    # 5. Memory store & schema validation check
    try:
        paths = get_memory_paths(workspace_root)
    except MemoryBridgeError as exc:
        checks.append(_make_check("Memory Store Path Safety", "FAIL", str(exc), "Remove symlinks inside .ai-memory/."))
        paths = None

    if paths and paths["memory_json"].exists():
        try:
            data = load_memory(workspace_root)
            entries = data.get("entries", [])
            unresolved = [c for c in data.get("conflicts", []) if c.get("status") == "unresolved"]
            checks.append(
                _make_check(
                    "Memory Schema & Store",
                    "PASS",
                    f"Schema v{data['schema_version']}, rev {data['revision']}, {len(entries)} entries.",
                )
            )
            # Conflict check
            if unresolved:
                checks.append(
                    _make_check(
                        "Memory Conflict Check",
                        "WARN",
                        f"{len(unresolved)} unresolved conflict(s) detected.",
                        "Run `python scripts/capture.py resolve-conflict` to resolve active conflicts.",
                    )
                )
            else:
                checks.append(_make_check("Memory Conflict Check", "PASS", "0 unresolved conflicts."))

            # Security scan across stored entries
            secret_count = 0
            injection_count = 0
            for entry in entries:
                blob = f"{entry.get('title', '')}\n{entry.get('content', '')}"
                secret_count += len(scan_for_secrets(blob))
                injection_count += len(scan_for_prompt_injection(blob))
            if secret_count == 0 and injection_count == 0:
                checks.append(
                    _make_check(
                        "Stored Memory Security Scan",
                        "PASS",
                        "No secrets or prompt injection patterns found in stored entries.",
                    )
                )
            else:
                checks.append(
                    _make_check(
                        "Stored Memory Security Scan",
                        "FAIL",
                        f"Found {secret_count} potential secret(s) and {injection_count} injection pattern(s) in memory.json!",
                        "Inspect and sanitize `.ai-memory/memory.json` immediately.",
                    )
                )

            # Stale file reference drift check
            stale_refs = detect_stale_file_references(workspace_root, entries)
            if not stale_refs:
                checks.append(
                    _make_check(
                        "Stale File Reference Check",
                        "PASS",
                        "All workspace file paths referenced in active memory entries exist.",
                    )
                )
            else:
                checks.append(
                    _make_check(
                        "Stale File Reference Check",
                        "WARN",
                        f"{len(stale_refs)} active entry/entries reference moved or deleted files.",
                        "Run `python scripts/capture.py check-stale` and supersede outdated entries.",
                    )
                )

            # Backup verification
            backups = list_backups(workspace_root)
            if backups:
                latest_b = backups[0]["backup_id"]
                verify_backup(workspace_root, latest_b)
                checks.append(
                    _make_check(
                        "Backup Integrity",
                        "PASS",
                        f"{len(backups)} backup(s) available; latest ({latest_b}) checksum verified.",
                    )
                )
            else:
                checks.append(
                    _make_check(
                        "Backup Integrity",
                        "WARN",
                        "No backups created yet in .ai-memory/backups/.",
                        "Run `python scripts/backup.py create` before major changes.",
                    )
                )

        except MemoryBridgeError as exc:
            checks.append(
                _make_check(
                    "Memory Schema & Store",
                    "FAIL",
                    str(exc),
                    "Restore from a valid backup using `python scripts/restore.py`.",
                )
            )
    elif paths:
        checks.append(
            _make_check(
                "Memory Schema & Store",
                "WARN",
                "Memory store (.ai-memory/memory.json) is not initialized in this workspace yet.",
                "Run `python scripts/init.py` to initialize project memory.",
            )
        )

    # 6. Detected agents
    detected_agents = detect_workspace_agents(workspace_root)
    checks.append(
        _make_check(
            "Detected Workspace Agents",
            "PASS",
            ", ".join(detected_agents) if detected_agents else "None detected yet (standard files will be created on sync/handoff)",
        )
    )

    failed = [c for c in checks if c["status"] == "FAIL"]
    warnings = [c for c in checks if c["status"] == "WARN"]

    return {
        "healthy": len(failed) == 0,
        "workspace": str(workspace_root),
        "summary": {
            "pass": len([c for c in checks if c["status"] == "PASS"]),
            "warn": len(warnings),
            "fail": len(failed),
        },
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run diagnostics on AI Memory Bridge setup and project memory.")
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    args = parser.parse_args(argv)

    report = run_diagnostics(Path(args.workspace))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"AI Memory Bridge Doctor — Workspace: {report['workspace']}")
        print("-" * 72)
        for item in report["checks"]:
            print(f"[{item['status']:4s}] {item['name']}: {item['detail']}")
            if item.get("fix"):
                print(f"       Fix: {item['fix']}")
        print("-" * 72)
        s = report["summary"]
        print(f"Summary: {s['pass']} passed, {s['warn']} warnings, {s['fail']} failed.")

    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
