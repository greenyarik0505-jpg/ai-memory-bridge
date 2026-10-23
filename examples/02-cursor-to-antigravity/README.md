# Example 2: Cursor to Google Antigravity Handoff

## Scenario
While editing in **Cursor**, you define strict technical constraints (Python 3.10+ stdlib only, Windows path compatibility) and queue a pending task. You then hand off the project to **Google Antigravity** to implement the pending task and verify it with subagents.

## Conversational Prompts

In **Cursor**:
> *"Save our technical constraints and pending tasks, and prepare a handoff for Google Antigravity."*

In **Google Antigravity**:
> *"Resume project from memory and complete the pending atomic persistence task."*

## Commands Executed by the Skill

```bash
python skills/ai-memory-bridge/scripts/init.py --workspace . --project-name "cross-platform-cli"
python skills/ai-memory-bridge/scripts/capture.py import --workspace . --from-json sample_entries.json --source cursor
python skills/ai-memory-bridge/scripts/handoff.py --workspace . --from cursor --to antigravity --note "Complete the atomic persistence task while respecting stdlib-only constraint."
```

## Verifiable Output

Run the self-checking demonstration script:

```bash
python examples/02-cursor-to-antigravity/run_example.py
```

Expected verifiable artifacts:
- `.ai-memory/handoffs/handoff-antigravity.md`
- `.agents/rules/ai-memory-bridge.md` (Automatically discovered by Google Antigravity)
- `.cursor/rules/ai-memory-bridge.mdc` (Synced when running `sync.py --targets cursor,antigravity`)
