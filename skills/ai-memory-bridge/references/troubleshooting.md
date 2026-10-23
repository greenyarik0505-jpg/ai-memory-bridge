# Troubleshooting & Recovery Runbook

## 1. Run Diagnostics First

Whenever an operation fails or behaves unexpectedly, run `doctor.py`:

```bash
python "<SKILL_DIR>/scripts/doctor.py" --workspace "."
```

`doctor.py` checks:
- Python version (`>= 3.10`)
- Skill bundle integrity (`SKILL.md` and all 8 scripts)
- Workspace write permissions and symlink safety
- `.gitignore` privacy protection for `.ai-memory/`
- `memory.json` schema validity (`v1.0.0`)
- Unresolved architectural or constraint conflicts
- Stored memory secret & prompt injection scan
- Backup checksum verification

---

## 2. Common Issues & Solutions

### Issue: `Memory store not initialized at '.ai-memory'. Run init.py first.`
- **Cause**: `.ai-memory/memory.json` does not exist yet in the current directory.
- **Fix**: Run `python "<SKILL_DIR>/scripts/init.py" --workspace "."` (or run `capture.py add`, which auto-initializes by default).

### Issue: `SecurityViolationError: Potential secret(s) detected in memory entry`
- **Cause**: The text passed to `capture.py` or `sync.py --import-markdown` matched an API key, token, password, or private key pattern.
- **Fix**: Remove the sensitive credential from the summary text (use placeholder names like `$OPENAI_API_KEY` or `process.env.DATABASE_URL`), or pass `--redact-secrets` to mask the secret automatically.

### Issue: `SecurityViolationError: Symbolic link detected and rejected`
- **Cause**: A file or directory inside `.ai-memory/` or a target rule file (`CLAUDE.md`, `AGENTS.md`) is a symlink.
- **Fix**: Replace the symlink with a regular file or directory inside the workspace.

### Issue: Unresolved Conflict Warning (`status: conflicted`)
- **Cause**: Two active `decision`, `constraint`, or `preference` entries share the same topic or specify mutually exclusive technologies (e.g., `PostgreSQL` vs `MongoDB`) without `--supersedes`.
- **Fix**:
  1. List conflicts: `python "<SKILL_DIR>/scripts/capture.py" list --workspace "." --status conflicted`
  2. Resolve by keeping the authoritative entry ID:
     ```bash
     python "<SKILL_DIR>/scripts/capture.py" resolve-conflict \
       --workspace "." \
       --conflict-id <CONFLICT_ID> \
       --keep <ENTRY_ID_TO_KEEP> \
       --note "Confirmed active architecture choice with user"
     ```

### Issue: Corrupted `memory.json` after manual editing
- **Cause**: Manual edits introduced syntax errors or invalid schema fields into `.ai-memory/memory.json`.
- **Fix**: Restore from the latest history revision snapshot in `.ai-memory/history/` or from `.ai-memory/backups/`:
  ```bash
  # Copy the latest valid history snapshot back if memory.json is unparseable
  python "<SKILL_DIR>/scripts/backup.py" list --workspace "."
  ```
