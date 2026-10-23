# Memory Format & Schema Specification (`v1.0.0`)

## `.ai-memory/` Directory Layout

```text
.ai-memory/
├── memory.json          # Canonical structured store (Schema v1.0.0)
├── context.md           # Auto-generated high-level project overview, goals, constraints, and summaries
├── decisions.md         # Auto-generated active, conflicted, and superseded architectural decisions
├── tasks.md             # Auto-generated immediate next steps, pending tasks, and completed tasks
├── handoffs/            # Structured agent-to-agent handoff packets
│   ├── handoff-codex.md
│   ├── handoff-cursor.md
│   └── handoff_20261023_150000_claude-code_to_codex.md
├── backups/             # Verified SHA-256 JSON snapshot bundles
│   └── backup_20261023_150000_000000_rev0003_manual.json
└── history/             # Append-only audit log and per-revision snapshots
    ├── events.jsonl
    ├── rev_00001.json
    ├── rev_00002.json
    └── rev_00003.json
```

---

## Entry Types (`type`)

Every entry in `memory.json` belongs to one of 9 universal types:

| Type Identifier | Section in Markdown Views | Purpose |
| :--- | :--- | :--- |
| `goal` | `context.md` | Core project objectives, target outcomes, and non-goals. |
| `decision` | `decisions.md` | Architectural, stack, data-model, or API design choices. |
| `task_done` | `tasks.md` | Completed features, milestones, or verified fixes. |
| `task_pending` | `tasks.md` | In-progress or queued tasks waiting to be completed. |
| `constraint` | `context.md` | Hard technical limits (e.g., Python 3.10+ stdlib only, offline-first). |
| `bug_fix` | `context.md` | Root cause of a resolved bug and how to avoid regressions. |
| `preference` | `context.md` | Developer workflow, style, or communication preferences. |
| `next_step` | `tasks.md` | Immediate actionable steps for the next agent session. |
| `session_summary` | `context.md` | High-level summary recorded at the end of a work session. |

---

## Entry Fields

Each object in `memory.json -> entries[]` contains:

```json
{
  "id": "mem_20261023150000_a1b2c3d4",
  "type": "decision",
  "title": "Primary Database Engine",
  "content": "Use PostgreSQL 16 with asyncpg and SQLAlchemy 2.0 for all transactional tables.",
  "source": "claude-code",
  "created_at": "2026-10-23T15:00:00Z",
  "updated_at": "2026-10-23T15:00:00Z",
  "status": "active",
  "priority": "high",
  "tags": ["database", "backend"],
  "supersedes": null,
  "superseded_by": null,
  "content_hash": "8f4b2c..."
}
```

### Status Lifecycle (`status`)
- `active`: Currently in force and included in context views, rule syncs, and handoff packets.
- `conflicted`: Flagged by `detect_conflicts_for_entry()` as contradicting another active entry on the same topic.
- `completed`: Used for tasks (`task_done` or completed `task_pending`).
- `superseded`: Replaced by a newer entry via `--supersedes <id>` or conflict resolution.
- `archived`: Rolled up during context compaction (`compact_memory()`).

### Priority Weights (`priority`)
1. `critical` (weight `4`): Never archived by compaction; always placed first in handoffs and rule snippets.
2. `high` (weight `3`): Core architectural decisions and active blockers.
3. `medium` (weight `2`): Default priority for standard tasks and notes.
4. `low` (weight `1`): Minor notes; first to be archived when token budgets are tight.

---

## Schema Migration

`memory_utils.py -> migrate_schema()` automatically upgrades older schema versions (`0.1.0`, `0.9.0`) to `1.0.0` on load by normalizing legacy `"task"` types into `"task_pending"` / `"task_done"`, computing missing `content_hash` values, and initializing missing `conflicts` and `metadata` blocks.
