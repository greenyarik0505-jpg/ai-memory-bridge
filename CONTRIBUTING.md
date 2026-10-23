# Contributing to AI Memory Bridge

Thank you for your interest in contributing to **AI Memory Bridge**!

## Core Engineering Principles

1. **Skill-First Design**: AI Memory Bridge is primarily an open-standard **Agent Skill** (`skills/ai-memory-bridge/SKILL.md`). Every feature must be usable through natural conversation with an AI agent while backed by deterministic Python scripts.
2. **Zero External Runtime Dependencies**: All scripts under `skills/ai-memory-bridge/scripts/` must use the Python 3.10+ standard library only. Do not add third-party `pip` packages required at runtime.
3. **Strict Security Guarantees**:
   - Never weaken secret scanning (`scan_for_secrets`), prompt injection checks (`scan_for_prompt_injection`), or path traversal/symlink guards (`safe_resolve_path`).
   - Never overwrite existing user rule files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursor/rules/`) outside bounded markers or dedicated files.
4. **Cross-Platform Compatibility**: All scripts and tests must run cleanly on Windows, macOS, and Linux.

## Local Development & Verification

```bash
# 1. Run the standard library unittest suite
python -m unittest discover -s tests -v

# 2. Run pytest (optional)
pytest tests -v

# 3. Run the 4 reproducible examples
python examples/01-claude-to-codex/run_example.py
python examples/02-cursor-to-antigravity/run_example.py
python examples/03-session-recovery/run_example.py
python examples/04-conflict-detection/run_example.py

# 4. Run doctor diagnostics
python skills/ai-memory-bridge/scripts/doctor.py --workspace .
```

## Submitting Pull Requests

1. Fork the repository and create a feature branch (`git checkout -b feat/your-feature`).
2. Add unit tests in `tests/` covering your changes.
3. Ensure all checks in the Pull Request template pass.
4. Open a Pull Request with a clear summary of the motivation and verification output.
