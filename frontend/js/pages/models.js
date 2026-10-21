import { h, fmt, chip, empty, toast, loading, errorBox, confirmBox } from '../ui.js';
import { get, post, session } from '../api.js';
import { barChart } from '../charts.js';

export async function render(box) {
  const host = h('div'); box.append(host); host.replaceChildren(loading('Loading models (first time may take a few seconds to train)…'));
  let d; const draw = () => host.replaceChildren(h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'AI models'), h('p', null, 'What is real, what was trained on simulated data, and what is only a slot waiting for a model. Nothing here is validated on real structures yet.'))),
    h('div', { class: 'note', style: { marginBottom: '14px' } }, `Deck targets: precision ≥ ${d.targets.precision * 100}% and false alarms ≤ ${d.targets.false_alarm_rate * 100}%. ${d.targets.note}`),
    h('div', { class: 'grid g2' }, d.models.map(m => h('section', { class: 'card' }, h('div', { class: 'card-h' }, h('div', null, h('small', { class: 'muted' }, 'Deck: ' + m.deck_role), h('h2', null, m.implementation.split(':')[0].split(' (')[0].slice(0, 60))), chip(m.status)),
      h('p', null, m.implementation), h('p', null, h('b', null, 'Training: '), m.training), m.metrics ? metrics(m.metrics) : null, h('p', { class: 'note', style: { marginTop: '8px' } }, h('b', null, 'Limits: '), m.limitations),
      m.slot ? h('div', { class: 'item', style: { marginTop: '8px' } }, chip(m.slot.status), h('div', { class: 'grow' }, h('h4', null, m.slot.name), h('p', null, m.slot.detail))) : null,
      m.retrainable ? h('button', { class: 'btn sm', disabled: !session.can('admin'), onclick: async () => { if (!await confirmBox('Retrain?', 'Retrains on simulated data (takes a few seconds).', 'Retrain')) return; try { await post(`/models/${m.id}/retrain`); toast('Retrained', 'ok'); d = await get('/models'); draw(); } catch (e) { toast(e.message, 'err'); } } }, 'Retrain (admin)') : null))));
  function metrics(m) {
    const rows = Object.entries(m).filter(([k, v]) => typeof v !== 'object');
    return h('div', null, h('dl', { class: 'stat-list' }, rows.flatMap(([k, v]) => [h('dt', null, k.replace(/_/g, ' ')), h('dd', null, typeof v === 'number' ? fmt.n(v, 3) : String(v).slice(0, 48))])),
      m.importances ? barChart(Object.entries(m.importances).map(([k, v]) => ({ label: k, value: v, text: fmt.n(v, 2) })), { max: 1 }) : null,
      m.detection_rate_by_simulated_damage ? h('div', null, h('small', { class: 'muted' }, 'Simulated-damage detection rate at 1% false alarms:'), barChart(Object.entries(m.detection_rate_by_simulated_damage).map(([k, v]) => ({ label: Math.round(k * 100) + '% stiffness loss', value: v * 100, text: Math.round(v * 100) + '%', color: 'var(--sim)' })), { max: 100 })) : null);
  }
  try { d = await get('/models'); draw(); } catch (e) { host.replaceChildren(errorBox(e)); }
}
