# Example 3: Session Recovery & Version Rollback

## Scenario
After several productive sessions, an agent records an experimental architectural change that you decide to discard. Using **AI Memory Bridge**, you preview the diff with `--dry-run` and roll back cleanly to a verified checkpoint while automatically preserving a pre-restore safety backup.

## Conversational Prompts

> *"Create a memory backup before we experiment with the GraphQL migration."*
> *"Roll back our project memory to the pre-experiment backup."*

## Commands Executed by the Skill

```bash
# 1. Create a verified SHA-256 backup checkpoint
python skills/ai-memory-bridge/scripts/backup.py create --workspace . --label "pre-experiment"

# 2. Preview rollback before applying
python skills/ai-memory-bridge/scripts/restore.py --workspace . --backup <BACKUP_ID> --dry-run

# 3. Execute confirmed rollback (creates an automatic pre-restore safety snapshot)
python skills/ai-memory-bridge/scripts/restore.py --workspace . --backup <BACKUP_ID> --confirm
```

## Verifiable Output

Run the self-checking demonstration script:

```bash
python examples/03-session-recovery/run_example.py
```
