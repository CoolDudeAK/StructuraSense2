"""Printable inspection report (HTML) and CSV exports."""
import csv
import html
import io
import json
import time

from .. import db
from . import health, impact

DISCLAIMER = ("StructuraSense is a decision-support prototype. Scores and alerts show CHANGES in measured response; they do not "
              "certify safety, locate cracks exactly or replace an engineer's inspection. Bands (80/60/40) are the team's own "
              "proposed thresholds pending field calibration.")


def _t(ms):
    return time.strftime("%d %b %Y, %H:%M", time.localtime(ms / 1000)) if ms else "-"


def _e(x):
    return html.escape("" if x is None else str(x))


def build_html(sid, user_name=""):
    s = db.one("SELECT * FROM structures WHERE id=?", (sid,))
    h = health.latest(sid)
    zones = {z["id"]: z["name"] for z in db.q("SELECT id,name FROM zones WHERE structure_id=?", (sid,))}
    alerts = db.q("SELECT * FROM alerts WHERE structure_id=? AND status IN ('open','acknowledged') ORDER BY ts_ms DESC", (sid,))
    cracks = db.q("SELECT * FROM crack_analyses WHERE structure_id=? ORDER BY ts_ms DESC LIMIT 8", (sid,))
    tasks = db.q("SELECT * FROM maintenance_tasks WHERE structure_id=? AND status IN ('proposed','approved','in_progress') ORDER BY priority, created_ms DESC", (sid,))
    mix = db.q("SELECT r.source s, COUNT(*) n FROM readings r JOIN devices d ON d.id=r.device_id WHERE d.structure_id=? AND r.ts_ms>? GROUP BY r.source",
               (sid, db.now_ms() - 86400_000))
    rows = []
    if h:
        for k, c in h["components"].items():
            rows.append(f"<tr><td>{_e(health.LABELS[k])}</td><td>{'-' if c['score'] is None else c['score']}</td><td>{int(c['weight']*100)}%</td>"
                        f"<td>{_e('; '.join(i['label'] for i in c['items']) or 'No data')}</td></tr>")
    zrows = "".join(f"<tr><td>{_e(zones.get(z))}</td><td>{'-' if v['score'] is None else v['score']}</td><td>{_e(v['band'])}</td></tr>"
                    for z, v in (h["zones"] if h else {}).items())
    arows = "".join(f"<tr><td>{_e(a['severity'])}</td><td>{_e(a['title'])}</td><td>{_e(zones.get(a['zone_id'], '-'))}</td><td>{_t(a['ts_ms'])}</td>"
                    f"<td>{_e(a['status'])}</td><td>{_e(a['origin'])}</td></tr>" for a in alerts) or "<tr><td colspan=6>No open alerts.</td></tr>"
    crows = "".join(f"<tr><td>{_t(c['ts_ms'])}</td><td>{_e(zones.get(c['zone_id'], '-'))}</td><td>{'yes' if c['crack_detected'] else 'no'}</td>"
                    f"<td>{'-' if c['max_width_mm'] is None else f'{c['max_width_mm']:.2f} mm'}</td><td>{_e(c['severity'])}</td><td>{_e(c['method'])}</td></tr>"
                    for c in cracks) or "<tr><td colspan=6>No crack images analysed yet.</td></tr>"
    trows = "".join(f"<tr><td>{_e(t['priority'])}</td><td>{_e(t['title'])}</td><td>{_e(t['status'])}</td><td>{_e(t['proposed_by'])}</td>"
                    f"<td>{_e(t['signed_off_by'] or '-')}</td></tr>" for t in tasks) or "<tr><td colspan=5>No open tasks.</td></tr>"
    prov = ", ".join(f"{m['s']}: {m['n']} readings" for m in mix) or "no readings in the last 24 h"
    b = impact.baseline(sid) if impact.supports(sid) else None
    impact_html = ""
    if b:
        tr = impact.trials(sid, limit=5)
        impact_html = ("<h2>Impact trials (specimen rig)</h2><p>Baseline from %d intact trials (%s). Latest trials:</p><table><tr><th>When</th><th>Condition</th>"
                       "<th>Score %%</th><th>Status</th><th>Data</th></tr>%s</table>" % (
                           b["num_trials"], _e(impact.LABELS.get(b["source"])), "".join(
                               f"<tr><td>{_t(t['ts_ms'])}</td><td>{_e(t['condition'])}</td><td>{'-' if t['anomaly_score'] is None else round(t['anomaly_score'],1)}</td>"
                               f"<td>{_e(t['status'])}</td><td>{_e(t['data_source'])}</td></tr>" for t in tr)))
    demo = "<p class=warn><b>Demo asset:</b> this structure is fictional and its data is simulated.</p>" if s["is_demo"] else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Inspection report - {_e(s['name'])}</title>
<style>body{{font:14px/1.5 system-ui,Segoe UI,Arial;margin:32px auto;max-width:900px;color:#14212b;padding:0 16px}}
h1{{font-size:22px;margin:0}}h2{{font-size:16px;margin:24px 0 6px;border-bottom:2px solid #14212b;padding-bottom:3px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #c9ced1;padding:4px 8px;text-align:left;vertical-align:top}}
th{{background:#eceeef}}.score{{font-size:44px;font-weight:700}}.warn{{background:#fff4d6;padding:8px 12px;border-left:4px solid #e8b200}}
.sign{{margin-top:36px;display:flex;gap:40px}}.sign div{{flex:1;border-top:1px solid #14212b;padding-top:4px;font-size:12px}}
@media print{{body{{margin:0}}}}</style></head><body>
<h1>Structural health report - {_e(s['name'])}</h1>
<p>{_e(s['id'])} - {_e(s['kind'])} - {_e(s['location'] or '')} - generated {_t(db.now_ms())}{(' by ' + _e(user_name)) if user_name else ''}</p>{demo}
<p class=warn>{_e(DISCLAIMER)}</p>
<h2>Structural Health Index</h2>
<p><span class=score>{'-' if not h or h['score'] is None else round(h['score'])}</span> / 100 &nbsp; <b>{_e(h['band'] if h else 'No data')}</b>
 &nbsp; (data coverage {int((h['coverage'] if h else 0)*100)}%, method {_e(h['method'] if h else '-')}, data mode: {_e(s['data_mode'])})</p>
<table><tr><th>Component</th><th>Score</th><th>Weight</th><th>Evidence</th></tr>{''.join(rows)}</table>
<h2>Zones</h2><table><tr><th>Zone</th><th>Score</th><th>Band</th></tr>{zrows}</table>
<h2>Open alerts</h2><table><tr><th>Severity</th><th>Alert</th><th>Zone</th><th>Raised</th><th>Status</th><th>Origin</th></tr>{arows}</table>
<h2>Crack image analyses</h2><table><tr><th>When</th><th>Zone</th><th>Crack</th><th>Max width</th><th>Severity</th><th>Method</th></tr>{crows}</table>
{impact_html}
<h2>Maintenance proposals</h2><table><tr><th>Priority</th><th>Task</th><th>Status</th><th>Proposed by</th><th>Signed off by</th></tr>{trows}</table>
<h2>Data provenance (last 24 h)</h2><p>{_e(prov)}. sim = simulated, live = real hardware, file = imported file.</p>
<div class=sign><div>Inspecting engineer (name, signature)</div><div>Date</div></div></body></html>"""


def readings_csv(sid, hours=24):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp_iso", "ts_ms", "structure_id", "device_id", "value", "unit", "source"])
    since = db.now_ms() - int(hours * 3600_000)
    for r in db.q("SELECT r.ts_ms,r.device_id,r.value,r.source,d.unit FROM readings r JOIN devices d ON d.id=r.device_id "
                  "WHERE d.structure_id=? AND r.ts_ms>? ORDER BY r.ts_ms LIMIT 200000", (sid, since)):
        w.writerow([time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(r["ts_ms"] / 1000)) + "Z", r["ts_ms"], sid,
                    r["device_id"], r["value"], r["unit"], r["source"]])
    return buf.getvalue()
