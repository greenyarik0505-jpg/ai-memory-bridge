# AI Memory Bridge — Reproducible Examples

Each example in this directory demonstrates a real, end-to-end multi-agent workflow with verifiable inputs, commands, and outputs. Every example runs in an isolated temporary workspace by default so it never mutates your repository.

| Example | Scenario | Agents Involved | Run Command |
| :--- | :--- | :--- | :--- |
| **[01-claude-to-codex](./01-claude-to-codex/README.md)** | Capturing architectural decisions in Claude Code and handing off context to OpenAI Codex | `claude-code` → `codex` | `python examples/01-claude-to-codex/run_example.py` |
| **[02-cursor-to-antigravity](./02-cursor-to-antigravity/README.md)** | Handing off pending tasks and technical constraints from Cursor to Google Antigravity | `cursor` → `antigravity` | `python examples/02-cursor-to-antigravity/run_example.py` |
| **[03-session-recovery](./03-session-recovery/README.md)** | Creating a checkpoint backup, recovering after an interrupted or unwanted session change, and rolling back to a known revision | Any agent | `python examples/03-session-recovery/run_example.py` |
| **[04-conflict-detection](./04-conflict-detection/README.md)** | Automatically detecting two contradictory architectural decisions (`PostgreSQL` vs `MongoDB`) and resolving the conflict | `claude-code` & `cursor` | `python examples/04-conflict-detection/run_example.py` |

## Running All Examples at Once

```bash
python examples/01-claude-to-codex/run_example.py
python examples/02-cursor-to-antigravity/run_example.py
python examples/03-session-recovery/run_example.py
python examples/04-conflict-detection/run_example.py
```
