// Thin wrapper around fetch: adds the login token, unwraps errors, and manages the live (SSE) connection.
// When the front end is hosted separately (e.g. Vercel), /config.js sets window.SS_API_BASE to the backend address.
const BASE = (window.SS_API_BASE || '').replace(/\/+$/, '');
let token = null;
try { token = localStorage.getItem('ss_token'); } catch (e) {}
export let user = null;
try { user = JSON.parse(localStorage.getItem('ss_user') || 'null'); } catch (e) {}

export const session = {
  set(t, u) { token = t; user = u; try { localStorage.setItem('ss_token', t); localStorage.setItem('ss_user', JSON.stringify(u)); } catch (e) {} },
  clear() { token = null; user = null; try { localStorage.removeItem('ss_token'); localStorage.removeItem('ss_user'); } catch (e) {} },
  get token() { return token; },
  get user() { return user; },
  can(role) { const r = { viewer: 1, engineer: 2, admin: 3 }; return user && r[user.role] >= r[role]; },
};

export class ApiError extends Error {
  constructor(msg, status, code) { super(msg); this.status = status; this.code = code; }
}

export async function api(path, { method = 'GET', body, form, raw } = {}) {
  const headers = {};
  if (token) headers.Authorization = 'Bearer ' + token;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  let res;
  try { res = await fetch(BASE + '/api' + path, { method, headers, body: payload }); }
  catch (e) { throw new ApiError('Cannot reach the StructuraSense server. Is it still running?', 0, 'network'); }
  if (res.status === 401 && !path.startsWith('/auth/login')) { session.clear(); location.hash = '#/login'; location.reload(); }
  if (raw) return res;
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) {
    const e = data && data.error;
    throw new ApiError((e && e.message) || ('Request failed (' + res.status + ')'), res.status, e && e.code);
  }
  return data;
}
export const get = (p) => api(p);
export const post = (p, body) => api(p, { method: 'POST', body: body || {} });
export const put = (p, body) => api(p, { method: 'PUT', body });
export const patch = (p, body) => api(p, { method: 'PATCH', body });
export const del = (p) => api(p, { method: 'DELETE' });
export const urlWithToken = (u) => (u.startsWith('/') ? BASE : '') + u + (u.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token || '');

// ---- live events (Server-Sent Events) ----
const listeners = {};
let es = null;
export const live = { connected: false, onstate: null };
export function on(evt, fn) { (listeners[evt] = listeners[evt] || new Set()).add(fn); return () => listeners[evt].delete(fn); }
export function connectLive() {
  if (es || !token) return;
  es = new EventSource(urlWithToken('/api/stream'));
  es.onopen = () => { live.connected = true; live.onstate && live.onstate(true); };
  es.onerror = () => { live.connected = false; live.onstate && live.onstate(false); };
  ['tick', 'p2p', 'waveform', 'health', 'alert', 'alert_update'].forEach(n =>
    es.addEventListener(n, ev => { let d = {}; try { d = JSON.parse(ev.data); } catch (e) {} (listeners[n] || []).forEach(f => f(d)); }));
}
export function disconnectLive() { if (es) { es.close(); es = null; live.connected = false; } }
