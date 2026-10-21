import { h, chip, loading, errorBox, table } from '../ui.js';
import { get } from '../api.js';

export async function render(box) {
  const host = h('div'); box.append(host); host.replaceChildren(loading());
  try {
    const rows = await get('/system/provenance'), order = ['REAL', 'SIMULATED', 'EXTERNAL', 'FUTURE'];
    host.replaceChildren(h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'What is real, and what is not'), h('p', null, 'An honest register of every capability in this prototype. Use it when someone asks "is this actually working?"'))),
      h('div', { class: 'legend', style: { marginBottom: '12px' } }, order.map(o => h('span', null, chip(o), ' ', h('small', null, rows.filter(r => r.status === o).length)))),
      order.map(o => rows.some(r => r.status === o) ? h('section', { class: 'card', style: { marginBottom: '14px' } }, h('h2', null, { REAL: 'Real — implemented and working', SIMULATED: 'Simulated — demonstration data', EXTERNAL: 'Needs something outside this computer', FUTURE: 'Future — not built' }[o]),
        table([{ label: 'Area', key: 'area' }, { label: 'Feature', render: r => r.feature }, { label: 'Status', render: r => chip(r.status) }, { label: 'Note', render: r => r.note }], rows.filter(r => r.status === o))) : null),
      h('p', { class: 'note' }, 'This prototype is a decision-support tool. It is not a certified safety system and must not replace inspection by a qualified engineer.'));
  } catch (e) { host.replaceChildren(errorBox(e)); }
}
