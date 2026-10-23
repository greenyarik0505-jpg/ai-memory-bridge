# Demo Recording Guide (`Claude Code -> Saved Memory -> Codex`)

This guide contains a reproducible [VHS](https://github.com/charmbracelet/vhs) tape script and terminal walkthrough to record a live GIF demonstration of **AI Memory Bridge** handing off context from **Claude Code** to **OpenAI Codex**.

> Note: An authentic SVG terminal snapshot generated from real script output is already bundled at [`skills/ai-memory-bridge/assets/demo-handoff.svg`](../skills/ai-memory-bridge/assets/demo-handoff.svg) and embedded in the root `README.md`.

---

## Option A: Record a GIF with Charmbracelet VHS

Save the block below as `demo.tape` and run `vhs demo.tape`:

```tape
Output docs/demo-handoff.gif
Set FontSize 15
Set Width 1000
Set Height 560
Set Theme "Catppuccin Mocha"
Set Padding 20

Type "# Step 1: Claude Code captures architectural decisions & progress"
Enter
Sleep 800ms

Type "python examples/01-claude-to-codex/run_example.py"
Enter
Sleep 4s

Type "# Step 2: Run AI Memory Bridge Doctor to verify schema & security"
Enter
Sleep 800ms

Type "python skills/ai-memory-bridge/scripts/doctor.py --workspace ."
Enter
Sleep 4s
```

---

## Option B: Interactive Terminal Walkthrough

Run these commands in an empty temporary folder to observe the full handoff flow interactively:

```bash
mkdir /tmp/demo-webhook && cd /tmp/demo-webhook

# 1. Initialize .ai-memory/
python /path/to/ai-memory-bridge/skills/ai-memory-bridge/scripts/init.py --project-name "webhook-service"

# 2. Capture decision from Claude Code
python /path/to/ai-memory-bridge/skills/ai-memory-bridge/scripts/capture.py add \
  --type decision \
  --title "Idempotency Store" \
  --content "Use PostgreSQL 16 transactional outbox with UNIQUE (provider_id, event_id)." \
  --priority critical \
  --source claude-code

# 3. Capture next step for Codex
python /path/to/ai-memory-bridge/skills/ai-memory-bridge/scripts/capture.py add \
  --type next_step \
  --title "Implement Outbox Worker" \
  --content "Build async worker polling pending outbox events with exponential backoff." \
  --priority high \
  --source claude-code

# 4. Generate Codex handoff packet and update AGENTS.md
python /path/to/ai-memory-bridge/skills/ai-memory-bridge/scripts/handoff.py \
  --from claude-code \
  --to codex \
  --note "Schema is ready; implement the worker next."

# 5. Inspect generated handoff packet
cat .ai-memory/handoffs/handoff-codex.md
```
