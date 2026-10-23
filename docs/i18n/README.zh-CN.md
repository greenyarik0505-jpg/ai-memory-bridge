<div align="center">

# 🌉 AI Memory Bridge (`ai-memory-bridge`)

### **统一记忆 · 适配所有 AI 编程代理**

**本地优先的项目记忆同步与跨 AI 编程代理无缝上下文交接技能（Agent Skill）。**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../../LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent_Skill-SKILL.md_v1.0-blue.svg)](../../skills/ai-memory-bridge/SKILL.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](../../pyproject.toml)
[![Dependencies: Zero](https://img.shields.io/badge/Dependencies-Zero_(Stdlib_Only)-success.svg)](../../pyproject.toml)

**支持代理：** Claude Code · OpenAI Codex · Cursor · Google Antigravity · Gemini CLI · OpenCode · GitHub Copilot

🌐 **语言：** [English](../../README.md) · [Русский](./README.ru.md) · [Українська](./README.uk.md) · **简体中文** · [Español](./README.es.md)

</div>

---

## 为什么选择 AI Memory Bridge？

在真实项目中，开发者往往同时使用多个 AI 编程工具：在 **Claude Code** 中设计架构，在 **OpenAI Codex** 中执行后台任务，在 **Cursor** 中打磨前端界面，并在 **Google Antigravity** 中进行多代理协同验证。

**AI Memory Bridge** 是一个遵循开放 `SKILL.md` 标准的原生 **Agent Skill**，底层基于零外部依赖的 Python 3.10+ 标准库引擎。您可以直接用**中文或任意语言**对 AI 代理下达自然语言指令，代理会自动调用本地脚本完成代码库扫描、密钥拦截、中文/多语言分词去重、架构冲突检测以及跨代理交接包生成。

---

## ⚡ 快速开始

### 1. 一键安装技能

```bash
npx skills add greenyarik0505-jpg/ai-memory-bridge
```

### 2. 使用自然语言与 AI 代理对话（无需手动输入命令行）

- **“记住这个项目”** / **"Remember this project"** → 初始化 `.ai-memory/`，1 秒自动扫描代码库技术栈与构建命令（`scan.py`），并记录核心目标与约束。
- **“保存当前进度”** / **"Save our progress"** → 提取已完成任务、待办事项、Bug 修复与下一步计划，自动拦截敏感密钥并写入 `.ai-memory/memory.json`。
- **“准备交接给 Codex”** / **"Prepare a handoff for Codex"** → 生成 `.ai-memory/handoffs/handoff-codex.md` 并无损更新 `AGENTS.md` 中的标记区块。
- **“从 Claude Code 停止的地方继续”** → 读取本地记忆并无缝接续开发。
- **“打开记忆面板”** → 生成支持中文界面的离线交互式面板 `.ai-memory/dashboard.html`。

完整英文文档请参见 [主 README.md](../../README.md)。
