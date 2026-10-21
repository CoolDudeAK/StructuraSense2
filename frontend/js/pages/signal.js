import { h, fmt, kpi, chip, empty, table, field, toast, loading, errorBox, confirmBox } from '../ui.js';
import { get, post, del, session, on } from '../api.js';
import { lineChart, spectrumChart, barChart } from '../charts.js';
import { nav, setSid } from '../main.js';

export async function render(box, { query }) {
  let sid = nav.sid, devs = [], dev = query.get('device'), caps = [], sel = null, detail = null, closed = false;
  const can = session.can('engineer');
  const host = h('div');
  const loadDevs = async () => { devs = (await get('/devices?structure_id=' + sid)).filter(d => d.channel === 'waveform'); if (!devs.find(d => d.id === dev)) dev = (devs[0] || {}).id; };
  const loadCaps = async () => { caps = dev ? await get(`/waveforms?device_id=${dev}&limit=40`) : []; sel = caps[0] && (caps.find(c => c.id === sel) ? sel : caps[0].id); detail = sel ? await get('/waveforms/' + sel) : null; };
  const draw = () => {
    if (closed) return;
    const structSel = h('select', { 'aria-label': 'Structure', onchange: async (e) => { sid = e.target.value; setSid(sid); dev = null; await loadDevs(); await loadCaps(); draw(); } }, nav.structures.map(s => h('option', { value: s.id, selected: s.id === sid }, s.id + ' · ' + s.name.split('(')[0])));
    const devSel = h('select', { 'aria-label': 'Sensor', onchange: async (e) => { dev = e.target.value; sel = null; await loadCaps(); draw(); } }, devs.map(d => h('option', { value: d.id, selected: d.id === dev }, d.name)));
    host.replaceChildren(
      h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'Signal Lab'), h('p', null, 'Vibration captures from piezo/accelerometer sensors. The dominant (natural) frequency is the key signal: when stiffness is lost, it falls.')),
        h('div', { class: 'row' }, structSel, devs.length ? devSel : null)),
      !devs.length ? empty('No vibration sensors on this structure', 'Impact Lab handles the 3-piezo specimen rig. Choose a bridge or building to see captures here.', h('a', { class: 'btn', href: '#/impact' }, 'Open Impact Lab')) :
        h('div', null, h('div', { class: 'split' }, detailCard(), listCard()), captureCard()));
  };
  function detailCard() {
    if (!detail) return h('section', { class: 'card' }, empty('No captures yet', 'Take a simulated capture, or send real data from Connect Data.'));
    const m = detail.meta, c = detail.compare;
    return h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('div', null, h('h2', null, 'Capture ', fmt.dt(m.ts_ms)), h('p', null, `${m.n} samples at ${m.fs} Hz`)), h('div', { class: 'row' }, chip(m.source), m.is_baseline ? h('span', { class: 'badge b-ok' }, 'BASELINE') : null)),
      lineChart([{ color: 'var(--ink-2)', points: detail.waveform.t.map((t, i) => [t, detail.waveform.v[i]]), width: 1.2 }], { xType: 'num', height: 150, title: 'Waveform (mean removed) · seconds' }),
      spectrumChart(detail.spectrum, detail.baseline_spectrum, { height: 190, title: 'Spectrum · Hz' }),
      h('div', { class: 'grid g4', style: { marginTop: '10px' } }, kpi('Dominant freq', fmt.n(m.dom_freq, 2) + ' Hz', c ? `${c.freq_shift_pct > 0 ? '+' : ''}${fmt.n(c.freq_shift_pct, 1)}% vs baseline` : 'no baseline', c && c.freq_shift_pct < -3 ? 'warn' : ''),
        kpi('RMS', fmt.n(m.rms * 1000, 2) + ' mg'), kpi('Damping ζ', fmt.n(m.damping, 3), c ? `${fmt.n(c.damping_ratio, 2)}× baseline` : ''), kpi('Anomaly score', c ? fmt.n(c.anomaly, 2) : '—', 'autoencoder, 0–1', c && c.anomaly > .6 ? 'crit' : '')),
      c ? h('p', { class: 'note info', style: { marginTop: '10px' } }, `Compared with ${c.baseline_kind} (${c.baseline_count} capture${c.baseline_count > 1 ? 's' : ''}, ${fmt.n(c.baseline_freq, 2)} Hz). The anomaly model is trained on simulated healthy data — treat it as a screening hint.`) : h('p', { class: 'note' }, 'No baseline for this sensor yet. Mark a healthy capture as baseline.'),
      h('div', { class: 'row', style: { marginTop: '10px' } }, can ? h('button', { class: 'btn', onclick: async () => { await post(`/waveforms/${m.id}/baseline`, { is_baseline: !m.is_baseline }); toast(m.is_baseline ? 'Baseline flag removed' : 'Marked as healthy baseline', 'ok'); await loadCaps(); draw(); } }, m.is_baseline ? 'Remove baseline flag' : 'Mark as healthy baseline') : null,
        can ? h('button', { class: 'btn danger', onclick: async () => { if (await confirmBox('Delete this capture?', 'It will be removed permanently.', 'Delete')) { await del('/waveforms/' + m.id); sel = null; await loadCaps(); draw(); } } }, 'Delete') : null));
  }
  function listCard() {
    return h('section', { class: 'card' }, h('h2', null, 'Recent captures'), h('p', { class: 'muted' }, 'Click to inspect.'), h('div', { class: 'list', style: { maxHeight: '520px', overflow: 'auto', marginTop: '8px' } },
      caps.map(c => h('button', { class: 'item', style: { textAlign: 'left', cursor: 'pointer', borderColor: c.id === sel ? 'var(--accent)' : 'var(--line)' }, onclick: async () => { sel = c.id; detail = await get('/waveforms/' + sel); draw(); } },
        h('div', { class: 'grow' }, h('h4', null, fmt.dt(c.ts_ms)), h('p', null, `${fmt.n(c.dom_freq, 2)} Hz · ζ ${fmt.n(c.damping, 3)}${c.is_baseline ? ' · baseline' : ''}`)), chip(c.source)))));
  }
  function captureCard() {
    const dmg = h('input', { type: 'range', min: 0, max: .6, step: .01, value: 0, 'aria-label': 'Simulated damage level' }), lab = h('output', null, '0%');
    dmg.oninput = () => lab.textContent = Math.round(dmg.value * 100) + '%';
    const pasted = h('textarea', { placeholder: 'Paste numbers (one per line or comma-separated), at least 64 samples', 'aria-label': 'Samples' }), fs = h('input', { type: 'number', value: 100, 'aria-label': 'Sample rate' }); const out = h('div');
    return h('div', { class: 'grid g2', style: { marginTop: '14px' } },
      h('section', { class: 'card' }, h('h2', null, 'Take a simulated capture ', chip('sim')), h('p', { class: 'muted' }, 'Synthetic bridge vibration whose natural frequency drops as you raise the damage. Use it to see how the screening reacts.'),
        field('Simulated stiffness loss', h('div', { class: 'row' }, dmg, lab)),
        h('button', { class: 'btn primary', disabled: !can, onclick: async () => { try { await post('/waveforms/simulate', { device_id: dev, damage: +dmg.value }); toast('Capture added (SIMULATED)', 'ok'); await loadCaps(); draw(); } catch (e) { toast(e.message, 'err'); } } }, 'Capture')),
      h('section', { class: 'card' }, h('h2', null, 'Analyse your own samples'), h('p', { class: 'muted' }, 'Paste raw acceleration numbers to get the frequency content immediately (nothing is saved).'), pasted, field('Sample rate (Hz)', fs),
        h('button', { class: 'btn', onclick: async () => { try { const x = pasted.value.split(/[\s,;]+/).filter(Boolean).map(Number); if (x.some(isNaN)) throw new Error('Some values are not numbers.'); const r = await post('/signal/analyze', { samples: x, fs: +fs.value }); out.replaceChildren(h('p', null, h('b', null, `Dominant frequency ${fmt.n(r.features.dom_freq, 2)} Hz`), ` · RMS ${fmt.n(r.features.rms, 4)} · damping ${fmt.n(r.features.damping, 3)}`), spectrumChart(r.spectrum, null, { height: 170 })); } catch (e) { out.replaceChildren(h('p', { class: 'note' }, e.message)); } } }, 'Analyse'), out));
  }
  box.append(host); host.replaceChildren(loading());
  try { await loadDevs(); await loadCaps(); } catch (e) { host.replaceChildren(errorBox(e)); return; }
  draw();
  const off = on('waveform', async (d) => { if (d.device_id === dev) { try { await loadCaps(); draw(); } catch (e) {} } });
  return () => { closed = true; off(); };
}
