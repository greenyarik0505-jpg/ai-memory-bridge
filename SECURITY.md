# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :--- |
| `1.0.x` | :white_check_mark: Yes |

## Security Architecture Overview

**AI Memory Bridge** processes local project context that is loaded into AI coding agents. To protect developers and repositories, the project enforces:

1. **100% Local Execution**: No external network calls, cloud servers, or telemetry exist in the codebase.
2. **Secret Detection (`scan_for_secrets`)**: Blocks API keys (OpenAI, Anthropic, Google, AWS, Stripe), GitHub/Slack tokens, PEM private keys, and database credential URIs before saving to `.ai-memory/memory.json`.
3. **Indirect Prompt Injection Defense (`scan_for_prompt_injection`)**: Blocks instruction overrides, system role hijacks, hidden shell execution payloads, and boundary marker breakouts.
4. **Path Traversal & Symlink Defense (`safe_resolve_path`)**: Rejects paths resolving outside the workspace root, null bytes, and symbolic links anywhere in the resolution chain.
5. **Default `.gitignore` Protection**: Automatically adds `.ai-memory/` to `.gitignore` on workspace initialization.

## Reporting a Vulnerability

Please **do not** report security vulnerabilities (such as regex bypasses in secret detection, prompt-injection filter bypasses, or path traversal vectors) through public GitHub issues.

Instead, please report them privately via **GitHub Security Advisories** (`Security` tab -> `Report a vulnerability`) on the repository. Include:
- A minimal proof-of-concept input or script invocation.
- Affected operating system and Python version.
- Suggested remediation if available.

We aim to acknowledge reports within 48 hours and release a verified patch within 7 days.
