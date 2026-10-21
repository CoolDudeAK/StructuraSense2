import { h, $, toast, fmt, errorBox, loading } from './ui.js';
import { api, get, post, session, connectLive, disconnectLive, live, on } from './api.js';

const ROUTES = [
  // [hash prefix, module, label, icon, group, minRole]
  ['overview', './pages/overview.js', 'Overview', '◎', 'Monitor'],
  ['impact', './pages/impact.js', 'Impact Lab (your rig)', '⚡', 'Monitor'],
  ['elements', './pages/elements.js', 'Element Tests (IS codes)', '▤', 'Monitor'],
  ['signal', './pages/signal.js', 'Signal Lab', '〰', 'Analyse'],
  ['vision', './pages/vision.js', 'Crack Vision', '▣', 'Analyse'],
  ['alerts', './pages/alerts.js', 'Alerts & Maintenance', '⚠', 'Act'],
  ['data', './pages/data.js', 'Connect Data', '⇄', 'Connect'],
  ['sim', './pages/sim.js', 'Simulator', '◐', 'Connect'],
  ['models', './pages/models.js', 'AI Models', '✦', 'System'],
  ['cloud', './pages/cloud.js', 'Cloud & Settings', '☁', 'System'],
  ['business', './pages/business.js', 'Business & Impact', '₹', 'System'],
  ['register', './pages/register.js', 'What is real?', '✓', 'System'],
];
export const nav = { structures: [], sid: null };
try { nav.sid = localStorage.getItem('ss_sid'); } catch (e) {}
export function setSid(id) { nav.sid = id; try { localStorage.setItem('ss_sid', id); } catch (e) {} }
export async function loadStructures() { nav.structures = await get('/structures'); if (!nav.structures.find(s => s.id === nav.sid)) setSid((nav.structures[0] || {}).id); return nav.structures; }

const app = $('#app');
let cleanup = null, navToken = 0;

function logo(sz = 30) {
  return h('span', { html: `<svg width="${sz}" height="${sz}" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#16405f"/><path d="M5 21h5l3-9 4 14 3-9 2 4h5" fill="none" stroke="#ff8a3d" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>` });
}

// -------------------------------------------------------------- sign in / sign up
function authScreen() {
  disconnectLive();
  let mode = 'in';
  const err = h('div', { class: 'note', style: { display: 'none', borderColor: 'var(--crit)', marginBottom: '12px' }, role: 'alert' });
  const email = h('input', { type: 'email', autocomplete: 'username', required: true, placeholder: 'you@example.com' });
  const pw = h('input', { type: 'password', autocomplete: 'current-password', required: true });
  const name = h('input', { type: 'text', autocomplete: 'name', placeholder: 'Your name' });
  const nameF = h('label', { class: 'field', style: { display: 'none' } }, h('span', { class: 'f-label' }, 'Full name'), name);
  const submit = h('button', { class: 'btn primary', type: 'submit', style: { width: '100%', justifyContent: 'center' } }, 'Sign in');
  const title = h('h2', null, 'Sign in');
  const swap = h('button', { class: 'btn ghost sm', type: 'button' }, 'New here? Create an account');
  const form = h('form', { onsubmit: async (e) => {
    e.preventDefault(); err.style.display = 'none'; submit.disabled = true;
    try {
      const r = mode === 'in' ? await post('/auth/login', { email: email.value, password: pw.value }) : await post('/auth/register', { email: email.value, password: pw.value, name: name.value });
      session.set(r.token, r.user); location.hash = '#/overview'; boot();
    } catch (ex) { err.textContent = ex.message; err.style.display = 'block'; } finally { submit.disabled = false; }
  } },
    err, nameF,
    h('label', { class: 'field' }, h('span', { class: 'f-label' }, 'Email'), email),
    h('label', { class: 'field' }, h('span', { class: 'f-label' }, 'Password'), pw, h('span', { class: 'f-hint', id: 'pwhint' }, '')),
    submit);
  swap.onclick = () => { mode = mode === 'in' ? 'up' : 'in'; nameF.style.display = mode === 'up' ? '' : 'none'; title.textContent = mode === 'in' ? 'Sign in' : 'Create account'; submit.textContent = mode === 'in' ? 'Sign in' : 'Create account'; swap.textContent = mode === 'in' ? 'New here? Create an account' : 'Have an account? Sign in'; $('#pwhint').textContent = mode === 'up' ? 'At least 8 characters. New accounts are read-only viewers until an admin promotes them.' : ''; };
  const demo = (label, em) => h('button', { class: 'btn', type: 'button', onclick: () => { email.value = em + '@vitaforge.demo'; pw.value = 'Sense@2026'; form.requestSubmit(); } }, label);
  app.replaceChildren(h('div', { class: 'auth' },
    h('section', { class: 'auth-hero' }, h('div', { class: 'row' }, logo(44), h('b', { style: { fontSize: '1.3rem' } }, 'StructuraSense')),
      h('h1', null, 'Know what your structure is telling you — before it fails.'),
      h('p', null, 'A decision-support prototype for structural health monitoring: vibration, crack imaging, strain and moisture fused into one health index, with an engineer always in the loop.'),
      h('div', { class: 'heroline' }, h('span', null, '● Real Arduino USB input'), h('span', null, '● ESP32 / CSV ready'), h('span', null, '● Simulated + live data, always labelled'))),
    h('section', { class: 'auth-form' }, h('div', { class: 'card' }, title, h('div', { style: { height: '12px' } }), form, h('div', { class: 'row', style: { justifyContent: 'space-between' } }, swap),
      h('hr', { style: { border: 0, borderTop: '1px solid var(--line)', margin: '14px 0' } }),
      h('small', null, 'Demo accounts (password Sense@2026):'), h('div', { class: 'demo-accts' }, demo('Engineer — can record, approve, configure', 'engineer'), demo('Admin — everything, including users', 'admin'), demo('Viewer — read-only', 'viewer'))))));
}

// -------------------------------------------------------------- shell
function shell() {
  const side = h('aside', { class: 'side', id: 'side' });
  const groups = {};
  ROUTES.forEach(r => (groups[r[4]] = groups[r[4]] || []).push(r));
  const navEl = h('nav', { class: 'nav', 'aria-label': 'Main' });
  Object.entries(groups).forEach(([g, rs]) => { navEl.append(h('div', { class: 'grp' }, g)); rs.forEach(r => navEl.append(h('a', { href: '#/' + r[0], 'data-r': r[0], onclick: () => side.classList.remove('open') }, h('span', { class: 'ico' }, r[3]), r[2]))); });
  const liveDot = h('span', { class: 'dots', id: 'livedot' });
  side.append(h('div', { class: 'brand' }, logo(34), h('div', null, h('b', null, 'StructuraSense'), h('small', null, 'Team VitaForge · prototype'))), navEl,
    h('div', { class: 'side-foot' }, h('div', null, liveDot, h('span', { id: 'livetxt' }, 'connecting…')), h('div', { class: 'who', style: { marginTop: '8px' } }, session.user.name), h('div', null, session.user.role),
      h('button', { class: 'btn sm', onclick: () => { session.clear(); disconnectLive(); location.hash = '#/login'; authScreen(); } }, 'Sign out')));
  const main = h('main', { class: 'main', id: 'main', tabindex: '-1' });
  app.replaceChildren(h('div', { class: 'topbar' }, h('button', { class: 'icon-btn', style: { color: '#fff' }, 'aria-label': 'Open menu', onclick: () => side.classList.toggle('open') }, '☰'), h('div', { class: 'grow' }, h('b', null, 'StructuraSense'))),
    h('div', { class: 'shell' }, side, main));
  live.onstate = (ok) => { liveDot.className = 'dots ' + (ok ? 'on' : 'off'); $('#livetxt').textContent = ok ? 'live updates on' : 'reconnecting…'; };
  connectLive();
  return main;
}

async function route() {
  if (!session.token) { authScreen(); return; }
  if (!$('#main')) return;
  const [seg, ...rest] = (location.hash.replace(/^#\/?/, '') || 'overview').split('?')[0].split('/');
  const r = ROUTES.find(x => x[0] === seg) || ROUTES[0];
  $$nav(r[0]);
  const main = $('#main'); const tok = ++navToken;
  if (cleanup) { try { cleanup(); } catch (e) {} cleanup = null; }
  main.replaceChildren(loading());
  try {
    const mod = await import(r[1]);
    if (!nav.structures.length) await loadStructures();
    const box = h('div');
    const c = await mod.render(box, { params: rest, query: new URLSearchParams((location.hash.split('?')[1]) || '') });
    if (tok !== navToken) { c && c(); return; }
    cleanup = c; main.replaceChildren(box); main.focus({ preventScroll: true }); window.scrollTo(0, 0);
  } catch (e) { main.replaceChildren(errorBox(e, route)); }
}
function $$nav(id) { document.querySelectorAll('.nav a').forEach(a => a.classList.toggle('on', a.dataset.r === id)); }

async function boot() {
  if (!session.token) { authScreen(); return; }
  try { const me = await get('/auth/me'); session.set(session.token, me.user); } catch (e) { session.clear(); authScreen(); return; }
  shell(); await route();
}
window.addEventListener('hashchange', () => { if (session.token && $('#main')) route(); });
boot();
