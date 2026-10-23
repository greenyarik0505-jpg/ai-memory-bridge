#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate an interactive, zero-dependency, offline HTML dashboard at .ai-memory/dashboard.html.

Visualizes project memory entries, agent attributions, active branches, supersede chains,
unresolved conflicts, and revision audit history.

Usage:
  python scripts/dashboard.py [--workspace .] [--out .ai-memory/dashboard.html] [--json]
"""
from __future__ import annotations

import argparse
import html
import json
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


def render_dashboard_html(workspace_root: Path, data: dict[str, Any]) -> str:
    """Render a self-contained, XSS-safe, interactive HTML dashboard for project memory."""
    paths = get_memory_paths(workspace_root)
    project = data.get("project", {})
    proj_name = html.escape(str(project.get("name", "Project")))
    rev = int(data.get("revision", 1))
    updated_at = html.escape(str(project.get("updated_at", "")))
    current_branch = html.escape(get_current_git_branch(workspace_root))

    all_entries = sort_entries_by_priority(data.get("entries", []), preferred_branch=current_branch)
    active_entries = [e for e in all_entries if e.get("status") in ("active", "conflicted")]
    decisions_count = len([e for e in active_entries if e.get("type") == "decision"])
    pending_count = len([e for e in active_entries if e.get("type") in ("task_pending", "next_step")])
    unresolved_conflicts = [c for c in data.get("conflicts", []) if c.get("status") == "unresolved"]
    stale_refs = detect_stale_file_references(workspace_root, active_entries)
    recent_events = _read_recent_events(paths["events_log"], limit=20)

    active_blob = " ".join(f"{e.get('title', '')} {e.get('content', '')}" for e in active_entries)
    est_tokens = estimate_tokens(active_blob) if active_entries else 0

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
          <h3>⚠️ Unresolved Architectural / Technical Conflicts ({len(unresolved_conflicts)})</h3>
          <ul>{items_html}</ul>
        </div>
        """

    stale_html = ""
    if stale_refs:
        s_items = "".join(
            f"<li><code>{html.escape(s['entry_id'])}</code> ({html.escape(s['title'])}) — missing file(s): "
            f"<code>{html.escape(', '.join(s['missing_files']))}</code></li>"
            for s in stale_refs
        )
        stale_html = f"""
        <div class="alert alert-stale">
          <h3>🔍 Stale File References Detected ({len(stale_refs)})</h3>
          <ul>{s_items}</ul>
        </div>
        """

    cards_html_list: list[str] = []
    for entry in all_entries:
        eid = html.escape(str(entry.get("id", "")))
        etype = html.escape(str(entry.get("type", "decision")))
        type_label = html.escape(ENTRY_TYPE_LABELS.get(entry.get("type", ""), etype))
        title = html.escape(str(entry.get("title", "")))
        content = html.escape(str(entry.get("content", "")))
        source = html.escape(str(entry.get("source", "manual")))
        prio = html.escape(str(entry.get("priority", "medium")))
        status = html.escape(str(entry.get("status", "active")))
        branch = html.escape(str(entry.get("branch", "main")))
        updated = html.escape(str(entry.get("updated_at", ""))[:19].replace("T", " "))
        tags = [html.escape(str(t)) for t in entry.get("tags", [])]
        tags_html = "".join(f'<span class="tag">#{t}</span>' for t in tags)

        sup_html = ""
        if entry.get("supersedes"):
            sup_html += f'<span class="meta-link">Supersedes: <code>{html.escape(str(entry["supersedes"]))}</code></span>'
        if entry.get("superseded_by"):
            sup_html += f'<span class="meta-link">Superseded by: <code>{html.escape(str(entry["superseded_by"]))}</code></span>'

        cards_html_list.append(
            f"""
            <article class="entry-card status-{status} prio-{prio}" data-type="{etype}" data-status="{status}" data-branch="{branch}">
              <div class="card-header">
                <div class="badges">
                  <span class="badge badge-prio-{prio}">{prio.upper()}</span>
                  <span class="badge badge-type">{type_label}</span>
                  <span class="badge badge-status-{status}">{status.upper()}</span>
                  <span class="badge badge-agent">🤖 {source}</span>
                  <span class="badge badge-branch">🌿 {branch}</span>
                </div>
                <code class="entry-id">{eid}</code>
              </div>
              <h3 class="card-title">{title}</h3>
              <p class="card-content">{content}</p>
              <div class="card-footer">
                <div class="tags-wrap">{tags_html} {sup_html}</div>
                <span class="timestamp">Updated: {updated} UTC</span>
              </div>
            </article>
            """
        )

    events_rows = "".join(
        f"""
        <tr>
          <td><code>{html.escape(str(ev.get('revision', '')))}</code></td>
          <td><span class="badge badge-type">{html.escape(str(ev.get('action', '')))}</span></td>
          <td><code>{html.escape(str(ev.get('agent', '')))}</code></td>
          <td>{html.escape(str(ev.get('timestamp', ''))[:19].replace('T', ' '))} UTC</td>
          <td><code>{html.escape(json.dumps(ev.get('details', {}))[:100])}</code></td>
        </tr>
        """
        for ev in recent_events
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Memory Bridge Dashboard — {proj_name}</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --surface: #111827;
      --surface-hover: #1e293b;
      --border: #1f2937;
      --text: #f3f4f6;
      --muted: #9ca3af;
      --accent: #38bdf8;
      --critical: #ef4444;
      --high: #f59e0b;
      --medium: #3b82f6;
      --low: #6b7280;
      --ok: #10b981;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem;
    }}
    .container {{ max-width: 1180px; margin: 0 auto; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 1rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 1.5rem;
    }}
    header h1 {{ font-size: 1.75rem; font-weight: 700; color: #fff; }}
    header .subtitle {{ color: var(--muted); font-size: 0.95rem; margin-top: 0.25rem; }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }}
    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.25rem;
    }}
    .kpi-label {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .kpi-value {{ font-size: 1.65rem; font-weight: 700; margin-top: 0.25rem; color: var(--accent); }}
    .alert {{
      border-radius: 10px;
      padding: 1rem 1.25rem;
      margin-bottom: 1.25rem;
      border: 1px solid;
    }}
    .alert h3 {{ font-size: 1rem; margin-bottom: 0.5rem; }}
    .alert ul {{ margin-left: 1.25rem; font-size: 0.9rem; }}
    .alert-conflict {{ background: rgba(239, 68, 68, 0.12); border-color: var(--critical); color: #fca5a5; }}
    .alert-stale {{ background: rgba(245, 158, 11, 0.12); border-color: var(--high); color: #fde68a; }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      align-items: center;
    }}
    .search-input {{
      flex: 1;
      min-width: 240px;
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.6rem 1rem;
      border-radius: 8px;
      font-size: 0.95rem;
    }}
    .filter-btn {{
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 0.5rem 0.85rem;
      border-radius: 8px;
      cursor: pointer;
      font-size: 0.85rem;
      transition: all 0.15s;
    }}
    .filter-btn.active, .filter-btn:hover {{
      border-color: var(--accent);
      color: #fff;
      background: rgba(56, 189, 248, 0.15);
    }}
    .entry-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-left: 4px solid var(--medium);
      border-radius: 10px;
      padding: 1.15rem 1.35rem;
      margin-bottom: 0.9rem;
    }}
    .entry-card.prio-critical {{ border-left-color: var(--critical); }}
    .entry-card.prio-high {{ border-left-color: var(--high); }}
    .entry-card.prio-low {{ border-left-color: var(--low); }}
    .entry-card.status-superseded, .entry-card.status-archived {{ opacity: 0.6; }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 0.6rem;
    }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 0.4rem; }}
    .badge {{
      font-size: 0.72rem;
      font-weight: 600;
      padding: 0.18rem 0.55rem;
      border-radius: 999px;
      background: #1f2937;
      color: #e5e7eb;
    }}
    .badge-prio-critical {{ background: rgba(239, 68, 68, 0.25); color: #fca5a5; }}
    .badge-prio-high {{ background: rgba(245, 158, 11, 0.25); color: #fde68a; }}
    .badge-prio-medium {{ background: rgba(59, 130, 246, 0.25); color: #93c5fd; }}
    .badge-status-conflicted {{ background: rgba(239, 68, 68, 0.35); color: #fecaca; }}
    .badge-status-completed {{ background: rgba(16, 185, 129, 0.25); color: #6ee7b7; }}
    .entry-id {{ color: var(--muted); font-size: 0.78rem; }}
    .card-title {{ font-size: 1.1rem; color: #fff; margin-bottom: 0.35rem; }}
    .card-content {{ color: #d1d5db; font-size: 0.95rem; white-space: pre-wrap; margin-bottom: 0.75rem; }}
    .card-footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      font-size: 0.8rem;
      color: var(--muted);
    }}
    .tag {{ color: var(--accent); margin-right: 0.5rem; }}
    .meta-link {{ margin-right: 0.75rem; color: #cbd5e1; }}
    .history-section {{ margin-top: 2.5rem; }}
    .history-section h2 {{ font-size: 1.25rem; margin-bottom: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 10px; overflow: hidden; }}
    th, td {{ text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.85rem; }}
    th {{ color: var(--muted); text-transform: uppercase; font-size: 0.75rem; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>🌉 AI Memory Bridge — {proj_name}</h1>
        <div class="subtitle">One Memory. Every AI Agent. Local-First Project Context Dashboard</div>
      </div>
      <div class="subtitle" style="text-align:right">
        <div>Branch: <strong>{current_branch}</strong> | Revision: <strong>#{rev}</strong></div>
        <div>Last Updated: {updated_at}</div>
      </div>
    </header>

    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Active Entries</div>
        <div class="kpi-value">{len(active_entries)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Architectural Decisions</div>
        <div class="kpi-value">{decisions_count}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Pending Tasks &amp; Steps</div>
        <div class="kpi-value">{pending_count}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Active Context Size</div>
        <div class="kpi-value">~{est_tokens} tok</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Unresolved Conflicts</div>
        <div class="kpi-value" style="color: {'#ef4444' if unresolved_conflicts else '#10b981'}">{len(unresolved_conflicts)}</div>
      </div>
    </section>

    {conflict_html}
    {stale_html}

    <section class="controls">
      <input type="text" id="searchInput" class="search-input" placeholder="Search entries by title, content, tag, or agent..." />
      <button class="filter-btn active" data-filter="all">All ({len(all_entries)})</button>
      <button class="filter-btn" data-filter="active-only">Active Only ({len(active_entries)})</button>
      <button class="filter-btn" data-filter="goal">Goals</button>
      <button class="filter-btn" data-filter="decision">Decisions</button>
      <button class="filter-btn" data-filter="task_pending">Pending Tasks</button>
      <button class="filter-btn" data-filter="next_step">Next Steps</button>
      <button class="filter-btn" data-filter="constraint">Constraints</button>
      <button class="filter-btn" data-filter="bug_fix">Bug Fixes</button>
    </section>

    <main id="entriesContainer">
      {"".join(cards_html_list) if cards_html_list else '<p style="color:var(--muted)">No memory entries recorded yet.</p>'}
    </main>

    <section class="history-section">
      <h2>Recent Audit History (`.ai-memory/history/events.jsonl`)</h2>
      <table>
        <thead>
          <tr>
            <th>Rev</th>
            <th>Action</th>
            <th>Source Agent</th>
            <th>Timestamp</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {events_rows}
        </tbody>
      </table>
    </section>
  </div>

  <script>
    const searchInput = document.getElementById('searchInput');
    const buttons = document.querySelectorAll('.filter-btn');
    const cards = document.querySelectorAll('.entry-card');
    let currentFilter = 'all';

    function applyFilters() {{
      const q = searchInput.value.toLowerCase().trim();
      cards.forEach(card => {{
        const type = card.getAttribute('data-type');
        const status = card.getAttribute('data-status');
        const text = card.innerText.toLowerCase();
        const matchesQuery = !q || text.includes(q);
        let matchesType = true;
        if (currentFilter === 'active-only') {{
          matchesType = (status === 'active' || status === 'conflicted');
        }} else if (currentFilter !== 'all') {{
          matchesType = (type === currentFilter);
        }}
        card.style.display = (matchesQuery && matchesType) ? 'block' : 'none';
      }});
    }}

    searchInput.addEventListener('input', applyFilters);
    buttons.forEach(btn => {{
      btn.addEventListener('click', () => {{
        buttons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.getAttribute('data-filter');
        applyFilters();
      }});
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
