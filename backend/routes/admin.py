"""
Admin panel — login (GitHub username + password) and analytics dashboard.
Served by the backend at /admin; stats come from PostgreSQL via services.db.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from jose import jwt, JWTError

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS
from services import db

router = APIRouter(prefix="/admin")

ADMIN_EXPIRE_HOURS = 24


def _require_admin(request: Request) -> str:
    """Validate the admin bearer token; returns the admin username."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth[7:].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not an admin")
    return payload.get("sub", "")


@router.post("/login")
async def admin_login(body: dict):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if not db.verify_admin(username, password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    payload = {
        "sub": username,
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=ADMIN_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token, "username": username}


@router.get("/stats")
async def admin_stats(request: Request):
    _require_admin(request)
    stats = db.get_stats()
    if not stats:
        raise HTTPException(status_code=503, detail="Analytics database not configured")
    return stats


@router.get("/users")
async def admin_users(request: Request):
    _require_admin(request)
    return {"users": db.list_users(100)}


@router.get("/jobs")
async def admin_jobs(request: Request):
    _require_admin(request)
    return {"jobs": db.list_jobs(100)}


@router.get("/events")
async def admin_events(request: Request):
    _require_admin(request)
    return {"events": db.list_events(200)}


@router.get("/logs")
async def admin_logs(request: Request):
    _require_admin(request)
    return {"logs": db.list_logs(200)}


PANEL_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clipo Admin</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b0f17; color: #e6edf7; min-height: 100vh;
  }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 20px 60px; }
  header { display: flex; align-items: center; justify-content: space-between; padding: 18px 0 22px; }
  header h1 { font-size: 22px; }
  header .who { color: #8ea2c0; font-size: 13px; }
  .btn {
    background: #3b82f6; color: #fff; border: 0; border-radius: 8px;
    padding: 10px 18px; font-size: 14px; cursor: pointer;
  }
  .btn:hover { background: #2f6fe0; }
  .btn.ghost { background: transparent; border: 1px solid #2b3a54; }
  .card {
    background: #131a26; border: 1px solid #22304a; border-radius: 12px; padding: 18px; margin-bottom: 18px;
  }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
  .stat { background: #131a26; border: 1px solid #22304a; border-radius: 12px; padding: 14px; }
  .stat .num { font-size: 26px; font-weight: 700; }
  .stat .lbl { color: #8ea2c0; font-size: 12px; margin-top: 4px; text-transform: uppercase; letter-spacing: .04em; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #1d2839; white-space: nowrap; }
  th { color: #8ea2c0; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }
  td .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; }
  .badge.green { background: #12351f; color: #4ade80; }
  .badge.red { background: #3b1216; color: #f87171; }
  .badge.yellow { background: #3a2e12; color: #fbbf24; }
  .badge.gray { background: #222b3b; color: #9aa8c0; }
  .bars { display: flex; align-items: flex-end; gap: 6px; height: 120px; padding-top: 10px; }
  .bars .bar { flex: 1; background: #3b82f6; border-radius: 4px 4px 0 0; min-height: 2px; position: relative; }
  .bars .bar span { position: absolute; top: -18px; left: 0; right: 0; text-align: center; font-size: 10px; color: #8ea2c0; }
  .day-lbl { font-size: 10px; color: #5d6f8c; text-align: center; margin-top: 6px; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 760px) { .grid2 { grid-template-columns: 1fr; } }
  .error { color: #f87171; font-size: 13px; min-height: 18px; margin-top: 10px; }
  .muted { color: #8ea2c0; font-size: 12px; }
  .log-err { color: #f87171; }
  .log-warn { color: #fbbf24; }
  input {
    width: 100%; background: #0b0f17; border: 1px solid #2b3a54; color: #e6edf7;
    border-radius: 8px; padding: 11px 12px; font-size: 14px; margin-bottom: 10px;
  }
  input:focus { outline: none; border-color: #3b82f6; }
  .login-card { max-width: 340px; margin: 12vh auto 0; }
  .login-card h2 { margin-bottom: 18px; }
  #logout-wrap { display: flex; align-items: center; gap: 10px; }
  .hidden { display: none !important; }
  .scroll { max-height: 340px; overflow-y: auto; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Clipo Admin</h1>
    <div id="logout-wrap" class="hidden"><span class="who" id="whoami"></span><button class="btn ghost" onclick="logout()">Logout</button></div>
  </header>

  <div id="login-view">
    <div class="card login-card">
      <h2>Admin Sign In</h2>
      <input id="user" placeholder="GitHub username" autocomplete="username">
      <input id="pass" type="password" placeholder="Password" autocomplete="current-password">
      <button class="btn" style="width:100%" onclick="login()">Sign in</button>
      <div class="error" id="login-err"></div>
    </div>
  </div>

  <div id="dash-view" class="hidden">
    <div class="stats" id="stats"></div>
    <div class="grid2" style="margin-top:18px">
      <div class="card">
        <h3 style="margin-bottom:6px">Signups (last 14 days)</h3>
        <div class="bars" id="signup-bars"></div>
      </div>
      <div class="card">
        <h3 style="margin-bottom:6px">Jobs (last 14 days)</h3>
        <div class="bars" id="jobs-bars"></div>
      </div>
    </div>
    <div class="card">
      <h3 style="margin-bottom:8px">Top events (last 14 days)</h3>
      <table><thead><tr><th>Event</th><th>Count</th></tr></thead><tbody id="top-events"></tbody></table>
    </div>
    <div class="grid2">
      <div class="card">
        <h3 style="margin-bottom:8px">Recent signups</h3>
        <div class="scroll"><table><thead><tr><th>Email</th><th>Name</th><th>Joined</th></tr></thead><tbody id="users"></tbody></table></div>
      </div>
      <div class="card">
        <h3 style="margin-bottom:8px">Recent jobs</h3>
        <div class="scroll"><table><thead><tr><th>Type</th><th>Status</th><th>Title</th><th>Created</th></tr></thead><tbody id="jobs"></tbody></table></div>
      </div>
    </div>
    <div class="card">
      <h3 style="margin-bottom:8px">Live events</h3>
      <div class="scroll"><table><thead><tr><th>Time</th><th>User</th><th>Event</th><th>Details</th></tr></thead><tbody id="events"></tbody></table></div>
    </div>
    <div class="card">
      <h3 style="margin-bottom:8px">Server logs</h3>
      <div class="scroll"><table><thead><tr><th>Time</th><th>Level</th><th>Message</th></tr></thead><tbody id="logs"></tbody></table></div>
    </div>
  </div>
</div>

<script>
let token = localStorage.getItem('clipo_admin_token') || '';
let autoRefresh = null;

function api(path) {
  return fetch(path, { headers: { 'Authorization': 'Bearer ' + token } })
    .then(r => { if (r.status === 401) { showLogin(); throw new Error('unauthorized'); } return r.json(); });
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function shortId(s) { return s && s.length > 12 ? s.slice(0, 12) + '…' : (s || '-'); }
function fmt(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function badge(status) {
  const cls = { completed: 'green', failed: 'red', pending: 'yellow', analyzing: 'yellow', transcribing: 'yellow' }[status] || 'gray';
  return '<span class="badge ' + cls + '">' + esc(status) + '</span>';
}
function renderBars(series, el) {
  const days = {};
  for (let i = 13; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    days[d.toISOString().slice(0, 10)] = 0;
  }
  (series || []).forEach(r => { days[r.day] = r.n; });
  const vals = Object.values(days);
  const max = Math.max(1, ...vals);
  el.innerHTML = vals.map(v =>
    '<div class="bar" style="height:' + (v / max * 100) + '%" title="' + v + '"><span>' + (v || '') + '</span></div>'
  ).join('');
}

function login() {
  const username = document.getElementById('user').value.trim();
  const password = document.getElementById('pass').value;
  document.getElementById('login-err').textContent = '';
  fetch('/admin/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  }).then(async r => {
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Login failed');
    token = d.token; localStorage.setItem('clipo_admin_token', token);
    showDash(d.username);
  }).catch(e => { document.getElementById('login-err').textContent = e.message; });
}
function logout() {
  token = ''; localStorage.removeItem('clipo_admin_token');
  if (autoRefresh) clearInterval(autoRefresh);
  showLogin();
}
function showLogin() {
  document.getElementById('login-view').classList.remove('hidden');
  document.getElementById('dash-view').classList.add('hidden');
  document.getElementById('logout-wrap').classList.add('hidden');
}
function showDash(username) {
  document.getElementById('login-view').classList.add('hidden');
  document.getElementById('dash-view').classList.remove('hidden');
  document.getElementById('logout-wrap').classList.remove('hidden');
  document.getElementById('whoami').textContent = 'Signed in as ' + username;
  loadDash();
  if (autoRefresh) clearInterval(autoRefresh);
  autoRefresh = setInterval(loadDash, 30000);
}
function loadDash() {
  api('/admin/stats').then(s => {
    document.getElementById('stats').innerHTML = [
      ['Users', s.total_users], ['Signups (7d)', s.signups_7d],
      ['Jobs', s.total_jobs], ['Jobs (7d)', s.jobs_7d],
      ['Completed', s.jobs_completed], ['Failed', s.jobs_failed],
      ['Events (24h)', s.events_24h], ['Errors (24h)', s.errors_24h]
    ].map(([l, n]) => '<div class="stat"><div class="num">' + n + '</div><div class="lbl">' + l + '</div></div>').join('');
    renderBars(s.signups_series, document.getElementById('signup-bars'));
    renderBars(s.jobs_series, document.getElementById('jobs-bars'));
    document.getElementById('top-events').innerHTML =
      (s.events_by_name || []).map(e => '<tr><td>' + esc(e.event_name) + '</td><td>' + e.n + '</td></tr>').join('');
  }).catch(() => {});
  api('/admin/users').then(d => {
    document.getElementById('users').innerHTML = (d.users || []).map(u =>
      '<tr><td>' + esc(u.email || '-') + '</td><td>' + esc(u.name || '-') + '</td><td class="muted">' + fmt(u.created_at) + '</td></tr>').join('');
  }).catch(() => {});
  api('/admin/jobs').then(d => {
    document.getElementById('jobs').innerHTML = (d.jobs || []).map(j =>
      '<tr><td class="mono">' + esc(j.source_type || '-') + '</td><td>' + badge(j.status) + '</td><td>' + esc((j.video_title || '').slice(0, 40)) + '</td><td class="muted">' + fmt(j.created_at) + '</td></tr>').join('');
  }).catch(() => {});
  api('/admin/events').then(d => {
    document.getElementById('events').innerHTML = (d.events || []).map(e => {
      let props = '';
      try { props = Object.entries(JSON.parse(e.properties || '{}')).map(([k, v]) => k + '=' + esc(String(v)).slice(0, 30)).join(', '); } catch (_) {}
      return '<tr><td class="muted">' + fmt(e.created_at) + '</td><td class="mono">' + shortId(e.user_id) + '</td><td>' + esc(e.event_name) + '</td><td class="muted">' + props + '</td></tr>';
    }).join('');
  }).catch(() => {});
  api('/admin/logs').then(d => {
    document.getElementById('logs').innerHTML = (d.logs || []).map(l =>
      '<tr><td class="muted">' + fmt(l.created_at) + '</td><td><span class="badge ' + (l.level === 'error' ? 'red' : l.level === 'warn' ? 'yellow' : 'gray') + '">' + esc(l.level) + '</span></td><td class="mono">' + esc(String(l.message).slice(0, 120)) + '</td></tr>').join('');
  }).catch(() => {});
}

if (token) { showDash(localStorage.getItem('clipo_admin_user') || ''); } else { showLogin(); }
</script>
</body>
</html>
"""


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_panel():
    return HTMLResponse(PANEL_HTML)
