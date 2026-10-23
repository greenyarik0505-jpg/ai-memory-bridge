#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate an offline, zero-dependency HTML engineering dashboard at .ai-memory/dashboard.html.

Designed with a clean, restrained developer-tool aesthetic (Linear / Vercel / GitHub Primer style):
- Zero emojis; crisp 1.5px stroke inline SVG iconography
- Zinc/Carbon monochrome palette with semantic 6px status indicators
- Unified hairline metric strip + 2-column sidebar workspace layout
- Full multilingual localization (RU / EN / UK / ZH / ES / DE) and Dark/Light mode

Usage:
  python scripts/dashboard.py [--workspace .] [--out .ai-memory/dashboard.html] [--json]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from memory_utils import (  # noqa: E402
    ENTRY_TYPE_LABELS,
    MemoryBridgeError,
    atomic_write_text,
    detect_stale_file_references,
    estimate_tokens,
    get_current_git_branch,
    get_memory_paths,
    load_memory,
    safe_resolve_path,
    sort_entries_by_priority,
)

BACKTICK_CODE_RE = re.compile(r"`([^`\n]{1,120})`")

# Crisp 1.5px stroke inline SVGs
SVG_BRANCH = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"></line><circle cx="18" cy="6" r="3"></circle><circle cx="6" cy="18" r="3"></circle><path d="M18 9a9 9 0 0 1-9 9"></path></svg>'
SVG_SEARCH = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>'
SVG_COPY = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>'
SVG_FILE = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>'
SVG_TERMINAL = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>'
SVG_THEME_MOON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>'
SVG_THEME_SUN = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>'
SVG_LOGO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>'


def _format_escaped_content(raw_text: str) -> str:
    """HTML-escape text strictly, then wrap inline `code` spans in styled <code> tags."""
    escaped = html.escape(str(raw_text))
    return BACKTICK_CODE_RE.sub(r'<code class="inline-code">\1</code>', escaped)


def _read_recent_events(events_log: Path, limit: int = 25) -> list[dict[str, Any]]:
    if not events_log.exists() or events_log.is_symlink():
        return []
    lines = events_log.read_text(encoding="utf-8", errors="replace").splitlines()
    parsed: list[dict[str, Any]] = []
    for raw in reversed(lines[-limit:]):
        try:
            parsed.append(json.loads(raw))
        except Exception:
            continue
    return parsed


def _format_event_details(details: Any) -> str:
    """Convert raw audit event details dict into a clean, human-readable summary."""
    if not isinstance(details, dict) or not details:
        return "—"
    parts: list[str] = []
    if details.get("title"):
        parts.append(f"<span class='ev-title'>{html.escape(str(details['title']))}</span>")
    if details.get("type"):
        parts.append(f"<span class='mono-tag'>{html.escape(str(details['type']))}</span>")
    if details.get("entry_id"):
        parts.append(f"<code class='mono-id'>{html.escape(str(details['entry_id']))}</code>")
    if details.get("from_agent") and details.get("to_agent"):
        parts.append(
            f"<code class='mono-id'>{html.escape(str(details['from_agent']))}</code> &rarr; "
            f"<code class='mono-id'>{html.escape(str(details['to_agent']))}</code>"
        )
    if details.get("targets"):
        t_list = details["targets"]
        if isinstance(t_list, list):
            parts.append("targets: " + ", ".join(f"<code class='mono-id'>{html.escape(str(x))}</code>" for x in t_list))
    if details.get("conflicts"):
        c_list = details["conflicts"]
        if isinstance(c_list, list) and c_list:
            parts.append(f"conflicts: {len(c_list)}")
    if not parts:
        compact = ", ".join(f"{html.escape(str(k))}={html.escape(str(v))}" for k, v in list(details.items())[:3])
        return f"<code class='mono-id'>{compact}</code>"
    return " &middot; ".join(parts)


def render_dashboard_html(workspace_root: Path, data: dict[str, Any]) -> str:
    """Render a self-contained, XSS-safe, Linear/Vercel-inspired engineering dashboard."""
    paths = get_memory_paths(workspace_root)
    project = data.get("project", {})
    proj_name = html.escape(str(project.get("name", "Project")))
    rev = int(data.get("revision", 1))
    updated_at = html.escape(str(project.get("updated_at", ""))[:19].replace("T", " "))
    current_branch = html.escape(get_current_git_branch(workspace_root))

    all_entries = sort_entries_by_priority(data.get("entries", []), preferred_branch=current_branch)
    active_entries = [e for e in all_entries if e.get("status") in ("active", "conflicted")]
    decisions_count = len([e for e in active_entries if e.get("type") == "decision"])
    pending_count = len([e for e in active_entries if e.get("type") in ("task_pending", "next_step")])
    completed_count = len([e for e in all_entries if e.get("type") == "task_done" or e.get("status") == "completed"])
    unresolved_conflicts = [c for c in data.get("conflicts", []) if c.get("status") == "unresolved"]
    stale_refs = detect_stale_file_references(workspace_root, active_entries)
    recent_events = _read_recent_events(paths["events_log"], limit=20)

    active_blob = " ".join(f"{e.get('title', '')} {e.get('content', '')}" for e in active_entries)
    est_tokens = estimate_tokens(active_blob) if active_entries else 0
    token_pct = min(100, int(round((est_tokens / 2500.0) * 100))) if est_tokens else 0

    agents_set = sorted({str(e.get("source", "manual")) for e in all_entries if e.get("source")})
    agent_options_html = "".join(
        f'<option value="{html.escape(a)}">{html.escape(a)}</option>' for a in agents_set
    )

    cat_counts = {
        "goal": len([e for e in all_entries if e.get("type") == "goal"]),
        "decision": len([e for e in all_entries if e.get("type") == "decision"]),
        "task_pending": len([e for e in all_entries if e.get("type") == "task_pending"]),
        "task_done": completed_count,
        "next_step": len([e for e in all_entries if e.get("type") == "next_step"]),
        "constraint": len([e for e in all_entries if e.get("type") == "constraint"]),
        "bug_fix": len([e for e in all_entries if e.get("type") == "bug_fix"]),
        "preference": len([e for e in all_entries if e.get("type") == "preference"]),
        "session_summary": len([e for e in all_entries if e.get("type") == "session_summary"]),
    }

    conflict_html = ""
    if unresolved_conflicts:
        items_html = "".join(
            f"<li><code>{html.escape(c['id'])}</code> ({html.escape(c.get('topic', ''))}) &mdash; "
            f"{html.escape(c.get('reason', ''))}</li>"
            for c in unresolved_conflicts
        )
        conflict_html = f"""
        <div class="banner banner-danger">
          <div class="banner-head">
            <span class="dot dot-critical"></span>
            <span data-i18n="conflict_banner">Unresolved Architectural / Technical Conflicts</span> ({len(unresolved_conflicts)})
          </div>
          <ul>{items_html}</ul>
        </div>
        """

    stale_html = ""
    if stale_refs:
        s_items = "".join(
            f"<li><code>{html.escape(s['entry_id'])}</code> ({html.escape(s['title'])}) &mdash; "
            f"<code>{html.escape(', '.join(s['missing_files']))}</code></li>"
            for s in stale_refs
        )
        stale_html = f"""
        <div class="banner banner-warn">
          <div class="banner-head">
            <span class="dot dot-high"></span>
            <span data-i18n="stale_banner">Stale File References Detected</span> ({len(stale_refs)})
          </div>
          <ul>{s_items}</ul>
        </div>
        """

    cards_html_list: list[str] = []
    for entry in all_entries:
        eid = html.escape(str(entry.get("id", "")))
        etype = html.escape(str(entry.get("type", "decision")))
        type_label = html.escape(ENTRY_TYPE_LABELS.get(entry.get("type", ""), etype))
        title_escaped = html.escape(str(entry.get("title", "")))
        content_formatted = _format_escaped_content(str(entry.get("content", "")))
        source = html.escape(str(entry.get("source", "manual")))
        prio = html.escape(str(entry.get("priority", "medium")))
        status = html.escape(str(entry.get("status", "active")))
        branch = html.escape(str(entry.get("branch", "main")))
        updated = html.escape(str(entry.get("updated_at", ""))[:19].replace("T", " "))
        tags = [html.escape(str(t)) for t in entry.get("tags", [])]
        files = [html.escape(str(f)) for f in entry.get("files", [])]

        tags_html = "".join(f'<span class="tag-chip">#{t}</span>' for t in tags)
        files_html = "".join(f'<span class="file-chip">{SVG_FILE}<span>{f}</span></span>' for f in files)

        sup_html = ""
        if entry.get("supersedes"):
            sup_html += (
                f'<span class="meta-item"><span data-i18n="lbl_supersedes">Supersedes</span> '
                f'<code class="mono-id">{html.escape(str(entry["supersedes"]))}</code></span>'
            )
        if entry.get("superseded_by"):
            sup_html += (
                f'<span class="meta-item"><span data-i18n="lbl_superseded_by">Superseded by</span> '
                f'<code class="mono-id">{html.escape(str(entry["superseded_by"]))}</code></span>'
            )

        cards_html_list.append(
            f"""
            <article class="entry-row status-{status} prio-{prio}"
                     data-type="{etype}"
                     data-status="{status}"
                     data-prio="{prio}"
                     data-agent="{source}"
                     data-branch="{branch}">
              <div class="row-top">
                <div class="row-meta-left">
                  <span class="prio-pill prio-pill-{prio}">
                    <span class="dot dot-{prio}"></span>
                    <span data-i18n="prio_{prio}">{prio.upper()}</span>
                  </span>
                  <span class="type-pill" data-i18n="type_{etype}">{type_label}</span>
                  <span class="status-tag status-tag-{status}" data-i18n="status_{status}">{status.upper()}</span>
                </div>
                <div class="row-meta-right">
                  <span class="agent-chip" title="Source Agent">{source}</span>
                  <span class="branch-chip" title="Git Branch">{SVG_BRANCH}<span>{branch}</span></span>
                  <button class="id-btn" type="button" onclick="copyText('{eid}')" title="Copy ID">
                    <span>{eid}</span> {SVG_COPY}
                  </button>
                </div>
              </div>
              <h3 class="row-title">{title_escaped}</h3>
              <div class="row-body">{content_formatted}</div>
              <div class="row-bottom">
                <div class="chips-group">{files_html}{tags_html}{sup_html}</div>
                <time class="row-time"><span data-i18n="lbl_updated">Updated</span> {updated} UTC</time>
              </div>
            </article>
            """
        )

    empty_state_html = f"""
    <div class="empty-panel">
      <div class="empty-header">
        <div class="empty-icon-box">{SVG_TERMINAL}</div>
        <div>
          <h3 data-i18n="empty_title">Memory store initialized and empty</h3>
          <p data-i18n="empty_desc">
            0 entries in <code>.ai-memory/memory.json</code>. No synthetic or placeholder data is loaded.
            Send any of the following prompts to your AI coding agent to populate project context:
          </p>
        </div>
      </div>
      <div class="cmd-list">
        <div class="cmd-row" onclick="copyText(this.querySelector('.cmd-text').innerText)">
          <div class="cmd-left">
            <span class="cmd-tag" data-i18n="prompt_lbl_1">Capture</span>
            <code class="cmd-text" data-i18n="prompt_cmd_1">Save our progress</code>
          </div>
          <span class="cmd-copy">{SVG_COPY} <span data-i18n="btn_copy">Copy</span></span>
        </div>
        <div class="cmd-row" onclick="copyText(this.querySelector('.cmd-text').innerText)">
          <div class="cmd-left">
            <span class="cmd-tag" data-i18n="prompt_lbl_2">Bootstrap</span>
            <code class="cmd-text" data-i18n="prompt_cmd_2">Remember this project</code>
          </div>
          <span class="cmd-copy">{SVG_COPY} <span data-i18n="btn_copy">Copy</span></span>
        </div>
        <div class="cmd-row" onclick="copyText(this.querySelector('.cmd-text').innerText)">
          <div class="cmd-left">
            <span class="cmd-tag" data-i18n="prompt_lbl_3">Handoff</span>
            <code class="cmd-text" data-i18n="prompt_cmd_3">Prepare a handoff for Codex</code>
          </div>
          <span class="cmd-copy">{SVG_COPY} <span data-i18n="btn_copy">Copy</span></span>
        </div>
      </div>
    </div>
    """

    events_rows = "".join(
        f"""
        <tr>
          <td class="col-rev"><span class="mono-rev">#{html.escape(str(ev.get('revision', '')))}</span></td>
          <td><span class="action-chip" data-i18n="act_{html.escape(str(ev.get('action', '')))}">{html.escape(str(ev.get('action', '')))}</span></td>
          <td><span class="agent-chip">{html.escape(str(ev.get('agent', '')))}</span></td>
          <td class="col-details">{_format_event_details(ev.get('details', {}))}</td>
          <td class="col-time">{html.escape(str(ev.get('timestamp', ''))[:19].replace('T', ' '))} UTC</td>
        </tr>
        """
        for ev in recent_events
    )

    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Memory Bridge — {proj_name}</title>
  <style>
    :root {{
      --bg: #09090b;
      --panel: #111114;
      --panel-elevated: #16161a;
      --panel-hover: #1c1c21;
      --border: #222228;
      --border-subtle: #1a1a1f;
      --border-focus: #52525b;
      --text: #f4f4f5;
      --text-secondary: #a1a1aa;
      --muted: #71717a;
      --code-bg: #141418;
      --accent: #e4e4e7;
      --critical: #ef4444;
      --high: #f59e0b;
      --medium: #3b82f6;
      --low: #71717a;
      --ok: #10b981;
      --font-sans: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
      --font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    }}
    html[data-theme="light"] {{
      --bg: #fafafa;
      --panel: #ffffff;
      --panel-elevated: #f4f4f5;
      --panel-hover: #f4f4f5;
      --border: #e4e4e7;
      --border-subtle: #f0f0f2;
      --border-focus: #a1a1aa;
      --text: #09090b;
      --text-secondary: #3f3f46;
      --muted: #71717a;
      --code-bg: #f4f4f5;
      --accent: #18181b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--font-sans);
      background-color: var(--bg);
      color: var(--text);
      font-size: 13.5px;
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
      min-height: 100vh;
    }}

    /* Top Bar */
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 50;
      height: 52px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 1.5rem;
    }}
    .topbar-left {{
      display: flex;
      align-items: center;
      gap: 0.65rem;
    }}
    .logo-mark {{
      width: 26px;
      height: 26px;
      border-radius: 6px;
      background: var(--text);
      color: var(--bg);
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .breadcrumb {{
      display: flex;
      align-items: center;
      gap: 0.45rem;
      font-size: 13.5px;
    }}
    .bc-brand {{ color: var(--muted); font-weight: 500; }}
    .bc-sep {{ color: var(--border-focus); }}
    .bc-proj {{ color: var(--text); font-weight: 600; }}
    .status-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 11.5px;
      color: var(--text-secondary);
      background: var(--panel-elevated);
      border: 1px solid var(--border);
      padding: 0.15rem 0.55rem;
      border-radius: 4px;
      margin-left: 0.4rem;
    }}
    .topbar-right {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }}
    .meta-pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-family: var(--font-mono);
      font-size: 11.5px;
      color: var(--text-secondary);
      background: var(--panel-elevated);
      border: 1px solid var(--border);
      padding: 0.24rem 0.6rem;
      border-radius: 5px;
      font-variant-numeric: tabular-nums;
    }}
    .ctrl-select, .icon-btn {{
      background: var(--panel-elevated);
      border: 1px solid var(--border);
      color: var(--text);
      font-family: var(--font-sans);
      font-size: 12px;
      height: 28px;
      padding: 0 0.55rem;
      border-radius: 5px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: border-color 0.12s, background 0.12s;
    }}
    .ctrl-select:hover, .icon-btn:hover {{
      border-color: var(--border-focus);
      background: var(--panel-hover);
    }}

    /* Main Container */
    .shell {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 1.5rem;
    }}

    /* Unified Hairline Metric Strip (Vercel / Linear style) */
    .metric-strip {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 1.5rem;
    }}
    @media (max-width: 900px) {{
      .metric-strip {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    .metric-cell {{
      padding: 1rem 1.2rem;
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .metric-cell:last-child {{ border-right: none; }}
    .m-label {{
      font-size: 11px;
      font-weight: 500;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .m-value-row {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      margin-top: 0.4rem;
    }}
    .m-value {{
      font-size: 22px;
      font-weight: 600;
      color: var(--text);
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.02em;
    }}
    .m-sub {{
      font-size: 11.5px;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }}
    .meter-track {{
      height: 3px;
      width: 100%;
      background: var(--border);
      border-radius: 2px;
      margin-top: 0.55rem;
      overflow: hidden;
    }}
    .meter-fill {{
      height: 100%;
      background: var(--text);
    }}

    /* Workspace 2-Column Split */
    .workspace-grid {{
      display: grid;
      grid-template-columns: 230px 1fr;
      gap: 1.5rem;
      align-items: start;
    }}
    @media (max-width: 860px) {{
      .workspace-grid {{ grid-template-columns: 1fr; }}
    }}

    /* Sidebar Navigation */
    .sidebar {{
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }}
    .nav-group {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .nav-heading {{
      font-size: 11px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0 0.55rem 0.35rem;
    }}
    .filter-btn {{
      width: 100%;
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-secondary);
      padding: 0.38rem 0.6rem;
      border-radius: 6px;
      cursor: pointer;
      font-family: var(--font-sans);
      font-size: 12.5px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      text-align: left;
      transition: background 0.1s, color 0.1s;
    }}
    .filter-btn:hover {{
      background: var(--panel-elevated);
      color: var(--text);
    }}
    .filter-btn.active {{
      background: var(--panel-elevated);
      border-color: var(--border);
      color: var(--text);
      font-weight: 500;
    }}
    .nav-left {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }}
    .nav-count {{
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }}
    .sidebar-selects {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      padding-top: 0.5rem;
      border-top: 1px solid var(--border);
    }}
    .sidebar-selects .ctrl-select {{
      width: 100%;
      justify-content: space-between;
    }}

    /* Semantic 6px Dots */
    .dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      display: inline-block;
      flex-shrink: 0;
    }}
    .dot-ok {{ background: var(--ok); }}
    .dot-critical {{ background: var(--critical); }}
    .dot-high {{ background: var(--high); }}
    .dot-medium {{ background: var(--medium); }}
    .dot-low {{ background: var(--low); }}
    .dot-neutral {{ background: var(--muted); }}

    /* Banners */
    .banner {{
      border-radius: 6px;
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      border: 1px solid var(--border);
      background: var(--panel);
      font-size: 12.5px;
    }}
    .banner-danger {{ border-left: 3px solid var(--critical); }}
    .banner-warn {{ border-left: 3px solid var(--high); }}
    .banner-head {{
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 0.45rem;
      margin-bottom: 0.35rem;
    }}
    .banner ul {{ margin-left: 1.2rem; color: var(--text-secondary); }}

    /* Search Toolbar */
    .feed-toolbar {{
      display: flex;
      align-items: center;
      gap: 0.65rem;
      margin-bottom: 0.85rem;
    }}
    .search-box {{
      flex: 1;
      position: relative;
      display: flex;
      align-items: center;
    }}
    .search-icon {{
      position: absolute;
      left: 0.75rem;
      color: var(--muted);
      display: flex;
      pointer-events: none;
    }}
    .search-input {{
      width: 100%;
      height: 34px;
      background: var(--panel);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0 2.2rem 0 2.15rem;
      border-radius: 6px;
      font-family: var(--font-sans);
      font-size: 12.5px;
      outline: none;
      transition: border-color 0.12s;
    }}
    .search-input:focus {{ border-color: var(--border-focus); }}
    .kbd-hint {{
      position: absolute;
      right: 0.6rem;
      font-family: var(--font-mono);
      font-size: 10.5px;
      color: var(--muted);
      border: 1px solid var(--border);
      background: var(--panel-elevated);
      padding: 0.05rem 0.35rem;
      border-radius: 4px;
      pointer-events: none;
    }}

    /* Entry Rows */
    .entries-list {{
      display: flex;
      flex-direction: column;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }}
    .entry-row {{
      padding: 1rem 1.15rem;
      border-bottom: 1px solid var(--border);
      border-left: 2px solid transparent;
      transition: background 0.1s;
    }}
    .entry-row:last-child {{ border-bottom: none; }}
    .entry-row:hover {{ background: var(--panel-elevated); }}
    .entry-row.prio-critical {{ border-left-color: var(--critical); }}
    .entry-row.prio-high {{ border-left-color: var(--high); }}
    .entry-row.prio-medium {{ border-left-color: var(--medium); }}
    .entry-row.status-superseded, .entry-row.status-archived {{ opacity: 0.55; }}

    .row-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 0.4rem;
    }}
    .row-meta-left, .row-meta-right {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.4rem;
    }}
    .prio-pill, .type-pill, .status-tag, .agent-chip, .branch-chip {{
      display: inline-flex;
      align-items: center;
      gap: 0.32rem;
      font-size: 11px;
      font-weight: 500;
      padding: 0.1rem 0.45rem;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: var(--panel-elevated);
      color: var(--text-secondary);
    }}
    .agent-chip, .branch-chip {{
      font-family: var(--font-mono);
      font-size: 11px;
    }}
    .status-tag-conflicted {{
      border-color: rgba(239, 68, 68, 0.4);
      color: var(--critical);
    }}
    .status-tag-completed {{
      border-color: rgba(16, 185, 129, 0.4);
      color: var(--ok);
    }}
    .id-btn {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted);
      background: transparent;
      border: 1px solid transparent;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      cursor: pointer;
    }}
    .id-btn:hover {{
      border-color: var(--border);
      background: var(--code-bg);
      color: var(--text);
    }}
    .row-title {{
      font-size: 14px;
      font-weight: 600;
      color: var(--text);
      margin-bottom: 0.25rem;
    }}
    .row-body {{
      color: var(--text-secondary);
      font-size: 13px;
      white-space: pre-wrap;
      margin-bottom: 0.65rem;
    }}
    .inline-code {{
      font-family: var(--font-mono);
      font-size: 11.5px;
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 0.05rem 0.32rem;
      border-radius: 4px;
      color: var(--text);
    }}
    .row-bottom {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      font-size: 11.5px;
      color: var(--muted);
    }}
    .chips-group {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.4rem;
    }}
    .file-chip, .tag-chip {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-secondary);
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 0.08rem 0.4rem;
      border-radius: 4px;
    }}
    .row-time {{
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted);
    }}

    /* Clean Developer Empty State */
    .empty-panel {{
      padding: 1.75rem;
    }}
    .empty-header {{
      display: flex;
      align-items: flex-start;
      gap: 0.9rem;
      margin-bottom: 1.25rem;
    }}
    .empty-icon-box {{
      width: 32px;
      height: 32px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--panel-elevated);
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--text-secondary);
      flex-shrink: 0;
    }}
    .empty-header h3 {{
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 0.2rem;
    }}
    .empty-header p {{
      color: var(--muted);
      font-size: 12.5px;
    }}
    .empty-header code {{
      font-family: var(--font-mono);
      font-size: 11.5px;
      color: var(--text-secondary);
    }}
    .cmd-list {{
      display: flex;
      flex-direction: column;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
      background: var(--code-bg);
    }}
    .cmd-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.65rem 0.9rem;
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      transition: background 0.1s;
    }}
    .cmd-row:last-child {{ border-bottom: none; }}
    .cmd-row:hover {{ background: var(--panel-hover); }}
    .cmd-left {{
      display: flex;
      align-items: center;
      gap: 0.65rem;
    }}
    .cmd-tag {{
      font-size: 10.5px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      width: 72px;
    }}
    .cmd-text {{
      font-family: var(--font-mono);
      font-size: 12.5px;
      color: var(--text);
    }}
    .cmd-copy {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-size: 11px;
      color: var(--muted);
    }}

    /* Audit Log Section */
    .history-section {{
      margin-top: 2rem;
    }}
    .section-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.65rem;
    }}
    .section-head h2 {{
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
    }}
    .table-card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      text-align: left;
      padding: 0.6rem 0.95rem;
      border-bottom: 1px solid var(--border);
      font-size: 12.5px;
    }}
    th {{
      font-size: 11px;
      font-weight: 500;
      color: var(--muted);
      background: var(--panel-elevated);
    }}
    tr:last-child td {{ border-bottom: none; }}
    .mono-rev, .mono-id, .mono-tag {{
      font-family: var(--font-mono);
      font-size: 11.5px;
      color: var(--text-secondary);
    }}
    .action-chip {{
      font-family: var(--font-mono);
      font-size: 11px;
      padding: 0.1rem 0.4rem;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: var(--panel-elevated);
      color: var(--text);
    }}
    .col-time {{
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted);
      white-space: nowrap;
    }}

    /* Toast */
    #toast {{
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: var(--text);
      color: var(--bg);
      padding: 0.45rem 0.85rem;
      border-radius: 5px;
      font-size: 12px;
      font-weight: 500;
      opacity: 0;
      pointer-events: none;
      transform: translateY(6px);
      transition: all 0.15s;
      z-index: 200;
    }}
    #toast.show {{ opacity: 1; transform: translateY(0); }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-left">
      <div class="logo-mark">{SVG_LOGO}</div>
      <div class="breadcrumb">
        <span class="bc-brand">AI Memory Bridge</span>
        <span class="bc-sep">/</span>
        <span class="bc-proj">{proj_name}</span>
      </div>
      <span class="status-badge">
        <span class="dot dot-ok"></span>
        <span data-i18n="local_active">Local Store</span>
      </span>
    </div>
    <div class="topbar-right">
      <span class="meta-pill" title="Git Branch">{SVG_BRANCH}<span>{current_branch}</span></span>
      <span class="meta-pill"><span data-i18n="revision">rev</span> #{rev}</span>
      <select id="langSelect" class="ctrl-select" aria-label="Language">
        <option value="ru">RU &middot; Русский</option>
        <option value="en">EN &middot; English</option>
        <option value="uk">UK &middot; Українська</option>
        <option value="zh">ZH &middot; 中文</option>
        <option value="es">ES &middot; Español</option>
        <option value="de">DE &middot; Deutsch</option>
      </select>
      <button id="themeBtn" class="icon-btn" type="button" title="Toggle Theme">{SVG_THEME_MOON}</button>
    </div>
  </header>

  <div class="shell">
    <section class="metric-strip">
      <div class="metric-cell">
        <span class="m-label" data-i18n="kpi_active">Active Entries</span>
        <div class="m-value-row">
          <span class="m-value">{len(active_entries)}</span>
          <span class="m-sub"><span data-i18n="kpi_total_sub">total</span> {len(all_entries)}</span>
        </div>
      </div>
      <div class="metric-cell">
        <span class="m-label" data-i18n="kpi_decisions">Architecture Decisions</span>
        <div class="m-value-row">
          <span class="m-value">{decisions_count}</span>
          <span class="m-sub"><span data-i18n="kpi_constraints_sub">constraints</span> {cat_counts['constraint']}</span>
        </div>
      </div>
      <div class="metric-cell">
        <span class="m-label" data-i18n="kpi_pending">Open Tasks</span>
        <div class="m-value-row">
          <span class="m-value">{pending_count}</span>
          <span class="m-sub"><span data-i18n="kpi_done_sub">done</span> {completed_count}</span>
        </div>
      </div>
      <div class="metric-cell">
        <span class="m-label" data-i18n="kpi_tokens">Context Budget</span>
        <div class="m-value-row">
          <span class="m-value">{est_tokens}</span>
          <span class="m-sub">/ 2500 tok</span>
        </div>
        <div class="meter-track"><div class="meter-fill" style="width:{token_pct}%"></div></div>
      </div>
      <div class="metric-cell">
        <span class="m-label" data-i18n="kpi_conflicts">Conflicts &amp; Drift</span>
        <div class="m-value-row">
          <span class="m-value" style="color: {'var(--critical)' if (unresolved_conflicts or stale_refs) else 'var(--text)'}">
            {len(unresolved_conflicts) + len(stale_refs)}
          </span>
          <span class="m-sub"><span data-i18n="kpi_stale_sub">stale</span> {len(stale_refs)}</span>
        </div>
      </div>
    </section>

    {conflict_html}
    {stale_html}

    <div class="workspace-grid">
      <aside class="sidebar">
        <div class="nav-group">
          <div class="nav-heading" data-i18n="nav_views">Views</div>
          <button class="filter-btn active" data-filter="all">
            <span class="nav-left"><span class="dot dot-neutral"></span><span data-i18n="filter_all">All Entries</span></span>
            <span class="nav-count">{len(all_entries)}</span>
          </button>
          <button class="filter-btn" data-filter="active-only">
            <span class="nav-left"><span class="dot dot-ok"></span><span data-i18n="filter_active">Active Only</span></span>
            <span class="nav-count">{len(active_entries)}</span>
          </button>
        </div>

        <div class="nav-group">
          <div class="nav-heading" data-i18n="nav_categories">Categories</div>
          <button class="filter-btn" data-filter="goal">
            <span class="nav-left"><span class="dot dot-critical"></span><span data-i18n="filter_goal">Goals</span></span>
            <span class="nav-count">{cat_counts['goal']}</span>
          </button>
          <button class="filter-btn" data-filter="decision">
            <span class="nav-left"><span class="dot dot-medium"></span><span data-i18n="filter_decision">Decisions</span></span>
            <span class="nav-count">{cat_counts['decision']}</span>
          </button>
          <button class="filter-btn" data-filter="task_pending">
            <span class="nav-left"><span class="dot dot-high"></span><span data-i18n="filter_pending">Pending Tasks</span></span>
            <span class="nav-count">{cat_counts['task_pending']}</span>
          </button>
          <button class="filter-btn" data-filter="task_done">
            <span class="nav-left"><span class="dot dot-ok"></span><span data-i18n="filter_done">Completed</span></span>
            <span class="nav-count">{cat_counts['task_done']}</span>
          </button>
          <button class="filter-btn" data-filter="next_step">
            <span class="nav-left"><span class="dot dot-medium"></span><span data-i18n="filter_next">Next Steps</span></span>
            <span class="nav-count">{cat_counts['next_step']}</span>
          </button>
          <button class="filter-btn" data-filter="constraint">
            <span class="nav-left"><span class="dot dot-critical"></span><span data-i18n="filter_constraint">Constraints</span></span>
            <span class="nav-count">{cat_counts['constraint']}</span>
          </button>
          <button class="filter-btn" data-filter="bug_fix">
            <span class="nav-left"><span class="dot dot-ok"></span><span data-i18n="filter_bug">Bug Fixes</span></span>
            <span class="nav-count">{cat_counts['bug_fix']}</span>
          </button>
          <button class="filter-btn" data-filter="preference">
            <span class="nav-left"><span class="dot dot-neutral"></span><span data-i18n="filter_pref">Preferences</span></span>
            <span class="nav-count">{cat_counts['preference']}</span>
          </button>
        </div>

        <div class="sidebar-selects">
          <div class="nav-heading" data-i18n="nav_filters">Filters</div>
          <select id="agentSelect" class="ctrl-select" aria-label="Filter by Agent">
            <option value="all" data-i18n="all_agents">All Agents</option>
            {agent_options_html}
          </select>
          <select id="prioSelect" class="ctrl-select" aria-label="Filter by Priority">
            <option value="all" data-i18n="all_priorities">All Priorities</option>
            <option value="critical" data-i18n="prio_critical">CRITICAL</option>
            <option value="high" data-i18n="prio_high">HIGH</option>
            <option value="medium" data-i18n="prio_medium">MEDIUM</option>
            <option value="low" data-i18n="prio_low">LOW</option>
          </select>
        </div>
      </aside>

      <main>
        <div class="feed-toolbar">
          <div class="search-box">
            <span class="search-icon">{SVG_SEARCH}</span>
            <input type="text" id="searchInput" class="search-input" placeholder="Filter entries by title, content, file, or tag..." />
            <span class="kbd-hint">/</span>
          </div>
        </div>

        <div class="entries-list" id="entriesContainer">
          {"".join(cards_html_list) if cards_html_list else empty_state_html}
        </div>

        <section class="history-section">
          <div class="section-head">
            <h2 data-i18n="audit_title">Revision Log (.ai-memory/history/events.jsonl)</h2>
            <span class="mono-id"><span data-i18n="last_updated">Updated</span> {updated_at} UTC</span>
          </div>
          <div class="table-card">
            <table>
              <thead>
                <tr>
                  <th data-i18n="th_rev">Rev</th>
                  <th data-i18n="th_action">Event</th>
                  <th data-i18n="th_agent">Agent</th>
                  <th data-i18n="th_details">Change Summary</th>
                  <th data-i18n="th_time">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {events_rows if events_rows else '<tr><td colspan="5" style="text-align:center;color:var(--muted)" data-i18n="no_events">No revision events recorded.</td></tr>'}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  </div>

  <div id="toast">Copied</div>

  <script>
    const searchInput = document.getElementById('searchInput');
    const langSelect = document.getElementById('langSelect');
    const agentSelect = document.getElementById('agentSelect');
    const prioSelect = document.getElementById('prioSelect');
    const themeBtn = document.getElementById('themeBtn');
    const buttons = document.querySelectorAll('.filter-btn');
    const cards = document.querySelectorAll('.entry-row');
    let currentFilter = 'all';

    const ICON_MOON = `{SVG_THEME_MOON}`;
    const ICON_SUN = `{SVG_THEME_SUN}`;

    const I18N = {{
      en: {{
        local_active: "Local Store", revision: "rev", last_updated: "Updated",
        kpi_active: "Active Entries", kpi_total_sub: "total",
        kpi_decisions: "Architecture Decisions", kpi_constraints_sub: "constraints",
        kpi_pending: "Open Tasks", kpi_done_sub: "done",
        kpi_tokens: "Context Budget",
        kpi_conflicts: "Conflicts & Drift", kpi_stale_sub: "stale",
        nav_views: "Views", nav_categories: "Categories", nav_filters: "Filters",
        conflict_banner: "Unresolved Architectural / Technical Conflicts",
        stale_banner: "Stale File References Detected",
        search_placeholder: "Filter entries by title, content, file, or tag...",
        all_agents: "All Agents", all_priorities: "All Priorities",
        filter_all: "All Entries", filter_active: "Active Only", filter_goal: "Goals",
        filter_decision: "Decisions", filter_pending: "Pending Tasks", filter_done: "Completed",
        filter_next: "Next Steps", filter_constraint: "Constraints", filter_bug: "Bug Fixes", filter_pref: "Preferences",
        prio_critical: "CRITICAL", prio_high: "HIGH", prio_medium: "MEDIUM", prio_low: "LOW",
        type_goal: "Goal", type_decision: "Decision", type_constraint: "Constraint",
        type_preference: "Preference", type_task_pending: "Pending Task", type_task_done: "Completed Task",
        type_bug_fix: "Bug Fix", type_next_step: "Next Step", type_session_summary: "Session Summary",
        status_active: "ACTIVE", status_completed: "COMPLETED", status_superseded: "SUPERSEDED",
        status_conflicted: "CONFLICTED", status_archived: "ARCHIVED",
        lbl_updated: "Updated", lbl_supersedes: "Supersedes", lbl_superseded_by: "Superseded by",
        empty_title: "Memory store initialized and empty",
        empty_desc: "0 entries in .ai-memory/memory.json. No synthetic or placeholder data is loaded. Send any of the following prompts to your AI coding agent to populate project context:",
        prompt_lbl_1: "Capture", prompt_cmd_1: "Save our progress",
        prompt_lbl_2: "Bootstrap", prompt_cmd_2: "Remember this project",
        prompt_lbl_3: "Handoff", prompt_cmd_3: "Prepare a handoff for Codex",
        btn_copy: "Copy",
        audit_title: "Revision Log (.ai-memory/history/events.jsonl)",
        th_rev: "Rev", th_action: "Event", th_agent: "Agent", th_details: "Change Summary", th_time: "Timestamp",
        act_init: "init", act_capture_add: "capture.add", act_deduplicate_update: "deduplicate",
        act_complete_task: "task.complete", act_handoff: "handoff", act_sync: "sync",
        act_resolve_conflict: "conflict.resolve", act_restore: "restore",
        toast_copied: "Copied"
      }},
      ru: {{
        local_active: "Локальное хранилище", revision: "рев.", last_updated: "Обновлено",
        kpi_active: "Активные записи", kpi_total_sub: "всего",
        kpi_decisions: "Архитектурные решения", kpi_constraints_sub: "ограничений",
        kpi_pending: "Открытые задачи", kpi_done_sub: "закрыто",
        kpi_tokens: "Бюджет контекста",
        kpi_conflicts: "Конфликты и файлы", kpi_stale_sub: "устаревших",
        nav_views: "Обзор", nav_categories: "Категории", nav_filters: "Фильтры",
        conflict_banner: "Неразрешённые архитектурные и технические конфликты",
        stale_banner: "Ссылки на удалённые или перемещённые файлы",
        search_placeholder: "Фильтр по заголовку, тексту, файлу или тегу...",
        all_agents: "Все ИИ-агенты", all_priorities: "Все приоритеты",
        filter_all: "Все записи", filter_active: "Только активные", filter_goal: "Цели проекта",
        filter_decision: "Решения", filter_pending: "Задачи в работе", filter_done: "Выполненные",
        filter_next: "Следующие шаги", filter_constraint: "Ограничения", filter_bug: "Исправления", filter_pref: "Предпочтения",
        prio_critical: "КРИТИЧНЫЙ", prio_high: "ВЫСОКИЙ", prio_medium: "СРЕДНИЙ", prio_low: "НИЗКИЙ",
        type_goal: "Цель", type_decision: "Решение", type_constraint: "Ограничение",
        type_preference: "Предпочтение", type_task_pending: "В работе", type_task_done: "Выполнено",
        type_bug_fix: "Исправление", type_next_step: "След. шаг", type_session_summary: "Итог сессии",
        status_active: "АКТИВНО", status_completed: "ЗАВЕРШЕНО", status_superseded: "ЗАМЕНЕНО",
        status_conflicted: "КОНФЛИКТ", status_archived: "АРХИВ",
        lbl_updated: "Обновлено", lbl_supersedes: "Заменяет", lbl_superseded_by: "Заменено на",
        empty_title: "Хранилище инициализировано и пусто",
        empty_desc: "В .ai-memory/memory.json сейчас 0 записей. Никаких искусственных или дефолтных данных нет. Отправьте любую из команд своему ИИ-агенту для сохранения контекста:",
        prompt_lbl_1: "Прогресс", prompt_cmd_1: "Сохрани наш прогресс",
        prompt_lbl_2: "Анализ", prompt_cmd_2: "Запомни этот проект",
        prompt_lbl_3: "Передача", prompt_cmd_3: "Подготовь передачу для Codex",
        btn_copy: "Копировать",
        audit_title: "Журнал ревизий (.ai-memory/history/events.jsonl)",
        th_rev: "Рев.", th_action: "Событие", th_agent: "Агент", th_details: "Изменения", th_time: "Время",
        act_init: "инициализация", act_capture_add: "запись", act_deduplicate_update: "дедупликация",
        act_complete_task: "завершение", act_handoff: "передача", act_sync: "синхронизация",
        act_resolve_conflict: "решение конфликта", act_restore: "откат",
        toast_copied: "Скопировано"
      }},
      uk: {{
        local_active: "Локальне сховище", revision: "рев.", last_updated: "Оновлено",
        kpi_active: "Активні записи", kpi_total_sub: "усього",
        kpi_decisions: "Архітектурні рішення", kpi_constraints_sub: "обмежень",
        kpi_pending: "Відкриті задачі", kpi_done_sub: "закрито",
        kpi_tokens: "Бюджет контексту",
        kpi_conflicts: "Конфлікти та файли", kpi_stale_sub: "застарілих",
        nav_views: "Огляд", nav_categories: "Категорії", nav_filters: "Фільтри",
        search_placeholder: "Фільтр за заголовком, текстом, файлом або тегом...",
        all_agents: "Усі ШІ-агенти", all_priorities: "Усі пріоритети",
        filter_all: "Усі записи", filter_active: "Лише активні", filter_goal: "Цілі проєкту",
        filter_decision: "Рішення", filter_pending: "Задачі в роботі", filter_done: "Виконані",
        filter_next: "Наступні кроки", filter_constraint: "Обмеження", filter_bug: "Виправлення", filter_pref: "Уподобання",
        empty_title: "Сховище ініціалізовано та порожнє",
        empty_desc: "У .ai-memory/memory.json наразі 0 записів. Жодних фейкових або дефолтних даних немає. Надішліть команду своєму ШІ-агенту:",
        prompt_lbl_1: "Прогрес", prompt_cmd_1: "Збережи наш прогрес",
        prompt_lbl_2: "Аналіз", prompt_cmd_2: "Запам'ятай цей проєкт",
        prompt_lbl_3: "Передача", prompt_cmd_3: "Підготуй передачу для Codex",
        btn_copy: "Копіювати",
        audit_title: "Журнал ревізій (.ai-memory/history/events.jsonl)",
        th_rev: "Рев.", th_action: "Подія", th_agent: "Агент", th_details: "Зміни", th_time: "Час",
        toast_copied: "Скопійовано"
      }},
      zh: {{
        local_active: "本地存储", revision: "版本", last_updated: "更新于",
        kpi_active: "有效条目", kpi_total_sub: "总计",
        kpi_decisions: "架构决策", kpi_constraints_sub: "约束",
        kpi_pending: "待办任务", kpi_done_sub: "已完成",
        kpi_tokens: "上下文预算",
        kpi_conflicts: "冲突与漂移", kpi_stale_sub: "失效文件",
        nav_views: "视图", nav_categories: "分类", nav_filters: "筛选",
        search_placeholder: "按标题、内容、文件或标签过滤...",
        all_agents: "所有代理", all_priorities: "所有优先级",
        filter_all: "全部条目", filter_active: "仅有效", filter_goal: "项目目标",
        filter_decision: "架构决策", filter_pending: "待办任务", filter_done: "已完成",
        filter_next: "下一步", filter_constraint: "技术约束", filter_bug: "缺陷修复", filter_pref: "偏好设置",
        empty_title: "存储已初始化且为空",
        empty_desc: ".ai-memory/memory.json 中当前为 0 条记录（无任何默认虚构数据）。向您的 AI 代理发送以下指令即可开始记录：",
        prompt_lbl_1: "保存", prompt_cmd_1: "保存当前进度",
        prompt_lbl_2: "引导", prompt_cmd_2: "记住这个项目",
        prompt_lbl_3: "交接", prompt_cmd_3: "准备交接给 Codex",
        btn_copy: "复制",
        audit_title: "版本日志 (.ai-memory/history/events.jsonl)",
        th_rev: "版本", th_action: "事件", th_agent: "代理", th_details: "变更摘要", th_time: "时间",
        toast_copied: "已复制"
      }},
      es: {{
        local_active: "Almacén Local", revision: "rev", last_updated: "Actualizado",
        kpi_active: "Entradas Activas", kpi_total_sub: "total",
        kpi_decisions: "Decisiones", kpi_constraints_sub: "restricciones",
        kpi_pending: "Tareas Abiertas", kpi_done_sub: "hechas",
        kpi_tokens: "Presupuesto",
        kpi_conflicts: "Conflictos", kpi_stale_sub: "obsoletos",
        nav_views: "Vistas", nav_categories: "Categorías", nav_filters: "Filtros",
        search_placeholder: "Filtrar por título, contenido, archivo o etiqueta...",
        all_agents: "Todos los Agentes", all_priorities: "Todas las Prioridades",
        filter_all: "Todas", filter_active: "Solo Activas", filter_goal: "Objetivos",
        filter_decision: "Decisiones", filter_pending: "Pendientes", filter_done: "Completadas",
        filter_next: "Siguientes Pasos", filter_constraint: "Restricciones", filter_bug: "Errores", filter_pref: "Preferencias",
        empty_title: "Almacén inicializado y vacío",
        empty_desc: "0 entradas en .ai-memory/memory.json. Envía un comando a tu agente IA para empezar:",
        btn_copy: "Copiar",
        audit_title: "Registro de Revisiones (.ai-memory/history/events.jsonl)",
        toast_copied: "Copiado"
      }},
      de: {{
        local_active: "Lokaler Speicher", revision: "Rev", last_updated: "Aktualisiert",
        kpi_active: "Aktive Einträge", kpi_total_sub: "gesamt",
        kpi_decisions: "Entscheidungen", kpi_constraints_sub: "Regeln",
        kpi_pending: "Offene Aufgaben", kpi_done_sub: "erledigt",
        kpi_tokens: "Kontext-Budget",
        kpi_conflicts: "Konflikte", kpi_stale_sub: "veraltet",
        nav_views: "Ansichten", nav_categories: "Kategorien", nav_filters: "Filter",
        search_placeholder: "Nach Titel, Inhalt, Datei oder Tag filtern...",
        all_agents: "Alle Agenten", all_priorities: "Alle Prioritäten",
        filter_all: "Alle Einträge", filter_active: "Nur Aktive", filter_goal: "Ziele",
        filter_decision: "Entscheidungen", filter_pending: "Offene Aufgaben", filter_done: "Erledigt",
        filter_next: "Nächste Schritte", filter_constraint: "Einschränkungen", filter_bug: "Bugfixes", filter_pref: "Präferenzen",
        empty_title: "Speicher initialisiert und leer",
        empty_desc: "0 Einträge in .ai-memory/memory.json. Senden Sie einen Befehl an Ihren KI-Agenten:",
        btn_copy: "Kopieren",
        audit_title: "Versionsprotokoll (.ai-memory/history/events.jsonl)",
        toast_copied: "Kopiert"
      }}
    }};

    let currentLang = 'ru';

    function setLanguage(lang) {{
      currentLang = I18N[lang] ? lang : 'en';
      const dict = {{ ...I18N.en, ...I18N[currentLang] }};
      document.documentElement.lang = currentLang;
      document.querySelectorAll('[data-i18n]').forEach(el => {{
        const key = el.getAttribute('data-i18n');
        if (dict[key]) el.textContent = dict[key];
      }});
      if (dict.search_placeholder) {{
        searchInput.placeholder = dict.search_placeholder;
      }}
      try {{ localStorage.setItem('ai_memory_bridge_lang', currentLang); }} catch (e) {{}}
    }}

    function copyText(text) {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text);
      }}
      const toast = document.getElementById('toast');
      const dict = {{ ...I18N.en, ...I18N[currentLang] }};
      toast.textContent = (dict.toast_copied || 'Copied') + ': ' + text;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 1800);
    }}

    function setTheme(theme) {{
      document.documentElement.setAttribute('data-theme', theme);
      themeBtn.innerHTML = theme === 'light' ? ICON_SUN : ICON_MOON;
      try {{ localStorage.setItem('ai_memory_bridge_theme', theme); }} catch (e) {{}}
    }}
    themeBtn.addEventListener('click', () => {{
      const cur = document.documentElement.getAttribute('data-theme') || 'dark';
      setTheme(cur === 'dark' ? 'light' : 'dark');
    }});
    const savedTheme = (() => {{
      try {{ return localStorage.getItem('ai_memory_bridge_theme'); }} catch (e) {{ return null; }}
    }})();
    if (savedTheme) setTheme(savedTheme);

    langSelect.addEventListener('change', (e) => setLanguage(e.target.value));
    const savedLang = (() => {{
      try {{ return localStorage.getItem('ai_memory_bridge_lang'); }} catch (e) {{ return null; }}
    }})();
    const browserLang = (navigator.language || 'ru').slice(0, 2).toLowerCase();
    const initialLang = savedLang || (I18N[browserLang] ? browserLang : 'ru');
    langSelect.value = initialLang;
    setLanguage(initialLang);

    function applyFilters() {{
      const q = searchInput.value.toLowerCase().trim();
      const selectedAgent = agentSelect.value;
      const selectedPrio = prioSelect.value;

      cards.forEach(card => {{
        const type = card.getAttribute('data-type');
        const status = card.getAttribute('data-status');
        const agent = card.getAttribute('data-agent');
        const prio = card.getAttribute('data-prio');
        const text = card.innerText.toLowerCase();

        const matchesQuery = !q || text.includes(q);
        const matchesAgent = (selectedAgent === 'all') || (agent === selectedAgent);
        const matchesPrio = (selectedPrio === 'all') || (prio === selectedPrio);

        let matchesType = true;
        if (currentFilter === 'active-only') {{
          matchesType = (status === 'active' || status === 'conflicted');
        }} else if (currentFilter !== 'all') {{
          matchesType = (type === currentFilter);
        }}
        card.style.display = (matchesQuery && matchesType && matchesAgent && matchesPrio) ? 'block' : 'none';
      }});
    }}

    searchInput.addEventListener('input', applyFilters);
    agentSelect.addEventListener('change', applyFilters);
    prioSelect.addEventListener('change', applyFilters);
    buttons.forEach(btn => {{
      btn.addEventListener('click', () => {{
        buttons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.getAttribute('data-filter');
        applyFilters();
      }});
    }});

    document.addEventListener('keydown', (e) => {{
      if (e.key === '/' && document.activeElement !== searchInput) {{
        e.preventDefault();
        searchInput.focus();
      }}
    }});
  </script>
</body>
</html>
"""


def generate_dashboard(
    workspace_root: Path,
    out_rel_path: str | None = None,
) -> dict[str, Any]:
    """Generate .ai-memory/dashboard.html from current memory.json."""
    workspace_root = workspace_root.resolve()
    paths = get_memory_paths(workspace_root)
    data = load_memory(workspace_root)
    target_path = (
        safe_resolve_path(workspace_root, out_rel_path)
        if out_rel_path
        else paths["dashboard_html"]
    )
    html_doc = render_dashboard_html(workspace_root, data)
    atomic_write_text(target_path, html_doc)
    return {
        "status": "generated",
        "dashboard_path": str(target_path),
        "revision": data.get("revision", 1),
        "entry_count": len(data.get("entries", [])),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an offline interactive HTML dashboard for AI Memory Bridge."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root directory.")
    parser.add_argument("--out", default=None, help="Optional relative output path (default: .ai-memory/dashboard.html).")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    args = parser.parse_args(argv)

    try:
        res = generate_dashboard(Path(args.workspace), out_rel_path=args.out)
    except MemoryBridgeError as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"Dashboard generated: {res['dashboard_path']} (rev {res['revision']}, {res['entry_count']} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
