import { h, fmt, chip, field, toast, loading, errorBox, kpi } from '../ui.js';
import { get, post, session, on } from '../api.js';
import { nav, loadStructures } from '../main.js';

export async function render(box) {
  const can = session.can('engineer'); let st, closed = false; const host = h('div');
  const load = async () => { st = await get('/sim/state'); await loadStructures(); };
  const draw = () => {
    if (closed) return;
    const iv = h('input', { type: 'number', min: 1, max: 30, value: st.interval_s, style: { width: '90px' }, 'aria-label': 'Seconds between ticks' });
    host.replaceChildren(h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'Simulator'), h('p', null, 'Generates realistic sensor data for the demo assets so the app is alive without hardware. Everything it makes is labelled SIMULATED and never mixes into real hardware data unless you choose "all data".'))),
      h('section', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'row' }, h('span', null, h('span', { class: 'dots ' + (st.running ? 'on' : '') }), h('b', null, st.running ? 'Running' : 'Paused')), h('span', { class: 'muted' }, `${st.ticks} ticks · every ${st.interval_s}s`), h('div', { class: 'grow' }), h('label', { class: 'row' }, h('small', null, 'Tick every (s)'), iv),
        h('button', { class: 'btn primary', disabled: !can, onclick: async () => { st = { ...st, ...(await post('/sim/control', { running: !st.running, interval: +iv.value })) }; toast(st.running ? 'Simulator started' : 'Simulator paused', 'ok'); await load(); draw(); } }, st.running ? '■ Pause' : '▶ Start'))),
      h('div', { class: 'grid g3' }, st.structures.map(s => card(s))));
  };
  function card(s) {
    const info = nav.structures.find(x => x.id === s.structure_id) || {}; const sc = h('select', { 'aria-label': 'Scenario', disabled: !can }, Object.entries(st.scenarios).map(([k, v]) => h('option', { value: k, selected: k === s.scenario }, v)));
    const act = (label, type, cls = '') => h('button', { class: 'btn sm ' + cls, disabled: !can, onclick: async () => { try { await post('/sim/inject', { structure_id: s.structure_id, type }); toast(label + ' applied', 'ok'); await load(); draw(); } catch (e) { toast(e.message, 'err'); } } }, label);
    return h('section', { class: 'card' }, h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('h3', null, s.structure_id), chip('sim')), h('p', { class: 'muted' }, (info.name || '').split('(')[0]),
      h('div', { class: 'grid g2', style: { gap: '8px', margin: '8px 0' } }, kpi('Simulated damage', Math.round(s.damage * 100) + '%'), kpi('Extra moisture', '+' + fmt.n(s.moisture_boost, 1) + ' %')),
      field('Scenario', sc), h('button', { class: 'btn sm', disabled: !can, onclick: async () => { try { await post('/sim/scenario', { structure_id: s.structure_id, scenario: sc.value }); toast('Scenario set', 'ok'); await load(); draw(); } catch (e) { toast(e.message, 'err'); } } }, 'Apply scenario'),
      h('h4', { style: { margin: '12px 0 6px' } }, 'Inject an event'), h('div', { class: 'row', style: { gap: '6px' } }, act('Crack step', 'crack_step'), act('Overloaded vehicle', 'overload_vehicle'), act('Moisture spike', 'moisture_spike'), act('Reset', 'reset', 'ghost')),
      h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn sm', disabled: !can, onclick: async () => { try { await post('/sim/step', { structure_id: s.structure_id, n: 30 }); toast('Added 30 ticks of history', 'ok'); } catch (e) { toast(e.message, 'err'); } } }, 'Fast-forward 30 ticks')));
  }
  box.append(host); host.replaceChildren(loading());
  try { await load(); } catch (e) { host.replaceChildren(errorBox(e)); return; }
  draw(); return () => { closed = true; };
}
