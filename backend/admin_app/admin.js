"use strict";

/* ─────────────────────────────────────────────────────────────────────────
   State
   ───────────────────────────────────────────────────────────────────────── */
const S = {
  token: localStorage.getItem("clipo_admin_token") || "",
  username: localStorage.getItem("clipo_admin_user") || "",
  page: "overview",
  tab: "timeseries",
  filters: {},
  autoloading: false,
  timer: null,
};

const PAGES = {
  overview:  { title: "Overview",  icon: "▦" },
  analytics: { title: "Analytics", icon: "◔" },
  sessions:  { title: "Sign-ins",  icon: "⟳" },
  requests:  { title: "Requests",  icon: "⌁" },
  users:     { title: "Users",     icon: "👤" },
  jobs:      { title: "Jobs",      icon: "◫" },
  online:    { title: "Live",      icon: "◉" },
  events:    { title: "Events",    icon: "☰" },
  backends:  { title: "Backends",  icon: "⬡" },
  logs:      { title: "Server logs", icon: "≡" },
  admins:    { title: "Admins",    icon: "⚙" },
};

/* ─────────────────────────────────────────────────────────────────────────
   Helpers
   ───────────────────────────────────────────────────────────────────────── */
const $ = (sel, el) => (el || document).querySelector(sel);
const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function trunc(v, n) {
  v = String(v ?? "");
  return v.length > n ? v.slice(0, n - 1) + "…" : v;
}
function fmt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function fmtDay(iso) {
  if (!iso) return "—";
  return String(iso).slice(0, 10);
}
function fmtMs(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)} s`;
  return `${(ms / 60000).toFixed(1)} min`;
}
function fmtNum(n) {
  n = Number(n || 0);
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}
function qs(params) {
  const parts = [];
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") parts.push(`${k}=${encodeURIComponent(v)}`);
  }
  return parts.length ? "?" + parts.join("&") : "";
}

function badge(text, cls) {
  return `<span class="badge b-${cls}">${esc(text)}</span>`;
}
function statusBadge(status) {
  const map = {
    completed: "green", failed: "red", running: "blue", queued: "yellow",
    cancelled: "gray", pending: "yellow", success: "green",
  };
  return badge(status || "—", map[status] || "gray");
}
function httpBadge(code) {
  if (code == null) return badge("—", "gray");
  const cls = code < 300 ? "green" : code < 400 ? "blue" : code < 500 ? "yellow" : "red";
  return badge(code, cls);
}
function boolBadge(v, t) {
  return v ? badge(t || "yes", "green") : badge(t ? "no" : "—", "gray");
}
function empty(msg) {
  return `<div class="empty">${esc(msg || "Nothing to show")}</div>`;
}
function loading() {
  return `<div class="loading">Loading…</div>`;
}
function deviceIcon(browser, os, device) {
  let icon = "🖥";
  if (/iphone|ipad|ipod/i.test(device || "")) icon = "📱";
  else if (/android/i.test(os || "")) icon = "📱";
  else if (/mac/i.test(os || "")) icon = "💻";
  else if (/windows/i.test(os || "")) icon = "🖥";
  return icon;
}
function userName(row) {
  return String(row.name || row.display_name || "").trim() || String(row.email || "").trim();
}
function userCell(row, idKey) {
  const label = userName(row) || String(row[idKey] || "—");
  const pic = row.picture;
  return (pic
    ? `<img class="uavatar" src="${esc(pic)}" alt="" onerror="this.style.display='none'">`
    : `<span class="uavatar uavatar-fallback">${esc((userName(row) || "?").slice(0, 1).toUpperCase())}</span>`) +
    `<span class="uname">${esc(trunc(label, 28))}${row[idKey] && userName(row) ? `<span class="faint mono">${esc(trunc(row[idKey], 14))}</span>` : ""}</span>`;
}

/* ─────────────────────────────────────────────────────────────────────────
   API
   ───────────────────────────────────────────────────────────────────────── */
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (S.token) headers["Authorization"] = "Bearer " + S.token;
  const res = await fetch("/admin/api" + path, {
    method: opts.method || "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) {
    doLogout();
    throw new Error("Session expired — please sign in again");
  }
  if (res.status === 403) {
    doLogout();
    throw new Error("Not an admin");
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
  if (!res.ok) {
    const detail = data && (data.detail || data.message) ? (data.detail || data.message) : res.status;
    throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
  }
  return data;
}

async function loadMe() {
  if (!S.token) return;
  try {
    const me = await api("/me");
    $("#server-info").textContent = `${me.backend.name} · v${me.backend.version}`;
    $("#server-info").title = JSON.stringify(me.backend, null, 2);
    $("#page-sub").textContent = me.db_enabled
      ? "Connected to analytics DB · " + fmt(me.server_time)
      : "Analytics DB not configured — data will be empty";
  } catch (e) { /* non-fatal */ }
}

async function download(kind, days) {
  try {
    const res = await fetch("/admin/api/export/" + kind + qs({ days, token: S.token }), {
      headers: S.token ? { "Authorization": "Bearer " + S.token } : {},
    });
    if (!res.ok) { alert("Export failed: HTTP " + res.status); return; }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `clipo_${kind}_${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
  } catch (e) { alert("Export failed: " + e.message); }
}

/* ─────────────────────────────────────────────────────────────────────────
   Charts (SVG, no deps)
   ───────────────────────────────────────────────────────────────────────── */
const C = { W: 900, H: 260, PL: 44, PR: 14, PT: 14, PB: 30 };

function svgEl(ns) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", ns);
  return s;
}
function drawChart(el, draw) {
  el.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.style.position = "relative";
  const svg = svgEl("svg");
  svg.setAttribute("viewBox", `0 0 ${C.W} ${C.H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const body = svgEl("g");
  svg.appendChild(body);
  wrap.appendChild(svg);
  el.appendChild(wrap);
  return { body, svg, wrap };
}
function gridlines(body, yMax, ticks) {
  for (let i = 0; i <= ticks; i++) {
    const y = C.PT + (C.H - C.PT - C.PB) * (1 - i / ticks);
    const line = svgEl("line");
    line.setAttribute("x1", C.PL); line.setAttribute("x2", C.W - C.PR);
    line.setAttribute("y1", y); line.setAttribute("y2", y);
    line.setAttribute("stroke", "#1e2736"); line.setAttribute("stroke-width", "1");
    body.appendChild(line);
  }
}
function axisLabels(body, labels, kind) {
  const n = labels.length;
  const step = Math.max(1, Math.ceil(n / 12));
  labels.forEach((label, i) => {
    if (i % step !== 0 && i !== n - 1) return;
    const x = C.PL + (C.W - C.PL - C.PR) * (n === 1 ? 0.5 : i / (n - 1));
    const t = svgEl("text");
    t.setAttribute("x", x); t.setAttribute("y", C.H - 8);
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("fill", "#5d6b80"); t.setAttribute("font-size", "10");
    t.textContent = kind === "time" ? label.slice(5) : trunc(label, 14);
    body.appendChild(t);
  });
}
function niceMax(v) {
  if (!v) return 10;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 5, 10]) if (v <= m * mag) return m * mag;
  return 10 * mag;
}
function niceLatencyMax(v) {
  if (!v) return 100;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 5, 10]) if (v <= m * mag) return m * mag;
  return 10 * mag;
}

function lineChart(el, points, lines, opts = {}) {
  const { body } = drawChart(el);
  const n = points.length;
  if (!n) { el.innerHTML = empty("No data in this window"); return; }
  const x = (i) => C.PL + (C.W - C.PL - C.PR) * (n === 1 ? 0.5 : i / (n - 1));
  const vals = lines.flatMap((l) => points.map((p) => Number(p[l.key]) || 0));
  const yMax = niceMax(Math.max(...vals));
  const y = (v) => C.PT + (C.H - C.PT - C.PB) * (1 - v / yMax);

  gridlines(body, yMax, 4);
  for (let i = 0; i <= 4; i++) {
    const t = svgEl("text");
    t.setAttribute("x", C.PL - 6); t.setAttribute("y", C.PT + (C.H - C.PT - C.PB) * (1 - i / 4) + 3);
    t.setAttribute("text-anchor", "end"); t.setAttribute("fill", "#5d6b80"); t.setAttribute("font-size", "10");
    t.textContent = opts.fmt ? opts.fmt(Math.round(yMax * i / 4)) : fmtNum(Math.round(yMax * i / 4));
    body.appendChild(t);
  }
  axisLabels(body, points.map((p) => p.day), "time");

  lines.forEach((l, li) => {
    const path = [];
    points.forEach((p, i) => {
      const px = x(i), py = y(Number(p[l.key]) || 0);
      path.push(`${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`);
    });
    if (opts.area && li === 0) {
      const d = `M${x(0).toFixed(1)},${y(0).toFixed(1)} ${path.slice(1).join(" ").replace(/^L/, "").split(" ").map(s => s[0] === "L" ? s.slice(1) : s).join(" ")} `;
      const areaD = `M${x(0).toFixed(1)},${y(0).toFixed(1)}` + path.slice(1).join(" ") +
        ` L${x(n - 1).toFixed(1)},${C.H - C.PB} L${x(0).toFixed(1)},${C.H - C.PB} Z`;
      const area = svgEl("path");
      area.setAttribute("d", areaD);
      area.setAttribute("fill", l.color || "#3b82f6");
      area.setAttribute("opacity", "0.12");
      body.appendChild(area);
    }
    const line = svgEl("path");
    line.setAttribute("d", path.join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", l.color || "#3b82f6");
    line.setAttribute("stroke-width", "2");
    line.setAttribute("stroke-linejoin", "round");
    body.appendChild(line);

    const dots = svgEl("g");
    points.forEach((p, i) => {
      const c = svgEl("circle");
      c.setAttribute("cx", x(i)); c.setAttribute("cy", y(Number(p[l.key]) || 0));
      c.setAttribute("r", "2.2");
      c.setAttribute("fill", l.color || "#3b82f6");
      dots.appendChild(c);
    });
    body.appendChild(dots);
  });

  const tip = document.createElement("div");
  tip.className = "tip"; tip.style.display = "none";
  el.firstElementChild.appendChild(tip);
  const rect = svgEl("rect");
  rect.setAttribute("x", C.PL); rect.setAttribute("y", C.PT);
  rect.setAttribute("width", C.W - C.PL - C.PR); rect.setAttribute("height", C.H - C.PT - C.PB);
  rect.setAttribute("fill", "transparent");
  body.appendChild(rect);
  rect.addEventListener("mousemove", (ev) => {
    const r = rect.getBoundingClientRect();
    const rel = (ev.clientX - r.left) / r.width * (C.W - C.PL - C.PR);
    const i = Math.min(n - 1, Math.max(0, Math.round(rel)));
    const p = points[i];
    tip.innerHTML = `<b>${esc(p.day)}</b>` + lines.map((l) =>
      `<div>${l.label}: <b>${opts.fmt ? opts.fmt(p[l.key]) : fmtNum(p[l.key])}</b></div>`).join("");
    tip.style.display = "block";
    const br = el.getBoundingClientRect();
    const tipW = tip.offsetWidth || 160;
    const tx = Math.max(4, Math.min(br.width - tipW - 4, (x(i) / C.W) * br.width - tipW / 2));
    tip.style.left = tx + "px";
    tip.style.top = "6px";
  });
  rect.addEventListener("mouseleave", () => { tip.style.display = "none"; });
}

function hBar(el, rows, opts = {}) {
  if (!rows || !rows.length) { el.innerHTML = empty("No data"); return; }
  const max = Math.max(...rows.map((r) => Number(r[opts.valueKey || "n"]) || 0));
  const list = document.createElement("div");
  rows.slice(0, opts.limit || 20).forEach((r) => {
    const row = document.createElement("div");
    row.style.cssText = "margin-bottom:10px";
    const top = document.createElement("div");
    top.style.cssText = "display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:3px";
    top.innerHTML = `<span>${esc(opts.labelFn ? opts.labelFn(r) : r.label)}</span>` +
      `<span class="muted">${esc(opts.valFn ? opts.valFn(r) : fmtNum(r[opts.valueKey || "n"]))}</span>`;
    const barWrap = document.createElement("div");
    barWrap.style.cssText = "background:#161d2b;border-radius:4px;height:8px;overflow:hidden";
    const bar = document.createElement("div");
    bar.style.cssText = `height:100%;width:${max ? (Number(r[opts.valueKey || "n"]) / max) * 100 : 0}%;` +
      `background:${opts.color || "#3b82f6"};border-radius:4px`;
    barWrap.appendChild(bar);
    row.appendChild(top); row.appendChild(barWrap);
    list.appendChild(row);
  });
  el.innerHTML = "";
  el.appendChild(list);
}

function donut(el, rows, opts = {}) {
  if (!rows || !rows.length) { el.innerHTML = empty("No data"); return; }
  const total = rows.reduce((a, r) => a + (Number(r[opts.valueKey || "n"]) || 0), 0);
  const colors = ["#3b82f6", "#22c55e", "#a78bfa", "#f97316", "#eab308", "#ef4444", "#06b6d4", "#8b98ac"];
  const svg = svgEl("svg");
  svg.setAttribute("viewBox", "0 0 200 200");
  svg.setAttribute("width", "200"); svg.setAttribute("height", "200");
  let angle = -90;
  rows.forEach((r, i) => {
    const frac = (Number(r[opts.valueKey || "n"]) || 0) / total;
    const start = angle;
    const end = angle + frac * 360;
    angle = end;
    const large = end - start > 180 ? 1 : 0;
    const x1 = 100 + 78 * Math.cos((start * Math.PI) / 180);
    const y1 = 100 + 78 * Math.sin((start * Math.PI) / 180);
    const x2 = 100 + 78 * Math.cos((end * Math.PI) / 180);
    const y2 = 100 + 78 * Math.sin((end * Math.PI) / 180);
    const seg = svgEl("path");
    seg.setAttribute("d", `M${x1.toFixed(1)} ${y1.toFixed(1)} A78 78 0 ${large} 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`);
    seg.setAttribute("fill", "none");
    seg.setAttribute("stroke", colors[i % colors.length]);
    seg.setAttribute("stroke-width", "22");
    seg.setAttribute("data-label", r.label);
    svg.appendChild(seg);
  });
  const t = svgEl("text");
  t.setAttribute("x", "100"); t.setAttribute("y", "107");
  t.setAttribute("text-anchor", "middle"); t.setAttribute("fill", "#e6edf6");
  t.setAttribute("font-size", "26"); t.setAttribute("font-weight", "700");
  t.textContent = fmtNum(total);
  svg.appendChild(t);
  const sub = svgEl("text");
  sub.setAttribute("x", "100"); sub.setAttribute("y", "125");
  sub.setAttribute("text-anchor", "middle"); sub.setAttribute("fill", "#8b98ac");
  sub.setAttribute("font-size", "10");
  sub.textContent = opts.label || "total";
  svg.appendChild(sub);
  el.innerHTML = "";
  el.appendChild(svg);

  const legend = document.createElement("div");
  legend.className = "legend";
  rows.slice(0, 10).forEach((r, i) => {
    const pct = total ? Math.round((Number(r[opts.valueKey || "n"]) || 0) / total * 100) : 0;
    const d = document.createElement("span");
    d.innerHTML = `<span class="sw" style="background:${colors[i % colors.length]}"></span>${esc(opts.labelFn ? opts.labelFn(r) : r.label)} · ${pct}%`;
    legend.appendChild(d);
  });
  el.appendChild(legend);
}

/* ─────────────────────────────────────────────────────────────────────────
   Pager + table
   ───────────────────────────────────────────────────────────────────────── */
function pagerHtml(p, cb) {
  const out = document.createElement("div");
  out.className = "pager";
  out.innerHTML = `<span>${p.total} results · page ${p.page} of ${Math.max(1, p.pages)}</span>` +
    `<div class="btns">
       <button class="btn sm" data-act="prev" ${p.page <= 1 ? "disabled" : ""}>‹ Prev</button>
       <button class="btn sm" data-act="next" ${p.page >= (p.pages || 1) ? "disabled" : ""}>Next ›</button>
     </div>`;
  $$("[data-act]", out).forEach((b) => b.addEventListener("click", () => {
    const delta = b.dataset.act === "next" ? 1 : -1;
    cb(p.page + delta);
  }));
  return out;
}

function tableHtml(headers, rowsHtml) {
  return `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th${h.num ? ' class="num"' : ""}>${h.label}</th>`).join("")}</tr></thead><tbody>${rowsHtml}</tbody></table></div>`;
}

/* ─────────────────────────────────────────────────────────────────────────
   Modal
   ───────────────────────────────────────────────────────────────────────── */
function openModal(title, bodyHtml) {
  $("#modal-title").innerHTML = title;
  $("#modal-body").innerHTML = bodyHtml;
  $("#modal").classList.remove("hidden");
}
function closeModal() { $("#modal").classList.add("hidden"); }
function kvHtml(obj) {
  const rows = [];
  for (const [k, v] of Object.entries(obj)) {
    let val = v;
    if (typeof v === "object" && v !== null) val = `<pre>${esc(JSON.stringify(v, null, 2))}</pre>`;
    else if (/^(created_at|last_login|last_seen|started_at|updated_at|server_time)$/.test(k)) val = fmt(v);
    else val = esc(v == null ? "" : String(v));
    rows.push(`<dt>${esc(k)}</dt><dd>${val}</dd>`);
  }
  return `<dl class="kv">${rows.join("")}</dl>`;
}

/* ─────────────────────────────────────────────────────────────────────────
   Filter bar builder
   ───────────────────────────────────────────────────────────────────────── */
function daysSelect(id, current) {
  const opts = [[7, "7 days"], [14, "14 days"], [30, "30 days"], [90, "90 days"]];
  return `<select id="${id}">${opts.map(([v, l]) => `<option value="${v}" ${current == v ? "selected" : ""}>${l}</option>`).join("")}</select>`;
}

function bindFilters(root, onApply, defaults = {}) {
  const btn = $("[data-apply]", root);
  if (btn) btn.addEventListener("click", () => {
    const f = {};
    $$("[data-f]", root).forEach((el) => { if (el.value !== "") f[el.dataset.f] = el.value; });
    onApply({ ...defaults, ...f }, 1);
  });
  $$("[data-f]", root).forEach((el) => el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") btn && btn.click();
  }));
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: overview
   ───────────────────────────────────────────────────────────────────────── */
function renderOverview() {
  const el = $("#page");
  el.innerHTML = loading();
  loadMe();
  api("/summary?days=14").then((s) => {
    const cards = [
      { v: fmtNum(s.total_users), l: "Total users", d: { t: s.signups_7d, c: "Signups (7d)", dir: "up" } },
      { v: fmtNum(s.total_logins), l: "Total sign-ins", d: { t: `${s.logins_24h} in 24h · ${s.login_success_rate}% success`, c: "", dir: s.login_success_rate >= 90 ? "up" : "down" } },
      { v: fmtNum(s.total_jobs), l: "Jobs", d: { t: `${s.jobs_completed} completed · ${s.jobs_failed} failed`, c: "", dir: "flat" } },
      { v: fmtNum(s.requests_total), l: "Requests tracked", d: { t: `${s.requests_24h} in 24h · ${s.request_error_rate_24h}% errors`, c: "", dir: "flat" } },
      { v: s.avg_latency_ms ? `${s.avg_latency_ms}ms` : "—", l: "Avg latency (7d)", d: { t: s.p95_latency_ms ? `p95 ${s.p95_latency_ms}ms` : "", c: "", dir: "flat" } },
      { v: fmtNum(s.active_users_7d), l: "Active users (7d)", d: { t: "", c: "", dir: "flat" } },
      { v: fmtNum(s.users_online_now), l: "Online now", d: { t: `${s.users_active_1h} in 1h · ${s.users_active_24h} in 24h`, c: "", dir: s.users_online_now ? "up" : "flat" } },
      { v: fmtNum(s.backends_online), l: "Backends online", d: { t: "", c: "", dir: s.backends_online ? "up" : "down" } },
      { v: fmtNum(s.events_24h), l: "Events (24h)", d: { t: s.errors_24h ? `${s.errors_24h} errors` : "", c: "", dir: "flat" } },
    ];
    el.innerHTML = `
      <div class="grid cols-4">
        ${cards.map((c) => `
          <div class="panel kpi">
            <div class="v">${esc(c.v)}</div>
            <div class="l">${esc(c.l)}</div>
            <div class="d ${c.d.dir}">${esc(c.d.t)}</div>
          </div>`).join("")}
      </div>

      <div style="height:16px"></div>
      <div class="grid cols-2-1">
        <div class="panel"><h3>Sign-ups vs Sign-ins · last 14 days</h3><div class="chart" style="height:250px" id="ch-signups"></div>
          <div class="legend"><span><span class="sw" style="background:#3b82f6"></span>Signups</span><span><span class="sw" style="background:#22c55e"></span>Successful sign-ins</span></div></div>
        <div class="panel"><h3>Requests · last 14 days</h3><div class="chart" style="height:250px" id="ch-requests"></div></div>
      </div>

      <div style="height:16px"></div>
      <div class="grid cols-2">
        <div class="panel"><h3>Top endpoints · 14 days</h3><div id="bar-endpoints"></div></div>
        <div class="panel"><h3>Job status</h3><div id="donut-jobs"></div></div>
      </div>

      <div style="height:16px"></div>
      <div class="grid cols-2">
        <div class="panel"><h3>Top users · 14 days</h3><div id="top-users"></div></div>
        <div class="panel"><h3>Job source mix · 14 days</h3><div id="bar-sources"></div></div>
      </div>`;

    const loginMap = Object.fromEntries(s.logins_series.map((p) => [p.day, p.n]));
    const combined = s.signups_series.map((p) => ({ day: p.day, a: p.n, b: loginMap[p.day] || 0 }));
    lineChart($("#ch-signups"), combined, [
      { key: "a", label: "Signups", color: "#3b82f6" },
      { key: "b", label: "Sign-ins", color: "#22c55e" },
    ]);
    lineChart($("#ch-requests"), s.requests_series, [
      { key: "n", label: "Requests", color: "#a78bfa" },
    ], { area: true });

    hBar($("#bar-endpoints"), s.top_endpoints, {
      labelFn: (r) => `<span class="badge b-blue">${esc(r.method)}</span> ${esc(trunc(r.path, 42))}`,
      valFn: (r) => `${r.n} <span class="faint">${r.errors ? "· " + r.errors + " err" : ""}</span>`,
    });
    donut($("#donut-jobs"), [
      { label: "Completed", n: s.jobs_completed },
      { label: "Failed", n: s.jobs_failed },
      { label: "Other", n: Math.max(0, s.total_jobs - s.jobs_completed - s.jobs_failed) },
    ], { label: "jobs" });
    hBar($("#top-users"), s.top_users, {
      labelFn: (r) => userCell(r, "id"),
      valFn: (r) => `${fmtNum(r.requests)} req <span class="faint">${r.errors ? "· " + r.errors + " err" : ""}</span>`,
    });
    hBar($("#bar-sources"), s.job_source_mix, {
      labelFn: (r) => `<span class="badge b-gray">${esc(r.label || "—")}</span>`,
      valFn: (r) => `${r.n} <span class="faint">${r.completed ? "· " + r.completed + " done" : ""}${r.failed ? " · " + r.failed + " failed" : ""}</span>`,
    });
  }).catch((e) => {
    el.innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`;
  });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: analytics
   ───────────────────────────────────────────────────────────────────────── */
function renderAnalytics() {
  const el = $("#page");
  el.innerHTML = `
    <div class="tabs">
      <button class="tab ${S.tab === "timeseries" ? "active" : ""}" data-tab="timeseries">Timeseries</button>
      <button class="tab ${S.tab === "breakdown" ? "active" : ""}" data-tab="breakdown">Breakdown</button>
      <button class="tab ${S.tab === "latency" ? "active" : ""}" data-tab="latency">Latency</button>
      <button class="tab ${S.tab === "retention" ? "active" : ""}" data-tab="retention">Retention</button>
    </div>
    <div class="filters" id="an-filters"></div>
    <div id="an-body"></div>`;
  $$(".tab", el).forEach((b) => b.addEventListener("click", () => {
    S.tab = b.dataset.tab;
    renderAnalytics();
  }));
  const fEl = $("#an-filters");
  const body = $("#an-body");

  if (S.tab === "timeseries") {
    const metrics = [
      ["signups", "Signups"], ["logins", "Sign-ins"], ["login_failures", "Failed sign-ins"],
      ["requests", "Requests"], ["events", "Events"], ["jobs", "Jobs"],
    ];
    fEl.innerHTML = `<label>Metric</label><select id="ts-metric">${metrics.map(([v, l]) => `<option value="${v}" ${(S.tsMetric || "signups") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Window</label>${daysSelect("ts-days", S.tsDays || 14)}
      <button class="btn sm primary" data-apply>Apply</button>`;
    bindFilters(fEl, (f) => { S.tsMetric = f.metric; S.tsDays = f.days; renderAnalytics(); });
    body.innerHTML = loading();
    api(`/timeseries?metric=${S.tsMetric || "signups"}&days=${S.tsDays || 14}`).then((r) => {
      body.innerHTML = `<div class="panel"><h3>${esc(r.metric)} · last ${r.days} days</h3><div class="chart" style="height:280px" id="ts-chart"></div></div>
        <div style="height:16px"></div>` + tableHtml(
          [{ label: "Day" }, { label: "Count", num: true }],
          r.points.map((p) => `<tr><td>${esc(p.day)}</td><td class="num">${fmtNum(p.n)}</td></tr>`).join(""),
        );
      lineChart($("#ts-chart"), r.points, [{ key: "n", label: r.metric, color: "#3b82f6" }], { area: true });
    }).catch((e) => { body.innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
  }

  if (S.tab === "breakdown") {
    const kinds = ["auth", "requests", "jobs"];
    const dimsAuth = [["frontend", "Frontend origin"], ["backend", "Backend"], ["browser", "Browser"], ["os", "OS"], ["device", "Device"], ["status", "Status"]];
    const dimsReq = [["path", "Path"], ["frontend", "Frontend"], ["backend", "Backend"], ["method", "Method"], ["status", "Status"], ["browser", "Browser"], ["os", "OS"], ["device", "Device"]];
    const dimsJobs = [["source_type", "Source type"], ["status", "Status"], ["user", "User"], ["provider", "AI provider"]];
    const kind = S.brKind || "auth";
    const dims = kind === "auth" ? dimsAuth : (kind === "jobs" ? dimsJobs : dimsReq);
    fEl.innerHTML = `<label>Kind</label><select id="br-kind">${kinds.map((k) => `<option value="${k}" ${kind === k ? "selected" : ""}>${k}</option>`).join("")}</select>
      <label>Dimension</label><select id="br-dim">${dims.map(([v, l]) => `<option value="${v}" ${(S.brDim || "frontend") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Window</label>${daysSelect("br-days", S.brDays || 14)}
      <button class="btn sm primary" data-apply>Apply</button>`;
    $("#br-kind", fEl).addEventListener("change", (e) => { S.brKind = e.target.value; S.brDim = kind === "jobs" ? "source_type" : "frontend"; renderAnalytics(); });
    bindFilters(fEl, (f) => { S.brKind = f.kind; S.brDim = f.dim; S.brDays = f.days; renderAnalytics(); });
    body.innerHTML = loading();
    api(`/breakdown?kind=${kind}&dim=${S.brDim || "frontend"}&days=${S.brDays || 14}`).then((r) => {
      const rows = r.rows;
      const headers = r.kind === "auth"
        ? [{ label: r.dim }, { label: "Total", num: true }, { label: "Success", num: true }, { label: "Failed", num: true }]
        : r.kind === "jobs"
          ? [{ label: r.dim }, { label: "Jobs", num: true }, { label: "Completed", num: true }, { label: "Failed", num: true }]
          : [{ label: r.dim }, { label: "Requests", num: true }, { label: "Errors", num: true }, { label: "Avg ms", num: true }];
      const rowHtml = rows.map((row) => r.kind === "auth"
        ? `<tr><td>${esc(row.label || "—")}</td><td class="num">${fmtNum(row.n)}</td><td class="num up">${fmtNum(row.success)}</td><td class="num down">${fmtNum(row.failed)}</td></tr>`
        : r.kind === "jobs"
          ? `<tr><td>${esc(trunc(row.label || "—", 60))}</td><td class="num">${fmtNum(row.n)}</td><td class="num up">${fmtNum(row.completed)}</td><td class="num down">${fmtNum(row.failed)}</td></tr>`
          : `<tr><td>${esc(trunc(row.label, 60))}</td><td class="num">${fmtNum(row.n)}</td><td class="num ${row.errors ? "down" : ""}">${fmtNum(row.errors)}</td><td class="num">${row.avg_ms != null ? Math.round(row.avg_ms) : "—"}</td></tr>`).join("");
      body.innerHTML = `<div class="grid cols-2">
        <div class="panel"><h3>By ${esc(r.dim)} (${esc(r.kind)}) · ${r.days}d</h3><div id="br-bar"></div></div>
        <div class="panel"><h3>Share</h3><div id="br-donut"></div></div>
      </div>
      <div style="height:16px"></div>` + tableHtml(headers, rowHtml);
      hBar($("#br-bar"), rows, { labelFn: (r) => esc(trunc(r.label || "—", 34)) });
      donut($("#br-donut"), rows.slice(0, 8));
    }).catch((e) => { body.innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
  }

  if (S.tab === "latency") {
    fEl.innerHTML = `<label>Window</label>${daysSelect("lt-days", S.ltDays || 14)}<button class="btn sm primary" data-apply>Apply</button>`;
    bindFilters(fEl, (f) => { S.ltDays = f.days; renderAnalytics(); });
    body.innerHTML = loading();
    api(`/latency?days=${S.ltDays || 14}`).then((r) => {
      body.innerHTML = `<div class="panel"><h3>Request latency · avg vs p95</h3><div class="chart" style="height:280px" id="lt-chart"></div>
        <div class="legend"><span><span class="sw" style="background:#3b82f6"></span>Avg (ms)</span><span><span class="sw" style="background:#f97316"></span>p95 (ms)</span></div></div>`;
      lineChart($("#lt-chart"), r.points, [
        { key: "avg_ms", label: "avg ms", color: "#3b82f6" },
        { key: "p95_ms", label: "p95 ms", color: "#f97316" },
      ], { fmt: (v) => v + "ms" });
    }).catch((e) => { body.innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
  }

  if (S.tab === "retention") {
    fEl.innerHTML = `<label>Weeks</label><select id="rt-weeks">${[4, 8, 12].map((w) => `<option value="${w}" ${(S.rtWeeks || 8) === w ? "selected" : ""}>${w}</option>`).join("")}</select>
      <button class="btn sm primary" data-apply>Apply</button>`;
    bindFilters(fEl, (f) => { S.rtWeeks = f.weeks; renderAnalytics(); });
    body.innerHTML = loading();
    api(`/retention?weeks=${S.rtWeeks || 8}`).then((r) => {
      if (!r.cohorts.length) { body.innerHTML = empty("Not enough data for cohorts yet"); return; }
      body.innerHTML = tableHtml(
        [{ label: "Cohort (week starting)" }, { label: "Size", num: true }, ...Array.from({ length: 4 }, (_, i) => ({ label: `W+${i}`, num: true }))],
        r.cohorts.map((c) => `<tr>
          <td>${esc(c.week)}</td><td class="num">${c.size}</td>
          ${c.retention.map((p) => `<td class="num"><span class="${p >= 50 ? "up" : p > 0 ? "flat" : "down"}">${p}%</span></td>`).join("")}
        </tr>`).join(""),
      );
    }).catch((e) => { body.innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
  }
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: sessions (sign-in tracing)
   ───────────────────────────────────────────────────────────────────────── */
function renderSessions(page = 1) {
  const el = $("#page");
  const f = S.filters.sessions || (S.filters.sessions = {});
  el.innerHTML = `
    <div class="filters">
      <input type="text" data-f="q" placeholder="Search email / IP / user id / frontend…" value="${esc(f.q || "")}">
      <label>Frontend</label><input type="text" data-f="frontend" placeholder="origin or name" value="${esc(f.frontend || "")}">
      <label>Backend</label><input type="text" data-f="backend" placeholder="backend id" value="${esc(f.backend || "")}">
      <label>Status</label><select data-f="status"><option value="">Any</option><option value="success" ${f.status === "success" ? "selected" : ""}>Success</option><option value="failed" ${f.status === "failed" ? "selected" : ""}>Failed</option></select>
      <label>Window</label>${daysSelect("sess-days", f.days || 14)}
      <button class="btn sm primary" data-apply>Apply</button>
      <span class="spacer"></span>
      <button class="btn sm" id="export-sessions">⬇ CSV</button>
    </div>
    <div id="sess-body">${loading()}</div>`;
  bindFilters(el, (nf) => { S.filters.sessions = nf; renderSessions(1); });
  $("#export-sessions", el).addEventListener("click", () => {
    download("sessions", f.days);
  });

  api("/sessions" + qs({ ...f, page, per: 25 })).then((r) => {
    if (!r.items.length) { $("#sess-body").innerHTML = empty("No sign-in events recorded yet"); return; }
    $("#sess-body").innerHTML = tableHtml(
      [{ label: "Time" }, { label: "" }, { label: "User" }, { label: "Frontend" }, { label: "Backend" }, { label: "IP / location" }, { label: "Result" }],
      r.items.map((row) => `<tr class="click" data-id="${esc(row.id)}">
        <td class="mono" style="white-space:nowrap">${fmt(row.created_at)}</td>
        <td>${deviceIcon(row.browser, row.os, row.device)}</td>
        <td>${esc(row.email || "—")}<div class="faint mono">${esc(trunc(row.user_id || "", 18))}</div></td>
        <td>${esc(trunc(row.frontend_origin || row.frontend || "—", 34))}</td>
        <td><span class="badge b-purple">${esc(trunc(row.backend_name || row.backend_id || "?", 16))}</span></td>
        <td class="mono">${esc(row.ip || "—")}<div class="faint">${esc(row.country || "")}</div></td>
        <td>${row.status === "success" ? badge("OK", "green") : badge(row.status || "failed", "red")}</td>
      </tr>`).join(""),
    ) + pagerHtml(r, (p) => renderSessions(p)).outerHTML;
    $$("[data-id]", $("#sess-body")).forEach((tr) => tr.addEventListener("click", () => {
      const row = r.items.find((x) => String(x.id) === String(tr.dataset.id));
      if (!row) return;
      openModal("Sign-in event", kvHtml(row));
    }));
  }).catch((e) => { $("#sess-body").innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: requests
   ───────────────────────────────────────────────────────────────────────── */
function renderRequests(page = 1) {
  const el = $("#page");
  const f = S.filters.requests || (S.filters.requests = {});
  el.innerHTML = `
    <div class="filters">
      <input type="text" data-f="q" placeholder="Search path / IP / user…" value="${esc(f.q || "")}">
      <label>Method</label><select data-f="method"><option value="">Any</option>${["GET", "POST", "PUT", "DELETE", "PATCH"].map((m) => `<option ${f.method === m ? "selected" : ""}>${m}</option>`).join("")}</select>
      <label>Status</label><input type="text" data-f="status" placeholder="e.g. 200" value="${esc(f.status || "")}">
      <label>Min status</label><select data-f="min_status"><option value="">Any</option><option value="400" ${f.min_status == 400 ? "selected" : ""}>400+ (errors)</option><option value="500" ${f.min_status == 500 ? "selected" : ""}>500+</option></select>
      <label>Backend</label><input type="text" data-f="backend" value="${esc(f.backend || "")}">
      <label>Window</label>${daysSelect("req-days", f.days || 7)}
      <button class="btn sm primary" data-apply>Apply</button>
      <span class="spacer"></span>
      <button class="btn sm" id="export-requests">⬇ CSV</button>
    </div>
    <div id="req-body">${loading()}</div>`;
  bindFilters(el, (nf) => { S.filters.requests = nf; renderRequests(1); });
  $("#export-requests", el).addEventListener("click", () => {
    download("requests", f.days);
  });

  api("/requests" + qs({ ...f, page, per: 25 })).then((r) => {
    if (!r.items.length) { $("#req-body").innerHTML = empty("No requests recorded yet"); return; }
    $("#req-body").innerHTML = tableHtml(
      [{ label: "Time" }, { label: "Status", num: true }, { label: "Method" }, { label: "Path" }, { label: "Latency" }, { label: "Frontend" }, { label: "Backend" }, { label: "IP / user" }],
      r.items.map((row) => `<tr class="click" data-id="${esc(row.id)}">
        <td class="mono" style="white-space:nowrap">${fmt(row.created_at)}</td>
        <td class="num">${httpBadge(row.status)}</td>
        <td>${esc(row.method || "—")}</td>
        <td class="mono">${esc(trunc(row.path, 46))}</td>
        <td class="num mono">${row.duration_ms != null ? fmtMs(row.duration_ms) : "—"}</td>
        <td>${esc(trunc(row.frontend_origin || row.frontend || "—", 30))}</td>
        <td><span class="badge b-purple">${esc(trunc(row.backend_name || row.backend_id || "?", 14))}</span></td>
        <td class="mono">${esc(row.ip || "—")}<div class="faint mono">${esc(trunc(row.user_id || "", 16))}</div></td>
      </tr>`).join(""),
    ) + pagerHtml(r, (p) => renderRequests(p)).outerHTML;
    $$("[data-id]", $("#req-body")).forEach((tr) => tr.addEventListener("click", () => {
      const row = r.items.find((x) => String(x.id) === String(tr.dataset.id));
      if (!row) return;
      openModal("Request", kvHtml(row));
    }));
  }).catch((e) => { $("#req-body").innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: users
   ───────────────────────────────────────────────────────────────────────── */
function renderUsers(page = 1) {
  const el = $("#page");
  const f = S.filters.users || (S.filters.users = {});
  el.innerHTML = `
    <div class="filters">
      <input type="text" data-f="q" placeholder="Search email / name / id…" value="${esc(f.q || "")}">
      <label>Created within</label>${daysSelect("usr-days", f.days || "")}
      <button class="btn sm primary" data-apply>Apply</button>
      <span class="spacer"></span>
      <button class="btn sm" id="export-users">⬇ CSV</button>
    </div>
    <div id="usr-body">${loading()}</div>`;
  bindFilters(el, (nf) => { S.filters.users = nf; renderUsers(1); });
  $("#export-users", el).addEventListener("click", () => {
    download("users", f.days);
  });

  api("/users" + qs({ ...f, page, per: 25 })).then((r) => {
    if (!r.items.length) { $("#usr-body").innerHTML = empty("No users yet"); return; }
    $("#usr-body").innerHTML = tableHtml(
      [{ label: "User" }, { label: "Email" }, { label: "Created" }, { label: "Last login" }],
      r.items.map((row) => `<tr class="click" data-id="${esc(row.id)}">
        <td><b>${esc(row.name || row.display_name || "—")}</b><div class="faint mono">${esc(trunc(row.id, 22))}</div></td>
        <td>${esc(row.email || "—")}</td>
        <td class="mono" style="white-space:nowrap">${fmt(row.created_at)}</td>
        <td class="mono" style="white-space:nowrap">${fmt(row.last_login)}</td>
      </tr>`).join(""),
    ) + pagerHtml(r, (p) => renderUsers(p)).outerHTML;
    $$("[data-id]", $("#usr-body")).forEach((tr) => tr.addEventListener("click", () => {
      const row = r.items.find((x) => String(x.id) === String(tr.dataset.id));
      if (!row) return;
      openModal("User · " + esc(row.email || row.id),
        kvHtml(row) +
        `<div style="height:14px"></div><div class="panel"><h3>Recent activity</h3><div id="usr-act">${loading()}</div></div>`);
      Promise.all([
        api("/sessions" + qs({ q: row.id, days: 30, per: 8 })),
        api("/events" + qs({ user_id: row.id, days: 30, per: 8 })),
        api("/jobs" + qs({ user_id: row.id, days: 30, per: 8 })),
      ]).then(([sess, evs, jobs]) => {
        let html = "";
        if (sess.items.length) html += `<b class="muted">Sign-ins</b>` + sess.items.map((s) => `<div class="faint mono">${fmt(s.created_at)} · ${esc(s.status)} · ${esc(s.ip || "")} · ${esc(s.frontend_origin || "")}</div>`).join("") + `<div style="height:8px"></div>`;
        if (evs.items.length) html += `<b class="muted">Events</b>` + evs.items.map((s) => `<div class="faint mono">${fmt(s.created_at)} · ${esc(s.event_name)}</div>`).join("") + `<div style="height:8px"></div>`;
        if (jobs.items.length) html += `<b class="muted">Jobs</b>` + jobs.items.map((s) => `<div class="faint mono">${fmt(s.created_at)} · ${esc(s.status)} · ${esc(trunc(s.video_title || s.job_id, 40))}</div>`).join("");
        $("#usr-act").innerHTML = html || empty("No activity");
      }).catch(() => { $("#usr-act").innerHTML = empty("Failed to load"); });
    }));
  }).catch((e) => { $("#usr-body").innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: jobs
   ───────────────────────────────────────────────────────────────────────── */
function renderJobs(page = 1) {
  const el = $("#page");
  const f = S.filters.jobs || (S.filters.jobs = {});
  el.innerHTML = `
    <div class="filters">
      <input type="text" data-f="q" placeholder="Search job id / user / title…" value="${esc(f.q || "")}">
      <label>Status</label><select data-f="status"><option value="">Any</option>${["queued", "running", "completed", "failed", "cancelled"].map((s) => `<option ${f.status === s ? "selected" : ""}>${s}</option>`).join("")}</select>
      <label>Source</label><input type="text" data-f="source_type" placeholder="youtube / url / file…" value="${esc(f.source_type || "")}" style="min-width:110px">
      <label>AI provider</label><input type="text" data-f="provider" placeholder="gemini / openai…" value="${esc(f.provider || "")}" style="min-width:110px">
      <label>Created within</label>${daysSelect("job-days", f.days || "")}
      <button class="btn sm primary" data-apply>Apply</button>
      <span class="spacer"></span>
      <button class="btn sm" id="export-jobs">⬇ CSV</button>
    </div>
    <div id="job-body">${loading()}</div>`;
  bindFilters(el, (nf) => { S.filters.jobs = nf; renderJobs(1); });
  $("#export-jobs", el).addEventListener("click", () => {
    download("jobs", f.days);
  });

  api("/jobs" + qs({ ...f, page, per: 25 })).then((r) => {
    if (!r.items.length) { $("#job-body").innerHTML = empty("No jobs yet"); return; }
    $("#job-body").innerHTML = tableHtml(
      [{ label: "Created" }, { label: "Job" }, { label: "Created by" }, { label: "Title" }, { label: "Source" }, { label: "AI provider" }, { label: "Status" }, { label: "Error" }],
      r.items.map((row) => `<tr class="click" data-id="${esc(row.job_id)}">
        <td class="mono" style="white-space:nowrap">${fmt(row.created_at)}</td>
        <td class="mono">${esc(trunc(row.job_id, 20))}</td>
        <td>${userCell(row, "user_id") || "—"}</td>
        <td>${esc(trunc(row.video_title || "—", 36))}</td>
        <td>${row.source_type ? `<span class="badge b-gray">${esc(row.source_type)}</span>` : "—"}</td>
        <td>${row.ai_usage && row.ai_usage.provider ? `<span class="badge b-purple">${esc(row.ai_usage.provider)}</span>` : "—"}</td>
        <td>${statusBadge(row.status)}</td>
        <td class="faint">${esc(trunc(row.error || "", 34))}</td>
      </tr>`).join(""),
    ) + pagerHtml(r, (p) => renderJobs(p)).outerHTML;
    $$("[data-id]", $("#job-body")).forEach((tr) => tr.addEventListener("click", () => {
      const row = r.items.find((x) => String(x.job_id) === String(tr.dataset.id));
      if (!row) return;
      openModal("Job", kvHtml(row));
    }));
  }).catch((e) => { $("#job-body").innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: online (live user activity)
   ───────────────────────────────────────────────────────────────────────── */
function renderOnline() {
  const el = $("#page");
  const f = S.filters.online || (S.filters.online = { minutes: 15 });
  el.innerHTML = `
    <div class="filters">
      <label>Window</label><select data-f="minutes">${[5, 15, 30, 60].map((m) => `<option value="${m}" ${(f.minutes || 15) == m ? "selected" : ""}>last ${m} min</option>`).join("")}</select>
      <button class="btn sm primary" data-apply>Refresh</button>
      <label><input type="checkbox" id="online-tail" ${S.onlineTail ? "checked" : ""}> auto-refresh</label>
    </div>
    <div id="online-body">${loading()}</div>`;
  bindFilters(el, (nf) => { S.filters.online = nf; renderOnline(); }, { minutes: f.minutes || 15 });
  $("#online-tail", el).addEventListener("change", (e) => {
    S.onlineTail = e.target.checked;
    clearInterval(S.timer);
    if (S.onlineTail && S.page === "online") S.timer = setInterval(() => renderOnline(), 15000);
  });

  api("/online" + qs({ minutes: f.minutes || 15 })).then((r) => {
    const cards = [
      { v: fmtNum(r.now), l: `Active in last 5 min` },
      { v: fmtNum(r.last_1h), l: "Active in last hour" },
      { v: fmtNum(r.last_24h), l: "Active in last 24h" },
      { v: fmtNum(r.users.length), l: `Users in window (${r.minutes}m)` },
    ];
    const bodyHtml = r.users.length
      ? tableHtml(
          [{ label: "User" }, { label: "Requests" }, { label: "Errors" }, { label: "Last activity" }, { label: "Last action" }, { label: "Client" }, { label: "Last event" }],
          r.users.map((u) => `<tr class="click" data-id="${esc(u.id)}">
            <td>${userCell(u, "id")}</td>
            <td class="num">${fmtNum(u.requests)}</td>
            <td class="num ${u.errors ? "down" : ""}">${fmtNum(u.errors)}</td>
            <td class="mono" style="white-space:nowrap">${fmt(u.last_seen)}</td>
            <td class="mono">${esc(u.last_method || "")} <span class="faint">${esc(trunc(u.last_path || "", 36))}</span></td>
            <td>${deviceIcon(null, null, u.last_device)} <span class="faint">${esc(trunc(u.last_frontend || u.last_device || "", 24))}</span>${u.last_ip ? `<div class="faint mono">${esc(u.last_ip)}</div>` : ""}</td>
            <td>${u.last_event ? `<span class="badge b-blue">${esc(u.last_event)}</span>` : "—"}</td>
          </tr>`).join(""),
        )
      : empty(`No users active in the last ${r.minutes} minutes`);
    $("#online-body").innerHTML = `
      <div class="grid cols-4">
        ${cards.map((c) => `<div class="panel kpi"><div class="v">${esc(c.v)}</div><div class="l">${esc(c.l)}</div></div>`).join("")}
      </div>
      <div style="height:16px"></div>
      <div id="online-list">${bodyHtml}</div>`;
    $$("[data-id]", $("#online-list")).forEach((tr) => tr.addEventListener("click", () => {
      const u = r.users.find((x) => String(x.id) === String(tr.dataset.id));
      if (!u) return;
      openModal("User · " + esc(userName(u) || u.id), kvHtml(u));
    }));
  }).catch((e) => { $("#online-body").innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: events
   ───────────────────────────────────────────────────────────────────────── */
function renderEvents(page = 1) {
  const el = $("#page");
  const f = S.filters.events || (S.filters.events = {});
  el.innerHTML = `
    <div class="filters">
      <input type="text" data-f="q" placeholder="Search event / user…" value="${esc(f.q || "")}">
      <input type="text" data-f="event_name" placeholder="event name" value="${esc(f.event_name || "")}">
      <input type="text" data-f="user_id" placeholder="user id" value="${esc(f.user_id || "")}">
      <label>Window</label>${daysSelect("ev-days", f.days || 14)}
      <button class="btn sm primary" data-apply>Apply</button>
      <span class="spacer"></span>
      <button class="btn sm" id="export-events">⬇ CSV</button>
    </div>
    <div id="ev-body">${loading()}</div>`;
  bindFilters(el, (nf) => { S.filters.events = nf; renderEvents(1); });
  $("#export-events", el).addEventListener("click", () => {
    download("events", f.days);
  });

  api("/events" + qs({ ...f, page, per: 50 })).then((r) => {
    if (!r.items.length) { $("#ev-body").innerHTML = empty("No events yet"); return; }
    $("#ev-body").innerHTML = tableHtml(
      [{ label: "Time" }, { label: "Event" }, { label: "User" }, { label: "Properties" }],
      r.items.map((row) => `<tr class="click" data-id="${esc(row.id)}">
        <td class="mono" style="white-space:nowrap">${fmt(row.created_at)}</td>
        <td><span class="badge b-blue">${esc(row.event_name)}</span></td>
        <td class="mono">${esc(trunc(row.user_id || "", 18))}</td>
        <td class="faint">${esc(trunc(JSON.stringify(row.properties || {}), 60))}</td>
      </tr>`).join(""),
    ) + pagerHtml(r, (p) => renderEvents(p)).outerHTML;
    $$("[data-id]", $("#ev-body")).forEach((tr) => tr.addEventListener("click", () => {
      const row = r.items.find((x) => String(x.id) === String(tr.dataset.id));
      if (!row) return;
      openModal("Event · " + esc(row.event_name), kvHtml(row));
    }));
  }).catch((e) => { $("#ev-body").innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: backends
   ───────────────────────────────────────────────────────────────────────── */
function renderBackends() {
  const el = $("#page");
  el.innerHTML = loading();
  api("/backends").then((r) => {
    const b = r.backends || [];
    if (!b.length) { el.innerHTML = empty("No backends seen yet"); return; }
    el.innerHTML = `<div class="grid cols-3">
      ${b.map((x) => `
        <div class="bcard">
          <div class="top"><span class="id">${esc(x.backend_id)}</span>
            ${x.status === "online" ? badge("online", "green") : badge(x.status || "offline", "gray")}</div>
          <div class="meta">
            ${x.name ? esc(x.name) + " · " : ""}v${esc(x.version || "?")}${x.region ? " · " + esc(x.region) : ""}
            <div class="faint mono">${esc(x.instance_id || "")}</div>
          </div>
          <div class="nums">
            <span><b>${fmtNum(x.req_1h)}</b> req/1h</span>
            <span><b class="${x.err_1h ? "down" : ""}">${fmtNum(x.err_1h)}</b> err/1h</span>
            <span><b>${fmtNum(x.req_total)}</b> total</span>
            <span class="faint">seen ${fmt(x.last_seen)}</span>
          </div>
        </div>`).join("")}
    </div>`;
  }).catch((e) => { el.innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: logs
   ───────────────────────────────────────────────────────────────────────── */
function renderLogs(page = 1) {
  const el = $("#page");
  const f = S.filters.logs || (S.filters.logs = {});
  el.innerHTML = `
    <div class="filters">
      <input type="text" data-f="q" placeholder="Search message…" value="${esc(f.q || "")}">
      <label>Level</label><select data-f="level"><option value="">Any</option>${["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map((l) => `<option ${f.level === l ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Backend</label><input type="text" data-f="backend" value="${esc(f.backend || "")}">
      <label>Window</label>${daysSelect("log-days", f.days || 7)}
      <button class="btn sm primary" data-apply>Apply</button>
      <label><input type="checkbox" id="log-tail" ${S.logTail ? "checked" : ""}> auto-refresh</label>
      <span class="spacer"></span>
      <button class="btn sm" id="export-logs">⬇ CSV</button>
    </div>
    <div id="log-body">${loading()}</div>`;
  bindFilters(el, (nf) => { S.filters.logs = nf; renderLogs(1); });
  $("#log-tail", el).addEventListener("change", (e) => { S.logTail = e.target.checked; scheduleTail(); });
  $("#export-logs", el).addEventListener("click", () => {
    download("logs", f.days);
  });

  api("/logs" + qs({ ...f, page, per: 50 })).then((r) => {
    if (!r.items.length) { $("#log-body").innerHTML = empty("No log entries"); return; }
    $("#log-body").innerHTML = tableHtml(
      [{ label: "Time" }, { label: "Level" }, { label: "Source" }, { label: "Backend" }, { label: "Message" }],
      r.items.map((row) => `<tr class="click" data-id="${esc(row.id)}">
        <td class="mono" style="white-space:nowrap">${fmt(row.created_at)}</td>
        <td><span class="lvl lvl-${esc(row.level)}">${esc(row.level)}</span></td>
        <td class="mono faint">${esc(row.logger || "")}${row.filename ? ` <span class="faint">${esc(row.filename)}:${esc(row.lineno ?? "")}</span>` : ""}</td>
        <td><span class="badge b-purple">${esc(trunc(row.backend_name || row.backend_id || "?", 12))}</span></td>
        <td class="mono">${esc(trunc(row.message, 110))}</td>
      </tr>`).join(""),
    ) + pagerHtml(r, (p) => renderLogs(p)).outerHTML;
    $$("[data-id]", $("#log-body")).forEach((tr) => tr.addEventListener("click", () => {
      const row = r.items.find((x) => String(x.id) === String(tr.dataset.id));
      if (!row) return;
      openModal("Log entry", kvHtml(row));
    }));
  }).catch((e) => { $("#log-body").innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

function scheduleTail() {
  clearInterval(S.timer);
  if (S.logTail && S.page === "logs") S.timer = setInterval(() => renderLogs(1), 15000);
}

/* ─────────────────────────────────────────────────────────────────────────
   PAGE: admins
   ───────────────────────────────────────────────────────────────────────── */
function renderAdmins() {
  const el = $("#page");
  el.innerHTML = loading();
  Promise.all([api("/admins"), api("/audit" + qs({ days: 14, per: 25 }))]).then(([adms, aud]) => {
    const list = adms.admins || [];
    el.innerHTML = `
      <div class="grid cols-2">
        <div class="panel">
          <h3>Admins</h3>
          <div id="adm-list"></div>
          <div style="height:16px"></div>
          <h3>Add admin</h3>
          <div class="filters">
            <input type="text" id="new-user" placeholder="username" style="min-width:110px">
            <input type="password" id="new-pass" placeholder="password (min 8)" style="min-width:120px">
            <button class="btn sm primary" id="add-admin">Add</button>
          </div>
        </div>
        <div class="panel">
          <h3>Admin audit trail · last 14 days</h3>
          <div class="filters">
            <input type="text" id="aud-q" placeholder="Search action / admin / detail…">
            <button class="btn sm primary" id="aud-go">Go</button>
          </div>
          <div id="aud-body">${loading()}</div>
        </div>
      </div>`;

    $("#adm-list").innerHTML = tableHtml(
      [{ label: "Username" }, { label: "Last login" }, { label: "" }],
      list.map((a) => `<tr>
        <td><b>${esc(a.username)}</b>${a.username === S.username ? badge("you", "blue") : ""}</td>
        <td class="mono">${fmt(a.last_login)}</td>
        <td>${a.username !== S.username ? `<button class="btn sm danger" data-del="${esc(a.username)}">Delete</button>` : ""}</td>
      </tr>`).join(""),
    );
    $$("[data-del]", $("#adm-list")).forEach((b) => b.addEventListener("click", () => {
      const u = b.dataset.del;
      if (!confirm(`Delete admin "${u}"?`)) return;
      api(`/admins/${encodeURIComponent(u)}`, { method: "DELETE" }).then(() => renderAdmins()).catch((e) => alert(e.message));
    }));
    $("#add-admin").addEventListener("click", () => {
      const username = $("#new-user").value.trim();
      const password = $("#new-pass").value;
      if (!username || password.length < 8) { alert("Username required, password min 8 chars"); return; }
      api("/admins", { method: "POST", body: { username, password } }).then(() => renderAdmins()).catch((e) => alert(e.message));
    });
    $("#aud-go").addEventListener("click", () => {
      const q = $("#aud-q").value.trim();
      api("/audit" + qs({ q, days: 14, per: 25 })).then((r) => { $("#aud-body").innerHTML = auditTable(r); bindAuditRows(r); })
        .catch((e) => { $("#aud-body").innerHTML = `<div class="error">${esc(e.message)}</div>`; });
    });
    $("#aud-body").innerHTML = auditTable(aud);
    bindAuditRows(aud);
  }).catch((e) => { el.innerHTML = `<div class="panel"><div class="error">${esc(e.message)}</div></div>`; });
}

function auditTable(r) {
  if (!r.items.length) return empty("No audit entries");
  return tableHtml(
    [{ label: "Time" }, { label: "Admin" }, { label: "Action" }, { label: "Detail" }, { label: "IP" }],
    r.items.map((row) => `<tr>
      <td class="mono" style="white-space:nowrap">${fmt(row.created_at)}</td>
      <td><b>${esc(row.admin_username)}</b></td>
      <td><span class="badge b-gray">${esc(row.action)}</span></td>
      <td class="faint">${esc(trunc(row.detail || "", 60))}</td>
      <td class="mono">${esc(row.ip || "—")}</td>
    </tr>`).join(""),
  );
}
function bindAuditRows(r) {
  const wrap = $("#aud-body");
  if (!wrap) return;
  const p = wrap.querySelector(".pager");
  if (p) p.outerHTML = pagerHtml(r, (page) => {
    api("/audit" + qs({ days: 14, per: 25, page })).then((r2) => {
      $("#aud-body").innerHTML = auditTable(r2);
      bindAuditRows(r2);
    });
  }).outerHTML;
}

/* ─────────────────────────────────────────────────────────────────────────
   Router / shell
   ───────────────────────────────────────────────────────────────────────── */
function render() {
  if (!S.token) { showLogin(); return; }
  clearInterval(S.timer);
  $("#app-view").classList.remove("hidden");
  $("#login-view").classList.add("hidden");
  $("#page-title").textContent = PAGES[S.page].title;
  $("#whoami").innerHTML = `Signed in as <b>${esc(S.username)}</b>`;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.page === S.page));

  const R = {
    overview: renderOverview, analytics: renderAnalytics, sessions: renderSessions,
    requests: renderRequests,     users: renderUsers, jobs: renderJobs, events: renderEvents,
    backends: renderBackends, logs: renderLogs, admins: renderAdmins, online: renderOnline,
  };
  R[S.page](1);
  scheduleTail();
}

function navigate(page) {
  S.page = page;
  render();
}

function showLogin() {
  $("#app-view").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
}

function doLogout() {
  S.token = ""; S.username = "";
  localStorage.removeItem("clipo_admin_token");
  localStorage.removeItem("clipo_admin_user");
  showLogin();
}

/* ─────────────────────────────────────────────────────────────────────────
   Init
   ───────────────────────────────────────────────────────────────────────── */
function init() {
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = $("#user").value.trim();
    const password = $("#pass").value;
    $("#login-err").textContent = "";
    try {
      const res = await fetch("/admin/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { $("#login-err").textContent = data.detail || "Login failed"; return; }
      S.token = data.token; S.username = data.username;
      localStorage.setItem("clipo_admin_token", data.token);
      localStorage.setItem("clipo_admin_user", data.username);
      render();
    } catch (err) { $("#login-err").textContent = "Network error — is the backend up?"; }
  });

  $("#nav").addEventListener("click", (e) => {
    const b = e.target.closest(".nav-item");
    if (b) navigate(b.dataset.page);
  });
  $("#logout-btn").addEventListener("click", doLogout);
  $("#refresh-btn").addEventListener("click", () => render());
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-backdrop").addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

  render();
}

init();
