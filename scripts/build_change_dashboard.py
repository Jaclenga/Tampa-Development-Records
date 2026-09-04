#!/usr/bin/env python3
"""Build the static snapshot-change dashboard from deterministic analysis artifacts."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import change_analysis  # noqa: E402


DASHBOARD = ROOT / "reports" / "dashboard"
DETAILS = DASHBOARD / "comparisons"
DISCLAIMER = (
    "This dashboard describes changes in records returned by published sources. "
    "A disappearance does not prove cancellation or deletion, a new record does not prove newly started work, "
    "and a phase change does not prove completed construction."
)


CSS = """
:root{--ink:#17212b;--muted:#52606d;--line:#d9e2ec;--paper:#fff;--wash:#f4f7fa;--blue:#145da0;--red:#a53b32;--amber:#8a5a00;--green:#276749}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--wash);line-height:1.45}
header,main,footer{max-width:1200px;margin:auto;padding:1rem 1.25rem}header{padding-top:2rem}h1{margin:.2rem 0;font-size:clamp(1.8rem,4vw,3rem)}h2{margin-top:2rem}a{color:#064f8c}code{overflow-wrap:anywhere}
.notice{border-left:.35rem solid var(--blue);background:#eaf3fb;padding:1rem}.banner{padding:1rem;border:2px solid;border-radius:.5rem}.critical{border-color:var(--red);background:#fff1ef}.review{border-color:var(--amber);background:#fff8e6}.healthy{border-color:var(--green);background:#edf9f0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.75rem}.card{background:var(--paper);border:1px solid var(--line);border-radius:.5rem;padding:1rem}.kpi{font-size:1.65rem;font-weight:700;display:block}.label{color:var(--muted);font-size:.9rem}
.table-wrap{overflow:auto;background:var(--paper);border:1px solid var(--line)}table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{padding:.55rem .65rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#edf2f7;position:sticky;top:0}td.num,th.num{text-align:right;white-space:nowrap}
.tag{display:inline-block;border:1px solid currentColor;border-radius:999px;padding:.1rem .45rem;font-size:.78rem;font-weight:650}.tag-critical{color:var(--red)}.tag-review{color:var(--amber)}.tag-healthy{color:var(--green)}
.chart{background:var(--paper);border:1px solid var(--line);padding:.75rem;overflow:auto}.chart svg{min-width:680px;width:100%;height:auto}.controls{display:flex;gap:.75rem;flex-wrap:wrap;align-items:end;margin:1rem 0}.controls label{display:grid;font-size:.85rem}.controls input,.controls select{font:inherit;padding:.4rem;min-width:11rem}.hidden{display:none}.heat{font-weight:650}.small{font-size:.85rem;color:var(--muted)}button{font:inherit;padding:.45rem .7rem;cursor:pointer}.drill td{max-width:28rem;overflow-wrap:anywhere}footer{color:var(--muted);font-size:.85rem;padding-bottom:3rem}
@media(max-width:650px){header,main,footer{padding-left:.75rem;padding-right:.75rem}th,td{padding:.4rem}.optional{display:none}}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "undefined"
    return f"{value * 100:{'+' if signed else ''}.1f}%"


def source_label(source: str) -> str:
    return source.replace("_", " ").title()


def page(title: str, body: str, *, prefix: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head><body>
<header><p class="small"><a href="{prefix}index.html">Tampa Published Development Records</a> / Snapshot change dashboard</p><h1>{esc(title)}</h1></header>
<main>{body}</main><footer>{esc(DISCLAIMER)}</footer></body></html>
"""


def tag(status: str) -> str:
    css = "critical" if status == "critical" else "review" if status in {"review", "warning"} else "healthy"
    return f'<span class="tag tag-{css}">{esc(status.upper())}</span>'


def metric_cards(overall: dict[str, object]) -> str:
    values = [
        ("Before", f"{overall['count_before']:,}"),
        ("After", f"{overall['count_after']:,}"),
        ("Net change", f"{overall['absolute_net_change']:+,}"),
        ("Newly observed", f"{overall['new_records']:,}"),
        ("No longer returned", f"{overall['disappeared_records']:,}"),
        ("Changed identities", f"{overall['unique_changed_record_identities']:,}"),
    ]
    return '<div class="grid">' + "".join(
        f'<div class="card"><span class="label">{esc(label)}</span><span class="kpi">{esc(value)}</span></div>'
        for label, value in values
    ) + "</div>"


def raw_vs_excluded(analysis: dict[str, object]) -> str:
    raw = analysis["overall"]
    excluded = raw["excluding_critical_sources"]
    rows = [
        f"<tr><th>All sources (raw)</th><td class=num>{raw['count_before']:,}</td><td class=num>{raw['count_after']:,}</td><td class=num>{raw['absolute_net_change']:+,}</td><td class=num>{pct(raw['percentage_net_change'], True)}</td><td class=num>{raw['new_records']:,}</td><td class=num>{raw['disappeared_records']:,}</td></tr>"
    ]
    note = "No critical source is excluded."
    if excluded:
        names = ", ".join(excluded["excluded_source_ids"])
        rows.append(
            f"<tr><th>Diagnostic excluding {esc(names)}</th><td class=num>{excluded['count_before']:,}</td><td class=num>{excluded['count_after']:,}</td><td class=num>{excluded['absolute_net_change']:+,}</td><td class=num>{pct(excluded['percentage_net_change'], True)}</td><td class=num>{excluded['new_records']:,}</td><td class=num>{excluded['disappeared_records']:,}</td></tr>"
        )
        note = f"Critical source IDs excluded only from the diagnostic row: {names}. Raw totals remain authoritative."
    return f"""<div class=table-wrap><table><caption>Raw totals and diagnostic exclusion view</caption><thead><tr><th>View</th><th class=num>Before</th><th class=num>After</th><th class=num>Net</th><th class=num>Percent</th><th class=num>New</th><th class=num>No longer returned</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><p class=small>{esc(note)}</p>"""


def source_table(analysis: dict[str, object]) -> str:
    rows = []
    for item in analysis["source_health"]:
        reasons = ", ".join(item["alert_reasons"]) or "none"
        rows.append(
            f"<tr><th><code>{esc(item['source_id'])}</code><br><span class=small>{esc(source_label(item['source_id']))}</span></th>"
            f"<td class=num>{item['before_count']:,}</td><td class=num>{item['after_count']:,}</td><td class=num>{item['absolute_delta']:+,}</td>"
            f"<td class=num>{item['new_records']:,}</td><td class=num>{item['disappeared_records']:,}</td><td class=num>{pct(item['retention_rate'])}</td>"
            f"<td class=num>{pct(item['publication_churn'])}</td><td>{tag(item['alert_level'])}<br><span class=small>{esc(reasons)}</span></td></tr>"
        )
    return f"""<div class=table-wrap><table><caption>Source health metrics</caption><thead><tr><th>Source</th><th class=num>Before</th><th class=num>After</th><th class=num>Net</th><th class=num>New</th><th class=num>No longer returned</th><th class=num>Retention</th><th class=num>Churn</th><th>Health and reasons</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""


def diverging_svg(analysis: dict[str, object]) -> str:
    sources = analysis["source_health"]
    width, label_width, half, row_height = 920, 210, 310, 42
    height = 70 + len(sources) * row_height
    maximum = max([1] + [max(row["new_records"], row["disappeared_records"]) for row in sources])
    center = label_width + half
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="div-title div-desc">',
        '<title id="div-title">New and disappeared published records by source</title>',
        '<desc id="div-desc">Blue bars extend right for newly observed records. Red bars extend left for records no longer returned. Exact values appear as text.</desc>',
        f'<line x1="{center}" y1="35" x2="{center}" y2="{height-15}" stroke="#52606d"/>',
    ]
    for index, row in enumerate(sources):
        y = 55 + index * row_height
        new_width = row["new_records"] / maximum * (half - 20)
        gone_width = row["disappeared_records"] / maximum * (half - 20)
        parts.extend([
            f'<text x="5" y="{y+5}" font-size="13">{esc(source_label(row["source_id"]))}</text>',
            f'<rect x="{center-gone_width}" y="{y-12}" width="{gone_width}" height="14" fill="#a53b32"><title>{row["disappeared_records"]} no longer returned</title></rect>',
            f'<rect x="{center}" y="{y+5}" width="{new_width}" height="14" fill="#145da0"><title>{row["new_records"]} newly observed</title></rect>',
            f'<text x="{center-6}" y="{y-1}" text-anchor="end" font-size="12">−{row["disappeared_records"]}</text>',
            f'<text x="{center+6}" y="{y+18}" font-size="12">+{row["new_records"]}</text>',
        ])
    parts.append("</svg>")
    return '<div class=chart>' + "".join(parts) + "</div>"


def history_svg(analyses: list[dict[str, object]], *, include_all: bool, kind: str) -> str:
    selected = analyses if include_all else [item for item in analyses if item["comparison"]["canonical_monthly_comparison"] and item["overall_status"] != "critical"]
    title = "Historical source record counts" if kind == "sources" else "Historical change-type totals"
    if not selected:
        return f'<div class="chart"><p>No eligible canonical month-end comparisons are available for {esc(title.lower())}.</p></div>'
    width, height = 920, 330
    if kind == "sources":
        series_names = sorted({row["source_id"] for item in selected for row in item["source_health"]})
        values = {name: [next(row["after_count"] for row in item["source_health"] if row["source_id"] == name) for item in selected] for name in series_names}
    else:
        series_names = sorted({key for item in selected for key in item["overall"]["change_type_counts"]})
        values = {name: [item["overall"]["change_type_counts"].get(name, 0) for item in selected] for name in series_names}
    maximum = max([1] + [value for rows in values.values() for value in rows])
    colors = ["#145da0", "#a53b32", "#276749", "#8a5a00", "#6b46c1", "#007c83", "#7a3e00", "#52606d", "#b83280", "#2b6cb0"]
    plot_left, plot_top, plot_width, plot_height = 80, 30, 650, 230
    x_step = plot_width / max(1, len(selected) - 1)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="hist-{kind}-title hist-{kind}-desc">', f'<title id="hist-{kind}-title">{esc(title)}</title>', f'<desc id="hist-{kind}-desc">Line chart with exact series values listed in the table below.</desc>', f'<line x1="{plot_left}" y1="{plot_top+plot_height}" x2="{plot_left+plot_width}" y2="{plot_top+plot_height}" stroke="#52606d"/>']
    for series_index, name in enumerate(series_names):
        points = []
        for index, value in enumerate(values[name]):
            x = plot_left + index * x_step
            y = plot_top + plot_height - value / maximum * plot_height
            points.append(f"{x:.1f},{y:.1f}")
        color = colors[series_index % len(colors)]
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"><title>{esc(name)}: {esc(values[name])}</title></polyline>')
        legend_y = 35 + series_index * 25
        parts.append(f'<rect x="755" y="{legend_y-10}" width="14" height="4" fill="{color}"/><text x="775" y="{legend_y}" font-size="11">{esc(name)}</text>')
    for index, item in enumerate(selected):
        x = plot_left + index * x_step
        parts.append(f'<text x="{x}" y="{plot_top+plot_height+22}" text-anchor="middle" font-size="11">{esc(item["comparison"]["comparison_month"])}</text>')
    parts.append("</svg>")
    table_rows = "".join(
        f"<tr><th>{esc(name)}</th>{''.join(f'<td class=num>{value:,}</td>' for value in values[name])}</tr>" for name in series_names
    )
    headers = "".join(f"<th class=num>{esc(item['comparison']['comparison_month'])}</th>" for item in selected)
    return f'<div class=chart>{"".join(parts)}</div><div class=table-wrap><table><caption>{esc(title)} exact values</caption><thead><tr><th>Series</th>{headers}</tr></thead><tbody>{table_rows}</tbody></table></div>'


def alerts_html(analysis: dict[str, object]) -> str:
    if not analysis["alerts"]:
        return "<p>No configured alerts.</p>"
    return "<ul>" + "".join(
        f"<li>{tag(item['severity'])} <code>{esc(item['alert_code'])}</code>"
        f"{' — <code>'+esc(item['source_id'])+'</code>' if item.get('source_id') else ''}: {esc(item['explanation'])}</li>"
        for item in analysis["alerts"]
    ) + "</ul>"


def load_analyses(analysis_dir: Path = change_analysis.ANALYSIS) -> list[dict[str, object]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(analysis_dir.glob("????-??.json"))]


def index_html(analyses: list[dict[str, object]]) -> str:
    latest = analyses[-1]
    comparison = latest["comparison"]
    omitted = [item for item in analyses if not item["comparison"]["canonical_monthly_comparison"] or item["overall_status"] == "critical"]
    history_rows = "".join(
        f'<tr><td><a href="comparisons/{esc(item["comparison"]["comparison_month"])}.html">{esc(item["comparison"]["comparison_month"])}</a></td>'
        f"<td>{esc(item['comparison']['snapshot_from'])} → {esc(item['comparison']['snapshot_to'])}</td><td>{esc(item['comparison']['comparison_kind'])}</td>"
        f"<td>{tag(item['overall_status'])}</td><td>{'yes' if item['comparison']['canonical_monthly_comparison'] else 'no'}</td>"
        f"<td>{'yes' if item['trend_eligibility']['usable_for_global_aggregate_trend'] else 'no'}</td></tr>" for item in analyses
    )
    body = f"""
<p class=notice>{esc(DISCLAIMER)}</p>
<section class="banner {esc(latest['overall_status'])}"><h2>Latest comparison: {tag(latest['overall_status'])}</h2><p><strong>{esc(comparison['snapshot_from'])} → {esc(comparison['snapshot_to'])}</strong>, {comparison['interval_days']} days, <code>{esc(comparison['comparison_kind'])}</code>. Canonical monthly comparison: <strong>{'yes' if comparison['canonical_monthly_comparison'] else 'no'}</strong>.</p>{alerts_html(latest)}</section>
<h2>Latest comparison metrics</h2>{metric_cards(latest['overall'])}
<h2>Raw and diagnostic views</h2>{raw_vs_excluded(latest)}
<h2>Source health</h2>{source_table(latest)}
<h2>New versus no longer returned by source</h2>{diverging_svg(latest)}
<h2>Historical source-count trends</h2><p class=small>Default trend charts include only noncritical canonical month-end-to-month-end comparisons. {len(omitted)} baseline, manual, or critical comparison(s) are omitted by default.</p>
<label><input id=show-all type=checkbox> Reveal noncanonical and critical intervals in historical charts</label>
<div id=canonical-source>{history_svg(analyses, include_all=False, kind='sources')}</div><div id=all-source class=hidden>{history_svg(analyses, include_all=True, kind='sources')}</div>
<h2>Historical change-type totals</h2><div id=canonical-change>{history_svg(analyses, include_all=False, kind='changes')}</div><div id=all-change class=hidden>{history_svg(analyses, include_all=True, kind='changes')}</div>
<h2>Comparison history</h2><div class=table-wrap><table><caption>All analyzed comparisons</caption><thead><tr><th>Month</th><th>Observations</th><th>Kind</th><th>Status</th><th>Canonical</th><th>Global trend eligible</th></tr></thead><tbody>{history_rows}</tbody></table></div>
<script>const toggle=document.getElementById('show-all');toggle.addEventListener('change',()=>{{for(const id of ['all-source','all-change'])document.getElementById(id).classList.toggle('hidden',!toggle.checked);for(const id of ['canonical-source','canonical-change'])document.getElementById(id).classList.toggle('hidden',toggle.checked);}});</script>
"""
    return page("Tampa snapshot-change dashboard", body)


def field_table(analysis: dict[str, object]) -> str:
    rows = []
    for item in sorted(analysis["field_change_concentration"], key=lambda row: (row["source_id"], -(row["affected_retained_rate"] or -1), row["changed_field"])):
        intensity = min(100, round((item["affected_retained_rate"] or 0) * 100))
        rows.append(
            f'<tr><th><code>{esc(item["source_id"])}</code></th><td><code>{esc(item["changed_field"])}</code></td><td>{esc(item["semantic_change_category"])}</td>'
            f'<td class="num heat" style="background:linear-gradient(90deg,#f7d9d5 {intensity}%,transparent {intensity}%);">{item["unique_retained_identities_affected"]:,} / {item["retained_record_denominator"]:,} ({pct(item["affected_retained_rate"])})</td><td>{"MASS REFRESH" if item["mass_refresh_warning"] else "no"}</td></tr>'
        )
    return f'<div class=table-wrap><table><caption>Exact-field change concentration; shading is supplemented by text values</caption><thead><tr><th>Source</th><th>Exact field</th><th>Category</th><th class=num>Affected retained records</th><th>Warning</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def transition_table(rows: list[dict[str, object]], caption: str) -> str:
    if not rows:
        return f"<p>No {esc(caption.lower())} observed.</p>"
    body = "".join(f'<tr><th><code>{esc(row["source_id"])}</code></th><td>{esc(row["old_value"])}</td><td>{esc(row["new_value"])}</td><td class=num>{row["unique_record_count"]:,}</td></tr>' for row in rows)
    return f'<div class=table-wrap><table><caption>{esc(caption)}; no universal ordinal direction is inferred</caption><thead><tr><th>Source</th><th>Earlier value</th><th>Later value</th><th class=num>Unique records</th></tr></thead><tbody>{body}</tbody></table></div>'


def summary_table(rows: list[dict[str, object]], caption: str, unit: str) -> str:
    if not rows:
        return f"<p>No {esc(caption.lower())}.</p>"
    body = "".join(
        f'<tr><th><code>{esc(row["source_id"])}</code></th><td>{esc(row["field"])}</td><td class=num>{row["change_count"]:,}</td><td>{esc(json.dumps(row["classification_counts"], sort_keys=True))}</td><td class=num>{esc(row.get("median_"+unit))}</td><td class=num>{esc(row.get("minimum_"+unit))}</td><td class=num>{esc(row.get("maximum_"+unit))}</td></tr>'
        for row in rows
    )
    return f'<div class=table-wrap><table><caption>{esc(caption)}</caption><thead><tr><th>Source</th><th>Field/type</th><th class=num>Changes</th><th>Classifications</th><th class=num>Median</th><th class=num>Minimum</th><th class=num>Maximum</th></tr></thead><tbody>{body}</tbody></table></div>'


def drilldown_rows(changes: list[dict[str, str]], analysis: dict[str, object]) -> list[dict[str, object]]:
    alert_by_source: dict[str, set[str]] = {}
    for item in analysis["alerts"]:
        if item.get("source_id"):
            alert_by_source.setdefault(item["source_id"], set()).add(item["alert_code"])
    mass = {(row["source_id"], row["changed_field"]) for row in analysis["field_change_concentration"] if row["mass_refresh_warning"]}
    output = []
    for row in changes:
        fields = change_analysis.split_fields(row) or ["(record)"]
        for field in fields:
            old = change_analysis.field_value(row.get("old_value", ""), field) if field != "(record)" else row.get("old_value", "")
            new = change_analysis.field_value(row.get("new_value", ""), field) if field != "(record)" else row.get("new_value", "")
            tags = set(alert_by_source.get(row["source_name"], set()))
            if (row["source_name"], field) in mass:
                tags.add("mass_field_refresh")
            output.append({
                "change_type": row["change_type"], "source_id": row["source_name"], "source_label": source_label(row["source_name"]),
                "record_identity": row["record_identity"], "source_record_id": row.get("source_record_id", ""), "changed_field": field,
                "old_value": change_analysis.display_value(old), "new_value": change_analysis.display_value(new),
                "raw_old_value": row.get("old_value", ""), "raw_new_value": row.get("new_value", ""),
                "source_url": row.get("source_url", "") if change_analysis.valid_url(row.get("source_url", "")) else "",
                "alert_tags": sorted(tags),
            })
    return sorted(output, key=lambda row: (row["source_id"], row["record_identity"], row["change_type"], row["changed_field"]))


def detail_html(analysis: dict[str, object], changes: list[dict[str, str]]) -> str:
    comp = analysis["comparison"]
    quality = analysis["identity_quality"]
    identity_rows = "".join(f"<tr><th>{esc(key)}</th><td>{esc(value if not isinstance(value, list) else json.dumps(value, sort_keys=True))}</td></tr>" for key, value in quality.items())
    data = json.dumps(drilldown_rows(changes, analysis), sort_keys=True, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = f"""
<p><a href="../index.html">← Dashboard index</a></p><p class=notice>{esc(DISCLAIMER)}</p>
<section class="banner {esc(analysis['overall_status'])}"><h2>{tag(analysis['overall_status'])} {esc(comp['snapshot_from'])} → {esc(comp['snapshot_to'])}</h2><p>{comp['interval_days']} days; <code>{esc(comp['comparison_kind'])}</code>; canonical monthly comparison: <strong>{'yes' if comp['canonical_monthly_comparison'] else 'no'}</strong>.</p>{alerts_html(analysis)}</section>
<h2>Overall metrics</h2>{metric_cards(analysis['overall'])}<h2>Raw and diagnostic views</h2>{raw_vs_excluded(analysis)}
<h2>Source health</h2>{source_table(analysis)}
<h2>Exact-field concentration</h2>{field_table(analysis)}
<h2>Status transitions</h2>{transition_table(analysis['status_transitions'],'Status transitions')}
<h2>Phase transitions</h2>{transition_table(analysis['phase_transitions'],'Phase transitions')}
<h2>Planned-date movements</h2>{summary_table(analysis['planned_date_changes']['summaries_by_source'],'Planned-date movement summaries','day_difference')}
<h2>Estimated and actual cost changes</h2><p class=notice>{esc(analysis['cost_changes']['aggregation_warning'])}</p>{summary_table(analysis['cost_changes']['summaries_by_source'],'Cost-change summaries','amount_difference')}
<h2>Identity quality</h2><div class=table-wrap><table><caption>Identity and link diagnostics</caption><tbody>{identity_rows}</tbody></table></div>
<h2>Identity-safe record drill-down</h2><p class=small>Canonical <code>record_identity</code> is the unique key. Native IDs are display values only and duplicate native IDs are never merged.</p>
<div class=controls><label>Search<input id=q type=search aria-label="Search record changes"></label><label>Source<select id=source aria-label="Filter by source"><option value="">All sources</option></select></label><label>Change type<select id=type aria-label="Filter by change type"><option value="">All change types</option></select></label><button id=sort type=button>Sort by identity</button><span id=count aria-live=polite></span></div>
<div class=table-wrap><table class=drill><caption>Filterable record-level published changes</caption><thead><tr><th>Change</th><th>Source</th><th>Canonical identity</th><th>Native ID</th><th>Exact field</th><th>Earlier</th><th>Later</th><th>Source link</th><th>Alerts</th></tr></thead><tbody id=drill-body></tbody></table></div>
<script id=drill-data type="application/json">{data}</script><script>
const rows=JSON.parse(document.getElementById('drill-data').textContent),body=document.getElementById('drill-body'),q=document.getElementById('q'),sf=document.getElementById('source'),tf=document.getElementById('type'),count=document.getElementById('count');let identitySort=false;
const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
for(const value of [...new Set(rows.map(r=>r.source_id))])sf.insertAdjacentHTML('beforeend',`<option>${{escapeHtml(value)}}</option>`);for(const value of [...new Set(rows.map(r=>r.change_type))])tf.insertAdjacentHTML('beforeend',`<option>${{escapeHtml(value)}}</option>`);
function render(){{const needle=q.value.toLowerCase();let shown=rows.filter(r=>(!sf.value||r.source_id===sf.value)&&(!tf.value||r.change_type===tf.value)&&(!needle||JSON.stringify(r).toLowerCase().includes(needle)));if(identitySort)shown=[...shown].sort((a,b)=>a.record_identity.localeCompare(b.record_identity)||a.changed_field.localeCompare(b.changed_field));body.innerHTML=shown.map(r=>`<tr><td>${{escapeHtml(r.change_type)}}</td><td><code>${{escapeHtml(r.source_id)}}</code><br><span class=small>${{escapeHtml(r.source_label)}}</span></td><td><code>${{escapeHtml(r.record_identity)}}</code></td><td>${{escapeHtml(r.source_record_id||'(blank)')}}</td><td><code>${{escapeHtml(r.changed_field)}}</code></td><td title="${{escapeHtml(r.raw_old_value)}}">${{escapeHtml(r.old_value)}}</td><td title="${{escapeHtml(r.raw_new_value)}}">${{escapeHtml(r.new_value)}}</td><td>${{r.source_url?`<a href="${{escapeHtml(r.source_url)}}">Open source</a>`:'Unavailable'}}</td><td>${{escapeHtml(r.alert_tags.join(', ')||'none')}}</td></tr>`).join('');count.textContent=`${{shown.length.toLocaleString()}} of ${{rows.length.toLocaleString()}} field/change rows`;}}q.addEventListener('input',render);sf.addEventListener('change',render);tf.addEventListener('change',render);document.getElementById('sort').addEventListener('click',()=>{{identitySort=!identitySort;render();}});render();
</script>
"""
    return page(f"Comparison {comp['snapshot_from']} to {comp['snapshot_to']}", body, prefix="../")


def build_dashboard(
    *,
    analysis_dir: Path = change_analysis.ANALYSIS,
    changes_dir: Path = change_analysis.CHANGES,
    output_dir: Path = DASHBOARD,
) -> dict[str, object]:
    analyses = load_analyses(analysis_dir)
    if not analyses:
        raise FileNotFoundError(f"No analysis JSON files found under {analysis_dir}")
    detail_dir = output_dir / "comparisons"
    pages = []
    for analysis in analyses:
        month = analysis["comparison"]["comparison_month"]
        changes = change_analysis.read_csv(changes_dir / f"{month}.csv")
        path = detail_dir / f"{month}.html"
        change_analysis.atomic_text(path, detail_html(analysis, changes))
        pages.append(path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path))
    index_path = output_dir / "index.html"
    change_analysis.atomic_text(index_path, index_html(analyses))
    return {
        "comparison_count": len(analyses),
        "index": index_path.relative_to(ROOT).as_posix() if index_path.is_relative_to(ROOT) else str(index_path),
        "detail_pages": pages,
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(build_dashboard(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
