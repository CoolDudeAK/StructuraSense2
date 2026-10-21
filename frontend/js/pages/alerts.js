import { h, fmt, chip, tabs, empty, field, toast, modal, loading, errorBox, debounce, table } from '../ui.js';
import { get, post, patch, session, on } from '../api.js';
import { nav } from '../main.js';

const PRI = { P1: ['P1 · this week', 'b-crit'], P2: ['P2 · this month', 'b-warn'], P3: ['P3 · routine', 'b-watch'] };
const NEXT = { proposed: [['approved', 'Approve', 'primary'], ['rejected', 'Reject', 'danger']], approved: [['in_progress', 'Start work', ''], ['done', 'Mark done', '']], in_progress: [['done', 'Mark done', 'primary']], rejected: [['proposed', 'Reopen', '']], done: [] };

export async function render(box, { query }) {
  let tab = query.get('tab') || 'alerts', fsev = 'all', fst = 'active', fsid = 'all', alerts = [], tasks = [], closed = false;
  const can = session.can('engineer'), host = h('div'), body = h('div');
  const load = async () => {
    const q = (fst === 'active' ? '?status=active' : fst === 'all' ? '?' : '?status=' + fst) + (fsid !== 'all' ? '&structure_id=' + fsid : '') + (fsev !== 'all' ? '&severity=' + fsev : '');
    [alerts, tasks] = await Promise.all([get('/alerts' + q + '&limit=200'), get('/maintenance' + (fsid !== 'all' ? '?structure_id=' + fsid : ''))]);
  };
  const draw = () => {
    if (closed) return;
    const pend = tasks.filter(t => t.status === 'proposed').length;
    host.replaceChildren(h('div', { class: 'pagehead' }, h('div', null, h('h1', null, 'Alerts & maintenance'), h('p', null, 'The system raises alerts from rules you can see. It can propose maintenance work, but only an engineer can approve it.'))),
      tabs([['alerts', `Alerts (${alerts.filter(a => ['open', 'acknowledged'].includes(a.status)).length} active)`], ['tasks', `Maintenance (${pend} to approve)`]], tab, (t) => { tab = t; draw(); }),
      tab === 'alerts' ? alertsView() : tasksView());
  };
  const reload = async () => { await load(); draw(); };
  function filters(extra) {
    return h('div', { class: 'row', style: { marginBottom: '12px' } }, h('select', { 'aria-label': 'Structure', style: { width: 'auto' }, onchange: (e) => { fsid = e.target.value; reload(); } }, h('option', { value: 'all' }, 'All structures'), nav.structures.map(s => h('option', { value: s.id, selected: s.id === fsid }, s.id))), extra);
  }
  function alertsView() {
    return h('div', null, filters([h('select', { 'aria-label': 'Status', style: { width: 'auto' }, onchange: (e) => { fst = e.target.value; reload(); } }, [['active', 'Active'], ['resolved', 'Resolved'], ['cleared', 'Auto-cleared'], ['dismissed', 'Dismissed'], ['all', 'Everything']].map(([v, t]) => h('option', { value: v, selected: v === fst }, t))),
      h('select', { 'aria-label': 'Severity', style: { width: 'auto' }, onchange: (e) => { fsev = e.target.value; reload(); } }, [['all', 'Any severity'], ['critical', 'Critical'], ['warning', 'Warning'], ['info', 'Info']].map(([v, t]) => h('option', { value: v, selected: v === fsev }, t)))]),
      alerts.length ? h('div', { class: 'list' }, alerts.map(a => h('article', { class: 'item' }, h('span', { class: 'sevbar sev-' + a.severity }),
        h('div', { class: 'grow' }, h('div', { class: 'row', style: { gap: '6px' } }, h('h4', null, a.title), chip(a.origin)), h('p', null, a.message),
          h('small', { class: 'muted' }, `${a.structure_name.split('(')[0]} · ${a.zone_name || 'structure-wide'} · ${fmt.ago(a.ts_ms)} · `, h('b', null, a.status), a.ack_by ? ` · seen by ${a.ack_by}` : '', a.resolution_note ? ` · note: "${a.resolution_note}"` : '')),
        can && ['open', 'acknowledged'].includes(a.status) ? h('div', { class: 'row', style: { alignSelf: 'center', flexWrap: 'nowrap' } },
          a.status === 'open' ? h('button', { class: 'btn sm', onclick: async () => { try { await post(`/alerts/${a.id}/ack`); await reload(); } catch (e) { toast(e.message, 'err'); } } }, 'Acknowledge') : null,
          h('button', { class: 'btn sm primary', onclick: () => resolve(a) }, 'Resolve'), h('button', { class: 'btn sm', onclick: async () => { await post(`/alerts/${a.id}/dismiss`); await reload(); } }, 'Dismiss')) : null)))
        : empty('No alerts match', 'Great — nothing needs attention with these filters.'));
  }
  function resolve(a) {
    const note = h('textarea', { placeholder: 'What did you check or do? e.g. "Inspected bearing, found loose bolt, tightened."', 'aria-label': 'Resolution note' });
    modal('Resolve: ' + a.title, h('div', null, h('p', { class: 'muted' }, 'A short note is required — it becomes part of the permanent record.'), note), [{ label: 'Cancel' }, { label: 'Resolve alert', kind: 'primary', run: async () => { try { await post(`/alerts/${a.id}/resolve`, { note: note.value }); toast('Alert resolved', 'ok'); await reload(); } catch (e) { toast(e.message, 'err'); return false; } } }]);
  }
  function tasksView() {
    const cols = ['proposed', 'approved', 'in_progress', 'done'], label = { proposed: 'Proposed by system', approved: 'Approved', in_progress: 'In progress', done: 'Done' };
    return h('div', null, filters(can ? h('button', { class: 'btn primary', onclick: newTask }, '+ New task') : null),
      h('p', { class: 'note info', style: { marginBottom: '12px' } }, 'Human in the loop: rule-proposed tasks stay "Proposed" until an engineer approves them. The approver\'s name and time are recorded.'),
      h('div', { class: 'grid g4', style: { alignItems: 'start' } }, cols.map(c => h('section', { class: 'card' }, h('h3', null, label[c], ' ', h('small', { class: 'muted' }, tasks.filter(t => t.status === c).length)),
        h('div', { class: 'list', style: { marginTop: '8px' } }, tasks.filter(t => t.status === c).map(t => h('div', { class: 'item', style: { flexDirection: 'column', gap: '4px' } },
          h('div', { class: 'row', style: { justifyContent: 'space-between', flexWrap: 'nowrap' } }, h('span', { class: 'badge ' + PRI[t.priority][1] }, t.priority), t.proposed_by === 'rules-engine' ? chip('SIMULATED', 'RULE-PROPOSED') : h('small', { class: 'muted' }, t.proposed_by)),
          h('h4', null, t.title), h('p', null, t.description), h('small', { class: 'muted' }, `${t.structure_name.split('(')[0]} · ${t.zone_name || 'whole structure'}${t.est_cost_inr ? ' · est. ' + fmt.inr(t.est_cost_inr) : ''}`),
          t.signed_off_by ? h('small', { class: 'muted' }, `${c === 'done' ? 'Done' : 'Signed off'} by ${t.signed_off_by}`) : null,
          can ? h('div', { class: 'row', style: { gap: '4px' } }, (NEXT[t.status] || []).map(([to, lab, k]) => h('button', { class: 'btn sm ' + k, onclick: async () => { try { await patch('/maintenance/' + t.id, { status: to }); await reload(); } catch (e) { toast(e.message, 'err'); } } }, lab))) : null)))))));
  }
  function newTask() {
    const sid = h('select', { 'aria-label': 'Structure' }, nav.structures.map(s => h('option', { value: s.id }, s.id + ' · ' + s.name.split('(')[0])));
    const title = h('input', { placeholder: 'e.g. Re-grout bearing pad, Span 2', maxlength: 120 }), desc = h('textarea'), pri = h('select', null, Object.entries(PRI).map(([k, v]) => h('option', { value: k }, v[0]))), cost = h('input', { type: 'number', min: 0, placeholder: 'optional' }), due = h('input', { type: 'date' });
    modal('New maintenance task', h('div', null, field('Structure', sid), field('Title', title), field('Details', desc), field('Priority', pri), field('Estimated cost (₹)', cost), field('Due date', due)),
      [{ label: 'Cancel' }, { label: 'Create (approved)', kind: 'primary', run: async () => { try { await post('/maintenance', { structure_id: sid.value, title: title.value, description: desc.value, priority: pri.value, est_cost_inr: cost.value ? +cost.value : null, due_date: due.value || null }); toast('Task created', 'ok'); await reload(); } catch (e) { toast(e.message, 'err'); return false; } } }]);
  }
  box.append(host); host.replaceChildren(loading());
  try { await load(); } catch (e) { host.replaceChildren(errorBox(e)); return; }
  draw();
  const re = debounce(() => reload().catch(() => {}), 1000);
  const offs = [on('alert', re), on('alert_update', re)];
  return () => { closed = true; offs.forEach(f => f()); };
}
