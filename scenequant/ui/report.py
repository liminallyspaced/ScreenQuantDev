# Report rendering: analysis results -> JSON-safe dict -> console text and a
# self-contained dark-theme HTML file. Pure presentation, no bpy, never writes
# to the scene. format_text/write_html consume ONLY the build_report_data dict.

import html
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

SEVERITY_ORDER = ("critical", "high", "medium", "info")
SEVERITY_COLORS = {
    "critical": "#ff6b81",
    "high": "#ffa94d",
    "medium": "#ffd43b",
    "info": "#74c0fc",
}
GRADE_COLORS = {"A": "#51cf66", "B": "#94d82d", "C": "#ffd43b",
                "D": "#ffa94d", "F": "#ff6b81"}
FALLBACK_COLOR = "#868e96"
MAX_IMAGE_ROWS = 40       # HTML memory table cap
MAX_OBJECT_ROWS = 20
MAX_TEXT_IMAGE_ROWS = 12  # console output cap
MAX_TARGET_ROWS = 40
MAX_SKIP_ROWS = 40
MAX_TEXT_SKIP_ROWS = 20

# fix_hint carries an operator idname; reports show the human button label.
FIX_LABELS = {
    "scenequant.analyze": "Analyze Scene",
    "scenequant.detect_vram": "Detect VRAM",
    "scenequant.autotune": "Auto-Tune Settings",
    "scenequant.fit_budget": "Fit to VRAM Budget",
    "scenequant.make_it_fast": "Make it Fast",
    "scenequant.probe_sample_knee": "Probe Sample Knee",
    "scenequant.verify_render": "Verify Render",
    "scenequant.dedup": "Merge Duplicate Data",
    "scenequant.trim_offscreen": "Trim Off-screen & Distant",
    "scenequant.quantize_textures": "Quantize Textures",
    "scenequant.draft_toggle": "Draft Mode",
    "scenequant.cull_paranoid": "Enable Camera Cull",
    "scenequant.revert_all": "Revert All Changes",
    "scenequant.purge_backups": "Purge Backups",
    "scenequant.export_report": "Export Report",
}


def fix_label(idname):
    return FIX_LABELS.get(idname, idname)


def build_report_data(grade, findings, mem, plan_or_none,
                      journal_count, vram_mb, blender_version):
    """The report dict. Deliberately carries no per-object coverage block:
    nothing here or in the panels renders it, and it was serialized into every
    saved .blend — megabytes of dead JSON on a large scene."""
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grade": str(grade) if grade is not None else "?",
        "blender_version": _version_str(blender_version),
        "vram_mb": vram_mb if isinstance(vram_mb, (int, float)) else None,
        "journal_count": int(journal_count or 0),
        "findings": [_jsonable(finding) for finding in findings or []],
        "memory": _jsonable(mem) if mem is not None else {},
        "plan": _jsonable(plan_or_none) if plan_or_none is not None else None,
    }


def _jsonable(value):
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [_jsonable(item) for item in sorted(value, key=str)]
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return str(value)


def _version_str(blender_version):
    if isinstance(blender_version, str):
        return blender_version
    try:
        return ".".join(str(part) for part in blender_version)
    except TypeError:
        return str(blender_version)


def _fmt_mb(value):
    if not isinstance(value, (int, float)):
        return "?"
    return f"{value:,.1f} MB"


def _severity_rank(finding):
    severity = finding.get("severity", "info")
    return SEVERITY_ORDER.index(severity) if severity in SEVERITY_ORDER else len(SEVERITY_ORDER)


def _sorted_findings(findings):
    return sorted(findings, key=_severity_rank)


def _top_mb_entries(mb_map, limit):
    entries = [(name, mb) for name, mb in mb_map.items()
               if isinstance(mb, (int, float))]
    entries.sort(key=lambda pair: pair[1], reverse=True)
    return entries[:limit], max(len(entries) - limit, 0)


def _all_caveats(data):
    """Plan caveats + estimator caveats, deduped preserving order."""
    seen = []
    plan = data.get("plan") or {}
    for caveat in list(plan.get("caveats") or []) + list(data.get("caveats") or []):
        caveat = str(caveat)
        if caveat not in seen:
            seen.append(caveat)
    return seen


def _iter_skip_entries(skip_reasons):
    """Normalize the payload's skip_reasons ({'scan': [...], 'apply': [...]}
    dict, or a bare list) into {'source','name','reason'} dicts."""
    if isinstance(skip_reasons, dict):
        groups = [skip_reasons.get(key) or [] for key in ("scan", "apply")]
    elif isinstance(skip_reasons, list):
        groups = [skip_reasons]
    else:
        return
    for group in groups:
        for entry in group:
            if isinstance(entry, dict):
                yield entry


def _target_rows(targets):
    """(rows, uncovered_count): images with a coverage-derived target, largest
    first; targets of 0 mean no coverage-tracked user resolved."""
    rows = [(name, int(px)) for name, px in (targets or {}).items()
            if isinstance(px, (int, float)) and px > 0]
    rows.sort(key=lambda pair: pair[1], reverse=True)
    uncovered = sum(1 for px in (targets or {}).values()
                    if not isinstance(px, (int, float)) or px <= 0)
    return rows, uncovered


# ---------------------------------------------------------------- text report

def format_text(data):
    lines = []
    lines += _text_header(data)
    lines += _text_findings(data.get("findings") or [])
    lines += _text_plan(data.get("plan"))
    lines += _text_caveats(_all_caveats(data))
    lines += _text_targets(data.get("per_image_targets") or {})
    lines += _text_memory(data.get("memory") or {})
    lines += _text_skips(data.get("skip_reasons"))
    lines += _text_journal(data.get("journal_tags") or [])
    return "\n".join(lines)


def _text_header(data):
    vram = data.get("vram_mb")
    vram_txt = f"VRAM {vram:,.0f} MB" if isinstance(vram, (int, float)) else "VRAM not detected"
    lines = [
        f"SceneQuant report — grade {data.get('grade', '?')}",
        (f"Blender {data.get('blender_version', '?')} · {vram_txt} · "
         f"journal entries: {data.get('journal_count', 0)}"),
    ]
    mem = data.get("memory") or {}
    if mem:
        lines.append(
            f"Estimated render memory: {_fmt_mb(mem.get('total_mb'))} "
            f"(textures {_fmt_mb(mem.get('texture_mb'))}, "
            f"geometry {_fmt_mb(mem.get('geometry_mb'))}, "
            f"{mem.get('render_triangles', 0):,} triangles)")
    return lines


def _text_findings(findings):
    if not findings:
        return ["", "Findings: none — scene looks clean."]
    lines = ["", f"Findings ({len(findings)}):"]
    for finding in _sorted_findings(findings):
        severity = finding.get("severity", "info").upper()
        lines.append(f"  [{severity}] {finding.get('code', '?')} — {finding.get('message', '')}")
        detail = []
        if finding.get("fix_hint"):
            detail.append(f"fix: {fix_label(finding['fix_hint'])}")
        if finding.get("est_savings_mb"):
            detail.append(f"est {_fmt_mb(finding['est_savings_mb'])}")
        items = finding.get("items") or []
        if items:
            detail.append("items: " + ", ".join(str(item) for item in items))
        if detail:
            lines.append("      " + " · ".join(detail))
    return lines


def _text_plan(plan):
    if not plan:
        return []
    verdict = "FITS" if plan.get("fits") else "OVER BUDGET"
    lines = ["", (f"Plan: {_fmt_mb(plan.get('est_before_mb'))} → "
                  f"{_fmt_mb(plan.get('est_after_mb'))} "
                  f"(budget {_fmt_mb(plan.get('budget_mb'))}) — {verdict}")]
    shortfall = plan.get("shortfall_mb")
    if not plan.get("fits") and isinstance(shortfall, (int, float)) and shortfall > 0:
        lines.append(f"  Still {_fmt_mb(shortfall)} over the headroom threshold "
                     "after every rung.")
    for index, action in enumerate(plan.get("actions") or [], start=1):
        lines.append(f"  {index}. [{action.get('kind', '?'):<14}] {action.get('label', '')} "
                     f"(visual cost {action.get('visual_cost', '?')})")
    return lines


def _text_caveats(caveats):
    if not caveats:
        return []
    lines = ["", "Caveats (estimator gaps and excluded savings):"]
    lines += [f"  - {caveat}" for caveat in caveats]
    return lines


def _text_targets(targets):
    rows, uncovered = _target_rows(targets)
    if not rows:
        return []
    lines = ["", "Quantize targets (needed edge px per image):"]
    for name, px in rows[:MAX_TEXT_IMAGE_ROWS]:
        lines.append(f"  {px:>6} px  {name}")
    more = len(rows) - MAX_TEXT_IMAGE_ROWS
    if more > 0:
        lines.append(f"  … +{more} more images")
    if uncovered:
        lines.append(f"  ({uncovered} image(s) kept: no coverage-tracked user)")
    return lines


def _text_skips(skip_reasons):
    entries = list(_iter_skip_entries(skip_reasons))
    if not entries:
        return []
    lines = ["", f"Skipped items ({len(entries)}):"]
    for entry in entries[:MAX_TEXT_SKIP_ROWS]:
        lines.append(f"  [{entry.get('source', '?')}] {entry.get('name', '?')} "
                     f"— {entry.get('reason', '')}")
    more = len(entries) - MAX_TEXT_SKIP_ROWS
    if more > 0:
        lines.append(f"  … +{more} more")
    return lines


def _text_journal(journal_tags):
    usable = [tag for tag in journal_tags
              if isinstance(tag, dict) and tag.get("tag")]
    if not usable:
        return []
    summary = " · ".join(f"{tag['tag']} ({tag.get('entries', 0)})" for tag in usable)
    return ["", f"Journal tags: {summary}"]


def _text_memory(mem):
    per_image = mem.get("per_image_mb") or {}
    if not per_image:
        return []
    rows, more = _top_mb_entries(per_image, MAX_TEXT_IMAGE_ROWS)
    lines = ["", "Top images by estimated memory:"]
    for name, mb in rows:
        lines.append(f"  {mb:>9,.1f} MB  {name}")
    if more:
        lines.append(f"  … +{more} more images")
    return lines


# ---------------------------------------------------------------- HTML report

_CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{background:#101216;color:#e6e8eb;font:14px/1.5 system-ui,'Segoe UI',sans-serif;
  margin:0;padding:2rem 1.2rem}
main{max-width:960px;margin:0 auto}
h1{font-size:1.35rem;margin:0}
h2{font-size:.95rem;margin:1.9rem 0 .6rem;color:#aeb4bd;text-transform:uppercase;
  letter-spacing:.06em}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{text-align:left;padding:.35rem .6rem;border-bottom:1px solid #23262d;vertical-align:top}
th{color:#8a919c;font-weight:600}
.badge{display:inline-flex;align-items:center;justify-content:center;width:3.4rem;
  height:3.4rem;border-radius:.7rem;font-size:1.9rem;font-weight:700;color:#101216}
.summary{display:flex;gap:.8rem;align-items:stretch;flex-wrap:wrap;margin:1rem 0 0}
.tile{background:#181b20;border:1px solid #23262d;border-radius:.6rem;
  padding:.55rem .9rem;font-size:.8rem;color:#8a919c}
.tile b{display:block;font-size:1.05rem;color:#e6e8eb;font-variant-numeric:tabular-nums}
.sev{font-weight:700;text-transform:uppercase;font-size:.72rem;letter-spacing:.04em}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.bar{background:#23262d;border-radius:3px;height:10px;min-width:120px;overflow:hidden}
.fill{background:linear-gradient(90deg,#4dabf7,#9775fa);height:100%}
.muted{color:#8a919c}
.fits-yes{color:#51cf66;font-weight:700}
.fits-no{color:#ff6b81;font-weight:700}
.scroll{overflow-x:auto}
footer{margin-top:2.2rem;color:#8a919c;font-size:.78rem}
"""


def write_html(path, data):
    document = _render_html(data)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return path


def _render_html(data):
    body = "".join([
        _html_header(data),
        _html_findings(data.get("findings") or []),
        _html_plan(data.get("plan")),
        _html_caveats(_all_caveats(data)),
        _html_targets(data.get("per_image_targets") or {}),
        _html_memory(data.get("memory") or {}),
        _html_skips(data.get("skip_reasons")),
        _html_footer(data),
    ])
    return ("<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>SceneQuant Report</title>"
            f"<style>{_CSS}</style></head><body><main>{body}</main></body></html>\n")


def _html_header(data):
    grade = html.escape(str(data.get("grade", "?")))
    color = GRADE_COLORS.get(data.get("grade"), FALLBACK_COLOR)
    vram = data.get("vram_mb")
    vram_txt = f"{vram:,.0f} MB" if isinstance(vram, (int, float)) else "not detected"
    mem = data.get("memory") or {}
    tiles = [
        ("Est. render memory", _fmt_mb(mem.get("total_mb"))),
        ("Textures", _fmt_mb(mem.get("texture_mb"))),
        ("Geometry", _fmt_mb(mem.get("geometry_mb"))),
        ("Triangles", f"{mem.get('render_triangles', 0):,}"),
        ("GPU VRAM", vram_txt),
    ]
    if isinstance(mem.get("overhead_mb"), (int, float)):
        tiles.insert(3, ("Runtime overhead", _fmt_mb(mem.get("overhead_mb"))))
    tile_html = "".join(f"<div class=\"tile\">{html.escape(caption)}<b>{html.escape(value)}</b></div>"
                        for caption, value in tiles)
    return (f"<div style=\"display:flex;gap:1rem;align-items:center\">"
            f"<span class=\"badge\" style=\"background:{color}\">{grade}</span>"
            f"<div><h1>SceneQuant Report</h1>"
            f"<div class=\"muted\">Blender {html.escape(str(data.get('blender_version', '?')))}"
            f" · generated {html.escape(str(data.get('generated', '')))}</div></div></div>"
            f"<div class=\"summary\">{tile_html}</div>")


def _html_findings(findings):
    if not findings:
        return "<h2>Findings</h2><p class=\"muted\">None — scene looks clean.</p>"
    rows = []
    for finding in _sorted_findings(findings):
        severity = str(finding.get("severity", "info"))
        color = SEVERITY_COLORS.get(severity, FALLBACK_COLOR)
        items = ", ".join(str(item) for item in finding.get("items") or [])
        savings = finding.get("est_savings_mb") or 0
        rows.append(
            f"<tr><td><span class=\"sev\" style=\"color:{color}\">{html.escape(severity)}</span></td>"
            f"<td>{html.escape(str(finding.get('code', '')))}</td>"
            f"<td>{html.escape(str(finding.get('message', '')))}"
            + (f"<div class=\"muted\">{html.escape(items)}</div>" if items else "")
            + f"</td><td>{html.escape(fix_label(str(finding.get('fix_hint') or '')))}</td>"
            f"<td class=\"num\">{savings:,.0f}</td></tr>")
    return ("<h2>Findings</h2><div class=\"scroll\"><table>"
            "<tr><th>Severity</th><th>Code</th><th>Finding</th><th>Fix</th>"
            "<th class=\"num\">Est. MB</th></tr>" + "".join(rows) + "</table></div>")


def _html_plan(plan):
    if not plan:
        return ""
    fits = bool(plan.get("fits"))
    verdict = ("<span class=\"fits-yes\">fits budget</span>" if fits
               else "<span class=\"fits-no\">over budget</span>")
    rows = []
    for index, action in enumerate(plan.get("actions") or [], start=1):
        rows.append(
            f"<tr><td class=\"num\">{index}</td>"
            f"<td>{html.escape(str(action.get('kind', '')))}</td>"
            f"<td>{html.escape(str(action.get('label', '')))}</td>"
            f"<td class=\"num\">{(action.get('est_savings_mb') or 0):,.0f}</td>"
            f"<td class=\"num\">{html.escape(str(action.get('visual_cost', '')))}</td></tr>")
    shortfall = plan.get("shortfall_mb")
    shortfall_txt = ""
    if not fits and isinstance(shortfall, (int, float)) and shortfall > 0:
        shortfall_txt = (f" · still <b>{_fmt_mb(shortfall)}</b> over the "
                         "headroom threshold after every rung")
    summary = (f"<p>{_fmt_mb(plan.get('est_before_mb'))} → "
               f"<b>{_fmt_mb(plan.get('est_after_mb'))}</b> · "
               f"budget {_fmt_mb(plan.get('budget_mb'))} · {verdict}{shortfall_txt}</p>")
    return ("<h2>Optimization Plan</h2>" + summary
            + "<div class=\"scroll\"><table><tr><th class=\"num\">#</th><th>Action</th>"
              "<th>Detail</th><th class=\"num\">Saves MB</th>"
              "<th class=\"num\">Visual cost</th></tr>" + "".join(rows) + "</table></div>")


def _html_caveats(caveats):
    if not caveats:
        return ""
    items = "".join(f"<li>{html.escape(caveat)}</li>" for caveat in caveats)
    return ("<h2>Caveats</h2><p class=\"muted\">Estimator gaps and savings the "
            f"solver excluded on purpose.</p><ul>{items}</ul>")


def _html_targets(targets):
    rows_data, uncovered = _target_rows(targets)
    if not rows_data:
        return ""
    rows = []
    for name, px in rows_data[:MAX_TARGET_ROWS]:
        rows.append(f"<tr><td>{html.escape(str(name))}</td>"
                    f"<td class=\"num\">{px:,}</td></tr>")
    more = len(rows_data) - MAX_TARGET_ROWS
    if more > 0:
        rows.append(f"<tr><td colspan=\"2\" class=\"muted\">… +{more} more images</td></tr>")
    if uncovered:
        rows.append(f"<tr><td colspan=\"2\" class=\"muted\">{uncovered} image(s) "
                    "kept at full size: no coverage-tracked user</td></tr>")
    return ("<h2>Quantize Targets</h2><p class=\"muted\">Needed long-edge "
            "resolution per image (camera coverage, atlas-corrected).</p>"
            "<div class=\"scroll\"><table><tr><th>Image</th>"
            "<th class=\"num\">Needed px</th></tr>" + "".join(rows) + "</table></div>")


def _html_skips(skip_reasons):
    entries = list(_iter_skip_entries(skip_reasons))
    if not entries:
        return ""
    rows = []
    for entry in entries[:MAX_SKIP_ROWS]:
        rows.append(f"<tr><td>{html.escape(str(entry.get('source', '?')))}</td>"
                    f"<td>{html.escape(str(entry.get('name', '?')))}</td>"
                    f"<td>{html.escape(str(entry.get('reason', '')))}</td></tr>")
    more = len(entries) - MAX_SKIP_ROWS
    if more > 0:
        rows.append(f"<tr><td colspan=\"3\" class=\"muted\">… +{more} more</td></tr>")
    return ("<h2>Skipped Items</h2><p class=\"muted\">What SceneQuant refused "
            "to touch, and why — skips are loud by design.</p>"
            "<div class=\"scroll\"><table><tr><th>Stage</th><th>Item</th>"
            "<th>Reason</th></tr>" + "".join(rows) + "</table></div>")


def _html_memory(mem):
    parts = []
    per_image = mem.get("per_image_mb") or {}
    if per_image:
        parts.append(_html_mb_table("Memory by Image", per_image, MAX_IMAGE_ROWS, "images"))
    per_object = mem.get("per_object_geo_mb") or {}
    if per_object:
        parts.append(_html_mb_table("Geometry by Object", per_object, MAX_OBJECT_ROWS, "objects"))
    return "".join(parts)


def _html_mb_table(title, mb_map, limit, noun):
    rows_data, more = _top_mb_entries(mb_map, limit)
    largest = rows_data[0][1] if rows_data and rows_data[0][1] > 0 else 1.0
    rows = []
    for name, mb in rows_data:
        width = max(min(mb / largest * 100.0, 100.0), 0.0)
        rows.append(
            f"<tr><td>{html.escape(str(name))}</td>"
            f"<td class=\"num\">{mb:,.1f}</td>"
            f"<td><div class=\"bar\"><div class=\"fill\" style=\"width:{width:.1f}%\"></div></div></td></tr>")
    if more:
        rows.append(f"<tr><td colspan=\"3\" class=\"muted\">… +{more} more {noun}</td></tr>")
    return (f"<h2>{html.escape(title)}</h2><div class=\"scroll\"><table>"
            f"<tr><th>Name</th><th class=\"num\">MB</th><th>Share of largest</th></tr>"
            + "".join(rows) + "</table></div>")


def _html_footer(data):
    tags = [tag for tag in data.get("journal_tags") or []
            if isinstance(tag, dict) and tag.get("tag")]
    tags_txt = ""
    if tags:
        summary = " · ".join(f"{tag['tag']} ({tag.get('entries', 0)})" for tag in tags)
        tags_txt = f" Tags: {html.escape(summary)} ·"
    return (f"<footer>Journal entries recorded: {data.get('journal_count', 0)} ·"
            f"{tags_txt} SceneQuant keeps every change reversible via Revert All.</footer>")
