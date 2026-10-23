# Usage Guide

**AI Memory Bridge** is designed for **zero-CLI-friction conversational use**. Once installed as a skill, you talk to your AI coding agent in plain English and the agent executes the underlying verification and storage scripts automatically.

---

## 1. Conversational Prompts Cheat Sheet

| What You Want to Do | What to Say to Your AI Agent | Script Executed by the Agent |
| :--- | :--- | :--- |
| **Initialize project memory** | *"Remember this project."* / *"Initialize AI Memory Bridge."* | `scripts/init.py` |
| **Save session progress** | *"Save our progress."* / *"Save everything important about this project."* | `scripts/capture.py add` |
| **Hand off to another agent** | *"Prepare a handoff for Codex."* / *"Prepare this project for Cursor."* | `scripts/handoff.py --to <agent>` |
| **Resume in a new agent** | *"Continue where Claude Code stopped."* / *"Resume from project memory."* | Reads `.ai-memory/handoffs/` & `capture.py list` |
| **Synchronize agent rules** | *"Sync project memory across our agents."* | `scripts/sync.py --targets detected` |
| **Compact long history** | *"Compact our project memory to fit 2,000 tokens."* | `scripts/capture.py compact --max-tokens 2000` |
| **Check for conflicts** | *"Check if we have any conflicting architectural decisions."* | `scripts/capture.py list --status conflicted` |
| **Create a backup checkpoint** | *"Create a memory backup before this refactor."* | `scripts/backup.py create` |
| **Roll back memory** | *"Restore our project memory to revision 3."* | `scripts/restore.py --revision 3 --dry-run` → `--confirm` |
| **Verify health & security** | *"Run AI Memory Bridge doctor."* | `scripts/doctor.py` |

---

## 2. Opt-In Automatic Capture via Lifecycle Hooks

By default, AI Memory Bridge never modifies your agent's lifecycle hooks without explicit consent.

If you use **Claude Code** or **Google Antigravity** and want automatic session context injection at startup (`SessionStart`) and automatic Markdown view syncing at turn completion (`Stop`), tell your agent:

> *"Enable AI Memory Bridge automatic hooks for Claude Code."*

Under the hood, the agent runs:

```bash
# For Claude Code (.claude/settings.json)
python scripts/init.py --workspace . --enable-hooks --agent claude-code

# For Google Antigravity (.agents/hooks.json)
python scripts/init.py --workspace . --enable-hooks --agent antigravity
```

---

## 3. Direct CLI Reference (Optional)

While normal usage is 100% conversational, every script supports `--help`, `--dry-run`, and `--json` for CI pipelines or power users:

```bash
# Initialize workspace
python skills/ai-memory-bridge/scripts/init.py --workspace . --project-name "my-service"

# Add a memory entry
python skills/ai-memory-bridge/scripts/capture.py add \
  --workspace . \
  --type decision \
  --title "Authentication Strategy" \
  --content "Use short-lived EdDSA JWT access tokens with HTTP-only refresh cookies." \
  --priority critical \
  --source claude-code

# Prepare a handoff packet for OpenAI Codex
python skills/ai-memory-bridge/scripts/handoff.py \
  --workspace . \
  --from claude-code \
  --to codex \
  --note "JWT verification is complete; implement token rotation endpoint next."

# Synchronize all detected agent rule files
python skills/ai-memory-bridge/scripts/sync.py --workspace . --targets detected

# Create and verify a backup snapshot
python skills/ai-memory-bridge/scripts/backup.py create --workspace . --label "pre-release"
python skills/ai-memory-bridge/scripts/backup.py list --workspace .

# Run full workspace diagnostics
python skills/ai-memory-bridge/scripts/doctor.py --workspace .
```
