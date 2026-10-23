#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate an interactive, zero-dependency, offline HTML dashboard at .ai-memory/dashboard.html.

Visualizes project memory entries, agent attributions, active branches, supersede chains,
token budget utilization, unresolved conflicts, and revision audit history with full
multilingual UI translation (EN / RU / UK / ZH / ES / DE) and Dark/Light theme support.

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
        parts.append(f"“{html.escape(str(details['title']))}”")
    if details.get("type"):
        parts.append(f"<span class='chip-mini'>{html.escape(str(details['type']))}</span>")
    if details.get("entry_id"):
        parts.append(f"<code>{html.escape(str(details['entry_id']))}</code>")
    if details.get("from_agent") and details.get("to_agent"):
        parts.append(
            f"<code>{html.escape(str(details['from_agent']))}</code> → "
            f"<code>{html.escape(str(details['to_agent']))}</code>"
        )
    if details.get("targets"):
        t_list = details["targets"]
        if isinstance(t_list, list):
            parts.append("targets: " + ", ".join(f"<code>{html.escape(str(x))}</code>" for x in t_list))
    if details.get("conflicts"):
        c_list = details["conflicts"]
        if isinstance(c_list, list) and c_list:
            parts.append(f"⚠️ conflicts: {len(c_list)}")
    if not parts:
        compact = ", ".join(f"{html.escape(str(k))}={html.escape(str(v))}" for k, v in list(details.items())[:3])
        return f"<code>{compact}</code>"
    return " · ".join(parts)


def render_dashboard_html(workspace_root: Path, data: dict[str, Any]) -> str:
    """Render a self-contained, XSS-safe, interactive HTML dashboard for project memory."""
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

    # Collect unique agents for agent filter dropdown
    agents_set = sorted({str(e.get("source", "manual")) for e in all_entries if e.get("source")})
    agent_options_html = "".join(
        f'<option value="{html.escape(a)}">🤖 {html.escape(a)}</option>' for a in agents_set
    )

    # Category breakdown counts for visual bar
    cat_counts = {
        "goal": len([e for e in active_entries if e.get("type") == "goal"]),
        "decision": decisions_count,
        "task_pending": pending_count,
        "task_done": completed_count,
        "constraint": len([e for e in active_entries if e.get("type") == "constraint"]),
        "bug_fix": len([e for e in active_entries if e.get("type") == "bug_fix"]),
    }
    total_cat = max(1, sum(cat_counts.values()))

    # Render conflict banner if any
    conflict_html = ""
    if unresolved_conflicts:
        items_html = "".join(
            f"<li><strong>{html.escape(c['id'])}</strong> ({html.escape(c.get('topic', ''))}): "
            f"{html.escape(c.get('reason', ''))}</li>"
            for c in unresolved_conflicts
        )
        conflict_html = f"""
        <div class="alert alert-conflict">
          <div class="alert-title">⚠️ <span data-i18n="conflict_banner">Unresolved Architectural / Technical Conflicts</span> ({len(unresolved_conflicts)})</div>
          <ul>{items_html}</ul>
        </div>
        """

    stale_html = ""
    if stale_refs:
        s_items = "".join(
            f"<li><code>{html.escape(s['entry_id'])}</code> ({html.escape(s['title'])}) — "
            f"<code>{html.escape(', '.join(s['missing_files']))}</code></li>"
            for s in stale_refs
        )
        stale_html = f"""
        <div class="alert alert-stale">
          <div class="alert-title">🔍 <span data-i18n="stale_banner">Stale File References Detected</span> ({len(stale_refs)})</div>
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

        tags_html = "".join(f'<span class="tag">#{t}</span>' for t in tags)
        files_html = "".join(f'<span class="file-chip">📄 {f}</span>' for f in files)

        sup_html = ""
        if entry.get("supersedes"):
            sup_html += (
                f'<span class="meta-link"><span data-i18n="lbl_supersedes">Supersedes</span>: '
                f'<code>{html.escape(str(entry["supersedes"]))}</code></span>'
            )
        if entry.get("superseded_by"):
            sup_html += (
                f'<span class="meta-link"><span data-i18n="lbl_superseded_by">Superseded by</span>: '
                f'<code>{html.escape(str(entry["superseded_by"]))}</code></span>'
            )

        cards_html_list.append(
            f"""
            <article class="entry-card status-{status} prio-{prio}"
                     data-type="{etype}"
                     data-status="{status}"
                     data-prio="{prio}"
                     data-agent="{source}"
                     data-branch="{branch}">
              <div class="card-header">
                <div class="badges">
                  <span class="badge badge-prio-{prio}" data-i18n="prio_{prio}">{prio.upper()}</span>
                  <span class="badge badge-type" data-i18n="type_{etype}">{type_label}</span>
                  <span class="badge badge-status-{status}" data-i18n="status_{status}">{status.upper()}</span>
                  <span class="badge badge-agent" title="Source AI Agent">🤖 {source}</span>
                  <span class="badge badge-branch" title="Git Branch">🌿 {branch}</span>
                </div>
                <div class="card-actions">
                  <button class="copy-btn" onclick="copyText('{eid}')" title="Copy Entry ID">
                    <code>{eid}</code> 📋
                  </button>
                </div>
              </div>
              <h3 class="card-title">{title_escaped}</h3>
              <p class="card-content">{content_formatted}</p>
              <div class="card-footer">
                <div class="tags-wrap">{files_html} {tags_html} {sup_html}</div>
                <span class="timestamp"><span data-i18n="lbl_updated">Updated</span>: {updated} UTC</span>
              </div>
            </article>
            """
        )

    empty_state_html = """
    <div class="empty-onboarding">
      <div class="empty-icon">🧠</div>
      <h3 data-i18n="empty_title">Project Memory Store is Ready &amp; Clean</h3>
      <p data-i18n="empty_desc">
        No memory entries have been recorded yet. There is no fake or placeholder data—entries appear here
        automatically as soon as you ask your AI coding agent to save project context or progress.
      </p>
      <div class="prompt-grid">
        <div class="prompt-box" onclick="copyText(this.querySelector('.p-cmd').innerText)">
          <span class="p-label" data-i18n="prompt_lbl_1">Save Progress</span>
          <code class="p-cmd" data-i18n="prompt_cmd_1">Save our progress</code>
        </div>
        <div class="prompt-box" onclick="copyText(this.querySelector('.p-cmd').innerText)">
          <span class="p-label" data-i18n="prompt_lbl_2">Auto-Scan Project</span>
          <code class="p-cmd" data-i18n="prompt_cmd_2">Remember this project</code>
        </div>
        <div class="prompt-box" onclick="copyText(this.querySelector('.p-cmd').innerText)">
          <span class="p-label" data-i18n="prompt_lbl_3">Agent Handoff</span>
          <code class="p-cmd" data-i18n="prompt_cmd_3">Prepare a handoff for Codex</code>
        </div>
      </div>
    </div>
    """

    events_rows = "".join(
        f"""
        <tr>
          <td><span class="rev-pill">#{html.escape(str(ev.get('revision', '')))}</span></td>
          <td><span class="badge badge-type" data-i18n="act_{html.escape(str(ev.get('action', '')))}">{html.escape(str(ev.get('action', '')))}</span></td>
          <td><span class="badge badge-agent">🤖 {html.escape(str(ev.get('agent', '')))}</span></td>
          <td class="td-details">{_format_event_details(ev.get('details', {}))}</td>
          <td class="td-time">{html.escape(str(ev.get('timestamp', ''))[:19].replace('T', ' '))} UTC</td>
        </tr>
        """
        for ev in recent_events
    )

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Memory Bridge Dashboard — {proj_name}</title>
  <style>
    :root {{
      --bg: #070a12;
      --bg-glow: radial-gradient(circle at 15% 10%, rgba(56, 189, 248, 0.10), transparent 40%),
                 radial-gradient(circle at 85% 15%, rgba(99, 102, 241, 0.10), transparent 40%);
      --surface: rgba(17, 24, 39, 0.82);
      --surface-solid: #111827;
      --surface-hover: rgba(30, 41, 59, 0.92);
      --border: rgba(255, 255, 255, 0.08);
      --border-strong: rgba(56, 189, 248, 0.35);
      --text: #f8fafc;
      --text-secondary: #cbd5e1;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-indigo: #818cf8;
      --critical: #f43f5e;
      --high: #f59e0b;
      --medium: #3b82f6;
      --low: #64748b;
      --ok: #10b981;
      --code-bg: rgba(15, 23, 42, 0.9);
      --shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }}
    html[data-theme="light"] {{
      --bg: #f8fafc;
      --bg-glow: radial-gradient(circle at 15% 10%, rgba(56, 189, 248, 0.12), transparent 40%),
                 radial-gradient(circle at 85% 15%, rgba(99, 102, 241, 0.08), transparent 40%);
      --surface: rgba(255, 255, 255, 0.92);
      --surface-solid: #ffffff;
      --surface-hover: #f1f5f9;
      --border: rgba(15, 23, 42, 0.10);
      --border-strong: rgba(2, 132, 199, 0.45);
      --text: #0f172a;
      --text-secondary: #334155;
      --muted: #64748b;
      --accent: #0284c7;
      --accent-indigo: #4f46e5;
      --code-bg: #f1f5f9;
      --shadow: 0 8px 24px -8px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg);
      background-image: var(--bg-glow);
      background-attachment: fixed;
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1.5rem 4rem;
      min-height: 100vh;
    }}
    .container {{ max-width: 1220px; margin: 0 auto; }}

    /* Top Header */
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1.25rem;
      padding: 1.35rem 1.6rem;
      background: var(--surface);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 16px;
      margin-bottom: 1.5rem;
      box-shadow: var(--shadow);
    }}
    .brand-row {{ display: flex; align-items: center; gap: 0.9rem; }}
    .brand-logo {{
      width: 44px; height: 44px;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--accent), var(--accent-indigo));
      display: flex; align-items: center; justify-content: center;
      font-size: 1.45rem;
      box-shadow: 0 4px 14px rgba(56, 189, 248, 0.3);
    }}
    header h1 {{ font-size: 1.45rem; font-weight: 700; letter-spacing: -0.02em; }}
    header .subtitle {{ color: var(--muted); font-size: 0.88rem; margin-top: 0.15rem; }}
    .header-right {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 0.55rem;
    }}
    .toolbar-row {{ display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }}
    .status-pill {{
      display: inline-flex; align-items: center; gap: 0.4rem;
      font-size: 0.78rem; font-weight: 600;
      padding: 0.3rem 0.7rem;
      border-radius: 999px;
      background: rgba(16, 185, 129, 0.14);
      color: var(--ok);
      border: 1px solid rgba(16, 185, 129, 0.28);
    }}
    .lang-select, .ctrl-select, .theme-btn {{
      background: var(--surface-solid);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.42rem 0.75rem;
      border-radius: 9px;
      font-size: 0.83rem;
      font-weight: 500;
      cursor: pointer;
      transition: border-color 0.15s;
    }}
    .lang-select:hover, .ctrl-select:hover, .theme-btn:hover {{
      border-color: var(--accent);
    }}
    .meta-bar {{ color: var(--muted); font-size: 0.8rem; }}
    .meta-bar strong {{ color: var(--text); }}

    /* KPI Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 1rem;
      margin-bottom: 1.25rem;
    }}
    .kpi-card {{
      background: var(--surface);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.15rem 1.3rem;
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
      transition: transform 0.15s, border-color 0.15s;
    }}
    .kpi-card:hover {{ transform: translateY(-2px); border-color: var(--border-strong); }}
    .kpi-top {{ display: flex; justify-content: space-between; align-items: center; }}
    .kpi-label {{ color: var(--muted); font-size: 0.76rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }}
    .kpi-icon {{ font-size: 1.15rem; opacity: 0.85; }}
    .kpi-value {{ font-size: 1.8rem; font-weight: 800; margin-top: 0.35rem; color: var(--text); letter-spacing: -0.02em; }}
    .kpi-sub {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.25rem; }}
    .progress-track {{
      height: 5px; width: 100%;
      background: rgba(148, 163, 184, 0.18);
      border-radius: 999px;
      margin-top: 0.55rem;
      overflow: hidden;
    }}
    .progress-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent-indigo));
      border-radius: 999px;
    }}

    /* Category Distribution Bar */
    .dist-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 0.85rem 1.25rem;
      margin-bottom: 1.4rem;
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
    }}
    .dist-header {{ display: flex; justify-content: space-between; font-size: 0.78rem; color: var(--muted); flex-wrap: wrap; gap: 0.5rem; }}
    .dist-bar {{
      display: flex;
      height: 8px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(148, 163, 184, 0.12);
      gap: 2px;
    }}
    .seg-goal {{ background: #f43f5e; }}
    .seg-decision {{ background: #38bdf8; }}
    .seg-pending {{ background: #f59e0b; }}
    .seg-done {{ background: #10b981; }}
    .seg-constraint {{ background: #a855f7; }}
    .seg-bug {{ background: #ec4899; }}

    /* Alerts */
    .alert {{
      border-radius: 12px;
      padding: 1rem 1.25rem;
      margin-bottom: 1.25rem;
      border: 1px solid;
    }}
    .alert-title {{ font-weight: 700; font-size: 0.95rem; margin-bottom: 0.45rem; }}
    .alert ul {{ margin-left: 1.25rem; font-size: 0.88rem; }}
    .alert-conflict {{ background: rgba(244, 63, 94, 0.12); border-color: var(--critical); color: #fda4af; }}
    .alert-stale {{ background: rgba(245, 158, 11, 0.12); border-color: var(--high); color: #fde68a; }}

    /* Controls & Filter Bar */
    .controls-panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1rem 1.2rem;
      margin-bottom: 1.4rem;
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
      box-shadow: var(--shadow);
    }}
    .search-row {{ display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; }}
    .search-wrap {{ flex: 1; min-width: 250px; position: relative; }}
    .search-input {{
      width: 100%;
      background: var(--surface-solid);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.62rem 1rem;
      border-radius: 10px;
      font-size: 0.9rem;
      outline: none;
      transition: border-color 0.15s;
    }}
    .search-input:focus {{ border-color: var(--accent); }}
    .filter-pills {{ display: flex; flex-wrap: wrap; gap: 0.45rem; }}
    .filter-btn {{
      background: var(--surface-solid);
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 0.42rem 0.85rem;
      border-radius: 999px;
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 500;
      transition: all 0.15s;
    }}
    .filter-btn.active, .filter-btn:hover {{
      border-color: var(--accent);
      color: var(--text);
      background: rgba(56, 189, 248, 0.15);
    }}

    /* Memory Cards */
    .entry-card {{
      background: var(--surface);
      backdrop-filter: blur(10px);
      border: 1px solid var(--border);
      border-left: 4px solid var(--medium);
      border-radius: 14px;
      padding: 1.2rem 1.4rem;
      margin-bottom: 0.95rem;
      box-shadow: var(--shadow);
      transition: transform 0.15s, border-color 0.15s;
    }}
    .entry-card:hover {{ border-color: var(--border-strong); }}
    .entry-card.prio-critical {{ border-left-color: var(--critical); }}
    .entry-card.prio-high {{ border-left-color: var(--high); }}
    .entry-card.prio-low {{ border-left-color: var(--low); }}
    .entry-card.status-superseded, .entry-card.status-archived {{ opacity: 0.58; }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 0.65rem;
    }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }}
    .badge {{
      font-size: 0.7rem;
      font-weight: 600;
      padding: 0.2rem 0.6rem;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.14);
      color: var(--text-secondary);
      border: 1px solid rgba(148, 163, 184, 0.2);
    }}
    .badge-prio-critical {{ background: rgba(244, 63, 94, 0.18); color: #fb7185; border-color: rgba(244, 63, 94, 0.35); }}
    .badge-prio-high {{ background: rgba(245, 158, 11, 0.18); color: #fbbf24; border-color: rgba(245, 158, 11, 0.35); }}
    .badge-prio-medium {{ background: rgba(59, 130, 246, 0.18); color: #60a5fa; border-color: rgba(59, 130, 246, 0.35); }}
    .badge-status-conflicted {{ background: rgba(244, 63, 94, 0.28); color: #fda4af; }}
    .badge-status-completed {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border-color: rgba(16, 185, 129, 0.35); }}
    .copy-btn {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 0.2rem 0.55rem;
      border-radius: 6px;
      font-size: 0.74rem;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .copy-btn:hover {{ border-color: var(--accent); color: var(--text); }}
    .card-title {{ font-size: 1.08rem; font-weight: 700; color: var(--text); margin-bottom: 0.4rem; }}
    .card-content {{ color: var(--text-secondary); font-size: 0.93rem; white-space: pre-wrap; margin-bottom: 0.85rem; }}
    .inline-code {{
      font-family: "JetBrains Mono", Consolas, monospace;
      font-size: 0.84em;
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 0.1rem 0.38rem;
      border-radius: 5px;
      color: var(--accent);
    }}
    .card-footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      font-size: 0.78rem;
      color: var(--muted);
      padding-top: 0.6rem;
      border-top: 1px solid var(--border);
    }}
    .tags-wrap {{ display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }}
    .tag {{ color: var(--accent); font-weight: 500; }}
    .file-chip {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 0.12rem 0.48rem;
      border-radius: 6px;
      font-family: monospace;
      font-size: 0.75rem;
      color: var(--text-secondary);
    }}
    .meta-link {{ color: var(--text-secondary); }}

    /* Empty Onboarding Card */
    .empty-onboarding {{
      background: var(--surface);
      border: 1px dashed var(--border-strong);
      border-radius: 16px;
      padding: 2.5rem 2rem;
      text-align: center;
      margin-bottom: 1.5rem;
    }}
    .empty-icon {{ font-size: 2.6rem; margin-bottom: 0.6rem; }}
    .empty-onboarding h3 {{ font-size: 1.25rem; margin-bottom: 0.45rem; }}
    .empty-onboarding p {{ color: var(--muted); max-width: 640px; margin: 0 auto 1.4rem; font-size: 0.92rem; }}
    .prompt-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 0.85rem;
      max-width: 780px;
      margin: 0 auto;
    }}
    .prompt-box {{
      background: var(--surface-solid);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.8rem 1rem;
      cursor: pointer;
      transition: all 0.15s;
      text-align: left;
    }}
    .prompt-box:hover {{ border-color: var(--accent); transform: translateY(-2px); }}
    .p-label {{ display: block; font-size: 0.72rem; color: var(--muted); text-transform: uppercase; margin-bottom: 0.25rem; }}
    .p-cmd {{ color: var(--accent); font-weight: 600; font-size: 0.88rem; }}

    /* Audit History Table */
    .history-section {{ margin-top: 2.2rem; }}
    .history-section h2 {{ font-size: 1.15rem; margin-bottom: 0.85rem; display: flex; align-items: center; gap: 0.5rem; }}
    .table-wrap {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow-x: auto;
      box-shadow: var(--shadow);
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 0.78rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.84rem; }}
    th {{ color: var(--muted); text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em; background: rgba(148, 163, 184, 0.05); }}
    tr:last-child td {{ border-bottom: none; }}
    .rev-pill {{
      font-family: monospace; font-weight: 700;
      color: var(--accent);
      background: rgba(56, 189, 248, 0.12);
      padding: 0.15rem 0.45rem;
      border-radius: 6px;
    }}
    .chip-mini {{
      font-size: 0.7rem; padding: 0.1rem 0.4rem;
      border-radius: 4px; background: rgba(148, 163, 184, 0.15);
    }}
    .td-time {{ color: var(--muted); white-space: nowrap; font-size: 0.78rem; }}

    /* Toast Notification */
    #toast {{
      position: fixed; bottom: 24px; right: 24px;
      background: var(--surface-solid);
      color: var(--text);
      border: 1px solid var(--accent);
      padding: 0.65rem 1.1rem;
      border-radius: 10px;
      font-size: 0.85rem;
      font-weight: 600;
      box-shadow: var(--shadow);
      opacity: 0; pointer-events: none;
      transform: translateY(10px);
      transition: all 0.2s;
      z-index: 999;
    }}
    #toast.show {{ opacity: 1; transform: translateY(0); }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand-row">
        <div class="brand-logo">🌉</div>
        <div>
          <h1>AI Memory Bridge — {proj_name}</h1>
          <div class="subtitle" data-i18n="subtitle">One Memory. Every AI Agent. Local-First Project Context Dashboard</div>
        </div>
      </div>
      <div class="header-right">
        <div class="toolbar-row">
          <span class="status-pill">● <span data-i18n="local_active">Local Store Active</span></span>
          <button id="themeBtn" class="theme-btn" type="button" title="Toggle Dark/Light Theme">🌙</button>
          <select id="langSelect" class="lang-select" aria-label="Language">
            <option value="ru">🌐 Русский (RU)</option>
            <option value="en">🌐 English (EN)</option>
            <option value="uk">🌐 Українська (UK)</option>
            <option value="zh">🌐 中文 (ZH)</option>
            <option value="es">🌐 Español (ES)</option>
            <option value="de">🌐 Deutsch (DE)</option>
          </select>
        </div>
        <div class="meta-bar">
          <span data-i18n="branch">Branch</span>: <strong>🌿 {current_branch}</strong> &nbsp;|&nbsp;
          <span data-i18n="revision">Revision</span>: <strong>#{rev}</strong> &nbsp;|&nbsp;
          <span data-i18n="last_updated">Last Updated</span>: <strong>{updated_at} UTC</strong>
        </div>
      </div>
    </header>

    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label" data-i18n="kpi_active">Active Entries</span>
          <span class="kpi-icon">📌</span>
        </div>
        <div class="kpi-value">{len(active_entries)}</div>
        <div class="kpi-sub"><span data-i18n="kpi_total_sub">Total recorded</span>: {len(all_entries)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label" data-i18n="kpi_decisions">Architectural Decisions</span>
          <span class="kpi-icon">🏛️</span>
        </div>
        <div class="kpi-value">{decisions_count}</div>
        <div class="kpi-sub"><span data-i18n="kpi_constraints_sub">Constraints</span>: {cat_counts['constraint']}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label" data-i18n="kpi_pending">Pending Tasks &amp; Steps</span>
          <span class="kpi-icon">⚡</span>
        </div>
        <div class="kpi-value">{pending_count}</div>
        <div class="kpi-sub"><span data-i18n="kpi_done_sub">Completed</span>: {completed_count}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label" data-i18n="kpi_tokens">Context Budget</span>
          <span class="kpi-icon">🧮</span>
        </div>
        <div class="kpi-value">~{est_tokens} <small style="font-size:0.85rem;font-weight:500;color:var(--muted)">tok</small></div>
        <div class="progress-track"><div class="progress-fill" style="width:{token_pct}%"></div></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label" data-i18n="kpi_conflicts">Conflicts &amp; Drift</span>
          <span class="kpi-icon">🛡️</span>
        </div>
        <div class="kpi-value" style="color: {'#f43f5e' if (unresolved_conflicts or stale_refs) else '#10b981'}">
          {len(unresolved_conflicts) + len(stale_refs)}
        </div>
        <div class="kpi-sub"><span data-i18n="kpi_stale_sub">Stale files</span>: {len(stale_refs)}</div>
      </div>
    </section>

    <div class="dist-card">
      <div class="dist-header">
        <span data-i18n="dist_title">Memory Category Distribution</span>
        <span>
          🎯 <span data-i18n="filter_goal">Goals</span>: {cat_counts['goal']} &nbsp;·&nbsp;
          🏛️ <span data-i18n="filter_decision">Decisions</span>: {cat_counts['decision']} &nbsp;·&nbsp;
          ⚡ <span data-i18n="filter_pending">Pending</span>: {cat_counts['task_pending']} &nbsp;·&nbsp;
          ✅ <span data-i18n="filter_done">Completed</span>: {cat_counts['task_done']} &nbsp;·&nbsp;
          🔒 <span data-i18n="filter_constraint">Constraints</span>: {cat_counts['constraint']} &nbsp;·&nbsp;
          🐛 <span data-i18n="filter_bug">Bug Fixes</span>: {cat_counts['bug_fix']}
        </span>
      </div>
      <div class="dist-bar">
        <div class="seg-goal" style="width:{(cat_counts['goal']/total_cat)*100:.1f}%"></div>
        <div class="seg-decision" style="width:{(cat_counts['decision']/total_cat)*100:.1f}%"></div>
        <div class="seg-pending" style="width:{(cat_counts['task_pending']/total_cat)*100:.1f}%"></div>
        <div class="seg-done" style="width:{(cat_counts['task_done']/total_cat)*100:.1f}%"></div>
        <div class="seg-constraint" style="width:{(cat_counts['constraint']/total_cat)*100:.1f}%"></div>
        <div class="seg-bug" style="width:{(cat_counts['bug_fix']/total_cat)*100:.1f}%"></div>
      </div>
    </div>

    {conflict_html}
    {stale_html}

    <section class="controls-panel">
      <div class="search-row">
        <div class="search-wrap">
          <input type="text" id="searchInput" class="search-input" placeholder="Search entries by title, content, tag, or agent (press '/' to focus)..." />
        </div>
        <select id="agentSelect" class="ctrl-select" aria-label="Filter by AI Agent">
          <option value="all" data-i18n="all_agents">🤖 All Agents</option>
          {agent_options_html}
        </select>
        <select id="prioSelect" class="ctrl-select" aria-label="Filter by Priority">
          <option value="all" data-i18n="all_priorities">🔥 All Priorities</option>
          <option value="critical" data-i18n="prio_critical">CRITICAL</option>
          <option value="high" data-i18n="prio_high">HIGH</option>
          <option value="medium" data-i18n="prio_medium">MEDIUM</option>
          <option value="low" data-i18n="prio_low">LOW</option>
        </select>
      </div>
      <div class="filter-pills">
        <button class="filter-btn active" data-filter="all"><span data-i18n="filter_all">All</span> ({len(all_entries)})</button>
        <button class="filter-btn" data-filter="active-only"><span data-i18n="filter_active">Active Only</span> ({len(active_entries)})</button>
        <button class="filter-btn" data-filter="goal" data-i18n="filter_goal">Goals</button>
        <button class="filter-btn" data-filter="decision" data-i18n="filter_decision">Decisions</button>
        <button class="filter-btn" data-filter="task_pending" data-i18n="filter_pending">Pending Tasks</button>
        <button class="filter-btn" data-filter="task_done" data-i18n="filter_done">Completed</button>
        <button class="filter-btn" data-filter="next_step" data-i18n="filter_next">Next Steps</button>
        <button class="filter-btn" data-filter="constraint" data-i18n="filter_constraint">Constraints</button>
        <button class="filter-btn" data-filter="bug_fix" data-i18n="filter_bug">Bug Fixes</button>
        <button class="filter-btn" data-filter="preference" data-i18n="filter_pref">Preferences</button>
      </div>
    </section>

    <main id="entriesContainer">
      {"".join(cards_html_list) if cards_html_list else empty_state_html}
    </main>

    <section class="history-section">
      <h2>📜 <span data-i18n="audit_title">Recent Audit History (`.ai-memory/history/events.jsonl`)</span></h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-i18n="th_rev">Rev</th>
              <th data-i18n="th_action">Action</th>
              <th data-i18n="th_agent">Source Agent</th>
              <th data-i18n="th_details">Summary</th>
              <th data-i18n="th_time">Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {events_rows if events_rows else '<tr><td colspan="5" style="text-align:center;color:var(--muted)" data-i18n="no_events">No audit events recorded yet.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <div id="toast">Copied to clipboard!</div>

  <script>
    const searchInput = document.getElementById('searchInput');
    const langSelect = document.getElementById('langSelect');
    const agentSelect = document.getElementById('agentSelect');
    const prioSelect = document.getElementById('prioSelect');
    const themeBtn = document.getElementById('themeBtn');
    const buttons = document.querySelectorAll('.filter-btn');
    const cards = document.querySelectorAll('.entry-card');
    let currentFilter = 'all';

    const I18N = {{
      en: {{
        subtitle: "One Memory. Every AI Agent. Local-First Project Context Dashboard",
        local_active: "Local Store Active",
        branch: "Branch", revision: "Revision", last_updated: "Last Updated",
        kpi_active: "Active Entries", kpi_total_sub: "Total recorded",
        kpi_decisions: "Architectural Decisions", kpi_constraints_sub: "Constraints",
        kpi_pending: "Pending Tasks & Steps", kpi_done_sub: "Completed",
        kpi_tokens: "Context Budget",
        kpi_conflicts: "Conflicts & Drift", kpi_stale_sub: "Stale files",
        dist_title: "Memory Category Distribution",
        conflict_banner: "Unresolved Architectural / Technical Conflicts",
        stale_banner: "Stale File References Detected",
        search_placeholder: "Search entries by title, content, tag, or agent (press '/' to focus)...",
        all_agents: "🤖 All Agents", all_priorities: "🔥 All Priorities",
        filter_all: "All", filter_active: "Active Only", filter_goal: "Goals",
        filter_decision: "Decisions", filter_pending: "Pending Tasks", filter_done: "Completed",
        filter_next: "Next Steps", filter_constraint: "Constraints", filter_bug: "Bug Fixes", filter_pref: "Preferences",
        prio_critical: "CRITICAL", prio_high: "HIGH", prio_medium: "MEDIUM", prio_low: "LOW",
        type_goal: "Project Goal", type_decision: "Architectural Decision", type_constraint: "Technical Constraint",
        type_preference: "User Preference", type_task_pending: "Pending Task", type_task_done: "Completed Task",
        type_bug_fix: "Bug Fix", type_next_step: "Next Step", type_session_summary: "Session Summary",
        status_active: "ACTIVE", status_completed: "COMPLETED", status_superseded: "SUPERSEDED",
        status_conflicted: "CONFLICTED", status_archived: "ARCHIVED",
        lbl_updated: "Updated", lbl_supersedes: "Supersedes", lbl_superseded_by: "Superseded by",
        empty_title: "Project Memory Store is Ready & Clean",
        empty_desc: "No memory entries have been recorded yet. There is no fake or placeholder data—entries appear here automatically as soon as you ask your AI coding agent to save project context or progress.",
        prompt_lbl_1: "Save Progress", prompt_cmd_1: "Save our progress",
        prompt_lbl_2: "Auto-Scan Project", prompt_cmd_2: "Remember this project",
        prompt_lbl_3: "Agent Handoff", prompt_cmd_3: "Prepare a handoff for Codex",
        audit_title: "Recent Audit History (.ai-memory/history/events.jsonl)",
        th_rev: "Rev", th_action: "Action", th_agent: "Source Agent", th_details: "Summary", th_time: "Timestamp",
        act_init: "Initialized Store", act_capture_add: "Added Entry", act_deduplicate_update: "Deduplicated",
        act_complete_task: "Completed Task", act_handoff: "Agent Handoff", act_sync: "Synced Rules",
        act_resolve_conflict: "Resolved Conflict", act_restore: "Restored Snapshot",
        toast_copied: "Copied to clipboard!"
      }},
      ru: {{
        subtitle: "Единая память. Любой ИИ-агент. Локальная панель контекста проекта",
        local_active: "Локальная память активна",
        branch: "Ветка", revision: "Ревизия", last_updated: "Обновлено",
        kpi_active: "Активные записи", kpi_total_sub: "Всего записей",
        kpi_decisions: "Архитектурные решения", kpi_constraints_sub: "Ограничений",
        kpi_pending: "Задачи в работе", kpi_done_sub: "Выполнено",
        kpi_tokens: "Бюджет контекста",
        kpi_conflicts: "Конфликты и файлы", kpi_stale_sub: "Удалённые файлы",
        dist_title: "Распределение памяти по категориям",
        conflict_banner: "Неразрешённые архитектурные и технические конфликты",
        stale_banner: "Обнаружены ссылки на удалённые или перемещённые файлы",
        search_placeholder: "Поиск по заголовку, тексту, тегам или агенту (нажмите '/' для поиска)...",
        all_agents: "🤖 Все ИИ-агенты", all_priorities: "🔥 Все приоритеты",
        filter_all: "Все", filter_active: "Активные", filter_goal: "Цели",
        filter_decision: "Решения", filter_pending: "В работе", filter_done: "Выполненные",
        filter_next: "След. шаги", filter_constraint: "Ограничения", filter_bug: "Исправления", filter_pref: "Предпочтения",
        prio_critical: "КРИТИЧНЫЙ", prio_high: "ВЫСОКИЙ", prio_medium: "СРЕДНИЙ", prio_low: "НИЗКИЙ",
        type_goal: "Цель проекта", type_decision: "Архитектурное решение", type_constraint: "Тех. ограничение",
        type_preference: "Предпочтение", type_task_pending: "Задача в работе", type_task_done: "Выполненная задача",
        type_bug_fix: "Исправление бага", type_next_step: "Следующий шаг", type_session_summary: "Итог сессии",
        status_active: "АКТИВНО", status_completed: "ВЫПОЛНЕНО", status_superseded: "ЗАМЕНЕНО",
        status_conflicted: "КОНФЛИКТ", status_archived: "В АРХИВЕ",
        lbl_updated: "Обновлено", lbl_supersedes: "Заменяет", lbl_superseded_by: "Заменено на",
        empty_title: "Хранилище памяти проекта чисто и готово к работе",
        empty_desc: "В памяти пока нет ни одной записи (никаких фейковых или дефолтных данных). Записи появятся здесь сразу после того, как вы попросите своего ИИ-агента сохранить прогресс или запомнить проект:",
        prompt_lbl_1: "Сохранить прогресс", prompt_cmd_1: "Сохрани наш прогресс",
        prompt_lbl_2: "Запомнить проект", prompt_cmd_2: "Запомни этот проект",
        prompt_lbl_3: "Передача другому агенту", prompt_cmd_3: "Подготовь передачу для Codex",
        audit_title: "Журнал изменений (.ai-memory/history/events.jsonl)",
        th_rev: "Рев.", th_action: "Действие", th_agent: "ИИ-агент", th_details: "Описание", th_time: "Время",
        act_init: "Инициализация", act_capture_add: "Добавлена запись", act_deduplicate_update: "Обновлён дубликат",
        act_complete_task: "Задача закрыта", act_handoff: "Передача агенту", act_sync: "Синхронизация правил",
        act_resolve_conflict: "Конфликт решён", act_restore: "Восстановление",
        toast_copied: "Скопировано в буфер обмена!"
      }},
      uk: {{
        subtitle: "Єдина пам'ять. Будь-який ШІ-агент. Локальна панель контексту проєкту",
        local_active: "Локальна пам'ять активна",
        branch: "Гілка", revision: "Ревізія", last_updated: "Оновлено",
        kpi_active: "Активні записи", kpi_total_sub: "Усього записів",
        kpi_decisions: "Архітектурні рішення", kpi_constraints_sub: "Обмежень",
        kpi_pending: "Задачі в роботі", kpi_done_sub: "Виконано",
        kpi_tokens: "Бюджет контексту",
        kpi_conflicts: "Конфлікти та файли", kpi_stale_sub: "Видалені файли",
        dist_title: "Розподіл пам'яті за категоріями",
        conflict_banner: "Невирішені архітектурні та технічні конфлікти",
        stale_banner: "Виявлено посилання на видалені або переміщені файли",
        search_placeholder: "Пошук за заголовком, текстом, тегами або агентом (натисніть '/')...",
        all_agents: "🤖 Усі ШІ-агенти", all_priorities: "🔥 Усі пріоритети",
        filter_all: "Усі", filter_active: "Активні", filter_goal: "Цілі",
        filter_decision: "Рішення", filter_pending: "В роботі", filter_done: "Виконані",
        filter_next: "Наст. кроки", filter_constraint: "Обмеження", filter_bug: "Виправлення", filter_pref: "Уподобання",
        prio_critical: "КРИТИЧНИЙ", prio_high: "ВИСОКИЙ", prio_medium: "СЕРЕДНІЙ", prio_low: "НИЗЬКИЙ",
        type_goal: "Ціль проєкту", type_decision: "Архітектурне рішення", type_constraint: "Тех. обмеження",
        type_preference: "Уподобання", type_task_pending: "Задача в роботі", type_task_done: "Виконана задача",
        type_bug_fix: "Виправлення бага", type_next_step: "Наступний крок", type_session_summary: "Підсумок сесії",
        status_active: "АКТИВНО", status_completed: "ВИКОНАНО", status_superseded: "ЗАМІНЕНО",
        status_conflicted: "КОНФЛІКТ", status_archived: "В АРХІВІ",
        lbl_updated: "Оновлено", lbl_supersedes: "Замінює", lbl_superseded_by: "Замінено на",
        empty_title: "Сховище пам'яті проєкту чисте й готове до роботи",
        empty_desc: "У пам'яті ще немає жодного запису (ніяких фейкових або дефолтних даних). Записи з'являться тут одразу після того, як ви попросите свого ШІ-агента зберегти прогрес:",
        prompt_lbl_1: "Зберегти прогрес", prompt_cmd_1: "Збережи наш прогрес",
        prompt_lbl_2: "Запам'ятати проєкт", prompt_cmd_2: "Запам'ятай цей проєкт",
        prompt_lbl_3: "Передача іншому агенту", prompt_cmd_3: "Підготуй передачу для Codex",
        audit_title: "Журнал змін (.ai-memory/history/events.jsonl)",
        th_rev: "Рев.", th_action: "Дія", th_agent: "ШІ-агент", th_details: "Опис", th_time: "Час",
        act_init: "Ініціалізація", act_capture_add: "Додано запис", act_deduplicate_update: "Оновлено дублікат",
        act_complete_task: "Задачу закрито", act_handoff: "Передача агенту", act_sync: "Синхронізація правил",
        act_resolve_conflict: "Конфлікт вирішено", act_restore: "Відновлення",
        toast_copied: "Скопійовано в буфер обміну!"
      }},
      zh: {{
        subtitle: "统一记忆 · 适配所有 AI 编程代理 · 本地优先项目上下文面板",
        local_active: "本地存储已激活",
        branch: "分支", revision: "版本", last_updated: "最后更新",
        kpi_active: "有效记忆条目", kpi_total_sub: "总记录数",
        kpi_decisions: "架构决策", kpi_constraints_sub: "技术约束",
        kpi_pending: "待办任务与下一步", kpi_done_sub: "已完成",
        kpi_tokens: "上下文预算",
        kpi_conflicts: "冲突与文件漂移", kpi_stale_sub: "失效文件引用",
        dist_title: "记忆类别分布",
        search_placeholder: "按标题、内容、标签或代理搜索记忆 (按 '/' 聚焦)...",
        all_agents: "🤖 所有 AI 代理", all_priorities: "🔥 所有优先级",
        filter_all: "全部", filter_active: "仅有效", filter_goal: "项目目标",
        filter_decision: "架构决策", filter_pending: "待办任务", filter_done: "已完成",
        filter_next: "下一步", filter_constraint: "技术约束", filter_bug: "缺陷修复", filter_pref: "开发偏好",
        prio_critical: "关键", prio_high: "高优", prio_medium: "中等", prio_low: "低优",
        type_goal: "项目目标", type_decision: "架构决策", type_constraint: "技术约束",
        type_preference: "开发偏好", type_task_pending: "待办任务", type_task_done: "已完成任务",
        type_bug_fix: "缺陷修复", type_next_step: "下一步", type_session_summary: "会话摘要",
        status_active: "有效", status_completed: "已完成", status_superseded: "已替代",
        status_conflicted: "冲突", status_archived: "已归档",
        lbl_updated: "更新于", lbl_supersedes: "替代", lbl_superseded_by: "被替代",
        empty_title: "项目记忆库已就绪（无默认冗余数据）",
        empty_desc: "当前没有任何虚构或默认数据。只需对您的 AI 编程代理发送以下自然语言指令即可自动记录：",
        prompt_lbl_1: "保存进度", prompt_cmd_1: "保存当前进度",
        prompt_lbl_2: "扫描并记住项目", prompt_cmd_2: "记住这个项目",
        prompt_lbl_3: "跨代理交接", prompt_cmd_3: "准备交接给 Codex",
        audit_title: "最近审计日志 (.ai-memory/history/events.jsonl)",
        th_rev: "版本", th_action: "操作", th_agent: "来源代理", th_details: "摘要", th_time: "时间戳",
        act_init: "初始化存储", act_capture_add: "新增记忆", act_deduplicate_update: "去重更新",
        toast_copied: "已复制到剪贴板！"
      }},
      es: {{
        subtitle: "Una Memoria. Todos los Agentes IA. Panel de Contexto Local",
        local_active: "Memoria Local Activa",
        branch: "Rama", revision: "Revisión", last_updated: "Actualizado",
        kpi_active: "Entradas Activas", kpi_total_sub: "Total registradas",
        kpi_decisions: "Decisiones de Arquitectura", kpi_constraints_sub: "Restricciones",
        kpi_pending: "Tareas Pendientes", kpi_done_sub: "Completadas",
        kpi_tokens: "Presupuesto de Contexto",
        kpi_conflicts: "Conflictos y Archivos", kpi_stale_sub: "Archivos faltantes",
        dist_title: "Distribución por Categorías",
        search_placeholder: "Buscar por título, contenido, etiqueta o agente...",
        all_agents: "🤖 Todos los Agentes", all_priorities: "🔥 Todas las Prioridades",
        filter_all: "Todas", filter_active: "Solo Activas", filter_goal: "Objetivos",
        filter_decision: "Decisiones", filter_pending: "Pendientes", filter_done: "Completadas",
        filter_next: "Siguientes Pasos", filter_constraint: "Restricciones", filter_bug: "Errores Corregidos", filter_pref: "Preferencias",
        empty_title: "Almacén de Memoria Listo y Limpio",
        empty_desc: "Aún no hay entradas registradas. Habla con tu agente IA para guardar el progreso del proyecto.",
        audit_title: "Historial de Auditoría (.ai-memory/history/events.jsonl)",
        th_rev: "Rev", th_action: "Acción", th_agent: "Agente", th_details: "Resumen", th_time: "Fecha",
        toast_copied: "¡Copiado al portapapeles!"
      }},
      de: {{
        subtitle: "Ein Gedächtnis. Jeder KI-Agent. Lokales Projekt-Kontext-Dashboard",
        local_active: "Lokaler Speicher Aktiv",
        branch: "Branch", revision: "Revision", last_updated: "Aktualisiert",
        kpi_active: "Aktive Einträge", kpi_total_sub: "Gesamt",
        kpi_decisions: "Architekturentscheidungen", kpi_constraints_sub: "Einschränkungen",
        kpi_pending: "Offene Aufgaben", kpi_done_sub: "Erledigt",
        kpi_tokens: "Kontext-Budget",
        kpi_conflicts: "Konflikte & Dateien", kpi_stale_sub: "Fehlende Dateien",
        dist_title: "Verteilung nach Kategorien",
        search_placeholder: "Einträge nach Titel, Inhalt, Tag oder Agent durchsuchen...",
        all_agents: "🤖 Alle Agenten", all_priorities: "🔥 Alle Prioritäten",
        filter_all: "Alle", filter_active: "Nur Aktive", filter_goal: "Ziele",
        filter_decision: "Entscheidungen", filter_pending: "Offene Aufgaben", filter_done: "Erledigt",
        filter_next: "Nächste Schritte", filter_constraint: "Einschränkungen", filter_bug: "Bugfixes", filter_pref: "Präferenzen",
        empty_title: "Projektspeicher ist bereit und sauber",
        empty_desc: "Noch keine Einträge vorhanden. Bitten Sie Ihren KI-Agenten, den Projektfortschritt zu speichern.",
        audit_title: "Versionsverlauf (.ai-memory/history/events.jsonl)",
        th_rev: "Rev", th_action: "Aktion", th_agent: "Agent", th_details: "Zusammenfassung", th_time: "Zeitstempel",
        toast_copied: "In die Zwischenablage kopiert!"
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
      toast.textContent = (dict.toast_copied || 'Copied!') + ' (' + text + ')';
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2200);
    }}

    // Theme management
    function setTheme(theme) {{
      document.documentElement.setAttribute('data-theme', theme);
      themeBtn.textContent = theme === 'light' ? '☀️' : '🌙';
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

    // Language initialization
    langSelect.addEventListener('change', (e) => setLanguage(e.target.value));
    const savedLang = (() => {{
      try {{ return localStorage.getItem('ai_memory_bridge_lang'); }} catch (e) {{ return null; }}
    }})();
    const browserLang = (navigator.language || 'ru').slice(0, 2).toLowerCase();
    const initialLang = savedLang || (I18N[browserLang] ? browserLang : 'ru');
    langSelect.value = initialLang;
    setLanguage(initialLang);

    // Filtering
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

    // Keyboard shortcut '/' to focus search
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
