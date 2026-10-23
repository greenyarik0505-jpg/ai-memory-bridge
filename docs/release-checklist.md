# Release & Publication Checklist

Follow this checklist before publishing **AI Memory Bridge** to GitHub.

## 1. Pre-Publication Verification

- [x] Verify `skills/ai-memory-bridge/SKILL.md` frontmatter (`name: ai-memory-bridge`, `description`, `license: MIT`, `compatibility`).
- [x] Run unit test suite: `python -m unittest discover -s tests -v`
- [x] Run pytest suite: `pytest tests -v`
- [x] Run all 4 reproducible examples:
  - `python examples/01-claude-to-codex/run_example.py`
  - `python examples/02-cursor-to-antigravity/run_example.py`
  - `python examples/03-session-recovery/run_example.py`
  - `python examples/04-conflict-detection/run_example.py`
- [x] Run `npx skills add . --list` to verify Skills CLI discovery of `ai-memory-bridge`.
- [x] Confirm zero secrets, zero Russian/Cyrillic characters, and zero temporary test artifacts in tracked files.

## 2. Replace Placeholder GitHub Owner (`OWNER`)

Before pushing to your GitHub account, replace `greenyarik0505-jpg/ai-memory-bridge` with your actual GitHub username or organization in:
- `README.md`
- `docs/installation.md`
- `pyproject.toml`
- `CHANGELOG.md`
- `skills/ai-memory-bridge/assets/memory-schema.v1.json`

## 3. Create GitHub Repository & Push

```bash
git init
git add .
git commit -m "feat: initial release of AI Memory Bridge v1.0.0"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/ai-memory-bridge.git
git push -u origin main
git tag -a v1.0.0 -m "AI Memory Bridge v1.0.0"
git push origin v1.0.0
```

## 4. Configure GitHub Repository Settings

Add the recommended **GitHub Topics** in the repository's "About" settings:
- `agent-skills`
- `ai-agents`
- `agent-memory`
- `claude-code`
- `codex`
- `cursor`
- `antigravity`
- `context-management`
- `developer-tools`
- `python`

Set the repository description to:
> `One Memory. Every AI Agent. Local-first memory synchronization and seamless context handoff for AI coding agents.`

## 5. Post-Publish Verification

Test one-command installation from the live GitHub repository in a clean temporary directory:

```bash
npx skills add <YOUR_GITHUB_USERNAME>/ai-memory-bridge --list
npx skills add <YOUR_GITHUB_USERNAME>/ai-memory-bridge
```
