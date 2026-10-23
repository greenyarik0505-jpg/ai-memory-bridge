#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Architecture & Constraint Guard (guard.py).

Actively checks workspace source code and dependency manifests against the project's
active `constraint` and `decision` entries in `.ai-memory/memory.json`.

Detects:
  1. Forbidden imports/libraries specified in memory constraints (e.g. "Never use requests",
     "Запрещено использовать sqlite3", "Do not import moment").
  2. Violations of "zero external dependencies / stdlib only" constraints in pyproject.toml,
     requirements.txt, or package.json.
  3. Forbidden code patterns explicitly backticked in negative constraints (e.g.
     "Never leave `console.log` in src", "Forbid `eval(`").

Usage:
  python scripts/guard.py [--workspace .] [--changed-only] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from memory_utils import (  # noqa: E402
    NEGATION_PATTERNS,
    MemoryBridgeError,
    get_memory_paths,
    load_memory,
)

SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".dart"}
IGNORED_DIRS = {
    ".git",
    ".ai-memory",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
}

ZERO_DEP_PATTERN = re.compile(
    r"(?i)(?:zero\s+(?:external\s+)?dependencies|stdlib\s+only|standard\s+library\s+only|"
    r"без\s+внешних\s+зависимостей|только\s+стандартн\w+\s+библиотек\w+|"
    r"без\s+зовнішніх\s+залежностей|零外部依赖|仅标准库)"
)

FORBIDDEN_TARGET_PATTERNS = [
    re.compile(
        r"(?i)(?:never\s+(?:use|import)|do\s+not\s+(?:use|import)|must\s+not\s+(?:use|import)|"
        r"forbid(?:den)?(?:\s+to\s+use)?|prohibit(?:ed)?|avoid\s+using|"
        r"не\s+использовать|запрещено\s+использовать|нельзя\s+использовать|"
        r"не\s+використовувати|заборонено\s+використовувати|"
        r"禁止使用|不要使用|严禁使用)\s+`?([a-zA-Z0-9_.\-]+(?:\()?)`?"
    ),
]


def extract_guard_rules(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive executable code compliance rules from active constraint and decision entries."""
    rules: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("status") not in ("active", "conflicted"):
            continue
        if entry.get("type") not in ("constraint", "decision", "preference"):
            continue

        eid = entry.get("id", "unknown")
        title = entry.get("title", "")
        content = entry.get("content", "")
        combined = f"{title}. {content}"

        # 1. Check for zero-dependency rule
        if ZERO_DEP_PATTERN.search(combined):
            rules.append(
                {
                    "rule_type": "zero_dependencies",
                    "target": "external_dependencies",
                    "entry_id": eid,
                    "entry_title": title,
                }
            )

        # 2. Check for explicit forbidden package / identifier after negation phrases
        for pat in FORBIDDEN_TARGET_PATTERNS:
            for match in pat.finditer(combined):
                target = match.group(1).strip().strip(".,;:")
                if len(target) >= 2 and target.lower() not in (
                    "the", "any", "this", "that", "it", "them", "external", "library", "libraries",
                    "пакеты", "библиотеки", "это",
                ):
                    rules.append(
                        {
                            "rule_type": "forbidden_token",
                            "target": target,
                            "entry_id": eid,
                            "entry_title": title,
                        }
                    )

        # 3. Also check backticked literals inside negative sentences
        if NEGATION_PATTERNS.search(combined):
            for bt_match in re.finditer(r"`([^`\n]{2,40})`", combined):
                literal = bt_match.group(1).strip()
                # Skip file paths or CLI commands with spaces unless it's a call like console.log
                if "/" in literal or "\\" in literal or " " in literal:
                    continue
                # Avoid flagging the positively recommended alternative in "Use `X`, never `Y`"
                before_pos = combined[: bt_match.start()]
                last_clause = re.split(r"[.;,!]|(?i:\binstead\s+of\b|\bвместо\b|\bзамість\b)", before_pos)[-1]
                if NEGATION_PATTERNS.search(last_clause):
                    if not any(r["entry_id"] == eid and r["target"] == literal for r in rules):
                        rules.append(
                            {
                                "rule_type": "forbidden_token",
                                "target": literal,
                                "entry_id": eid,
                                "entry_title": title,
                            }
                        )

    return rules


def _collect_candidate_files(workspace_root: Path, changed_only: bool = False) -> list[Path]:
    if changed_only:
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(workspace_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if proc.returncode == 0:
                files: list[Path] = []
                for line in proc.stdout.splitlines():
                    if len(line) > 3:
                        rel = line[3:].strip().strip('"')
                        if " -> " in rel:
                            rel = rel.split(" -> ")[-1].strip()
                        cand = (workspace_root / rel).resolve()
                        if cand.is_file() and cand.suffix.lower() in SOURCE_EXTENSIONS:
                            files.append(cand)
                return files
        except Exception:
            pass

    collected: list[Path] = []
    for root, dirs, filenames in os_walk_filtered(workspace_root):
        for fname in filenames:
            fpath = root / fname
            if fpath.suffix.lower() in SOURCE_EXTENSIONS and not fpath.is_symlink():
                collected.append(fpath)
    return collected


def os_walk_filtered(workspace_root: Path):
    import os

    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".pytest")]
        yield Path(root), dirs, files


def _check_zero_dependencies(workspace_root: Path, rule: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    pkg_json = workspace_root / "package.json"
    if pkg_json.is_file() and not pkg_json.is_symlink():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            deps = data.get("dependencies", {})
            if isinstance(deps, dict) and len(deps) > 0:
                violations.append(
                    {
                        "file": "package.json",
                        "line": 1,
                        "rule_type": "zero_dependencies",
                        "target": ", ".join(sorted(deps.keys())),
                        "entry_id": rule["entry_id"],
                        "entry_title": rule["entry_title"],
                        "snippet": f"package.json contains runtime dependencies: {list(deps.keys())}",
                    }
                )
        except Exception:
            pass

    req_txt = workspace_root / "requirements.txt"
    if req_txt.is_file() and not req_txt.is_symlink():
        lines = [
            ln.strip()
            for ln in req_txt.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if lines:
            violations.append(
                {
                    "file": "requirements.txt",
                    "line": 1,
                    "rule_type": "zero_dependencies",
                    "target": ", ".join(lines[:5]),
                    "entry_id": rule["entry_id"],
                    "entry_title": rule["entry_title"],
                    "snippet": f"requirements.txt lists external packages: {lines[:5]}",
                }
            )
    return violations


def _file_violates_token(file_path: Path, rel_path: str, target: str) -> list[tuple[int, str]]:
    """Check if a source file imports or invokes a forbidden package/pattern."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    hits: list[tuple[int, str]] = []
    escaped = re.escape(target.rstrip("("))
    is_ident = bool(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", target))

    if is_ident and file_path.suffix == ".py":
        # Check Python import or direct call/usage
        import_re = re.compile(rf"^\s*(?:import\s+{escaped}\b|from\s+{escaped}(?:\.[a-zA-Z0-9_]+)*\s+import\b)")
        call_re = re.compile(rf"\b{escaped}\s*\(")
        for idx, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if import_re.search(line) or (target in ("eval", "exec", "print") and call_re.search(line)):
                hits.append((idx, stripped[:120]))
    else:
        # Check JS/TS import, require, or literal pattern like console.log / eval(
        pattern = re.compile(
            rf"(?:from\s+['\"]{escaped}['\"]|require\(\s*['\"]{escaped}['\"]\s*\)|\b{escaped})"
        )
        for idx, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("#"):
                continue
            if pattern.search(line):
                hits.append((idx, stripped[:120]))

    return hits


def run_guard(workspace_root: Path, changed_only: bool = False) -> dict[str, Any]:
    """Run architectural & constraint compliance checks on workspace files."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    if not paths["memory_json"].exists():
        raise MemoryBridgeError("Memory store is not initialized (.ai-memory/memory.json missing).")

    data = load_memory(workspace_root)
    rules = extract_guard_rules(data.get("entries", []))
    candidate_files = _collect_candidate_files(workspace_root, changed_only=changed_only)

    violations: list[dict[str, Any]] = []
    for rule in rules:
        if rule["rule_type"] == "zero_dependencies":
            violations.extend(_check_zero_dependencies(workspace_root, rule))
        elif rule["rule_type"] == "forbidden_token":
            target = rule["target"]
            for fpath in candidate_files:
                rel = fpath.relative_to(workspace_root).as_posix()
                # Skip test files when checking general production constraints unless target is in src
                if rel.startswith("tests/") or rel.startswith("test_"):
                    continue
                for line_no, snippet in _file_violates_token(fpath, rel, target):
                    violations.append(
                        {
                            "file": rel,
                            "line": line_no,
                            "rule_type": "forbidden_token",
                            "target": target,
                            "entry_id": rule["entry_id"],
                            "entry_title": rule["entry_title"],
                            "snippet": snippet,
                        }
                    )

    return {
        "status": "pass" if not violations else "violation",
        "rules_extracted": len(rules),
        "files_scanned": len(candidate_files),
        "violations_count": len(violations),
        "rules": rules,
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify workspace code compliance against active AI Memory Bridge constraints and decisions."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    parser.add_argument("--changed-only", action="store_true", help="Only scan files modified in Git working tree.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    args = parser.parse_args(argv)

    try:
        report = run_guard(Path(args.workspace), changed_only=args.changed_only)
    except MemoryBridgeError as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"=== AI Memory Bridge Architecture Guard: {report['status'].upper()} "
            f"({report['rules_extracted']} rules checked across {report['files_scanned']} files) ==="
        )
        if report["violations"]:
            for v in report["violations"]:
                print(
                    f"  [VIOLATION] {v['file']}:{v['line']} violates {v['entry_id']} "
                    f"('{v['entry_title']}') -> forbidden '{v['target']}': {v['snippet']}"
                )
        else:
            print("  All scanned files comply with active project memory constraints and decisions.")

    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
