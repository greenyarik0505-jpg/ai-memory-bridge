# Changelog

All notable changes to **AI Memory Bridge** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-23

### Added
- **Agent Skill Bundle (`skills/ai-memory-bridge/SKILL.md`)**: Full compliance with the open Agent Skills specification, compatible with `npx skills add greenyarik0505-jpg/ai-memory-bridge`.
- **Universal Local Memory Store (`.ai-memory/`)**: Versioned `memory.json` (Schema `v1.0.0`) with automatic rendering of `context.md`, `decisions.md`, and `tasks.md`.
- **9 Universal Memory Entry Types**: `goal`, `decision`, `task_done`, `task_pending`, `constraint`, `bug_fix`, `preference`, `next_step`, and `session_summary`.
- **Cross-Agent Handoff Engine (`handoff.py`)**: Structured handoff packets and non-destructive rule updates across Claude Code, OpenAI Codex, Cursor, Google Antigravity, Gemini CLI, OpenCode, and GitHub Copilot.
- **Smart Memory Engine (`memory_utils.py`, `capture.py`, `sync.py`)**:
  - Exact SHA-256 and fuzzy similarity deduplication with priority boosting.
  - Supersede chains (`--supersedes`) for updating outdated architectural decisions.
  - Automatic conflict detection (`detect_conflicts_for_entry`) for competing technology choices and contradictory directives.
  - Token-budget context compaction (`compact_memory`) preserving critical entries.
  - Append-only audit log (`history/events.jsonl`) and per-revision snapshots (`history/rev_NNNNN.json`).
- **Defense-in-Depth Security**:
  - Secret scanning and optional redaction (`--redact-secrets`) for API keys, tokens, private keys, and DB URIs.
  - Prompt injection and command-execution directive blocking.
  - Path traversal and symbolic link rejection (`safe_resolve_path`).
  - Atomic file persistence (`tempfile` + `os.fsync` + `os.replace`).
- **Backup & Recovery (`backup.py`, `restore.py`, `doctor.py`)**: SHA-256 verified backup bundles, `--dry-run` restore previews, `--confirm` safety gates, automatic pre-restore backups, and workspace health diagnostics.
- **Reproducible Examples & Cross-Platform Test Suite**: 4 runnable examples and 25 unit/integration tests running across Windows, macOS, and Linux.
