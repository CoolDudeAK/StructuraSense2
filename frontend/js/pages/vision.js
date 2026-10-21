import { h, fmt, kpi, chip, empty, table, field, toast, loading, errorBox, confirmBox } from '../ui.js';
import { get, post, del, api, session, urlWithToken } from '../api.js';
import { nav, setSid } from '../main.js';

export async function render(box) {
  let sid = nav.sid, zones = [], samples = [], past = [], det = [], result = null, closed = false;
  const can = session.can('engineer'), host = h('div');
  const load = async () => { const [s, sm, p, d] = await Promise.all([get('/structures/' + sid), get('/vision/samples'), get('/vision/analyses?structure_id=' + sid), get('/vision/detectors')]); zones = s.zones; samples = sm; past = p; det = d; };
  const sevCls = (s) => ({ fine: 'b-ok', hairline: 'b-ok', moderate: 'b-warn', severe: 'b-crit', structural: 'b-crit' }[s] || 'b-watch');
  function draw() {
    if (closed) return;
    const file = h('input', { type: 'file', accept: 'image/jpeg,image/png', 'aria-label': 'Photo' });
    const zone = h('select', { 'aria-label': 'Zone' }, h('option', { value: '' }, 'Whole structure / unknown'), zones.map(z => h('option', { value: z.id }, z.name)));
    const scale = h('input', { type: 'number', step: 'any', min: 0.01, placeholder: 'e.g. 10', 'aria-label': 'Pixels per mm' });
    const msg = h('div'); const prev = h('img', { alt: 'Preview', style: { display: 'none', maxWidth: '100%', borderRadius: '8px', marginTop: '8px' } });
    file.onchange = () => { const f = file.files[0]; if (f) { prev.src = URL.createObjectURL(f); prev.style.display = 'block'; } };
    const run = async (url, form, jb) => { msg.replaceChildren(loading('Analysing crack pattern…')); try { result = await api(url, { method: 'POST', form, body: form ? undefined : (jb || {}) }); toast('Analysis complete', 'ok'); await load(); draw(); } catch (e) { msg.replaceChildren(h('p', { class: 'note', style: { borderColor: 'var(--crit)' } }, e.message)); } };
    host.replaceChildren(
      h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'Crack Vision'), h('p', null, 'Upload a close-up photo of a concrete surface. The detector finds thin dark ridges and measures their length and width. Results feed the cracks component of the health index.')),
        h('select', { 'aria-label': 'Structure', onchange: async (e) => { sid = e.target.value; setSid(sid); result = null; await load(); draw(); } }, nav.structures.map(s => h('option', { value: s.id, selected: s.id === sid }, s.id + ' · ' + s.name.split('(')[0])))),
      h('div', { class: 'row', style: { marginBottom: '12px' } }, det.map(d => h('span', { class: 'row', style: { gap: '6px' } }, chip(d.status), h('small', null, d.name)))),
      h('div', { class: 'split' },
        h('section', { class: 'card' }, h('h2', null, 'Analyse a photo'), field('Photo (JPG or PNG, up to 12 MB)', file), prev, field('Zone', zone), field('Scale: pixels per millimetre', scale, 'Photograph a ruler or a coin next to the crack to find this. Leave blank for an uncalibrated result (area % only, no mm).'),
          h('button', { class: 'btn primary', disabled: !can, onclick: () => { if (!file.files[0]) { toast('Choose a photo first.', 'warn'); return; } const f = new FormData(); f.append('image', file.files[0]); f.append('structure_id', sid); f.append('zone_id', zone.value); if (scale.value) f.append('scale_px_per_mm', scale.value); run('/vision/analyze', f); } }, 'Analyse photo'), !can ? h('p', { class: 'muted' }, 'Viewers cannot upload.') : null, msg),
        h('section', { class: 'card' }, h('h2', null, 'Try a bundled sample ', chip('sim', 'SYNTHETIC')), h('p', { class: 'muted' }, 'Computer-generated concrete textures with known crack widths — good for a demo.'),
          h('div', { class: 'list' }, samples.map(s => h('div', { class: 'item' }, h('img', { src: urlWithToken(s.url), alt: s.label, style: { width: '74px', height: '54px', objectFit: 'cover', borderRadius: '6px' } }), h('div', { class: 'grow' }, h('h4', null, s.label), h('p', null, s.caption)),
            h('button', { class: 'btn sm', disabled: !can, onclick: () => run(`/vision/samples/${s.file}/analyze`, null, { structure_id: sid, zone_id: zone.value }) }, 'Run')))))),
      result ? resultCard(result) : null,
      h('section', { class: 'card', style: { marginTop: '14px' } }, h('h2', null, 'History for this structure'),
        table([{ label: 'When', render: a => fmt.dt(a.ts_ms) }, { label: 'Zone', render: a => (zones.find(z => z.id === a.zone_id) || {}).name || '—' }, { label: 'Result', render: a => a.crack_detected ? h('span', { class: 'badge ' + sevCls(a.severity) }, a.severity) : h('span', { class: 'badge b-ok' }, 'no crack') },
          { label: 'Max width', cls: 'num', render: a => a.max_width_mm != null ? fmt.n(a.max_width_mm, 2) + ' mm' : '—' }, { label: 'Area', cls: 'num', render: a => fmt.n(a.crack_area_pct, 2) + '%' }, { label: 'Image', render: a => chip(a.origin === 'sample' ? 'sim' : 'file', a.origin === 'sample' ? 'SYNTHETIC' : 'UPLOAD') },
          { label: '', render: a => h('span', { class: 'row', style: { flexWrap: 'nowrap', gap: '4px' } }, h('button', { class: 'btn sm', onclick: () => { result = a; draw(); window.scrollTo({ top: 300, behavior: 'smooth' }); } }, 'View'), can ? h('button', { class: 'btn sm danger', 'aria-label': 'Delete analysis', onclick: async () => { if (await confirmBox('Delete this analysis?', 'The image and result are removed.', 'Delete')) { await del('/vision/analyses/' + a.id); if (result && result.id === a.id) result = null; await load(); draw(); } } }, '✕') : null) }], past, { empty: 'No analyses yet — upload a photo above.' })));
  }
  function resultCard(r) {
    const cal = r.scale_px_per_mm != null;
    return h('section', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'card-h' }, h('div', null, h('h2', null, r.crack_detected ? 'Crack detected' : 'No crack detected'), h('p', null, `${r.filename || ''} · method ${r.method}`)), h('span', { class: 'badge ' + (r.crack_detected ? sevCls(r.severity) : 'b-ok') }, r.crack_detected ? r.severity : 'clear')),
      h('div', { class: 'grid g2' }, h('figure', { class: 'imgbox', style: { margin: 0 } }, h('img', { src: urlWithToken(r.image_url), alt: 'Original photo' }), h('figcaption', { class: 'muted' }, 'Original')),
        h('figure', { class: 'imgbox', style: { margin: 0 } }, h('img', { src: urlWithToken(r.overlay_url), alt: 'Detected crack overlay' }), h('figcaption', { class: 'muted' }, 'Detection overlay'))),
      h('div', { class: 'grid g4', style: { marginTop: '12px' } }, kpi('Max width', cal && r.crack_detected ? fmt.n(r.max_width_mm, 2) + ' mm' : r.crack_detected ? fmt.n(r.max_width_px, 1) + ' px' : '—', cal ? 'calibrated' : 'uncalibrated (pixels)'), kpi('Length', cal && r.crack_detected ? fmt.n(r.length_mm, 0) + ' mm' : r.crack_detected ? fmt.n(r.length_px, 0) + ' px' : '—'), kpi('Crack area', fmt.n(r.crack_area_pct, 2) + '%'), kpi('Segments', r.segments ?? '—')),
      h('p', { class: 'note', style: { marginTop: '10px' } }, 'Classical image processing, tuned on synthetic images only. Shadows, stains, formwork lines and rebar marks can fool it, and widths depend on your scale. A human must confirm any finding. A trained YOLO/CNN model can plug into this same screen later (see AI Models).'));
  }
  box.append(host); host.replaceChildren(loading());
  try { await load(); } catch (e) { host.replaceChildren(errorBox(e)); return; }
  // sample analyse needs structure_id in the body: patch run for samples
  const origApi = null; draw();
  return () => { closed = true; };
}
