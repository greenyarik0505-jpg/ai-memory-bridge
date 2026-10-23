# Multi-Agent Compatibility Matrix & Integration Guide

AI Memory Bridge is tested and designed to work across major AI coding agents supporting the open **Agent Skills (`SKILL.md`)** specification and workspace rule files.

## Compatibility Matrix

| AI Agent | Support Tier | Skill Discovery Path (Project / Global) | Rule / Context Sync Target | Lifecycle Hooks Support | Context Handoff Support |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Claude Code** | **Full** | `.claude/skills/ai-memory-bridge/SKILL.md`<br>`~/.claude/skills/ai-memory-bridge/SKILL.md` | `CLAUDE.md` (bounded block) | Yes (`.claude/settings.json`: `SessionStart`, `Stop`) | Full (`handoff-claude-code.md` + `CLAUDE.md`) |
| **OpenAI Codex** | **Full** | `.codex/skills/ai-memory-bridge/SKILL.md`<br>`~/.codex/skills/ai-memory-bridge/SKILL.md` | `AGENTS.md` (bounded block) | Conversational / Manual (no local hook config in CLI) | Full (`handoff-codex.md` + `AGENTS.md`) |
| **Cursor** | **Full** | `.cursor/skills/ai-memory-bridge/SKILL.md`<br>`.agents/skills/ai-memory-bridge/SKILL.md` | `.cursor/rules/ai-memory-bridge.mdc` (dedicated `.mdc`) | Conversational / Manual | Full (`handoff-cursor.md` + `.mdc` rule) |
| **Google Antigravity** | **Full** | `.agents/skills/ai-memory-bridge/SKILL.md`<br>`~/.gemini/config/skills/ai-memory-bridge/SKILL.md` | `.agents/rules/ai-memory-bridge.md` (dedicated rule) | Yes (`.agents/hooks.json`: `SessionStart`, `Stop`) | Full (`handoff-antigravity.md` + `.agents/rules/`) |
| **Gemini CLI** | **Full** | `.agents/skills/ai-memory-bridge/SKILL.md`<br>`~/.gemini/skills/ai-memory-bridge/SKILL.md` | `GEMINI.md` (bounded block) | Conversational / Manual | Full (`handoff-gemini-cli.md` + `GEMINI.md`) |
| **OpenCode** | **Supported** | `.opencode/skills/ai-memory-bridge/SKILL.md`<br>`~/.config/opencode/skills/ai-memory-bridge/SKILL.md` | `AGENTS.md` (bounded block) | Conversational / Manual | Full (`handoff-opencode.md` + `AGENTS.md`) |
| **GitHub Copilot** | **Partial** | `.github/skills/ai-memory-bridge/SKILL.md`<br>`~/.copilot/skills/ai-memory-bridge/SKILL.md` | `.github/instructions/ai-memory-bridge.instructions.md` | Not supported | Rule sync + Handoff packet (requires VS Code Agent Mode for script execution) |

---

## Agent-Specific Details

### 1. Claude Code (`claude-code`)
- **Skill Activation**: Automatically reads `.claude/skills/ai-memory-bridge/SKILL.md` description at startup and loads the full skill on memory/handoff prompts.
- **Rule Synchronization**: `sync.py` and `handoff.py` update `CLAUDE.md` using `<!-- AI-MEMORY-BRIDGE:START -->` and `<!-- AI-MEMORY-BRIDGE:END -->` markers so existing instructions in `CLAUDE.md` remain untouched.
- **Opt-In Hooks**: Running `python scripts/init.py --enable-hooks --agent claude-code` adds `SessionStart` and `Stop` hooks to `.claude/settings.json`.

### 2. OpenAI Codex (`codex`)
- **Skill Activation**: Discovers `.codex/skills/ai-memory-bridge/SKILL.md` or `.agents/skills/ai-memory-bridge/SKILL.md`.
- **Rule Synchronization**: Codex natively loads `AGENTS.md` from the repository root. AI Memory Bridge maintains a bounded memory summary block inside `AGENTS.md` and writes detailed handoffs to `.ai-memory/handoffs/handoff-codex.md`.

### 3. Cursor (`cursor`)
- **Skill Activation**: Cursor Agent mode supports `.cursor/skills/ai-memory-bridge/SKILL.md` and `.agents/skills/ai-memory-bridge/SKILL.md`.
- **Rule Synchronization**: Writes a dedicated `.cursor/rules/ai-memory-bridge.mdc` file with `alwaysApply: true` YAML frontmatter. It never modifies or overwrites any other `.mdc` files in `.cursor/rules/`.

### 4. Google Antigravity (`antigravity`)
- **Skill Activation**: Discovers `.agents/skills/ai-memory-bridge/SKILL.md` in the workspace or `~/.gemini/config/skills/ai-memory-bridge/SKILL.md` globally.
- **Rule Synchronization**: Writes a dedicated `.agents/rules/ai-memory-bridge.md` rule file automatically discovered by Antigravity's hierarchical rule loader.
- **Opt-In Hooks**: Running `python scripts/init.py --enable-hooks --agent antigravity` configures `.agents/hooks.json` with `SessionStart` (`injectSteps` system message) and `Stop` handlers following the Antigravity hooks contract.

### 5. Gemini CLI (`gemini-cli`)
- **Skill Activation**: Discovers `.agents/skills/ai-memory-bridge/SKILL.md` or `~/.gemini/skills/ai-memory-bridge/SKILL.md`.
- **Rule Synchronization**: Updates `GEMINI.md` via bounded markers.

### 6. OpenCode (`opencode`)
- **Skill Activation**: Discovers `.opencode/skills/ai-memory-bridge/SKILL.md` (and falls back to `.claude/skills/` or `.agents/skills/`).
- **Rule Synchronization**: Shares the bounded block in `AGENTS.md`.

### 7. GitHub Copilot (`github-copilot`)
- **Why Partial Support**: GitHub Copilot supports `.github/instructions/*.instructions.md` across IDEs and `.github/skills/` in VS Code Agent Mode, but inline completions and non-agent chat views cannot execute local Python scripts autonomously. In VS Code Copilot Agent Mode (with terminal tool access enabled), Copilot can run the skill scripts directly.
