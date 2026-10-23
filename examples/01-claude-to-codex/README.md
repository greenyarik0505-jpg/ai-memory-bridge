# Example 1: Claude Code to OpenAI Codex Handoff

## Scenario
You start architecting a webhook ingestion service in **Claude Code**. After implementing the HMAC signature middleware and deciding on a PostgreSQL transactional outbox pattern, you want to switch to **OpenAI Codex** to implement the background worker without re-explaining the architecture.

## Conversational Prompts

In **Claude Code**:
> *"Save our architectural decisions and progress, then prepare a handoff for Codex."*

In **OpenAI Codex**:
> *"Continue where Claude Code stopped."*

## Commands Executed by the Skill

```bash
# 1. Initialize .ai-memory/ in the project
python skills/ai-memory-bridge/scripts/init.py --workspace . --project-name "webhook-service"

# 2. Import captured session entries from Claude Code
python skills/ai-memory-bridge/scripts/capture.py import \
  --workspace . \
  --from-json sample_entries.json \
  --source claude-code

# 3. Generate the Codex handoff packet and update AGENTS.md non-destructively
python skills/ai-memory-bridge/scripts/handoff.py \
  --workspace . \
  --from claude-code \
  --to codex \
  --note "HMAC middleware is done; implement the PostgreSQL outbox worker next."
```

## Verifiable Output

Run the self-checking demonstration script:

```bash
python examples/01-claude-to-codex/run_example.py
```

Expected verifiable artifacts created in the workspace:
- `.ai-memory/memory.json` (Revision 5, 4 active entries, schema `1.0.0`)
- `.ai-memory/handoffs/handoff-codex.md` (Full structured handoff packet for OpenAI Codex)
- `AGENTS.md` (Updated with bounded `<!-- AI-MEMORY-BRIDGE:START -->` block while preserving existing custom instructions)
