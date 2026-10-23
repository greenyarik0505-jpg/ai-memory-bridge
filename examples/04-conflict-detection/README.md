# Example 4: Automatic Conflict Detection & Resolution

## Scenario
Agent A (**Claude Code**) records an architectural decision to use **PostgreSQL 16** for primary storage. Later, Agent B (**Cursor**) records a decision on the same topic proposing **MongoDB** without superseding the first decision. **AI Memory Bridge** automatically flags the conflict, surfaces it in `.ai-memory/decisions.md` and `.ai-memory/context.md`, and lets the agent resolve it cleanly.

## Conversational Prompts

> *"Check if there are any conflicting architectural decisions in project memory."*
> *"Resolve the database conflict by keeping the PostgreSQL decision."*

## Commands Executed by the Skill

```bash
# 1. Agent A records PostgreSQL decision
python skills/ai-memory-bridge/scripts/capture.py add \
  --workspace . \
  --type decision \
  --title "Primary Database Architecture" \
  --content "Use PostgreSQL 16 with strict ACID transactions." \
  --priority high \
  --source claude-code

# 2. Agent B records conflicting MongoDB decision (triggers automatic conflict detection)
python skills/ai-memory-bridge/scripts/capture.py add \
  --workspace . \
  --type decision \
  --title "Primary Database Architecture" \
  --content "Use MongoDB document store for primary storage." \
  --priority high \
  --source cursor

# 3. Resolve conflict by keeping Agent A's decision
python skills/ai-memory-bridge/scripts/capture.py resolve-conflict \
  --workspace . \
  --conflict-id <CONFLICT_ID> \
  --keep <POSTGRES_ENTRY_ID> \
  --note "Confirmed ACID requirement with engineering lead"
```

## Verifiable Output

Run the self-checking demonstration script:

```bash
python examples/04-conflict-detection/run_example.py
```
