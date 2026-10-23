<div align="center">

# 🌉 AI Memory Bridge (`ai-memory-bridge`)

### **Єдина пам'ять. Будь-який ШІ-агент.**

**Локальна синхронізація пам'яті та безшовна передача контексту між ШІ-агентами для програмування.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../../LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent_Skill-SKILL.md_v1.0-blue.svg)](../../skills/ai-memory-bridge/SKILL.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](../../pyproject.toml)
[![Dependencies: Zero](https://img.shields.io/badge/Dependencies-Zero_(Stdlib_Only)-success.svg)](../../pyproject.toml)

**Працює з:** Claude Code · OpenAI Codex · Cursor · Google Antigravity · Gemini CLI · OpenCode · GitHub Copilot

🌐 **Мови:** [English](../../README.md) · [Русский](./README.ru.md) · **Українська** · [简体中文](./README.zh-CN.md) · [Español](./README.es.md)

</div>

---

## Навіщо потрібен AI Memory Bridge?

Під час розробки реальних проєктів рідко використовується лише один ШІ-агент: ви можете проєктувати архітектуру в **Claude Code**, делегувати фонові задачі в **OpenAI Codex**, допрацьовувати інтерфейс у **Cursor** та координувати мультиагентну перевірку в **Google Antigravity**.

**AI Memory Bridge** зберігає єдине локальне джерело істини в `.ai-memory/` за допомогою нативного **Agent Skill (`SKILL.md`)** та движка на Python 3.10+ без зовнішніх залежностей. Спілкуйтеся зі своїм агентом **будь-якою мовою** — агент сам запускає перевірені скрипти, блокує витік секретів, усуває дублікати, знаходить конфлікти та генерує пакет передачі (`handoff`).

---

## ⚡ Швидкий старт

### 1. Встановлення однією командою

```bash
npx skills add greenyarik0505-jpg/ai-memory-bridge
```

### 2. Спілкуйтеся з ШІ-агентом природною мовою

- **«Запам'ятай цей проєкт»** / **"Remember this project"** → Ініціалізує `.ai-memory/`, автоматично сканує стек проєкту (`scan.py`) та зберігає цілі й обмеження.
- **«Збережи наш прогрес»** / **"Save our progress"** → Зберігає виконані та поточні задачі, виправлення багів і наступні кроки в `.ai-memory/memory.json`.
- **«Підготуй передачу для Codex»** / **"Prepare a handoff for Codex"** → Генерує `.ai-memory/handoffs/handoff-codex.md` та безпечно оновлює `AGENTS.md`.
- **«Продовж з того місця, де зупинився Claude Code»** → Відновлює повний контекст проєкту без повторних пояснень.
- **«Відкрий панель пам'яті»** → Генерує інтерактивну офлайн-панель `.ai-memory/dashboard.html` з підтримкою української, російської, англійської, китайської, іспанської та німецької мов.

Повна документація доступна в [основному README.md](../../README.md).
