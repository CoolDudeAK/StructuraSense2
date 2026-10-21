import { h, fmt, chip, tabs, empty, table, field, toast, modal, loading, errorBox, confirmBox, download } from '../ui.js';
import { get, post, patch, del, api, session } from '../api.js';
import { nav, setSid } from '../main.js';

export async function render(box, { query }) {
  let tab = query.get('tab') || 'devices', sid = nav.sid, devs = [], zones = [], hist = [], closed = false, lastKey = null;
  const can = session.can('engineer'), host = h('div');
  const load = async () => { const [d, s, hi] = await Promise.all([get('/devices?structure_id=' + sid), get('/structures/' + sid), get('/ingest/csv/history?structure_id=' + sid)]); devs = d; zones = s.zones; hist = hi; };
  const draw = () => {
    if (closed) return;
    host.replaceChildren(h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'Connect data'), h('p', null, 'Three ways real measurements get in — Arduino over USB, ESP32/any device over Wi-Fi (HTTP), and CSV files. Everything that arrives is tagged LIVE or FILE; the simulator is always tagged SIMULATED.')),
      h('select', { 'aria-label': 'Structure', onchange: async (e) => { sid = e.target.value; setSid(sid); await load(); draw(); } }, nav.structures.map(s => h('option', { value: s.id, selected: s.id === sid }, s.id + ' · ' + s.name.split('(')[0])))),
      tabs([['devices', 'Devices'], ['arduino', 'Arduino USB'], ['esp32', 'ESP32 / HTTP'], ['csv', 'CSV import']], tab, (t) => { tab = t; draw(); }),
      tab === 'devices' ? devicesTab() : tab === 'arduino' ? arduinoTab() : tab === 'esp32' ? esp32Tab() : csvTab());
  };
  const reload = async () => { await load(); draw(); };

  function showKey(res, title = 'Device key') {
    const origin = location.origin;
    modal(title, h('div', null, h('p', { class: 'note' }, 'Copy this key now — it is shown only once. The server stores only a scrambled version.'), h('pre', null, h('code', null, res.api_key)),
      h('p', null, 'Test it from any computer (replace the address if the device is on another machine):'), h('pre', null, h('code', null, `curl -X POST ${origin}/api/ingest/readings \\\n  -H "X-Device-Key: ${res.api_key}" -H "Content-Type: application/json" \\\n  -d '{"device_id":"${res.id}","readings":[{"value":25.4}]}'`))),
      [{ label: 'Copy key', run: async () => { try { await navigator.clipboard.writeText(res.api_key); toast('Key copied', 'ok'); } catch (e) { toast('Select and copy it manually.', 'warn'); } return false; } }, { label: 'Done', kind: 'primary' }]);
    lastKey = res;
  }
  function addDevice() {
    const id = h('input', { placeholder: 'e.g. esp-strain-04', maxlength: 41 }), name = h('input', { placeholder: 'Human name, e.g. Strain gauge — girder G2' }), kind = h('select', null, ['strain', 'temperature', 'moisture', 'lvdt', 'wim', 'accelerometer', 'piezo', 'microphone', 'rf_coil'].map(k => h('option', { value: k }, k)));
    const unit = h('input', { placeholder: 'µε, °C, %, mm, kN, g…' }), zone = h('select', null, h('option', { value: '' }, 'Not assigned'), zones.map(z => h('option', { value: z.id }, z.name))), src = h('select', null, [['esp32_http', 'ESP32 / HTTP'], ['arduino_serial', 'Arduino serial'], ['manual', 'Manual / other'], ['csv', 'CSV only']].map(([v, t]) => h('option', { value: v }, t)));
    const fs = h('input', { type: 'number', placeholder: 'Hz (vibration sensors)', min: 1 });
    modal('Add a device', h('div', null, field('Device id', id, 'Letters, numbers, - and _. This is what the hardware sends.'), field('Name', name), field('Type', kind), field('Unit', unit), field('Zone', zone), field('Source', src), field('Sample rate (vibration sensors only)', fs)),
      [{ label: 'Cancel' }, { label: 'Create & get key', kind: 'primary', run: async () => { try { const r = await post('/devices', { structure_id: sid, id: id.value.trim(), name: name.value, kind: kind.value, unit: unit.value, zone_id: zone.value, source_type: src.value, fs: fs.value ? +fs.value : undefined }); await reload(); showKey(r, 'Device created'); } catch (e) { toast(e.message, 'err'); return false; } } }]);
  }
  function devicesTab() {
    return h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('div', null, h('h2', null, 'Devices on ', sid), h('p', null, 'A simulated device becomes a real one the moment real data arrives for it.')), can ? h('button', { class: 'btn primary', onclick: addDevice }, '+ Add device') : null),
      table([{ label: 'Id', render: d => h('code', null, d.id) }, { label: 'Name', key: 'name' }, { label: 'Type', key: 'kind' }, { label: 'Source', render: d => chip(d.source_type === 'simulated' ? 'sim' : 'live', d.source_type.replace('_', ' ').toUpperCase()) },
        { label: 'Status', render: d => h('span', null, h('span', { class: 'dots ' + (d.status === 'online' ? 'on' : d.status === 'offline' ? 'off' : '') }), d.status) }, { label: 'Last seen', render: d => fmt.ago(d.last_seen_ms) },
        { label: '', render: d => can ? h('span', { class: 'row', style: { gap: '4px', flexWrap: 'nowrap' } }, h('button', { class: 'btn sm', onclick: async () => { if (await confirmBox('Make a new key?', `The old key for ${d.id} stops working immediately.`, 'New key')) showKey(await post(`/devices/${d.id}/rotate-key`), 'New key'); } }, 'Key'),
          h('button', { class: 'btn sm danger', 'aria-label': 'Delete device', onclick: async () => { if (await confirmBox('Delete device?', `${d.name} and ALL its stored readings will be removed.`, 'Delete')) { await del('/devices/' + d.id); await reload(); } } }, '✕')) : null }], devs));
  }
  function arduinoTab() {
    return h('div', { class: 'grid g2' }, h('section', { class: 'card' }, h('h2', null, 'Arduino over USB ', chip('REAL', 'REAL INPUT')), h('p', null, 'Your 3-piezo specimen rig is already wired up: Impact Lab reads the Arduino directly from the browser.'), h('a', { class: 'btn primary', href: '#/impact/STR-001?x=1', onclick: () => setTimeout(() => {}, 0) }, 'Open Impact Lab → Connect Arduino'),
      h('p', { class: 'muted' }, 'Tested here with simulated packets only. Your physical Arduino is the final test.')),
      h('section', { class: 'card' }, h('h2', null, 'Other Arduino sensors'), h('p', null, 'Any Arduino that prints ', h('code', null, 'S|device_id|value'), ' (one reading) or ', h('code', null, 'W|device_id|rate|v1,v2,…'), ' (one raw vibration capture; see firmware/arduino_piezo) can be forwarded by the bridge script:'), h('pre', null, h('code', null, 'python tools/serial_bridge.py --port COM3 --structure STR-002 --email engineer@vitaforge.demo --password Sense@2026')),
        h('p', { class: 'muted' }, 'On macOS/Linux use a port like /dev/ttyUSB0. The script lists available ports if you omit --port.')));
  }
  function esp32Tab() {
    const o = location.origin, dv = devs.find(d => d.source_type === 'esp32_http') || devs[0];
    const code = `#include <WiFi.h>\n#include <HTTPClient.h>\n\nconst char* WIFI_SSID = "YOUR_WIFI";\nconst char* WIFI_PASS = "YOUR_PASSWORD";\n// Use your COMPUTER's address on the same Wi-Fi, not 127.0.0.1\nconst char* URL = "http://COMPUTER_IP:5000/api/ingest/readings";\nconst char* DEVICE_ID = "${dv ? dv.id : 'esp-strain-04'}";\nconst char* DEVICE_KEY = "PASTE_KEY_HERE";  // from Devices → Key\n\nvoid setup(){ Serial.begin(115200); WiFi.begin(WIFI_SSID, WIFI_PASS);\n  while(WiFi.status()!=WL_CONNECTED) delay(300); }\n\nvoid loop(){\n  float v = analogRead(34) * (3.3/4095.0);   // replace with your sensor reading\n  HTTPClient http; http.begin(URL);\n  http.addHeader("Content-Type","application/json");\n  http.addHeader("X-Device-Key", DEVICE_KEY);\n  String body = String("{\\"device_id\\":\\"") + DEVICE_ID + "\\",\\"readings\\":[{\\"value\\":" + v + "}]}";\n  int code = http.POST(body);  Serial.println(code);   // 200 = accepted\n  http.end(); delay(2000);\n}`;
    return h('div', { class: 'grid g2' }, h('section', { class: 'card' }, h('h2', null, 'ESP32 (or any Wi-Fi board) ', chip('EXTERNAL', 'NEEDS YOUR HARDWARE')), h('ol', { style: { paddingLeft: '1.2em' } }, h('li', null, 'Add a device on the Devices tab and copy its key.'), h('li', null, 'Find your computer\'s Wi-Fi address (Windows: run ', h('code', null, 'ipconfig'), ', look for IPv4).'), h('li', null, 'Start the server so other devices can reach it: ', h('code', null, 'python run.py --host 0.0.0.0')), h('li', null, 'Paste the sketch → Arduino IDE, fill in the 4 values, upload.'), h('li', null, 'The device turns LIVE on the Devices tab within seconds.')),
      h('p', { class: 'note' }, 'Anyone on your network can reach the server when you use 0.0.0.0. Fine for a demo; do not do this on a public network.')),
      h('section', { class: 'card' }, h('h2', null, 'Sketch'), h('pre', null, h('code', null, code)), h('div', { class: 'row' }, h('button', { class: 'btn sm', onclick: () => { navigator.clipboard.writeText(code).then(() => toast('Copied', 'ok')).catch(() => toast('Select and copy manually', 'warn')); } }, 'Copy'), h('button', { class: 'btn sm', onclick: () => download('esp32_http.ino', code, 'text/plain') }, 'Download .ino')),
        h('p', { class: 'muted' }, 'The same file is in firmware/esp32_http in the project folder.')));
  }
  function csvTab() {
    let prev = null; const file = h('input', { type: 'file', accept: '.csv,.txt,text/csv' }), out = h('div'), mode = h('select', { 'aria-label': 'Format' }, [['', 'Auto-detect'], ['long', 'Long: timestamp, device_id, value'], ['wide', 'Wide: timestamp + one column per device'], ['waveform', 'Raw waveform: one column of samples']].map(([v, t]) => h('option', { value: v }, t)));
    const dev = h('select', { 'aria-label': 'Waveform device' }, devs.filter(d => d.channel === 'waveform').map(d => h('option', { value: d.id }, d.name))), fs = h('input', { type: 'number', placeholder: 'Sample rate Hz', 'aria-label': 'Sample rate' });
    const fd = () => { const f = new FormData(); f.append('file', file.files[0]); f.append('structure_id', sid); if (mode.value) f.append('mode', mode.value); if (mode.value === 'waveform' || (prev && prev.mode_guess === 'waveform')) { f.append('device_id', dev.value); if (fs.value) f.append('fs', fs.value); } return f; };
    file.onchange = async () => { if (!file.files[0]) return; out.replaceChildren(loading('Reading file…')); try { prev = await api('/ingest/csv/preview', { method: 'POST', form: (() => { const f = new FormData(); f.append('file', file.files[0]); f.append('structure_id', sid); return f; })() });
      out.replaceChildren(h('p', null, h('b', null, prev.filename), ` · ${prev.rows} rows · looks like: `, h('code', null, prev.mode_guess)), table(prev.columns.map((c, i) => ({ label: c, render: r => r[i] })), prev.preview), prev.matching_device_columns.length ? h('p', { class: 'muted' }, 'Columns matching devices here: ' + prev.matching_device_columns.join(', ')) : h('p', { class: 'note' }, 'No column matches a device id on this structure. Rename the column headers to device ids, or use the long format with a device_id column.')); } catch (e) { out.replaceChildren(h('p', { class: 'note' }, e.message)); } };
    return h('div', { class: 'grid g2' }, h('section', { class: 'card' }, h('h2', null, 'Import a CSV ', chip('file')), h('p', { class: 'muted' }, 'Readings imported from files are tagged FILE. Timestamps can be ISO dates (2026-10-01T10:00:00Z) or epoch seconds/milliseconds.'),
      field('CSV file', file), field('Format', mode), field('Waveform device (waveform format only)', dev), field('Sample rate (waveform format only)', fs), out,
      h('button', { class: 'btn primary', disabled: !can, onclick: async () => { if (!file.files[0]) { toast('Choose a file first.', 'warn'); return; } try { const r = await api('/ingest/csv', { method: 'POST', form: fd() }); toast(`Imported ${r.rows_ok} rows (${r.rows_rejected} rejected)`, r.rows_rejected ? 'warn' : 'ok', 7000); if (r.errors.length) out.replaceChildren(h('div', { class: 'note' }, h('b', null, 'Some rows were skipped:'), h('ul', null, r.errors.map(e => h('li', null, e))))); await reload(); } catch (e) { toast(e.message, 'err', 8000); } } }, 'Import')),
      h('section', { class: 'card' }, h('h2', null, 'Recent imports'), table([{ label: 'When', render: i => fmt.dt(i.ts_ms) }, { label: 'File', key: 'filename' }, { label: 'Format', key: 'mode' }, { label: 'OK', cls: 'num', key: 'rows_ok' }, { label: 'Skipped', cls: 'num', key: 'rows_rejected' }], hist, { empty: 'Nothing imported yet.' }),
        h('h3', { style: { marginTop: '14px' } }, 'Example files'), h('p', { class: 'muted' }, 'Sample CSVs are in the data/ folder of the project (long, wide and waveform).')));
  }
  box.append(host); host.replaceChildren(loading());
  try { await load(); } catch (e) { host.replaceChildren(errorBox(e)); return; }
  draw();
  return () => { closed = true; };
}
