# Security Model & Threat Mitigation

AI Memory Bridge is designed with a strict local-first, defense-in-depth security model. Because project memory is injected into AI coding agent contexts, untrusted or unvalidated memory files could become vectors for secret leakage, path traversal, or indirect prompt injection.

---

## 1. Local-First Privacy & Gitignore Protection

- **100% Offline Execution**: No telemetry, cloud APIs, external databases, or network requests are ever made by any script in `ai-memory-bridge`.
- **Automatic `.gitignore` Guard**: `init.py` automatically adds `.ai-memory/` to the workspace's `.gitignore` so session history, internal paths, and work-in-progress notes are not accidentally pushed to public GitHub repositories.

---

## 2. Secret Detection & Prevention (`scan_for_secrets`)

Before any entry is saved (`capture.py add`, `capture.py import`, `sync.py --import-markdown`), `memory_utils.py` scans both the title and content against high-precision patterns:
- **OpenAI API Keys** (`sk-...`, `sk-proj-...`, `sk-svcacct-...`)
- **Anthropic API Keys** (`sk-ant-api03-...`)
- **GitHub Personal & Fine-Grained Tokens** (`ghp_...`, `gho_...`, `ghu_...`, `ghs_...`, `ghr_...`, `github_pat_...`)
- **AWS Access Key IDs** (`AKIA...`, `ASIA...`)
- **Google Cloud / Firebase API Keys** (`AIza...`)
- **Slack Tokens** (`xoxb-...`, `xoxp-...`, etc.)
- **Stripe Live & Test Secret Keys** (`sk_live_...`, `rk_live_...`)
- **PEM / OpenSSH / PGP Private Keys** (`-----BEGIN ... PRIVATE KEY-----`)
- **Database Connection Strings with Embedded Passwords** (`postgres://user:pass@host`, `mongodb+srv://...`, `redis://...`)
- **Generic High-Entropy Secret Assignments** (`api_key = "..."`, `password: "..."`, `client_secret = "..."`)

**Default Behavior**: Rejects the operation immediately with `SecurityViolationError` and exit code `1`. If `--redact-secrets` is explicitly passed, matches are replaced with `[REDACTED:<TYPE>]` before persistence.

---

## 3. Prompt Injection & Command Execution Defense (`scan_for_prompt_injection`)

Because handoff packets and rule files are read by LLMs, `memory_utils.py` blocks entries attempting to hijack agent instructions:
- **Instruction Overrides**: Blocks phrases like `"ignore all previous instructions"`, `"disregard system prompt"`, `"forget prior rules"`.
- **System Role Hijacking**: Blocks `<|im_start|>system`, `<system_instruction>`, `[SYSTEM OVERRIDE]`, and jailbreak mode declarations.
- **Hidden Command Directives**: Blocks `<!-- EXEC: ... -->`, `"run this shell command without asking"`, and pipe-to-shell payloads (`curl ... | sh`).
- **Exfiltration Directives**: Blocks instructions attempting to upload `.env`, SSH keys, or environment variables.
- **Boundary Escaping**: Strips null bytes and escapes `<!-- AI-MEMORY-BRIDGE:START -->` / `<!-- AI-MEMORY-BRIDGE:END -->` markers inside user text so an entry cannot break out of the managed markdown block.
- **Passive Data Framing**: Every generated markdown view and handoff packet includes an explicit security header instructing the receiving agent to treat all entries strictly as descriptive data and never execute embedded commands.

---

## 4. Path Traversal & Symbolic Link Protection (`safe_resolve_path`)

- All file operations validate that resolved target paths stay strictly inside the workspace root directory (`resolved.relative_to(workspace_root.resolve())`).
- Relative traversal sequences (`../../etc/passwd`, `..\Windows\System32`) outside the workspace root raise `SecurityViolationError`.
- `check_no_symlinks_in_chain()` inspects every path component from the target up to the workspace root and rejects symbolic links (`.is_symlink()`), preventing symlink-based arbitrary file overwrite attacks.

---

## 5. Atomic Writes, Dry-Run Previews, and Confirmation Gates

- **Atomic File Replacement**: `atomic_write_text()` writes to a temporary file in the same directory, flushes and `os.fsync()`s the file descriptor, and atomically replaces the target via `os.replace()`.
- **Pre-Restore Automatic Backups**: `restore.py` requires `--confirm` (or `--dry-run` for preview) and automatically creates a SHA-256 verified backup (`pre-restore-auto`) before rolling back `memory.json`.
