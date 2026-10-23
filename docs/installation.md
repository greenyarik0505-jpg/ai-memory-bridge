# Installation Guide

**AI Memory Bridge** is packaged as a standard **Agent Skill** (`skills/ai-memory-bridge/SKILL.md`). It requires **Python 3.10+** and uses only the Python standard library (zero third-party runtime dependencies).

---

## 1. One-Command Installation (Recommended via Skills CLI)

Once the repository is published to GitHub under your account (`greenyarik0505-jpg/ai-memory-bridge`), install it with a single command using the open-source Skills CLI:

```bash
npx skills add greenyarik0505-jpg/ai-memory-bridge
```

### Target Specific AI Agents or Global Scope

```bash
# Install for specific agents in the current project
npx skills add greenyarik0505-jpg/ai-memory-bridge --agent claude-code codex cursor

# Install globally for your user profile across all projects
npx skills add greenyarik0505-jpg/ai-memory-bridge -g

# Install from a local clone (works offline before publishing to GitHub)
npx skills add ./ai-memory-bridge --skill ai-memory-bridge
```

---

## 2. Manual Installation (Zero Node.js / `npx` Required)

If you do not use Node.js or prefer manual setup, copy `skills/ai-memory-bridge` directly into your agent's skills directory.

### Project-Scoped Manual Install (Recommended for Teams)

Clone the repository and copy the skill folder into your project's customization directory:

```bash
git clone https://github.com/greenyarik0505-jpg/ai-memory-bridge.git
```

| AI Agent | Target Directory in Your Project | Copy Command (macOS / Linux) | Copy Command (Windows PowerShell) |
| :--- | :--- | :--- | :--- |
| **Claude Code** | `.claude/skills/ai-memory-bridge/` | `mkdir -p .claude/skills && cp -R ai-memory-bridge/skills/ai-memory-bridge .claude/skills/` | `New-Item -ItemType Directory -Force .claude/skills; Copy-Item -Recurse ai-memory-bridge\skills\ai-memory-bridge .claude\skills\` |
| **OpenAI Codex** | `.codex/skills/ai-memory-bridge/` | `mkdir -p .codex/skills && cp -R ai-memory-bridge/skills/ai-memory-bridge .codex/skills/` | `New-Item -ItemType Directory -Force .codex/skills; Copy-Item -Recurse ai-memory-bridge\skills\ai-memory-bridge .codex\skills\` |
| **Cursor** | `.cursor/skills/ai-memory-bridge/` | `mkdir -p .cursor/skills && cp -R ai-memory-bridge/skills/ai-memory-bridge .cursor/skills/` | `New-Item -ItemType Directory -Force .cursor/skills; Copy-Item -Recurse ai-memory-bridge\skills\ai-memory-bridge .cursor\skills\` |
| **Google Antigravity** | `.agents/skills/ai-memory-bridge/` | `mkdir -p .agents/skills && cp -R ai-memory-bridge/skills/ai-memory-bridge .agents/skills/` | `New-Item -ItemType Directory -Force .agents/skills; Copy-Item -Recurse ai-memory-bridge\skills\ai-memory-bridge .agents\skills\` |
| **Gemini CLI** | `.agents/skills/ai-memory-bridge/` | `mkdir -p .agents/skills && cp -R ai-memory-bridge/skills/ai-memory-bridge .agents/skills/` | `New-Item -ItemType Directory -Force .agents/skills; Copy-Item -Recurse ai-memory-bridge\skills\ai-memory-bridge .agents\skills\` |
| **OpenCode** | `.opencode/skills/ai-memory-bridge/` | `mkdir -p .opencode/skills && cp -R ai-memory-bridge/skills/ai-memory-bridge .opencode/skills/` | `New-Item -ItemType Directory -Force .opencode/skills; Copy-Item -Recurse ai-memory-bridge\skills\ai-memory-bridge .opencode\skills\` |
| **GitHub Copilot** | `.github/skills/ai-memory-bridge/` | `mkdir -p .github/skills && cp -R ai-memory-bridge/skills/ai-memory-bridge .github/skills/` | `New-Item -ItemType Directory -Force .github/skills; Copy-Item -Recurse ai-memory-bridge\skills\ai-memory-bridge .github\skills\` |

### Global Manual Install (User Home Directory)

- **Claude Code**: `~/.claude/skills/ai-memory-bridge/`
- **OpenAI Codex**: `~/.codex/skills/ai-memory-bridge/`
- **Cursor**: `~/.cursor/skills/ai-memory-bridge/`
- **Google Antigravity**: `~/.gemini/config/skills/ai-memory-bridge/`
- **Gemini CLI**: `~/.gemini/skills/ai-memory-bridge/`
- **OpenCode**: `~/.config/opencode/skills/ai-memory-bridge/`

---

## 3. Verify Your Installation

Ask your AI coding agent:
> *"Run the AI Memory Bridge doctor check on this workspace."*

Or run the diagnostic script directly:

```bash
python .agents/skills/ai-memory-bridge/scripts/doctor.py --workspace .
```
