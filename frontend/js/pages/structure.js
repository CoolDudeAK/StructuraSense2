import { h, fmt, kpi, chip, bandClass, tabs, empty, table, field, toast, confirmBox, download, debounce, loading, errorBox } from '../ui.js';
import { get, post, put, patch, on, session, urlWithToken } from '../api.js';
import { ring, lineChart, elevation, barChart, sparkline, scoreColor } from '../charts.js';
import { setSid } from '../main.js';

const COMP_NAMES = { vibration: 'Vibration / stiffness', cracks: 'Cracks (vision)', strain_fatigue: 'Strain & fatigue', deflection: 'Deflection', environment: 'Moisture & environment', load: 'Traffic load (WIM)', thermal: 'Temperature / thermal', internal: 'Internal discontinuity (RF coil)' };

export async function render(box, { params, query }) {
  const sid = params[0]; setSid(sid);
  let tab = query.get('tab') || 'health', st, hist, alerts, devs, chan;
  let closed = false;
  const load = async () => {
    [st, hist, alerts, chan] = await Promise.all([get('/structures/' + sid), get(`/structures/${sid}/health/history?hours=${window._hh || 72}`), get('/alerts?status=active&structure_id=' + sid), get(`/structures/${sid}/channels`)]);
    devs = st.device_list;
  };
  const draw = () => {
    if (closed) return;
    const hf = st.health_full, sc = hf && hf.score;
    box.replaceChildren(h('div', null,
      h('a', { href: '#/overview', class: 'muted' }, '← Portfolio'),
      h('div', { class: 'pagehead', style: { marginTop: '6px' } },
        h('div', null, h('div', { class: 'row', style: { gap: '8px' } }, h('span', { class: 'mono muted' }, st.id), st.is_demo ? chip('SIMULATED', 'DEMO ASSET') : chip('live', 'REAL ASSET')), h('h1', null, st.name),
          h('p', null, [st.location, st.material, st.span_m ? st.span_m + ' m span' : null, st.built_year ? 'built ' + st.built_year : null].filter(Boolean).join(' · '))),
        h('div', { class: 'row' }, h('label', { class: 'f-label' }, 'Health uses '), (() => { const sel = h('select', { style: { width: 'auto' }, 'aria-label': 'Which data feeds the health score', disabled: !session.can('engineer'), onchange: async () => { try { await patch('/structures/' + sid, { data_mode: sel.value }); await post(`/structures/${sid}/health/recompute`); await load(); draw(); toast('Health recalculated using ' + sel.options[sel.selectedIndex].text, 'ok'); } catch (e) { toast(e.message, 'err'); } } },
          [['all', 'all data'], ['live', 'real hardware data only'], ['sim', 'simulated data only']].map(([v, t]) => h('option', { value: v, selected: st.data_mode === v }, t))); return sel; })(),
          h('a', { class: 'btn', href: urlWithToken(`/api/structures/${sid}/report`), target: '_blank', rel: 'noopener' }, 'Printable report'))),
      st.data_mode === 'live' && (!hf || hf.score == null) ? h('div', { class: 'note', style: { marginBottom: '12px' } }, 'No real hardware data has arrived for this structure yet, so there is no real health score. Connect a device under Connect Data, or switch to "all data" to see the simulation.') : null,
      tabs([['health', 'Health'], ['channels', 'Sensor channels'], ['sensors', 'Sensors'], ['trends', 'Trends'], ['alerts', 'Alerts (' + alerts.length + ')']], tab, (t) => { tab = t; history.replaceState(null, '', `#/overview/${sid}?tab=${t}`); draw(); }),
      tab === 'health' ? healthTab() : tab === 'channels' ? channelsTab() : tab === 'sensors' ? sensorsTab() : tab === 'trends' ? trendsTab() : alertsTab()));
  };


  function channelsTab() {
    const act = chan.channels.filter(c => c.state === 'active');
    const toggle = async (c) => { try { await put(`/structures/${sid}/channels/${c.key}`, { enabled: c.state === 'disabled' }); await load(); draw(); toast(c.state === 'disabled' ? 'Channel switched on' : 'Channel switched off. The overall score now ignores it.', 'ok'); } catch (e) { toast(e.message, 'err'); } };
    return h('div', null,
      h('div', { class: 'grid g3', style: { marginBottom: '14px' } },
        kpi('Overall health (SHS)', chan.score == null ? '—' : fmt.n(chan.score, 0), chan.band),
        kpi('Active channels', `${act.length} of ${chan.channels.length}`, act.length ? act.map(c => c.device).join(', ') : 'none'),
        kpi('Coverage', Math.round((chan.coverage || 0) * 100) + '%', 'share of total weight with live data')),
      h('p', { class: 'note' }, 'Each device family is its own channel and scores itself. ', h('b', null, chan.formula), ' A single active channel is enough to produce a score; inactive channels are left out, not counted as zero. Weights and the 80/60/40 bands are project proposals, not standards.'),
      h('div', { class: 'grid g3', style: { marginTop: '14px' } }, chan.channels.map(c => h('section', { class: 'card chan chan-' + c.state },
        h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('h3', { style: { margin: 0 } }, c.device), h('span', { class: 'badge ' + ({ active: 'b-ok', inactive: 'b-none', disabled: 'b-warn' }[c.state]) }, c.state.toUpperCase())),
        h('p', { class: 'muted', style: { margin: '4px 0' } }, `${c.parameter} · ${c.purpose}`),
        c.state === 'active' ? h('div', null,
          h('div', { class: 'row', style: { alignItems: 'baseline', gap: '10px' } }, h('span', { class: 'kpi-v', style: { color: scoreColor(c.score) } }, c.score == null ? '—' : fmt.n(c.score, 0)), h('span', { class: 'muted' }, c.band)),
          h('div', { class: 'chan-bar' }, h('i', { style: { width: (c.effective_weight_pct || 0) + '%' } })),
          h('small', { class: 'muted' }, `weight ${c.effective_weight_pct}% of the overall score · adds ${c.contribution ?? 0} points`),
          c.items && c.items.length ? h('ul', { class: 'chan-items' }, c.items.slice(0, 3).map(i => h('li', null, i.label))) : null)
          : h('p', { class: 'muted' }, c.state === 'disabled' ? 'Switched off by an engineer. Not part of the overall score.' : c.why_inactive),
        h('div', { class: 'row', style: { justifyContent: 'space-between', marginTop: '8px' } },
          h('small', { class: 'muted' }, c.key === 'cracks' ? 'camera photos' : `${c.devices_online}/${c.devices} devices online`, c.sources.length ? ' · ' + c.sources.map(x => x.replace('_', ' ')).join(', ') : ''),
          session.can('engineer') && c.state !== 'inactive' ? h('button', { class: 'btn sm ghost', onclick: () => toggle(c) }, c.state === 'disabled' ? 'Switch on' : 'Switch off') : null)))),
      h('p', { class: 'note', style: { marginTop: '14px' } }, 'RF-coil readings are EXPERIMENTAL (no Indian Standard exists for them). Simulated devices are labelled under the Sensors tab.'));
  }

  function healthTab() {
    const hf = st.health_full; if (!hf || hf.score == null) return empty('No health score yet', 'Wait for data, or press Recalculate.', session.can('engineer') ? h('button', { class: 'btn primary', onclick: async () => { await post(`/structures/${sid}/health/recompute`); await load(); draw(); } }, 'Recalculate') : null);
    const alertsByZone = {}; alerts.forEach(a => a.zone_id && (alertsByZone[a.zone_id] = (alertsByZone[a.zone_id] || 0) + 1));
    const comps = Object.entries(hf.components);
    return h('div', null,
      h('div', { class: 'split' },
        h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('div', null, h('h2', null, 'Where is it weakest?'), h('p', null, 'Zone health along the structure. Click a sensor for its detail. Hatched = no data for that zone.'))),
          elevation(st, hf.zones, devs, (d) => sensorDetail(d), alertsByZone)),
        h('section', { class: 'card', style: { textAlign: 'center' } }, h('div', { class: 'row', style: { justifyContent: 'center' } }, ring(hf.score, 170, hf.band)),
          h('div', { style: { margin: '6px 0' } }, h('span', { class: 'badge ' + bandClass(hf.score) }, hf.band)),
          h('p', { class: 'muted' }, `Data coverage ${Math.round(hf.coverage * 100)}% of the framework weight`), h('p', { class: 'muted' }, 'Updated ' + fmt.ago(hf.ts_ms)),
          hf.coverage < 1 ? h('p', { class: 'note', style: { textAlign: 'left' } }, 'Some components have no data, so the score is re-weighted over what is available. Coverage below 100% means lower confidence.') : null)),
      h('div', { class: 'grid g2', style: { marginTop: '14px' } },
        h('section', { class: 'card' }, h('h2', null, 'Score breakdown'), h('p', { class: 'muted' }, 'Five components, weighted per the framework (v1 — proposed weights, not a standard).'),
          barChart(comps.map(([k, c]) => ({ label: COMP_NAMES[k], value: c.score ?? 0, text: c.score == null ? 'no data' : fmt.n(c.score, 0) + ' · ' + Math.round(c.weight * 100) + '%', color: c.score == null ? 'var(--line)' : scoreColor(c.score) })), { max: 100 })),
        h('section', { class: 'card' }, h('h2', null, 'What is driving it'), h('div', { class: 'list', style: { marginTop: '8px' } },
          comps.flatMap(([k, c]) => c.items.map(i => ({ ...i, k }))).sort((a, b) => a.score - b.score).slice(0, 6).map(i => h('div', { class: 'item' }, h('span', { class: 'sevbar', style: { background: scoreColor(i.score) } }), h('div', { class: 'grow' }, h('h4', null, COMP_NAMES[i.k]), h('p', null, i.label)), h('b', { class: 'mono' }, Math.round(i.score))))))),
      h('section', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'card-h' }, h('div', null, h('h2', null, 'Health over time'), h('p', null, 'Dips usually match a recorded event or injected scenario.')),
        h('div', { class: 'pill-row' }, [[24, '24 h'], [72, '3 days'], [168, '7 days']].map(([v, t]) => h('button', { class: 'pill' + ((window._hh || 72) === v ? ' on' : ''), onclick: async () => { window._hh = v; await load(); draw(); } }, t)))),
        lineChart([{ name: 'Health index', color: 'var(--accent)', points: hist.map(p => [p.ts_ms, p.score]), fill: true, width: 2 }], { xType: 'time', yMin: 0, yMax: 100, refs: [{ y: 80, label: 'optimal', color: 'var(--ok)' }, { y: 60, label: 'routine', color: 'var(--watch)' }, { y: 40, label: 'urgent', color: 'var(--crit)' }], height: 230, label: 'Health index over time' })));
  }

  function sensorDetail(d) {
    const body = h('div', null, loading());
    const m = import('../ui.js').then(({ modal }) => modal(d.name, body, [{ label: 'Close' }]));
    (async () => {
      try {
        if (d.channel === 'waveform') { location.hash = '#/signal?device=' + d.id; (await m).close(); return; }
        const r = await get(`/structures/${sid}/readings?device_id=${d.id}&hours=24`);
        body.replaceChildren(h('div', { class: 'row' }, chip(d.source_type === 'simulated' ? 'sim' : 'live'), h('span', { class: 'muted' }, `${d.kind} · ${d.unit || ''} · ${d.status}`)),
          lineChart([{ color: 'var(--accent)', points: r.points, dots: false }], { xType: 'time', height: 190, label: d.name }),
          r.stats ? h('dl', { class: 'stat-list' }, [['Latest', fmt.n(r.stats.last, 2)], ['Min', fmt.n(r.stats.min, 2)], ['Max', fmt.n(r.stats.max, 2)], ['Mean', fmt.n(r.stats.mean, 2)], ['Readings', r.stats.n]].flatMap(([a, b]) => [h('dt', null, a), h('dd', null, b)])) : empty('No readings in the last 24 h'));
      } catch (e) { body.replaceChildren(errorBox(e)); }
    })();
  }

  function sensorsTab() {
    return h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('div', null, h('h2', null, 'Sensors on this structure'), h('p', null, 'Source tells you whether numbers came from the simulator or real hardware.')), h('a', { class: 'btn sm primary', href: '#/data' }, 'Connect a device')),
      table([{ label: 'Sensor', render: d => h('b', null, d.name) }, { label: 'Type', key: 'kind' }, { label: 'Source', render: d => chip(d.source_type === 'simulated' ? 'sim' : 'live', d.source_type.replace('_', ' ').toUpperCase()) },
        { label: 'Status', render: d => h('span', null, h('span', { class: 'dots ' + (d.status === 'online' ? 'on' : d.status === 'offline' ? 'off' : '') }), d.status) },
        { label: 'Last value', cls: 'num', render: d => d.last ? `${fmt.n(d.last.value, 2)} ${d.channel === 'waveform' ? 'Hz' : d.unit || ''}` : '—' }, { label: 'Seen', render: d => fmt.ago(d.last_seen_ms) },
        { label: '', render: d => h('button', { class: 'btn sm', onclick: () => sensorDetail(d) }, 'Open') }], devs));
  }

  function trendsTab() {
    const wave = devs.filter(d => d.channel === 'waveform'), scal = devs.filter(d => d.channel === 'scalar' && !['piezo'].includes(d.kind));
    const holder = h('div', { class: 'grid g2' });
    [...wave.map(d => ['freq', d]), ...scal.map(d => ['sc', d])].forEach(async ([t, d]) => {
      const c = h('section', { class: 'card' }, h('h3', null, d.name), loading()); holder.append(c);
      try {
        if (t === 'freq') { const tr = await get(`/devices/${d.id}/trend`); c.replaceChildren(h('h3', null, d.name), h('div', { class: 'row' }, chip(tr.at(-1)?.source || 'sim'), h('small', null, 'dominant frequency, Hz — a falling trend means lost stiffness')),
          lineChart([{ color: 'var(--accent)', points: tr.map(p => [p.ts_ms, p.dom_freq, p.source]), dots: tr.length < 60 }], { xType: 'time', height: 170 })); }
        else { const r = await get(`/structures/${sid}/readings?device_id=${d.id}&hours=24`); c.replaceChildren(h('h3', null, d.name + ` (${d.unit || ''})`), lineChart([{ color: 'var(--ink-2)', points: r.points }], { xType: 'time', height: 170 })); }
      } catch (e) { c.replaceChildren(h('h3', null, d.name), errorBox(e)); }
    });
    return holder;
  }

  function alertsTab() {
    return alerts.length ? h('div', { class: 'list' }, alerts.map(a => h('div', { class: 'item' }, h('span', { class: 'sevbar sev-' + a.severity }), h('div', { class: 'grow' }, h('h4', null, a.title), h('p', null, a.message), h('small', null, `${a.zone_name || 'structure-wide'} · ${fmt.ago(a.ts_ms)} · ${a.status}`)), chip(a.origin))))
      : empty('No open alerts for this structure');
  }

  try { await load(); } catch (e) { box.replaceChildren(errorBox(e)); return; }
  draw();
  const re = debounce(async () => { try { await load(); draw(); } catch (e) {} }, 2000);
  const offs = [on('health', d => d.structure_id === sid && re()), on('alert', d => d.structure_id === sid && re())];
  return () => { closed = true; offs.forEach(f => f()); };
}
