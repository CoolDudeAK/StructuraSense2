import { h, fmt, kpi, chip, bandClass, bandLabel, empty, debounce } from '../ui.js';
import { get } from '../api.js';
import { ring, sparkline } from '../charts.js';
import { on } from '../api.js';
import { nav, loadStructures, setSid } from '../main.js';

function mixChips(src) {
  const t = Object.entries(src || {});
  if (!t.length) return h('small', null, 'no readings in the last hour');
  return h('span', { class: 'row', style: { gap: '4px' } }, t.map(([k, v]) => h('span', null, chip(k), ' ', h('small', null, v))));
}

function card(s) {
  const a = s.open_alerts, n = a.critical + a.warning + a.info, sc = s.health && s.health.score;
  return h('a', { class: 'card sc-card', href: '#/overview/' + s.id, 'aria-label': s.name, onclick: (e) => { e.preventDefault(); setSid(s.id); location.hash = '#/overview/' + s.id; } },
    h('div', { class: 'sc' }, ring(sc, 112),
      h('div', { class: 'grow' }, h('div', { class: 'row', style: { gap: '6px' } }, h('small', { class: 'mono' }, s.id), s.is_demo ? chip('SIMULATED', 'DEMO ASSET') : chip('live', 'REAL ASSET')),
        h('h3', { style: { margin: '4px 0' } }, s.name),
        h('small', null, s.location || ''),
        h('div', { style: { marginTop: '6px' } }, h('span', { class: 'badge ' + bandClass(sc) }, s.health ? s.health.band : 'No data')))),
    h('div', { class: 'row', style: { justifyContent: 'space-between', marginTop: '10px' } }, sparkline(s.trend, 'var(--accent)', 150, 34),
      h('div', { style: { textAlign: 'right', fontSize: '.82rem' } }, n ? h('b', { style: { color: a.critical ? 'var(--crit)' : 'var(--warn)' } }, `${n} open alert${n > 1 ? 's' : ''}`) : h('span', { class: 'muted' }, 'No open alerts'),
        h('div', { class: 'muted' }, `${s.devices_online}/${s.devices} sensors online`))),
    h('div', { style: { marginTop: '8px' } }, mixChips(s.sources_1h), sc != null && !Object.keys(s.sources_1h || {}).length ? h('div', { class: 'muted', style: { fontSize: '.78rem' } }, 'Score is from stored records (including simulated demo trials).') : null));
}

export async function render(box, { params, query }) {
  if (params[0]) { const m = await import('./structure.js'); return m.render(box, { params, query }); }
  const draw = async () => {
    const sts = await loadStructures();
    const [al] = await Promise.all([get('/alerts?status=active')]);
    const crit = al.filter(a => a.severity === 'critical').length, warn = al.filter(a => a.severity === 'warning').length;
    const dev = sts.reduce((t, s) => t + s.devices, 0), on_ = sts.reduce((t, s) => t + s.devices_online, 0);
    const worst = sts.filter(s => s.health).sort((a, b) => a.health.score - b.health.score)[0];
    box.replaceChildren(
      h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'Portfolio overview'), h('p', null, 'Every monitored structure, ranked by what needs attention. Scores are a decision aid for engineers, not a safety certificate.'))),
      h('div', { class: 'grid g4', style: { marginBottom: '16px' } },
        kpi('Structures', sts.length, `${sts.filter(s => !s.is_demo).length} real · ${sts.filter(s => s.is_demo).length} demo`),
        kpi('Open alerts', al.length, `${crit} critical · ${warn} warning`, crit ? 'crit' : warn ? 'warn' : 'ok'),
        kpi('Sensors online', `${on_}/${dev}`, 'seen within the last 5 min'),
        kpi('Lowest health', worst ? Math.round(worst.health.score) : '—', worst ? worst.name.split('(')[0] : '', worst && worst.health.score < 60 ? 'warn' : '')),
      h('div', { class: 'grid g3' }, sts.map(card)),
      h('div', { class: 'split', style: { marginTop: '16px' } },
        h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('div', null, h('h2', null, 'Needs attention'), h('p', null, 'Open alerts across all structures, worst first.')), h('a', { class: 'btn sm', href: '#/alerts' }, 'All alerts')),
          al.length ? h('div', { class: 'list' }, al.slice(0, 6).map(a => h('div', { class: 'item' }, h('span', { class: 'sevbar sev-' + a.severity }), h('div', { class: 'grow' }, h('h4', null, a.title), h('p', null, `${a.structure_name.split('(')[0]} · ${a.zone_name || 'structure-wide'} · ${fmt.ago(a.ts_ms)}`)), chip(a.origin))))
            : empty('All clear', 'No open alerts right now.')),
        h('section', { class: 'card' }, h('h2', null, 'Getting real data in'), h('ol', { style: { paddingLeft: '1.1em', margin: '8px 0', color: 'var(--ink-2)' } },
          h('li', null, 'Plug your Arduino into this computer\'s USB port.'), h('li', null, 'Open ', h('a', { href: '#/impact/STR-001' }, 'Impact Lab'), ' → Connect Arduino.'), h('li', null, 'Record baseline trials, then test the specimen.')),
          h('p', { class: 'note info' }, 'ESP32, CSV and other sensors: see ', h('a', { href: '#/data' }, 'Connect Data'), '. Anything simulated carries a violet SIMULATED tag; hardware data is teal LIVE.'))));
  };
  await draw();
  const redraw = debounce(() => draw().catch(() => {}), 1500);
  const offs = [on('health', redraw), on('alert', redraw), on('alert_update', redraw)];
  return () => offs.forEach(f => f());
}
