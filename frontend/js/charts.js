// Hand-drawn SVG charts (no libraries, works offline). Colours come from CSS variables.
import { h, fmt } from './ui.js';
const NS = 'http://www.w3.org/2000/svg';
export function s(tag, attrs, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) e.setAttribute(k, v);
  kids.flat().forEach(k => k != null && e.append(k.nodeType ? k : document.createTextNode(k)));
  return e;
}
const nice = (min, max, n = 4) => {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(v => v >= step0);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step, t = [];
  for (let v = lo; v <= hi + step / 2; v += step) t.push(+v.toFixed(10));
  return { lo, hi, ticks: t };
};

/** series: [{name, color, points:[[x,y,(source)]], dashed, fill}]. opts: xType 'time'|'num', refs:[{y,label,color}], band:{lo,hi}, height, yLabel, xLabel, yMin, yMax */
export function lineChart(series, o = {}) {
  const W = 640, Hh = o.height || 220, m = { l: 46, r: 12, t: 10, b: 28 };
  const svg = s('svg', { viewBox: `0 0 ${W} ${Hh}`, class: 'chart', role: 'img', 'aria-label': o.label || 'chart', preserveAspectRatio: 'xMidYMid meet' });
  const all = series.flatMap(x => x.points);
  if (!all.length) { svg.append(s('text', { x: W / 2, y: Hh / 2, 'text-anchor': 'middle', class: 'ax' }, 'No data in this period')); return wrap(svg, series, o); }
  let xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  (o.refs || []).forEach(r => ys.push(r.y));
  if (o.band) ys.push(o.band.lo, o.band.hi);
  let xmin = Math.min(...xs), xmax = Math.max(...xs); if (xmin === xmax) xmax = xmin + 1;
  const ny = nice(o.yMin ?? Math.min(...ys), o.yMax ?? Math.max(...ys));
  const X = v => m.l + (v - xmin) / (xmax - xmin) * (W - m.l - m.r);
  const Y = v => Hh - m.b - (v - ny.lo) / (ny.hi - ny.lo) * (Hh - m.t - m.b);
  ny.ticks.forEach(t => { svg.append(s('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: 'grid' }), s('text', { x: m.l - 6, y: Y(t) + 4, 'text-anchor': 'end', class: 'ax' }, +t.toFixed(2))); });
  const nx = o.xType === 'time' && (xmax - xmin) > 36e5 * 20 ? 3 : 5;
  for (let i = 0; i <= nx; i++) {
    const v = xmin + (xmax - xmin) * i / nx;
    svg.append(s('text', { x: X(v), y: Hh - 8, 'text-anchor': i === 0 ? 'start' : i === nx ? 'end' : 'middle', class: 'ax' }, o.xType === 'time' ? ((xmax - xmin) > 36e5 * 20 ? fmt.dh(v) : (xmax - xmin) > 36e5 ? fmt.hm(v) : fmt.time(v)) : (+v.toFixed(2))));
  }
  if (o.band) svg.append(s('rect', { x: m.l, width: W - m.l - m.r, y: Y(o.band.hi), height: Math.abs(Y(o.band.lo) - Y(o.band.hi)), class: 'band' }));
  (o.refs || []).forEach(r => svg.append(s('line', { x1: m.l, x2: W - m.r, y1: Y(r.y), y2: Y(r.y), stroke: r.color || 'var(--warn)', 'stroke-dasharray': '5 4', 'stroke-width': 1.2 }),
    r.label ? s('text', { x: W - m.r - 2, y: Y(r.y) - 4, 'text-anchor': 'end', class: 'ax', fill: r.color || 'var(--warn)' }, r.label) : null));
  series.forEach(sr => {
    if (!sr.points.length) return;
    const pts = sr.points.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`);
    if (sr.fill) svg.append(s('polygon', { points: `${X(sr.points[0][0])},${Y(ny.lo)} ${pts.join(' ')} ${X(sr.points.at(-1)[0])},${Y(ny.lo)}`, fill: sr.color, opacity: .12 }));
    svg.append(s('polyline', { points: pts.join(' '), fill: 'none', stroke: sr.color, 'stroke-width': sr.width || 1.8, 'stroke-linejoin': 'round', 'stroke-dasharray': sr.dashed ? '6 4' : null }));
    if (sr.points.length < 80 || sr.dots) sr.points.forEach(p => svg.append(s('circle', { cx: X(p[0]), cy: Y(p[1]), r: 2.6, fill: p[2] === 'live' ? 'var(--live)' : p[2] === 'sim' ? 'var(--sim)' : sr.color, stroke: 'var(--panel)', 'stroke-width': 1 }, s('title', {}, `${o.xType === 'time' ? fmt.dt(p[0]) : p[0]}: ${(+p[1]).toFixed(2)}${p[2] ? ' (' + p[2] + ')' : ''}`))));
  });
  return wrap(svg, series, o);
}
function wrap(svg, series, o) {
  const named = series.filter(x => x.name);
  return h('figure', { class: 'fig' }, o.title ? h('figcaption', null, o.title) : null, svg,
    named.length > 1 || o.legend ? h('div', { class: 'legend' }, named.map(x => h('span', null, h('i', { style: { background: x.color } }), x.name))) : null);
}

/** Spectrum with optional baseline overlay: data {f:[], a:[]} */
export function spectrumChart(cur, base, o = {}) {
  const sr = [];
  if (base) sr.push({ name: 'Baseline', color: 'var(--muted)', points: base.f.map((f, i) => [f, base.a[i]]), dashed: true });
  sr.push({ name: 'This capture', color: 'var(--accent)', points: cur.f.map((f, i) => [f, cur.a[i]]), fill: true });
  return lineChart(sr, { ...o, xType: 'num', legend: !!base, yMin: 0 });
}

export function sparkline(vals, color = 'var(--ink)', w = 110, hgt = 30) {
  const svg = s('svg', { viewBox: `0 0 ${w} ${hgt}`, class: 'spark', 'aria-hidden': 'true' });
  if (!vals || vals.length < 2) return svg;
  const mn = Math.min(...vals), mx = Math.max(...vals), sp = mx - mn || 1;
  svg.append(s('polyline', { points: vals.map((v, i) => `${(i / (vals.length - 1) * (w - 4) + 2).toFixed(1)},${(hgt - 3 - (v - mn) / sp * (hgt - 6)).toFixed(1)}`).join(' '), fill: 'none', stroke: color, 'stroke-width': 1.6, 'stroke-linejoin': 'round' }));
  return svg;
}

export function barChart(items, o = {}) { // items [{label, value, color, sub}]
  const max = o.max ?? Math.max(1, ...items.map(i => i.value));
  return h('div', { class: 'bars' }, items.map(i => h('div', { class: 'bar-row' },
    h('span', { class: 'bar-l' }, i.label),
    h('span', { class: 'bar-t' }, h('span', { class: 'bar-f', style: { width: Math.max(0, Math.min(100, i.value / max * 100)) + '%', background: i.color || 'var(--accent)' } })),
    h('span', { class: 'bar-v' }, i.text ?? fmt.n(i.value)))));
}

/** Ring gauge 0-100 with band colour */
export function ring(score, size = 150, label) {
  const r = size / 2 - 12, c = 2 * Math.PI * r, v = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  const col = score == null ? 'var(--line)' : score >= 80 ? 'var(--ok)' : score >= 60 ? 'var(--watch)' : score >= 40 ? 'var(--warn)' : 'var(--crit)';
  return s('svg', { viewBox: `0 0 ${size} ${size}`, width: size, height: size, class: 'ring', role: 'img', 'aria-label': 'Health index ' + (score == null ? 'not available' : Math.round(score)) },
    s('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--line)', 'stroke-width': 11 }),
    s('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', stroke: col, 'stroke-width': 11, 'stroke-linecap': 'round', 'stroke-dasharray': `${c * v} ${c}`, transform: `rotate(-90 ${size / 2} ${size / 2})`, style: 'transition:stroke-dasharray .6s' }),
    s('text', { x: size / 2, y: size / 2 + 6, 'text-anchor': 'middle', class: 'ring-n', fill: 'var(--ink)' }, score == null ? '—' : Math.round(score)),
    s('text', { x: size / 2, y: size / 2 + 26, 'text-anchor': 'middle', class: 'ax' }, label || '/ 100'));
}

export const scoreColor = (sc) => sc == null ? 'var(--line)' : sc >= 80 ? 'var(--ok)' : sc >= 60 ? 'var(--watch)' : sc >= 40 ? 'var(--warn)' : 'var(--crit)';

/** Elevation drawing of the structure with per-zone health heat-bands and device markers. */
export function elevation(st, zonesHealth, devices, onDevice, alertsByZone = {}) {
  const W = 760, Hh = 230, x0 = 30, x1 = W - 30, topY = 70, botY = 130;
  const svg = s('svg', { viewBox: `0 0 ${W} ${Hh}`, class: 'elev', role: 'img', 'aria-label': 'Structure elevation with zone health' });
  const len = x1 - x0, kind = st.kind;
  const zone = (z) => ({ a: x0 + z.x0 * len, b: x0 + z.x1 * len, sc: zonesHealth?.[z.id]?.score, local: zonesHealth?.[z.id]?.local_data });
  svg.append(s('defs', {}, s('pattern', { id: 'nodata', width: 8, height: 8, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, s('rect', { width: 8, height: 8, fill: 'var(--panel2)' }), s('line', { x1: 0, y1: 0, x2: 0, y2: 8, stroke: 'var(--line)', 'stroke-width': 3 }))));
  // ground
  svg.append(s('line', { x1: 10, x2: W - 10, y1: 205, y2: 205, stroke: 'var(--ink-3)', 'stroke-width': 1.5 }));
  if (kind === 'building') { // frame
    const floors = 4, y0 = 40, fh = 33;
    (st.zones || []).forEach(z => { const q = zone(z); svg.append(s('rect', { x: q.a, y: y0, width: q.b - q.a, height: floors * fh, fill: q.sc == null ? 'url(#nodata)' : scoreColor(q.sc), opacity: q.sc == null ? 1 : .78, stroke: 'var(--ink)', 'stroke-width': 1.2 })); });
    for (let i = 1; i < floors; i++) svg.append(s('line', { x1: x0, x2: x1, y1: y0 + i * fh, y2: y0 + i * fh, stroke: 'var(--ink)', 'stroke-width': 1 }));
  } else if (kind === 'specimen') { // test block
    (st.zones || []).forEach(z => { const q = zone(z); svg.append(s('rect', { x: q.a + 2, y: 60, width: q.b - q.a - 4, height: 110, rx: 4, fill: q.sc == null ? 'url(#nodata)' : scoreColor(q.sc), opacity: q.sc == null ? 1 : .78, stroke: 'var(--ink)', 'stroke-width': 1.2 })); });
  } else { // bridge / flyover / dam: deck beam + piers
    (st.zones || []).forEach(z => { const q = zone(z); const deck = z.name.toLowerCase().includes('span') || z.name.toLowerCase().includes('deck') || kind !== 'bridge' && kind !== 'flyover';
      svg.append(s('rect', { x: q.a, y: deck ? topY : topY + 6, width: q.b - q.a, height: deck ? botY - topY : botY - topY + 78, fill: q.sc == null ? 'url(#nodata)' : scoreColor(q.sc), opacity: q.sc == null ? 1 : .78, stroke: 'var(--ink)', 'stroke-width': 1.2 })); });
    svg.append(s('rect', { x: x0 - 6, y: topY - 8, width: len + 12, height: 9, fill: 'var(--ink)' }));
  }
  (st.zones || []).forEach(z => { const q = zone(z); const n = alertsByZone[z.id] || 0;
    svg.append(s('text', { x: (q.a + q.b) / 2, y: 224, 'text-anchor': 'middle', class: 'ax' }, z.name.length > 14 ? z.name.slice(0, 13) + '…' : z.name));
    if (q.sc != null) svg.append(s('text', { x: (q.a + q.b) / 2, y: kind === 'building' ? 112 : 112, 'text-anchor': 'middle', class: 'zone-n' }, Math.round(q.sc)));
    if (n) svg.append(s('circle', { cx: q.b - 10, cy: 56, r: 9, fill: 'var(--crit)' }), s('text', { x: q.b - 10, y: 60, 'text-anchor': 'middle', fill: '#fff', style: 'font:700 11px system-ui' }, n)); });
  (devices || []).forEach(d => {
    if (d.pos_x == null) return;
    const cx = x0 + d.pos_x * len, cy = 28 + d.pos_y * 160;
    const col = d.status === 'online' ? 'var(--live)' : d.status === 'idle' ? 'var(--watch)' : 'var(--muted)';
    const g = s('g', { class: 'dev', tabindex: 0, role: 'button', 'aria-label': `${d.name}, ${d.status}`, style: 'cursor:pointer' });
    g.append(s('circle', { cx, cy, r: 7.5, fill: 'var(--panel)', stroke: col, 'stroke-width': 3 }), s('circle', { cx, cy, r: 2.5, fill: d.source_type === 'simulated' ? 'var(--sim)' : 'var(--live)' }), s('title', {}, `${d.name} · ${d.kind} · ${d.source_type} · ${d.status}`));
    g.addEventListener('click', () => onDevice && onDevice(d)); g.addEventListener('keydown', e => e.key === 'Enter' && onDevice && onDevice(d));
    svg.append(g);
  });
  return h('div', { class: 'elev-wrap' }, svg, h('div', { class: 'legend' },
    [['var(--ok)', '≥80 optimal'], ['var(--watch)', '60–79 routine'], ['var(--warn)', '40–59 inspect'], ['var(--crit)', '<40 urgent']].map(([c, t]) => h('span', null, h('i', { style: { background: c } }), t)),
    h('span', null, h('i', { class: 'hatch' }), 'no data'), h('span', null, h('b', { class: 'dotp sim' }), 'simulated sensor'), h('span', null, h('b', { class: 'dotp live' }), 'real sensor')));
}
