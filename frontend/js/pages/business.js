import { h, fmt, chip, field, toast, loading, errorBox, table, kpi } from '../ui.js';
import { get, post } from '../api.js';

export async function render(box) {
  const host = h('div'); box.append(host); host.replaceChildren(loading());
  try {
    const [claims, bench] = await Promise.all([get('/business/claims'), get('/business/benchmarks')]);
    const n = h('input', { type: 'number', min: 1, max: 1000, value: 30 }), kit = h('select', null, ['basic', 'standard', 'extended'].map(k => h('option', { value: k, selected: k === 'standard' }, k))), yrs = h('input', { type: 'number', min: 1, max: 15, value: 5 });
    const out = h('div'); const calc = async () => { try { const q = await post('/business/imaas-quote', { structures: +n.value, kit: kit.value, years: +yrs.value }); const p = q.per_structure;
      out.replaceChildren(h('div', { class: 'grid g3' }, kpi('Per structure (hardware + install)', `${fmt.inr(p.capex_low)} – ${fmt.inr(p.capex_high)}`, `${q.kit} · ${q.sensors} sensors`), kpi('Annual service fee / structure', fmt.inr(p.annual_service_fee), `volume discount ${Math.round(q.volume_discount * 100)}%`), kpi(`${p.years}-year cost / structure`, `${fmt.inr(p.tco_low)} – ${fmt.inr(p.tco_high)}`, `vs ₹${(q.reference.bhm_installed_low / 1e5).toFixed(0)}–${(q.reference.bhm_installed_high / 1e5).toFixed(0)} lakh installed (traditional)`)),
      h('p', null, h('b', null, `${q.portfolio.structures} structures: `), `up-front ${fmt.inr(q.portfolio.capex_low)} – ${fmt.inr(q.portfolio.capex_high)}, annual revenue ${fmt.inr(q.portfolio.annual_revenue)}`), h('p', { class: 'note', style: { marginTop: '8px' } }, q.disclaimer), h('p', { class: 'muted' }, q.reference.note)); } catch (e) { out.replaceChildren(h('p', { class: 'note' }, e.message)); } };
    host.replaceChildren(h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'Business & impact'), h('p', null, 'The commercial story from your dossier, with every claim marked verified, unverified or a hypothesis. Nothing here is a proven result.'))),
      h('div', { class: 'grid g2' }, h('section', { class: 'card' }, h('h2', null, 'IMaaS pricing sketch ', chip('SIMULATED', 'ILLUSTRATIVE')), field('Structures', n), field('Sensor kit', kit), field('Contract years', yrs), h('button', { class: 'btn primary', onclick: calc }, 'Estimate'), out),
        h('section', { class: 'card' }, h('h2', null, 'Where this sits'), table([{ label: 'Who', key: 'name' }, { label: 'Approach', key: 'approach' }, { label: 'Type', key: 'kind' }], bench.rows), h('p', { class: 'muted' }, bench.positioning))),
      h('section', { class: 'card', style: { marginTop: '14px' } }, h('h2', null, 'Claims register'), table([{ label: 'Claim', key: 'claim' }, { label: 'Status', render: c => h('span', { class: 'badge ' + ({ verified: 'b-ok', unverified: 'b-warn', hypothesis: 'b-watch', target: 'b-watch', caution: 'b-warn', future: 'b-none', removed: 'b-crit' }[c.status] || 'b-none') }, c.status) }, { label: 'Basis', key: 'basis' }], claims)));
    calc();
  } catch (e) { host.replaceChildren(errorBox(e)); }
}
