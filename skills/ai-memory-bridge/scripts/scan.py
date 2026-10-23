#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Auto-scan an existing codebase to populate initial AI Memory Bridge context in 1 second.

Detects programming languages, frameworks, package managers, build/test commands,
top-level architecture layout, and existing AI agent rule files using only the
Python 3.10+ standard library.

Usage:
  python scripts/scan.py [--workspace .] [--apply] [--dry-run] [--json]
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
from init import initialize_workspace  # noqa: E402
from memory_utils import (  # noqa: E402
    MemoryBridgeError,
    safe_resolve_path,
)
from sync import detect_workspace_agents  # noqa: E402

COMMON_SOURCE_DIRS = (
    "src",
    "app",
    "lib",
    "pkg",
    "cmd",
    "internal",
    "skills",
    "scripts",
    "tests",
    "test",
    "docs",
    "examples",
    "api",
    "components",
    "services",
    "backend",
    "frontend",
)


def _scan_package_json(workspace_root: Path) -> dict[str, Any]:
    pkg_path = workspace_root / "package.json"
    if not pkg_path.exists() or pkg_path.is_symlink():
        return {}
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    deps = {}
    for sec in ("dependencies", "devDependencies"):
        if isinstance(data.get(sec), dict):
            deps.update(data[sec])

    frameworks: list[str] = []
    for key, label in (
        ("next", "Next.js"),
        ("react", "React"),
        ("vue", "Vue.js"),
        ("svelte", "Svelte"),
        ("vite", "Vite"),
        ("express", "Express"),
        ("@nestjs/core", "NestJS"),
        ("tailwindcss", "Tailwind CSS"),
        ("typescript", "TypeScript"),
        ("playwright", "Playwright"),
        ("vitest", "Vitest"),
        ("jest", "Jest"),
    ):
        if key in deps:
            frameworks.append(label)

    scripts = data.get("scripts", {}) if isinstance(data.get("scripts"), dict) else {}
    important_scripts = {
        k: str(v)
        for k, v in scripts.items()
        if k in ("dev", "start", "build", "test", "lint", "typecheck", "check")
    }

    pkg_manager = "npm"
    if (workspace_root / "pnpm-lock.yaml").exists():
        pkg_manager = "pnpm"
    elif (workspace_root / "yarn.lock").exists():
        pkg_manager = "yarn"
    elif (workspace_root / "bun.lockb").exists() or (workspace_root / "bun.lock").exists():
        pkg_manager = "bun"

    return {
        "name": str(data.get("name", "")),
        "package_manager": pkg_manager,
        "frameworks": frameworks,
        "scripts": important_scripts,
    }


def _scan_pyproject(workspace_root: Path) -> dict[str, Any]:
    pyproj = workspace_root / "pyproject.toml"
    if not pyproj.exists() or pyproj.is_symlink():
        return {}
    text = pyproj.read_text(encoding="utf-8", errors="replace")

    name_match = re.search(r'(?m)^name\s*=\s*["\']([^"\']+)["\']', text)
    req_py_match = re.search(r'(?m)^requires-python\s*=\s*["\']([^"\']+)["\']', text)

    frameworks: list[str] = []
    for kw, label in (
        ("fastapi", "FastAPI"),
        ("django", "Django"),
        ("flask", "Flask"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pydantic", "Pydantic"),
        ("pytest", "pytest"),
        ("ruff", "Ruff"),
    ):
        if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
            frameworks.append(label)

    pkg_manager = "uv" if (workspace_root / "uv.lock").exists() else "pip"
    return {
        "name": name_match.group(1) if name_match else "",
        "requires_python": req_py_match.group(1) if req_py_match else ">=3.10",
        "package_manager": pkg_manager,
        "frameworks": frameworks,
    }


def scan_codebase(workspace_root: Path) -> dict[str, Any]:
    """Perform a fast, deterministic static scan of the workspace structure and manifests."""
    workspace_root = workspace_root.resolve()
    safe_resolve_path(workspace_root, ".")

    stacks: list[str] = []
    commands: list[str] = []
    constraints: list[str] = []
    detected_project_name = workspace_root.name

    # 1. Python detection
    py_info = _scan_pyproject(workspace_root)
    if py_info or (workspace_root / "requirements.txt").exists():
        stacks.append("Python")
        if py_info.get("name"):
            detected_project_name = py_info["name"]
        if py_info.get("requires_python"):
            constraints.append(f"Python version requirement: {py_info['requires_python']}.")
        if py_info.get("frameworks"):
            stacks.extend(py_info["frameworks"])
        if (workspace_root / "tests").is_dir():
            commands.append("Run Python unit tests: `python -m unittest discover -s tests -v` or `pytest tests`.")

    # 2. Node.js / TypeScript detection
    node_info = _scan_package_json(workspace_root)
    if node_info:
        pm = node_info["package_manager"]
        stacks.append(f"Node.js ({pm})")
        if node_info.get("name") and detected_project_name == workspace_root.name:
            detected_project_name = node_info["name"]
        stacks.extend(node_info.get("frameworks", []))
        for script_name in ("build", "test", "lint", "dev"):
            if script_name in node_info.get("scripts", {}):
                commands.append(f"`{pm} run {script_name}` -> `{node_info['scripts'][script_name]}`")

    # 3. Rust / Go / Dart / Docker detection
    if (workspace_root / "Cargo.toml").exists():
        stacks.append("Rust (Cargo)")
        commands.append("Build & test Rust crate: `cargo build` and `cargo test`.")
    if (workspace_root / "go.mod").exists():
        stacks.append("Go (Modules)")
        commands.append("Build & test Go packages: `go build ./...` and `go test ./...`.")
    if (workspace_root / "pubspec.yaml").exists():
        stacks.append("Dart / Flutter")
        commands.append("Analyze & test Dart/Flutter: `dart analyze` and `flutter test`.")
    if (workspace_root / "Dockerfile").exists() or (workspace_root / "docker-compose.yml").exists():
        stacks.append("Docker")

    # 4. Top-level directory layout
    present_dirs = [
        d for d in COMMON_SOURCE_DIRS if (workspace_root / d).is_dir() and not (workspace_root / d).is_symlink()
    ]

    # 5. Agent Skill detection
    skill_files = list(workspace_root.glob("skills/*/SKILL.md"))
    skill_names = [sf.parent.name for sf in skill_files if not sf.is_symlink()]
    if skill_names:
        stacks.append(f"Agent Skills ({', '.join(skill_names)})")

    detected_agents = detect_workspace_agents(workspace_root)

    # Construct synthesized memory entries ready for capture
    proposed_entries: list[dict[str, Any]] = []
    if stacks or present_dirs:
        stack_str = ", ".join(dict.fromkeys(stacks)) if stacks else "General repository"
        dirs_str = ", ".join(f"`{d}/`" for d in present_dirs) if present_dirs else "root directory"
        proposed_entries.append(
            {
                "type": "decision",
                "title": "Detected Technology Stack & Architecture Layout",
                "content": f"Primary stack: {stack_str}. Key workspace directories: {dirs_str}.",
                "priority": "high",
                "source": "auto-scanner",
                "tags": ["stack", "architecture", "auto-scan"],
            }
        )

    if commands:
        proposed_entries.append(
            {
                "type": "preference",
                "title": "Standard Build & Verification Commands",
                "content": " | ".join(commands),
                "priority": "high",
                "source": "auto-scanner",
                "tags": ["commands", "verification", "auto-scan"],
            }
        )

    if constraints:
        proposed_entries.append(
            {
                "type": "constraint",
                "title": "Detected Runtime & Environment Constraints",
                "content": " ".join(constraints),
                "priority": "high",
                "source": "auto-scanner",
                "tags": ["constraints", "auto-scan"],
            }
        )

    return {
        "project_name": detected_project_name,
        "workspace": str(workspace_root),
        "stacks": list(dict.fromkeys(stacks)),
        "directories": present_dirs,
        "commands": commands,
        "constraints": constraints,
        "detected_agents": detected_agents,
        "proposed_entries": proposed_entries,
    }


def scan_and_populate(
    workspace_root: Path,
    apply_entries: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan workspace and optionally record discovered facts into .ai-memory/memory.json."""
    workspace_root = workspace_root.resolve()
    scan_report = scan_codebase(workspace_root)
    saved_ids: list[str] = []

    if apply_entries and not dry_run:
        initialize_workspace(workspace_root, project_name=scan_report["project_name"])
        for item in scan_report["proposed_entries"]:
            res = add_memory_entry(
                workspace_root=workspace_root,
                entry_type=item["type"],
                title=item["title"],
                content=item["content"],
                source=item["source"],
                priority=item["priority"],
                tags=item["tags"],
                allow_redact_secrets=True,
                dry_run=False,
            )
            saved_ids.append(res["entry"]["id"])

    return {
        "status": "scanned_and_applied" if (apply_entries and not dry_run) else "scanned_only",
        "dry_run": dry_run,
        "saved_entry_ids": saved_ids,
        "scan": scan_report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Auto-scan a repository to detect stack, layout, and build commands for AI Memory Bridge."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    parser.add_argument("--no-apply", action="store_true", help="Inspect only without saving entries to .ai-memory/.")
    parser.add_argument("--dry-run", action="store_true", help="Preview discovered entries without writing files.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    args = parser.parse_args(argv)

    try:
        res = scan_and_populate(
            workspace_root=Path(args.workspace),
            apply_entries=not args.no_apply,
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
        s = res["scan"]
        print(f"AI Memory Bridge Auto-Scanner — Project: {s['project_name']}")
        print(f"  Detected Stack       : {', '.join(s['stacks']) or 'Generic'}")
        print(f"  Source Directories   : {', '.join(s['directories']) or '(root)'}")
        print(f"  Detected AI Agents   : {', '.join(s['detected_agents']) or 'None yet'}")
        print(f"  Entries Recorded     : {len(res['saved_entry_ids'])} ({res['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
