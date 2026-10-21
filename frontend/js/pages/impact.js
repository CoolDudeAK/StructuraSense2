// Impact Lab — the user's real Arduino UNO + 3 piezo specimen workflow (ported from the Streamlit prototype).
import { h, fmt, kpi, chip, tabs, empty, table, field, toast, confirmBox, download, modal, loading, errorBox, debounce } from '../ui.js';
import { get, post, put, del, on, session, urlWithToken, api } from '../api.js';
import { lineChart, barChart } from '../charts.js';
import { nav } from '../main.js';

const SC = ['var(--accent)', 'var(--live)', 'var(--sim)'];
const stClass = (s) => !s ? 's-NONE' : s.startsWith('NORMAL') ? 's-NORMAL' : s.startsWith('POSSIBLE') ? 's-POSSIBLE' : s.startsWith('URGENT') ? 's-URGENT' : 's-NONE';

// ---- Web Serial (Chrome / Edge). Reads raw lines from the Arduino and forwards them to the server. ----
const serial = { port: null, reader: null, running: false, buf: [], sent: 0, bad: 0, timer: null };
async function serialConnect(sid, baud, onState) {
  if (!('serial' in navigator)) throw new Error('This browser cannot read USB serial. Use Google Chrome or Microsoft Edge on a computer, or use the bridge script (see "Other ways to connect").');
  serial.port = await navigator.serial.requestPort();
  await serial.port.open({ baudRate: baud });
  serial.running = true; onState();
  const dec = new TextDecoderStream(); serial.port.readable.pipeTo(dec.writable).catch(() => {});
  serial.reader = dec.readable.getReader();
  serial.timer = setInterval(async () => {
    if (!serial.buf.length) return;
    const lines = serial.buf.splice(0, 400);
    try { const r = await post('/ingest/serial-lines', { structure_id: sid, lines }); serial.sent += r.accepted; serial.bad += r.rejected; } catch (e) { serial.bad += lines.length; }
    onState();
  }, 250);
  (async () => {
    let rest = '';
    try { while (serial.running) { const { value, done } = await serial.reader.read(); if (done) break; rest += value; const parts = rest.split(/\r?\n/); rest = parts.pop(); parts.forEach(l => l.trim() && serial.buf.push(l.trim())); } } catch (e) { /* unplugged */ }
    await serialDisconnect(onState);
  })();
}
async function serialDisconnect(onState) {
  serial.running = false; clearInterval(serial.timer);
  try { await serial.reader?.cancel(); } catch (e) {} try { await serial.port?.close(); } catch (e) {}
  serial.port = null; serial.reader = null; onState && onState();
}

export async function render(box, { params }) {
  const sid = params[0] || (nav.structures.find(s => s.has_impact_lab) || {}).id;
  if (!sid) { box.replaceChildren(empty('No rig structure', 'Create a "specimen" structure with 3 piezo devices to use Impact Lab.')); return; }
  let ov, tab = 'live', closed = false, rec = null, recTimer = null;
  const pts = { t: [], s1: [], s2: [], s3: [] }; let liveStatus = null, connected = false, dataSource = null;
  const canEdit = session.can('engineer');
  const load = async () => { ov = await get(`/impact/${sid}/overview`); Object.assign(pts, ov.live.points); liveStatus = ov.live.status; connected = ov.live.connected; dataSource = ov.live.source; };
  const struct = nav.structures.find(s => s.id === sid);

  const body = h('div');
  const redrawBody = () => { if (closed) return; body.replaceChildren(tab === 'live' ? liveTab() : tab === 'baseline' ? baselineTab() : tab === 'results' ? resultsTab() : tab === 'connect' ? connectTab() : settingsTab()); };
  const head = () => h('div', { class: 'pagehead' }, h('div', null, h('div', { class: 'row', style: { gap: '8px' } }, h('span', { class: 'mono muted' }, sid), chip('live', 'REAL RIG WORKFLOW')), h('h1', null, 'Impact Lab'),
    h('p', null, 'Tap the specimen, let three piezo sensors respond, and compare against the healthy baseline you recorded. Same method as your Streamlit prototype — now saved to a database and feeding the structure health index. ', h('a', { href: '#/elements' }, 'Test cubes, beams, slabs and columns to IS codes →'))));

  // ---------- live tab
  const liveHost = h('div'), statusHost = h('div'), chartHost = h('div');
  function paintStatus() {
    const s = liveStatus, b = ov.baseline;
    const cls = !b ? 's-NONE' : stClass(s && s.status);
    statusHost.replaceChildren(h('div', { class: 'status-banner ' + cls },
      h('div', null, h('div', { style: { fontSize: '.75rem', opacity: .85, letterSpacing: '.08em' } }, 'LIVE STATUS vs BASELINE'), h('div', { class: 'big' }, !b ? 'NO BASELINE' : s ? s.status : connected ? 'Waiting for taps…' : 'NO SIGNAL')),
      s ? h('div', null, h('div', { class: 'big' }, fmt.n(s.combined_score, 1) + '%'), h('div', { style: { fontSize: '.8rem' } }, `deviation over last ${s.window_s}s · most-changed: ${s.largest_deviation_sensor.replace('sensor', 'S')}`)) : null,
      h('div', { class: 'grow' }), dataSource ? chip(dataSource === 'live' ? 'live' : 'sim', dataSource === 'live' ? 'LIVE HARDWARE' : 'SIMULATED') : null));
  }
  function paintChart() {
    const t0 = pts.t.length ? pts.t[pts.t.length - 1] : 0;
    const mk = (k, i) => ({ name: 'S' + (i + 1), color: SC[i], points: pts.t.map((t, j) => [(t - t0) / 1000, pts[k][j]]) });
    chartHost.replaceChildren(lineChart(['s1', 's2', 's3'].map(mk), { xType: 'num', height: 240, yMin: 0, yMax: 5000 > Math.max(0, ...pts.s1, ...pts.s2, ...pts.s3) * 2 ? undefined : 5000, legend: true, label: 'Live sensor response', title: 'Sensor response (ADC counts) · x-axis = seconds ago' }));
  }
  function paintTiles() {
    const l = pts.t.length ? { s1: pts.s1.at(-1), s2: pts.s2.at(-1), s3: pts.s3.at(-1) } : null, b = ov.baseline;
    tiles.replaceChildren(...[1, 2, 3].map(i => h('div', { class: 'kpi' }, h('div', { class: 'kpi-l' }, `Sensor ${i} (A${i - 1}) now`), h('div', { class: 'kpi-v', style: { color: SC[i - 1] } }, l ? fmt.n(l['s' + i], 0) : '—'),
      h('div', { class: 'kpi-s' }, liveStatus ? `p2p ${fmt.n(liveStatus.current_p2p['sensor' + i], 0)} vs baseline ${b ? fmt.n(b['s' + i + '_mean'], 0) : '—'}` : b ? `baseline p2p ${fmt.n(b['s' + i + '_mean'], 0)}` : 'no baseline yet'))));
  }
  const tiles = h('div', { class: 'sensor-trio' });
  const recHost = h('div');
  function paintRec() {
    if (rec) { const left = Math.max(0, rec.end - Date.now()) / 1000; recHost.replaceChildren(h('div', { class: 'note good' }, h('b', null, `Recording ${rec.label}… ${left.toFixed(1)} s left. `), 'Tap the specimen now, with the same force and spot each time.'));
      if (left <= 0) finishRec(); }
    else recHost.replaceChildren();
  }
  async function startRec(purpose, condition) {
    if (!connected) { toast('No data is arriving. Connect your Arduino or start the demo tap simulator first.', 'warn'); return; }
    try {
      const r = await post(`/impact/${sid}/record/start`, { purpose, condition, duration: ov.settings.trial_duration_sec });
      rec = { job: r.job_id, end: Date.now() + r.duration_s * 1000, label: purpose === 'calibration' ? 'baseline trial' : condition + ' trial', purpose };
      clearInterval(recTimer); recTimer = setInterval(paintRec, 150); paintRec();
    } catch (e) { toast(e.message, 'err'); }
  }
  async function finishRec() {
    clearInterval(recTimer); const r0 = rec; rec = null; paintRec();
    try {
      const r = await post(`/impact/${sid}/record/finish`, { job_id: r0.job });
      if (r.purpose === 'calibration') { toast(`Baseline trial ${r.calibration.count}/${r.calibration.target} saved.`, 'ok'); await load(); tab = 'baseline'; paintAll(); }
      else { const t = r.trial; toast(`${t.condition} trial: ${t.status} (${fmt.n(t.anomaly_score, 1)}% deviation)`, t.status === 'NORMAL' ? 'ok' : 'warn', 7000); await load(); paintAll(); }
    } catch (e) { toast(e.message, 'err', 7000); }
  }
  function liveTab() {
    paintStatus(); paintChart(); paintTiles(); paintRec();
    const cond = h('select', { 'aria-label': 'Specimen condition', style: { width: 'auto' } }, h('option', { value: 'Intact' }, 'Specimen is intact'), h('option', { value: 'Damaged' }, 'Specimen is damaged'));
    return h('div', null, statusHost, h('div', { style: { height: '12px' } }), tiles, h('div', { style: { height: '12px' } }),
      h('div', { class: 'split' },
        h('section', { class: 'card' }, chartHost),
        h('section', { class: 'card' }, h('h2', null, 'Record a test trial'), h('p', { class: 'muted' }, `Records ${ov.settings.trial_duration_sec} s of response, then measures each sensor's peak-to-peak and scores it against the baseline.`),
          !ov.baseline ? h('div', { class: 'note' }, 'No baseline yet. Go to the Baseline tab first and record healthy trials.') : null,
          field('What are you testing?', cond), h('button', { class: 'btn primary', disabled: !canEdit || !!rec || !ov.baseline, onclick: () => startRec('trial', cond.value) }, '● Start trial'),
          !canEdit ? h('p', { class: 'muted' }, 'Viewers can watch but not record.') : null, recHost,
          h('hr', { style: { border: 0, borderTop: '1px solid var(--line)', margin: '14px 0' } }), demoControls())));
  }
  function demoControls() {
    const sel = h('select', { 'aria-label': 'Demo scenario', onchange: async () => { if (!ov.demo.running) return; try { ov.demo = await post(`/impact/${sid}/demo`, { running: true, scenario: sel.value }); toast('Demo scenario changed', 'ok'); paintAll(); } catch (e) { toast(e.message, 'err'); } } }, Object.entries(ov.demo.scenarios).map(([k, v]) => h('option', { value: k, selected: k === ov.demo.scenario }, v)));
    return h('div', null, h('h3', null, 'Demo tap simulator ', chip('sim')), h('p', { class: 'muted' }, 'No hardware? This generates tap packets in the same format as your Arduino so you can try the whole workflow. Marked SIMULATED everywhere. Auto-stops after 30 min.'),
      sel, h('div', { class: 'row', style: { marginTop: '8px' } },
        h('button', { class: 'btn', disabled: !canEdit, onclick: async () => { try { ov.demo = await post(`/impact/${sid}/demo`, { running: !ov.demo.running, scenario: sel.value }); toast(ov.demo.running ? 'Demo taps started' : 'Demo stopped', 'ok'); paintAll(); } catch (e) { toast(e.message, 'err'); } } }, ov.demo.running ? '■ Stop demo' : '▶ Start demo taps'),
        ov.demo.running ? h('small', null, 'running…') : null));
  }

  // ---------- baseline tab
  function baselineTab() {
    const c = ov.calibration, b = ov.baseline, prog = Math.min(100, c.count / c.target * 100);
    const spec = h('input', { value: (b && b.specimen_id) || 'specimen-1', 'aria-label': 'Specimen name' });
    return h('div', { class: 'grid g2' },
      h('section', { class: 'card' }, h('h2', null, '1 · Record healthy baseline trials'), h('p', { class: 'muted' }, `Tap the intact specimen the same way each time. Record ${c.target} trials (minimum 3). Each trial's peak-to-peak response is stored; their mean and spread become the baseline.`),
        h('div', { class: 'bar-t', style: { height: '14px', margin: '10px 0' } }, h('span', { class: 'bar-f', style: { width: prog + '%' } })), h('p', null, h('b', null, `${c.count} / ${c.target}`), ' trials recorded ', c.source ? chip(c.source === 'live' ? 'live' : c.source === 'sim' ? 'sim' : 'mixed') : null),
        h('div', { class: 'row' }, h('button', { class: 'btn primary', disabled: !canEdit || !!rec, onclick: () => startRec('calibration', 'Intact') }, '● Record baseline trial'),
          h('button', { class: 'btn', disabled: !canEdit || !c.count, onclick: async () => { await post(`/impact/${sid}/calibration/undo`); await load(); paintAll(); } }, 'Undo last'),
          h('button', { class: 'btn danger', disabled: !canEdit || !c.count, onclick: async () => { if (await confirmBox('Clear staged trials?', 'This removes the baseline trials you recorded so far (not a saved baseline).', 'Clear')) { await del(`/impact/${sid}/calibration`); await load(); paintAll(); } } }, 'Clear')), recHost,
        c.count ? table([{ label: '#', render: (r) => c.trials.indexOf(r) + 1 }, { label: 'S1', cls: 'num', render: r => fmt.n(r.s1, 0) }, { label: 'S2', cls: 'num', render: r => fmt.n(r.s2, 0) }, { label: 'S3', cls: 'num', render: r => fmt.n(r.s3, 0) }, { label: 'Source', render: r => chip(r.source === 'live' ? 'live' : 'sim') }], c.trials) : null),
      h('section', { class: 'card' }, h('h2', null, '2 · Save the baseline'), c.preview ? h('dl', { class: 'stat-list' }, [1, 2, 3].flatMap(i => [h('dt', null, `S${i} mean ± std`), h('dd', null, `${fmt.n(c.preview['s' + i + '_mean'], 1)} ± ${fmt.n(c.preview['s' + i + '_std'], 1)}`)])) : h('p', { class: 'muted' }, 'Record at least 3 trials to preview the baseline.'),
        field('Specimen name', spec), h('button', { class: 'btn dark', disabled: !canEdit || c.count < 3, onclick: async () => { try { await post(`/impact/${sid}/baseline/save`, { specimen_id: spec.value }); toast('Baseline saved. New trials are now scored against it.', 'ok'); await load(); paintAll(); } catch (e) { toast(e.message, 'err'); } } }, 'Save as baseline'),
        h('hr', { style: { border: 0, borderTop: '1px solid var(--line)', margin: '14px 0' } }), h('h3', null, 'Current saved baseline'),
        b ? h('div', null, h('p', null, chip(b.source === 'live' ? 'live' : b.source === 'sim' ? 'sim' : 'mixed'), ` ${b.num_trials} trials · "${b.specimen_id}" · saved ${fmt.dt(b.created_ms)}`),
          barChart([1, 2, 3].map(i => ({ label: `Sensor ${i}`, value: b['s' + i + '_mean'], text: `${fmt.n(b['s' + i + '_mean'], 0)} ± ${fmt.n(b['s' + i + '_std'], 0)}`, color: SC[i - 1] })), { max: Math.max(b.s1_mean, b.s2_mean, b.s3_mean) * 1.2 }),
          b.source === 'sim' ? h('p', { class: 'note info' }, 'This baseline came from the demo simulator. Record real trials and save again to replace it with a real-specimen baseline.') : null) : h('p', { class: 'muted' }, 'No baseline saved yet.')));
  }

  // ---------- results tab
  let trialsData = [], an = null, filt = 'All';
  async function loadResults() { [trialsData, an] = await Promise.all([get(`/impact/${sid}/trials?condition=${filt}`), get(`/impact/${sid}/analysis`)]); }
  function resultsTab() {
    const host = h('div', null, loading());
    loadResults().then(() => {
      if (closed) return;
      host.replaceChildren(h('div', { class: 'grid g2' },
        h('section', { class: 'card' }, h('h2', null, 'Intact vs damaged'), an.n_intact && an.n_damaged ? h('div', null, h('p', { class: 'muted' }, `${an.n_intact} intact and ${an.n_damaged} damaged trials. Bigger gaps = the sensor "notices" the damage.`),
          barChart(an.deviation.map(d => ({ label: `Sensor ${d.sensor}`, value: d.pct_deviation, text: fmt.n(d.pct_deviation, 1) + '%', color: SC[d.sensor - 1] })), { max: 100 })) : empty('Not enough data', 'Record at least one Intact and one Damaged trial to compare.')),
        h('section', { class: 'card' }, h('h2', null, 'Trial scores over time'), lineChart([{ name: 'Health score', color: 'var(--accent)', points: [...trialsData].reverse().map(t => [t.ts_ms, t.health_score ?? 0, t.source]), dots: true }], { xType: 'time', height: 200, yMin: 0, yMax: 100, label: 'Trial health scores' }))),
        h('section', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'card-h' }, h('div', null, h('h2', null, 'All trials')), h('div', { class: 'row' },
          h('select', { 'aria-label': 'Filter by condition', style: { width: 'auto' }, onchange: async (e) => { filt = e.target.value; redrawBody(); } }, ['All', 'Intact', 'Damaged'].map(c => h('option', { selected: c === filt }, c))),
          h('a', { class: 'btn sm', href: urlWithToken(`/api/impact/${sid}/export.csv`) }, 'Export CSV'),
          h('button', { class: 'btn sm danger', disabled: !canEdit || !trialsData.length, onclick: async () => { if (await confirmBox('Delete ALL trials?', 'This permanently deletes every recorded trial for this specimen. The baseline is kept.', 'Delete all')) { await del(`/impact/${sid}/trials?confirm=yes`); await load(); redrawBody(); } } }, 'Delete all'))),
          table([{ label: 'When', render: t => fmt.dt(t.ts_ms) }, { label: 'Condition', key: 'condition' }, { label: 'S1', cls: 'num', render: t => fmt.n(t.s1, 0) }, { label: 'S2', cls: 'num', render: t => fmt.n(t.s2, 0) }, { label: 'S3', cls: 'num', render: t => fmt.n(t.s3, 0) },
            { label: 'Deviation', cls: 'num', render: t => t.anomaly_score == null ? '—' : fmt.n(t.anomaly_score, 1) + '%' }, { label: 'Status', render: t => h('span', { class: 'badge ' + (t.status === 'NORMAL' ? 'b-ok' : t.status === 'URGENT REVIEW' ? 'b-crit' : t.status === 'POSSIBLE ANOMALY' ? 'b-warn' : 'b-none') }, t.status || '—') },
            { label: 'Data', render: t => chip(t.source === 'live' ? 'live' : t.source === 'sim' ? 'sim' : 'mixed') },
            { label: '', render: t => h('span', { class: 'row', style: { gap: '4px', flexWrap: 'nowrap' } }, h('button', { class: 'btn sm', onclick: () => showTrial(t) }, 'Trace'), canEdit ? h('button', { class: 'btn sm danger', 'aria-label': 'Delete trial', onclick: async () => { await del(`/impact/${sid}/trials/${t.id}`); await load(); redrawBody(); } }, '✕') : null) }], trialsData, { empty: 'No trials yet. Record one on the Live tab.' })));
    }).catch(e => host.replaceChildren(errorBox(e, redrawBody)));
    return host;
  }
  async function showTrial(t) {
    const d = await get(`/impact/${sid}/trials/${t.id}`); const tr = d.trace;
    const t0 = tr ? tr[0][0] : 0;
    modal(`${t.condition} trial · ${fmt.dt(t.ts_ms)}`, h('div', null, h('div', { class: 'row' }, chip(t.source === 'live' ? 'live' : 'sim'), h('span', { class: 'badge ' + (t.status === 'NORMAL' ? 'b-ok' : 'b-warn') }, t.status)), tr ? lineChart([1, 2, 3].map(i => ({ name: 'S' + i, color: SC[i - 1], points: tr[0].map((x, j) => [(x - t0) / 1000, tr[i][j]]) })), { xType: 'num', height: 220, legend: true }) : empty('No trace stored'),
      h('p', { class: 'muted' }, `${t.samples} samples over ${fmt.n(t.duration_s, 1)} s. Peak-to-peak: S1 ${fmt.n(t.s1, 0)}, S2 ${fmt.n(t.s2, 0)}, S3 ${fmt.n(t.s3, 0)}.`), t.notes ? h('p', { class: 'muted' }, t.notes) : null), [{ label: 'Close' }]);
  }

  // ---------- connect tab
  function connectTab() {
    const baud = h('input', { type: 'number', value: ov.settings.baud_rate, 'aria-label': 'Baud rate', style: { width: '130px' } });
    const stat = h('div', { class: 'muted' });
    const upd = () => { stat.replaceChildren(serial.running ? h('span', null, h('span', { class: 'dots on' }), `Reading from Arduino · ${serial.sent} packets accepted, ${serial.bad} rejected`) : h('span', null, h('span', { class: 'dots' }), 'Not connected')); btn.textContent = serial.running ? '■ Disconnect Arduino' : '🔌 Connect Arduino (USB)'; };
    const btn = h('button', { class: 'btn primary', disabled: !canEdit, onclick: async () => { try { if (serial.running) await serialDisconnect(upd); else await serialConnect(sid, +baud.value || 115200, upd); } catch (e) { if (e.name !== 'NotFoundError') toast(e.message, 'err', 8000); } upd(); } });
    upd();
    return h('div', { class: 'grid g2' },
      h('section', { class: 'card' }, h('h2', null, 'Connect your Arduino UNO'), h('div', { class: 'note info', style: { margin: '8px 0' } }, 'Your Arduino sketch must print one line per reading like ', h('code', null, '184,126,171'), ' (or ', h('code', null, 'S1:184,S2:126,S3:171'), '). The original firmware in firmware/arduino_p2p already does this.'),
        h('ol', { style: { paddingLeft: '1.2em' } }, h('li', null, 'Plug the Arduino into a USB port.'), h('li', null, 'Close the Arduino IDE\'s Serial Monitor (only one program can use the port).'), h('li', null, 'Press the button below, choose your Arduino in the pop-up (called "USB Serial" or "Arduino Uno"), press Connect.'), h('li', null, 'Tap the specimen. Live values appear on the Live tab.')),
        h('div', { class: 'row' }, btn, h('label', { class: 'row', style: { gap: '6px' } }, h('small', null, 'Baud'), baud)), stat,
        'serial' in navigator ? null : h('div', { class: 'note', style: { marginTop: '10px', borderColor: 'var(--crit)' } }, 'This browser does not support USB access. Open this page in Google Chrome or Microsoft Edge (desktop). Firefox and Safari cannot do this.'),
        h('p', { class: 'muted' }, 'Keep this tab open while recording: the browser is what carries your Arduino\'s data to the app.')),
      h('section', { class: 'card' }, h('h2', null, 'Other ways to connect'), h('h3', { style: { marginTop: '10px' } }, 'A · Bridge script (no browser needed)'),
        h('p', { class: 'muted' }, 'Run this in a terminal on the computer the Arduino is plugged into. It needs an engineer device key or login — see Connect Data.'), h('pre', null, h('code', null, `pip install pyserial requests\npython tools/serial_bridge.py --structure ${sid} --email engineer@vitaforge.demo --password Sense@2026`)),
        h('h3', null, 'B · ESP32 over Wi-Fi'), h('p', { class: 'muted' }, 'Planned and ready: the ESP32 posts the same packets to /api/ingest/serial-lines with a device key. See Connect Data → ESP32.'),
        h('h3', null, 'C · CSV of past recordings'), h('p', { class: 'muted' }, 'Upload under Connect Data → CSV import. Marked FILE.')));
  }

  function settingsTab() {
    const s = ov.settings, inp = {};
    const f = (k, label, hint, step = 'any') => { inp[k] = h('input', { type: 'number', step, value: s[k], disabled: !canEdit }); return field(label, inp[k], hint); };
    return h('section', { class: 'card', style: { maxWidth: '620px' } }, h('h2', null, 'Rig settings'), h('p', { class: 'muted' }, 'Same parameters as your Streamlit prototype. The 20% / 60% thresholds are your project\'s choices, not an engineering standard.'),
      f('trial_duration_sec', 'Trial duration (seconds)', 'How long each recording lasts'), f('num_baseline_trials', 'Baseline trials to record', 'Minimum 3'), f('anomaly_threshold_pct', 'Possible-anomaly threshold (%)', 'Deviation above this = POSSIBLE ANOMALY'), f('urgent_threshold_pct', 'Urgent-review threshold (%)', 'Deviation above this = URGENT REVIEW'),
      f('min_quality_samples', 'Minimum samples per trial', 'Rejects trials with fewer readings (bad connection)'), f('baud_rate', 'Serial baud rate', 'Must match the Arduino sketch (115200)'),
      h('button', { class: 'btn primary', disabled: !canEdit, onclick: async () => { try { const body = {}; for (const k in inp) body[k] = +inp[k].value; await put(`/impact/${sid}/settings`, body); toast('Settings saved', 'ok'); await load(); paintAll(); } catch (e) { toast(e.message, 'err'); } } }, 'Save settings'));
  }

  const tabBar = () => tabs([['live', 'Live & test'], ['baseline', 'Baseline'], ['results', 'Results'], ['connect', 'Connect Arduino'], ['settings', 'Settings']], tab, (t) => { tab = t; paintAll(); });
  const tabHost = h('div');
  function paintAll() { if (closed) return; tabHost.replaceChildren(tabBar()); redrawBody(); }

  try { await load(); } catch (e) { box.replaceChildren(errorBox(e)); return; }
  box.replaceChildren(head(), tabHost, body); paintAll();
  // live stream: append packets, refresh the status line a few times a second
  let lastPaint = 0;
  const offP2 = on('p2p', d => {
    if (d.structure_id !== sid) return;
    pts.t.push(d.ts_ms); pts.s1.push(d.s1); pts.s2.push(d.s2); pts.s3.push(d.s3);
    while (pts.t.length > 120) { pts.t.shift(); pts.s1.shift(); pts.s2.shift(); pts.s3.shift(); }
    connected = true; dataSource = d.source;
    if (tab === 'live' && Date.now() - lastPaint > 400) { lastPaint = Date.now(); paintChart(); paintTiles(); paintStatus(); }
  });
  const poll = setInterval(async () => { if (tab !== 'live' || closed) return; try { const l = await get(`/impact/${sid}/live`); liveStatus = l.status; connected = l.connected; dataSource = l.source; ov.baseline = l.baseline; paintStatus(); } catch (e) {} }, 1500);
  return () => { closed = true; offP2(); clearInterval(poll); clearInterval(recTimer); };
}
