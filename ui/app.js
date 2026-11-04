"use strict";
/* Killcam UI. Talks to the local Python API (token-protected) and to window.pywebview.api for
   native things: file dialogs, saving clips, drag & drop. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

// The per-launch token arrives in the URL hash; keep it in memory only.
// sessionStorage keeps it across F5 inside this window; it dies with the window.
const TOKEN = (location.hash.match(/token=([\w-]+)/) || [])[1] || sessionStorage.getItem("kc") || "";
try { sessionStorage.setItem("kc", TOKEN); } catch { }
if (/token=/.test(location.hash)) history.replaceState(null, "", location.pathname + "#/library");

let LANG = "ru";
const t = (key, p = {}) => {
  const s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.en[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => p[k] ?? "");
};

async function api(path, body) {
  const r = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: {"X-Killcam-Token": TOKEN, ...(body ? {"Content-Type": "application/json"} : {})},
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.error || r.statusText), {code: j.error});
  return j;
}
const media = (key, file) => `/library/${encodeURIComponent(key)}/${encodeURIComponent(file)}?t=${TOKEN}`;
const native = () => window.pywebview && window.pywebview.api;
const errText = e => {
  const code = (e && (e.code || e)) || "unknown";
  return I18N[LANG]["err_" + code] ? t("err_" + code) : t("err_unknown", {detail: e && (e.detail || e.message || code)});
};

/* ---------- visuals ---------- */
const ICON = {
  logo: `<svg viewBox="0 0 64 64" fill="none"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff4d2e"/><stop offset=".6" stop-color="#ff7a2f"/><stop offset="1" stop-color="#ffb347"/></linearGradient></defs><rect x="2" y="2" width="60" height="60" rx="16" fill="#15161d"/><rect x="2.5" y="2.5" width="59" height="59" rx="15.5" stroke="url(#lg)" stroke-opacity=".5"/><circle cx="32" cy="32" r="15" stroke="url(#lg)" stroke-width="4"/><path d="M32 9v11M32 44v11M9 32h11M44 32h11" stroke="url(#lg)" stroke-width="4" stroke-linecap="round"/><circle cx="32" cy="32" r="4" fill="url(#lg)"/></svg>`,
  library: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>`,
  rec: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5" fill="currentColor"/></svg>`,
  gear: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>`,
  upload: `<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5M12 3v12"/></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>`,
  save: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/></svg>`,
  prev: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h2v14H6zM20 5v14L9 12z"/></svg>`,
  next: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 5h2v14h-2zM4 5l11 7-11 7z"/></svg>`,
  back: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>`,
  eye: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>`,
  skull: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3a8 8 0 0 0-8 8c0 2.6 1.3 4.4 3 5.5V20h10v-3.5c1.7-1.1 3-2.9 3-5.5a8 8 0 0 0-8-8z"/><circle cx="9" cy="11" r="1.6" fill="currentColor"/><circle cx="15" cy="11" r="1.6" fill="currentColor"/></svg>`,
  rounds: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 18V9M10 18V5M16 18v-7M22 18H2"/></svg>`,
  warn: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>`,
  bug: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2l1.9 1.9M16 2l-1.9 1.9M9 7.1V6a3 3 0 0 1 6 0v1.1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6zM12 20v-9M6 13H2M22 13h-4M6.5 8.5L4 7M17.5 8.5L20 7M6.5 17.5L4 19M17.5 17.5L20 19"/></svg>`,
  send: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>`,
  up: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg>`,
  github: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 0-.8.4-1.3.7-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2 0-.4-.5-1.6.2-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.7 1.6.2 2.8.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .5z"/></svg>`,
};
const MAP_COLORS = {
  dust2: ["#d39b5e", "#5a3519"], mirage: ["#e0a86b", "#6d2f1f"], inferno: ["#e8743a", "#4d150c"],
  nuke: ["#5aa3e0", "#14284a"], ancient: ["#59a86a", "#163020"], anubis: ["#dcb45a", "#2f4870"],
  vertigo: ["#93b8de", "#23314b"], overpass: ["#7cb06b", "#26382b"], train: ["#9ea7b2", "#2a3038"],
  office: ["#a7b4c4", "#2d3746"], italy: ["#d98e5f", "#5a2d1c"],
};
const mapKey = m => (m || "").replace(/^(de|cs|ar)_/, "").toLowerCase();
const mapName = m => { const k = mapKey(m); return k ? k[0].toUpperCase() + k.slice(1) : "?"; };
const mapGrad = m => { const [a, b] = MAP_COLORS[mapKey(m)] || ["#ff6a3d", "#3a1410"]; return `linear-gradient(135deg, ${a} 0%, ${b} 100%)`; };
// A frame from the user's own footage of this map (library/_maps), falling back to the colour gradient.
const mapBg = (m, thumb) => `url('${thumb || media("_maps", (m || "x") + ".jpg")}') center/cover no-repeat, ${mapGrad(m)}`;
const fmtMatch = ts => ts ? new Date(ts * 1000).toLocaleString(LANG === "ru" ? "ru-RU" : "en-GB",
  {day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit"}) : "";
const scoreHtml = s => !s || (!s[0] && !s[1]) ? "" :
  `<span class="score ${s[0] > s[1] ? "win" : s[0] < s[1] ? "loss" : "draw"} num">${s[0]}<i>:</i>${s[1]}</span>`;
const niceDate = s => {
  const m = (s || "").match(/^(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d)/);
  if (!m) return s || "";
  return new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}`).toLocaleString(LANG === "ru" ? "ru-RU" : "en-GB",
    {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"});
};
const W = w => (w || "").replace(/^weapon_/, "").replace("usp_silencer", "USP-S").replace("m4a1_silencer", "M4A1-S")
  .replace("hegrenade", "HE").replace("inferno", "molotov").replace("knife_t", "knife").toUpperCase();
const fmtTime = s => s < 60 ? `${Math.max(1, Math.round(s))} ${LANG === "ru" ? "с" : "s"}` : `${Math.round(s / 60)} ${LANG === "ru" ? "мин" : "min"}`;

/* ---------- toasts & modal ---------- */
function toast(text, kind = "", action) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<span>${esc(text)}</span>` + (action ? `<a>${esc(action.label)}</a>` : "");
  if (action) el.querySelector("a").onclick = action.fn;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 5000);
}
function confirmModal(title, text, okLabel) {
  return new Promise(res => {
    const m = $("#modal");
    m.innerHTML = `<div class="dialog"><h3>${esc(title)}</h3><p>${esc(text)}</p>
      <div class="row"><button class="btn ghost" data-v="0">${esc(t("cancel"))}</button>
      <button class="btn danger-solid" data-v="1">${esc(okLabel)}</button></div></div>`;
    m.hidden = false;
    const done = v => { m.hidden = true; m.innerHTML = ""; res(v); };
    m.onclick = e => { if (e.target === m) done(false); };
    $$("button", m).forEach(b => b.onclick = () => done(b.dataset.v === "1"));
  });
}

/* ---------- state ---------- */
const S = {job: null, settings: null, picked: null, demoInfo: null, players: [], recStarted: 0, update: null};
const isDemo = () => S.settings && S.settings.channel === "demo";
const maxPlayers = () => (S.settings && S.settings.max_players) || 1;
let jobTimer = null, viewTimer = null;

async function boot() {
  try { S.settings = await api("/api/settings"); LANG = S.settings.lang; } catch { }
  document.documentElement.lang = LANG;
  const st = await api("/api/setup").catch(() => null);
  if (!st || !st.ready) return welcome(st);
  renderShell();
  window.addEventListener("hashchange", route);
  route();
  pollJob();
  setTimeout(() => checkUpdates(false), 1500);
  setTimeout(soundCheck, 600);
}

/* ---------- CS2 sound left muted by 2.0.0–2.0.1 ---------- */
async function soundCheck() {
  const s = await api("/api/sound").catch(() => null);
  if (!s || !s.pending || !$("#modal").hidden) return;
  const m = $("#modal");
  m.innerHTML = `<div class="dialog wide"><h3>${esc(t("snd_title"))}</h3>
    <p>${esc(t("snd_text"))}</p><p class="fine">${esc(t("snd_hint"))}</p>
    <div class="row"><button class="btn ghost" id="sndLater">${esc(t("snd_later"))}</button>
    <button class="btn ghost" id="sndDone">${esc(t("snd_done_self"))}</button>
    <button class="btn primary" id="sndFix">${esc(t("snd_fix"))}</button></div></div>`;
  m.hidden = false;
  const close = () => { m.hidden = true; m.innerHTML = ""; };
  $("#sndLater").onclick = close;
  $("#sndDone").onclick = async () => { await api("/api/sound/dismiss", {}).catch(() => { }); close(); };
  $("#sndFix").onclick = async () => {
    $$("button", m).forEach(b => b.disabled = true);
    $("#sndFix").textContent = t("snd_fixing");
    try { await api("/api/sound/fix", {}); } catch (e) { close(); return toast(errText(e), "err"); }
    const tick = async () => {
      const r = await api("/api/sound").catch(() => ({state: "fixing"}));
      if (r.state === "fixing") return setTimeout(tick, 1000);
      close();
      r.state === "done" ? toast(t("snd_ok"), "ok") : toast(t("snd_err"), "err");
    };
    tick();
  };
}

/* ---------- first run ---------- */
function welcome(st) {
  st = st || {};
  const installing = st.running || (st.accepted && !st.error && st.cs2_found);
  if (st.accepted && !st.running && !st.error && st.cs2_found) api("/api/setup/accept", {}).catch(() => { });
  $("#root").innerHTML = `
    <div class="welcome"><div class="welcome-inner">
      <div class="seg lang-switch">${["ru", "en"].map(l => `<button data-l="${l}" class="${l === LANG ? "on" : ""}">${l.toUpperCase()}</button>`).join("")}</div>
      <div class="logo-big">${ICON.logo}</div>
      <h1>${t("w_title")}</h1>
      <p class="lead">${esc(t("w_lead"))}</p>
      ${installing ? `
        <div class="panel terms">
          <h3 style="margin:0 0 6px;font:700 18px var(--display)">${esc(t("w_installing"))}</h3>
          <p class="muted" style="margin:0 0 16px">${esc(st.step || "…")} · ${esc(t("w_once"))}</p>
          <div class="bar"><i style="width:${Math.round((st.progress || 0) * 100)}%"></i></div>
        </div>` : `
        <div class="features">
          ${[["eye", "w_f1"], ["skull", "w_f2"], ["rounds", "w_f3"]].map(([i, k]) => `
            <div class="panel feature"><div class="fi">${ICON[i]}</div><b>${esc(t(k))}</b><span>${esc(t(k + "d"))}</span></div>`).join("")}
        </div>
        <div class="panel terms">
          <b>${esc(t("w_terms"))}</b>
          <ul>${["w_t1", "w_t2", "w_t3", "w_t4", "w_t5", "w_t6"].map(k => `<li>${t(k, {dir: esc(st.data_dir || "")})}</li>`).join("")}</ul>
        </div>
        ${st.error ? `<div class="error-box" style="margin-top:14px">${esc(st.error)}</div>` : ""}
        ${st.cs2_found === false ? `<div class="error-box" style="margin-top:14px">${esc(t("w_no_cs2"))}</div>` : ""}
        <div class="agree" id="agree"><span class="check">${ICON.check}</span>${esc(t("w_agree"))}</div>
        <button class="btn primary lg" id="accept" disabled>${esc(st.error ? t("w_retry") : t("w_install"))}</button>`}
    </div></div>`;
  $$(".lang-switch button").forEach(b => b.onclick = async () => {
    LANG = b.dataset.l;
    await api("/api/settings", {lang: LANG}).catch(() => { });
    welcome(await api("/api/setup").catch(() => st));
  });
  if (installing) { setTimeout(async () => { const s = await api("/api/setup").catch(() => st); s.ready ? boot() : welcome(s); }, 700); return; }
  let agreed = false;
  $("#agree").onclick = () => {
    agreed = !agreed;
    $("#agree").classList.toggle("on", agreed);
    $("#accept").disabled = !agreed || st.cs2_found === false;
  };
  $("#accept").onclick = async () => welcome(await api("/api/setup/accept", {}));
}

/* ---------- shell ---------- */
function renderShell() {
  $("#root").innerHTML = `
    <div class="shell">
      <aside class="side">
        <div class="brand">${ICON.logo}<div><b>Killcam${isDemo() ? `<span class="demo-tag">DEMO</span>` : ""}</b><small>${esc(t("tagline"))}</small></div></div>
        <nav class="nav">
          <a data-r="library">${ICON.library}<span>${esc(t("nav_library"))}</span></a>
          <a data-r="new">${ICON.plus}<span>${esc(t("nav_new"))}</span></a>
          <a data-r="settings">${ICON.gear}<span>${esc(t("nav_settings"))}</span></a>
        </nav>
        <div class="side-foot">
          <div id="recChip"></div>
          <div id="updChip"></div>
          <a class="side-link" id="bugBtn">${ICON.bug}<span>${esc(t("bug_btn"))}</span></a>
          <div class="version">Killcam ${esc(S.settings ? S.settings.version : "")}</div>
        </div>
      </aside>
      <main class="main" id="main"></main>
    </div>`;
  $$(".nav a").forEach(a => a.onclick = () => go(a.dataset.r));
  $("#bugBtn").onclick = bugReport;
  renderUpdChip();
}

/* ---------- bug report ---------- */
function bugReport() {
  const m = $("#modal");
  m.innerHTML = `<div class="dialog wide"><h3>${esc(t("bug_title"))}</h3>
    <textarea id="bugText" placeholder="${esc(t("bug_ph"))}"></textarea>
    <p class="fine">${esc(t("bug_what"))}</p>
    <div class="row"><button class="btn ghost" id="bugCancel">${esc(t("cancel"))}</button>
    <button class="btn primary" id="bugSend">${ICON.send}${esc(t("bug_send"))}</button></div></div>`;
  m.hidden = false;
  const close = () => { m.hidden = true; m.innerHTML = ""; };
  m.onclick = e => { if (e.target === m) close(); };
  $("#bugCancel").onclick = close;
  setTimeout(() => $("#bugText").focus(), 50);
  $("#bugSend").onclick = async () => {
    const b = $("#bugSend");
    b.disabled = true; b.textContent = t("bug_sending");
    try {
      const r = await api("/api/report", {comment: $("#bugText").value});
      close();
      if (r.sent) toast(t("bug_sent"), "ok");
      else toast(t("bug_saved"), "ok", {label: t("bug_where"), fn: () => native() && native().show_in_folder(r.path)});
    } catch (e) { b.disabled = false; b.textContent = t("bug_send"); toast(errText(e), "err"); }
  };
}

/* ---------- updates ---------- */
async function checkUpdates(force) {
  if (!force && S.settings && S.settings.auto_update === false) return;
  try { S.update = await api("/api/update/check", {}); } catch { }
  renderUpdChip();
}
function renderUpdChip() {
  const el = $("#updChip");
  if (!el) return;
  const u = S.update;
  el.innerHTML = u && u.available ? `<div class="rec-chip upd"><div class="row1">${ICON.up}${esc(t("upd_chip"))}</div>
    <div class="row2">${esc(t("upd_chip_sub", {v: u.latest}))}</div></div>` : "";
  el.onclick = () => go("settings");
}
function updText() {
  const u = S.update;
  if (!u || !u.checked) return "";
  if (u.error) return t("upd_err", {e: u.error});
  const when = new Date(u.checked * 1000).toLocaleTimeString(LANG === "ru" ? "ru-RU" : "en-GB", {hour: "2-digit", minute: "2-digit"});
  return (u.available ? t("upd_av", {v: u.latest}) : t("upd_ok")) + " · " + t("upd_checked", {t: when});
}
async function installUpdate() {
  await api("/api/update/install", {}).catch(e => toast(errText(e), "err"));
  const tick = async () => {
    const u = S.update = await api("/api/update").catch(() => S.update);
    const box = $("#updStatus");
    if (box) box.textContent = t("upd_dl", {p: Math.round((u.progress || 0) * 100)});
    if (u.error) { toast(t("upd_err", {e: u.error}), "err"); return pageSettings($("#main")); }
    setTimeout(tick, 700);  // the app closes itself once the installer starts
  };
  tick();
}
const go = r => { location.hash = "#/" + r; };

function route() {
  clearTimeout(viewTimer);
  const h = location.hash.replace(/^#\//, "");
  const [name, arg] = h.split("/");
  $$(".nav a").forEach(a => a.classList.toggle("on", a.dataset.r === (name === "watch" ? "library" : name || "library")));
  const main = $("#main");
  main.scrollTop = 0;
  if (name === "new") return pageNew(main);
  if (name === "settings") return pageSettings(main);
  if (name === "watch" && arg) return pageWatch(main, decodeURIComponent(arg));
  return pageLibrary(main);
}

/* ---------- job polling (sidebar chip + recording page) ---------- */
async function pollJob() {
  clearTimeout(jobTimer);
  const prev = S.job;
  try { S.job = await api("/api/job"); } catch { }
  const j = S.job || {};
  const chip = $("#recChip");
  if (chip) {
    chip.innerHTML = j.running ? `
      <div class="rec-chip"><div class="row1"><span class="pulse"></span>${esc(t("rec_chip"))}</div>
      <div class="row2 num">${esc(t("rec_chip_sub", {done: j.done, total: j.total || "…", player: j.player || ""}))}</div>
      <div class="bar" style="height:5px;margin-top:8px"><i style="width:${j.total ? Math.round(j.done / j.total * 100) : 3}%"></i></div></div>` : "";
    chip.onclick = () => go("new");
  }
  if (prev && prev.running && !j.running) {
    if (j.error) toast(errText(j.error), "err");
    else if (j.result) toast(t("rec_done", {n: ""}).replace(/\s*$/, ""), "ok", {label: t("rec_watch"), fn: () => go("watch/" + j.result)});
  }
  if (location.hash.startsWith("#/new") && (j.running || (prev && prev.running))) renderRecording();
  // keep the library's "recording · N clips" card live
  const onLib = location.hash === "#/library" || location.hash === "" || location.hash === "#/";
  if (onLib && $("#main") && (j.running ? j.done !== (prev && prev.done) : prev && prev.running)) pageLibrary($("#main"));
  jobTimer = setTimeout(pollJob, j.running ? 1200 : 4000);
}

/* ---------- library ---------- */
async function pageLibrary(main) {
  const items = (await api("/api/library").catch(() => [])).sort((a, b) => (b.match_time || 0) - (a.match_time || 0) || (b.recorded > a.recorded ? 1 : -1));
  if (!items.length) {
    main.innerHTML = `<div class="page"><div class="empty">
      <svg class="art" viewBox="0 0 140 140" fill="none"><circle cx="70" cy="70" r="52" stroke="#ff4d2e" stroke-opacity=".35" stroke-width="3"/><circle cx="70" cy="70" r="30" stroke="#ff7a2f" stroke-width="5"/><path d="M70 10v26M70 104v26M10 70h26M104 70h26" stroke="#ff7a2f" stroke-width="5" stroke-linecap="round"/><circle cx="70" cy="70" r="7" fill="#ff4d2e"/></svg>
      <h2>${esc(t("lib_empty_t"))}</h2><p>${esc(t("lib_empty_p"))}</p>
      <button class="btn primary lg" id="cta">${ICON.plus}${esc(t("lib_empty_cta"))}</button></div></div>`;
    $("#cta").onclick = () => go("new");
    return;
  }
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>${esc(t("lib_title"))}</h1><p>${esc(t("lib_sub"))}</p></div>
      <div class="actions"><button class="btn primary" id="newRec">${ICON.plus}${esc(t("lib_new"))}</button></div></div>
    <div class="grid">${items.map(d => `
      <div class="card" data-k="${esc(d.key)}">
        <button class="menu" title="${esc(t("del_ok"))}" data-del="${esc(d.key)}">${ICON.trash}</button>
        <div class="banner pic" style="background:${mapBg(d.map, d.thumb && media(d.key, d.thumb))}">
          <div class="tags">${d.status === "recording" ? `<span class="badge live"><span class="pulse" style="background:#fff"></span>${esc(t("status_rec"))}</span>` : ""}
            ${d.status === "stopped" ? `<span class="badge stopped">${esc(t("status_stopped"))}</span>` : ""}
            <span class="badge">${esc(t("clips_n", {n: d.clips}))}</span></div>
          <div class="map-name">${esc(mapName(d.map))}</div>
        </div>
        <div class="card-body">
          <div class="who">${esc(d.player.name)}<span class="kd num"><span class="k">${d.player.kills}</span> <span class="dim">/</span> <span class="d">${d.player.deaths}</span></span></div>
          <div class="meta"><span>${esc(d.match_time ? fmtMatch(d.match_time) : niceDate(d.recorded))}</span>${scoreHtml(d.score)}</div>
        </div>
      </div>`).join("")}
      <div class="card new" id="newCard"><div class="plus">${ICON.plus}</div><b>${esc(t("lib_card_new"))}</b></div>
    </div></div>`;
  $("#newRec").onclick = $("#newCard").onclick = () => go("new");
  $$(".card[data-k]").forEach(c => c.onclick = () => go("watch/" + encodeURIComponent(c.dataset.k)));
  $$("[data-del]").forEach(b => b.onclick = async e => {
    e.stopPropagation();
    const d = items.find(i => i.key === b.dataset.del);
    if (!await confirmModal(t("del_title"), t("del_text", {player: d.player.name, map: mapName(d.map)}), t("del_ok"))) return;
    await api("/api/delete", {key: d.key}).catch(err => toast(errText(err), "err"));
    pageLibrary(main);
  });
}

/* ---------- new recording ---------- */
async function pageNew(main) {
  if (S.job && S.job.running) return renderRecording();
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>${esc(t("new_title"))}</h1><p>${esc(t("new_sub"))}</p></div></div>
    <div class="two">
      <div>
        <div class="drop" id="drop"><div class="ico">${ICON.upload}</div>
          <h3>${esc(t("drop_t"))}</h3><p>${esc(t("drop_p"))}</p>
          <button class="btn" id="pick">${ICON.folder}${esc(t("drop_btn"))}</button></div>
        <div class="section-title">${esc(t("found"))}</div>
        <div class="list" id="found"><div class="muted">…</div></div>
      </div>
      <div id="playerSide"></div>
    </div></div>`;
  renderPlayers();
  const drop = $("#drop");
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  $("#pick").onclick = async () => {
    const p = native() ? await native().pick_demo() : prompt("Demo path");
    if (p) openDemo(p);
  };
  const list = await api("/api/demos").catch(() => []);
  if (!$("#found")) return;
  $("#found").innerHTML = list.length ? list.slice(0, 30).map(d => `
    <div class="item ${S.picked === d.path ? "sel" : ""}" data-p="${esc(d.path)}" title="${esc(d.name)}">
      <div class="tile pic" style="background:${mapBg(d.map)}"><span>${esc(mapName(d.map).slice(0, 4))}</span></div>
      <div class="grow"><div class="t1">${esc(mapName(d.map))}</div><div class="t2 num">${esc(niceDate(d.modified))} · ${d.size_mb} ${LANG === "ru" ? "МБ" : "MB"}</div></div>
    </div>`).join("") : `<div class="muted">${esc(t("found_none"))}</div>`;
  $$("#found .item").forEach(r => r.onclick = () => openDemo(r.dataset.p));
}
// drag & drop of a file onto the window is resolved to a real path by Python
window.onDemoDropped = path => { if (!location.hash.startsWith("#/new")) go("new"); setTimeout(() => openDemo(path), 50); };

async function openDemo(path) {
  S.picked = path; S.demoInfo = null; S.players = [];
  $$("#found .item").forEach(r => r.classList.toggle("sel", r.dataset.p === path));
  renderPlayers(true);
  try { S.demoInfo = await api("/api/analyze", {path}); }
  catch (e) { S.demoInfo = {error: e.message}; }
  renderPlayers();
}

function renderPlayers(loading) {
  const side = $("#playerSide");
  if (!side) return;
  const d = S.demoInfo;
  if (loading) { side.innerHTML = `<div class="panel" style="padding:40px;text-align:center" class="muted">${esc(t("reading"))}</div>`; return; }
  if (!d) { side.innerHTML = `<div class="panel" style="padding:40px;text-align:center"><span class="muted">${esc(t("choose_first"))}</span></div>`; return; }
  if (d.error) { side.innerHTML = `<div class="error-box">${esc(d.error)}</div>`; return; }
  const multi = maxPlayers() > 1;
  const team = n => d.players.filter(p => p.team === n).map(p => `
    <div class="item player ${S.players.includes(p.steamid) ? "sel" : ""}" data-s="${p.steamid}">
      ${multi ? `<span class="check">${ICON.check}</span>` : ""}
      <div class="grow"><div class="name">${esc(p.name)}</div><div class="t2">${esc(t("clips_n", {n: p.clips}))}</div></div>
      <div class="kd num"><span class="k">${p.kills}</span> <span class="dim">/</span> <span class="d">${p.deaths}</span></div>
    </div>`).join("");
  const sel = S.players.map(s => d.players.find(p => p.steamid === s)).filter(Boolean);
  const clipsSum = sel.reduce((a, p) => a + p.clips, 0);
  const minSum = Math.max(1, Math.round(sel.reduce((a, p) => a + p.video_seconds, 0) / 60));
  side.innerHTML = `
    <div class="match-head"><div class="tile pic" style="background:${mapBg(d.map)}"><span>${esc(mapName(d.map).slice(0, 4))}</span></div>
      <div><h3>${esc(mapName(d.map))} ${(p => p ? scoreHtml([p.won, p.lost]) : "")(d.players.find(p => p.team === 2))}</h3><div class="muted">${esc(t("rounds_n", {n: d.rounds}))} · ${esc(multi ? t("pick_players", {n: maxPlayers()}) : t("pick_player"))}</div></div></div>
    <div class="teams">
      <div class="team t"><h4><i></i>${esc(t("team_t"))}</h4><div class="list">${team(2)}</div></div>
      <div class="team ct"><h4><i></i>${esc(t("team_ct"))}</h4><div class="list">${team(3)}</div></div>
    </div>
    <div class="go-bar">
      <div class="info">${sel.length ? `<b>${esc(t("go_sel", {name: sel.map(p => p.name).join(", ")}))}</b><span class="muted num">${esc(t("go_info", {clips: clipsSum, min: minSum}))}</span>`
        : `<span class="muted">${esc(t("pick_player"))}</span>`}</div>
      <button class="btn primary lg" id="goRec" ${sel.length ? "" : "disabled"}>${ICON.rec}${esc(t("go_btn"))}</button>
    </div>`;
  $$(".player", side).forEach(r => r.onclick = () => {
    const s = r.dataset.s;
    if (!multi) S.players = [s];
    else if (S.players.includes(s)) S.players = S.players.filter(x => x !== s);
    else if (S.players.length >= maxPlayers()) return toast(t("pick_max", {n: maxPlayers()}), "err");
    else S.players = [...S.players, s];
    renderPlayers();
  });
  const btn = $("#goRec");
  if (btn) btn.onclick = async () => {
    btn.disabled = true;
    try {
      await api("/api/record", {path: d.path, steamids: S.players});
      S.recStarted = Date.now();
      S.job = {running: true, phase: "launch", done: 0, total: 0, player: sel.map(p => p.name).join(", "), map: d.map};
      renderRecording();
      pollJob();
    } catch (e) { toast(errText(e), "err"); btn.disabled = false; }
  };
}

function renderRecording() {
  const main = $("#main");
  if (!main || !location.hash.startsWith("#/new")) return;
  const j = S.job || {};
  const phases = ["launch", "loading", "recording", "finishing"];
  const finished = !j.running;
  const cur = finished ? (j.error ? -1 : 4) : phases.indexOf(j.phase);
  const pct = finished ? 100 : j.total ? Math.round(j.done / j.total * 100) : [2, 6, 8, 98][Math.max(0, cur)];
  let eta = "";
  if (j.running && j.total && j.done > 1 && S.recStarted) {
    const per = (Date.now() - S.recStarted) / 1000 / j.done;
    eta = t("rec_eta", {t: fmtTime(per * (j.total - j.done))});
  }
  main.innerHTML = `<div class="page" style="max-width:900px">
    <div class="page-head"><div><h1>${esc(finished ? (j.error ? t("rec_failed") : t("ph_done")) : t("rec_title"))}</h1></div></div>
    <div class="panel progress-card">
      <div class="banner" style="background:${mapBg(j.map)}"><div class="map-name">${esc(mapName(j.map))}</div></div>
      <div class="body">
        <div style="display:flex;align-items:flex-end;gap:16px;margin-bottom:14px">
          <div><div class="muted">${esc(j.player || "")}</div><div class="big-num num">${pct}%</div></div>
          <div style="margin-left:auto;text-align:right" class="muted num">${j.total ? esc(t("rec_seg", {done: j.done, total: j.total})) : ""}<br>${esc(eta)}</div>
        </div>
        <div class="bar"><i style="width:${pct}%"></i></div>
        <div class="steps">${phases.map((p, i) => `<div class="step ${i < cur ? "done" : i === cur ? "now" : ""}"><span class="dot"></span>${esc(t("ph_" + p))}</div>`).join("")}</div>
        ${j.error ? `<div class="error-box" style="margin-top:18px">${esc(errText(j.error))}</div>` : ""}
        ${!finished ? `<div class="note" style="margin-top:18px">${ICON.warn}<span>${esc(t("rec_note"))}</span></div>` : ""}
        <div style="display:flex;gap:10px;margin-top:20px">
          ${j.result || (j.running && j.done > 0) ? `<button class="btn primary" id="watchNow">${esc(finished ? t("rec_open") : t("rec_watch"))}</button>` : ""}
          ${finished ? `<button class="btn" id="again">${ICON.plus}${esc(t("rec_new"))}</button>` : ""}
        </div>
      </div>
    </div></div>`;
  const w = $("#watchNow");
  if (w) w.onclick = async () => {
    const key = j.result || ((await api("/api/library").catch(() => [])).find(i => i.status === "recording") || {}).key;
    if (key) go("watch/" + encodeURIComponent(key));
  };
  const a = $("#again");
  if (a) a.onclick = () => { S.job = {...S.job, error: null, result: null}; S.demoInfo = null; S.players = []; S.picked = null; api("/api/job").then(x => { S.job = {...x, running: false}; }); pageNewFresh(); };
}
function pageNewFresh() { S.job = {running: false}; pageNew($("#main")); }

/* ---------- viewer ---------- */
async function pageWatch(main, key) {
  let meta;
  try { meta = await (await fetch(media(key, "meta.json"), {cache: "no-store"})).json(); }
  catch { main.innerHTML = `<div class="page"><div class="empty"><h2>404</h2></div></div>`; return; }
  const me = meta.player;
  let clips = meta.clips.filter(c => c.file);
  let filter = "all", cur = null, stopAt = null, autoplay = true;
  const picks = [];  // demo build: clips ticked for gluing, in the order they were ticked

  main.innerHTML = `<div class="page">
    <div class="viewer-head">
      <button class="btn icon-btn" id="back">${ICON.back}</button>
      <div class="tile pic" style="background:${mapBg(meta.map, meta.thumb && media(key, meta.thumb))};width:46px;height:46px"></div>
      <div><h1>${esc(me.name)} ${scoreHtml(meta.score)}</h1><div class="sub"><span>${esc(mapName(meta.map))}</span>${meta.match_time ? " · " + esc(fmtMatch(meta.match_time)) : ""} · <span id="vstatus"></span></div></div>
      <div class="kd num" style="margin-left:auto;font-size:22px"><span class="k">${me.kills}</span> <span class="dim">/</span> <span class="d">${me.deaths}</span></div>
    </div>
    <div class="viewer">
      <div>
        <div class="stage"><video id="v" controls playsinline></video>
          <div class="overlay" id="ov"></div></div>
        <div class="toolbar">
          <div class="seg" id="flt">
            <button data-f="all" class="on">${esc(t("v_all"))}</button><button data-f="kill">${esc(t("v_kills"))}</button><button data-f="death">${esc(t("v_deaths"))}</button>
          </div>
          <button class="btn icon-btn" id="prev" title="←">${ICON.prev}</button>
          <button class="btn icon-btn" id="next" title="→">${ICON.next}</button>
          <span class="switch on" id="auto"><i></i>${esc(t("v_auto"))}</span>
          <span class="spacer"></span>
          ${isDemo() ? `<button class="btn" id="exportBtn">${ICON.send}${esc(t("x_btn"))}</button>` : ""}
          <button class="btn primary" id="save">${ICON.save}${esc(t("v_save"))}</button>
          <button class="btn icon-btn" id="folder" title="${esc(t("v_folder"))}">${ICON.folder}</button>
        </div>
        <div class="timeline" id="tl"></div>
        <div class="dim" style="margin-top:10px;font-size:12px">${esc(t("v_keys"))}</div>
      </div>
      <div><div id="xbar"></div><div class="side-list" id="list"></div></div>
    </div></div>`;

  const v = $("#v");
  const visible = () => clips.filter(c => filter === "all" ? !c.inside_death : c.kind === filter);
  const title = c => c.kind === "kill"
    ? (c.events.length > 1 ? `${c.events.length}K · ` : "") + c.events.map(e => esc(e.victim_name)).join(", ")
    : esc(t("v_killed_by", {name: c.events[0].attacker_name || t("v_world")}));
  const sub = c => c.events.map(e => [W(e.weapon), e.headshot && t("v_hs"), e.wallbang && t("v_wb"), e.thrusmoke && t("v_smoke"), e.noscope && t("v_noscope")]
    .filter(Boolean).join(" · ")).join("  |  ") + (c.kind === "death" && c.segments.length > 1 ? `<span class="chip">${esc(t("v_cam"))}</span>` : "");

  function renderStatus() {
    const all = meta.clips.filter(c => !c.inside_death).length;
    const ready = meta.clips.filter(c => c.file && !c.inside_death).length;
    $("#vstatus").textContent = meta.status === "recording" ? t("v_live", {ready, all})
      : `${t("rounds_n", {n: meta.rounds.length})} · ${t("v_rec_in", {m: Math.max(1, Math.round(meta.took_seconds / 60))})}`;
  }
  function renderTimeline() {
    $("#tl").innerHTML = meta.rounds.map(r => {
      const rc = clips.filter(c => c.round === r.number);
      const pips = rc.filter(c => c.kind === "kill").flatMap(c => c.events).map(() => `<span class="pip kill"></span>`).join("")
        + rc.filter(c => c.kind === "death").map(() => `<span class="pip death"></span>`).join("");
      return `<div class="rnd ${cur && cur.round === r.number ? "cur" : ""}" data-r="${r.number}" title="${esc(t("v_round", {n: r.number}))}">
        <span class="n num">${r.number}</span><div class="dots">${pips || `<span class="none"></span>`}</div></div>`;
    }).join("");
    $$("#tl .rnd").forEach(el => el.onclick = () => {
      const c = visible().find(c => c.round === +el.dataset.r) || clips.find(c => c.round === +el.dataset.r);
      if (c) play(c);
    });
  }
  function renderList() {
    const list = visible();
    const rounds = [...new Set(list.map(c => c.round))];
    $("#list").innerHTML = rounds.length ? rounds.map(r => `
      <div class="rgroup"><h5>${esc(t("v_round", {n: r}))}</h5>${list.filter(c => c.round === r).map(c => `
        <div class="clip ${c.kind} ${cur === c ? "cur" : ""} ${picks.includes(c.id) ? "picked" : ""}" data-id="${c.id}">
          ${isDemo() ? `<span class="check" data-pick="${c.id}" title="${esc(t("x_pick"))}">${ICON.check}</span>` : ""}
          <div class="ic">${c.kind === "kill" ? (c.events.length > 1 ? c.events.length + "K" : "K") : "✕"}</div>
          <div class="grow"><div class="t">${title(c)}</div><div class="s">${sub(c)}</div></div>
        </div>`).join("")}</div>`).join("")
      : `<div class="panel" style="padding:30px;text-align:center"><span class="muted">${esc(t("v_empty"))}</span></div>`;
    $$("#list .clip").forEach(el => el.onclick = () => play(clips.find(c => c.id === el.dataset.id)));
    $$("#list [data-pick]").forEach(el => el.onclick = e => {
      e.stopPropagation();
      const id = el.dataset.pick, i = picks.indexOf(id);
      i >= 0 ? picks.splice(i, 1) : picks.push(id);
      renderList();
    });
    const curEl = $("#list .clip.cur");
    if (curEl) curEl.scrollIntoView({block: "nearest"});
    renderXbar();
  }
  function renderXbar() {
    const bar = $("#xbar");
    if (!bar) return;
    bar.innerHTML = isDemo() && picks.length ? `<div class="export-bar">
      <span class="grow">${esc(t("x_picked", {n: picks.length}))}</span>
      <a id="xClear">${esc(t("x_clear"))}</a>
      <button class="btn primary" id="xGo">${esc(t("x_glue"))}</button></div>` : "";
    if (!picks.length) return;
    $("#xClear").onclick = () => { picks.length = 0; renderList(); };
    $("#xGo").onclick = () => exportModal(key, meta, [...picks]);
  }
  function load(c, start, autoplayNow) {
    const src = media(key, c.file);
    if (!v.src.endsWith(src)) {
      v.src = src;
      v.addEventListener("loadedmetadata", () => { v.currentTime = start; if (autoplayNow) v.play().catch(() => { }); }, {once: true});
    } else { v.currentTime = start; if (autoplayNow) v.play().catch(() => { }); }
  }
  function play(c, autoplayNow = true) {
    cur = c;
    const start = c.offset || 0;
    stopAt = c.inside_death ? start + 4 : null;
    load(c, start, autoplayNow);
    renderTimeline(); renderList(); badge();
  }
  function step(d) {
    const list = visible();
    const n = list[list.indexOf(cur) + d];
    if (n) play(n);
  }
  function badge() {
    if (!cur) { $("#ov").innerHTML = ""; return; }
    const offs = cur.part_offsets || [0];
    const cam = cur.kind === "death" && !cur.inside_death && offs.length > 1 && v.currentTime >= offs[1];
    $("#ov").innerHTML = `<span class="tag">${esc(t("v_round", {n: cur.round}))}</span>` + (cam
      ? `<span class="tag cam">${esc(t("v_killcam", {name: cur.segments[1].pov_name}))}</span>`
      : `<span class="tag ${cur.kind}">${esc(cur.kind === "kill" ? t("v_kill") : t("v_death"))}</span>`);
  }
  v.addEventListener("timeupdate", () => {
    if (!cur) return;
    if (stopAt && v.currentTime >= stopAt) { stopAt = null; v.pause(); if (autoplay) step(1); return; }
    badge();
  });
  v.addEventListener("ended", () => { if (autoplay) step(1); });
  $("#back").onclick = () => go("library");
  $("#prev").onclick = () => step(-1);
  $("#next").onclick = () => step(1);
  $("#auto").onclick = () => { autoplay = !autoplay; $("#auto").classList.toggle("on", autoplay); };
  $("#folder").onclick = () => api("/api/open-folder", {key}).catch(e => toast(errText(e), "err"));
  $("#save").onclick = async () => {
    if (!cur) return;
    const name = `Killcam_${me.name}_${mapName(meta.map)}_R${cur.round}_${cur.kind}.mp4`.replace(/[^\w.\-]+/g, "_");
    if (!native()) return window.open(media(key, cur.file));
    const r = await native().save_clip(key, cur.file, name);
    if (r && r.ok) toast(t("saved"), "ok", {label: t("show"), fn: () => native().show_in_folder(r.path)});
  };
  if ($("#exportBtn")) $("#exportBtn").onclick = () => {
    const ids = picks.length ? [...picks] : cur ? [cur.id] : [];
    if (ids.length) exportModal(key, meta, ids);
  };
  $$("#flt button").forEach(b => b.onclick = () => {
    filter = b.dataset.f;
    $$("#flt button").forEach(x => x.classList.toggle("on", x === b));
    renderList();
    const first = visible()[0]; if (first) play(first);
  });
  const onKey = e => {
    if (!location.hash.startsWith("#/watch")) return document.removeEventListener("keydown", onKey);
    if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    else if (e.key === " " && e.target === document.body) { e.preventDefault(); v.paused ? v.play() : v.pause(); }
  };
  document.addEventListener("keydown", onKey);

  async function refresh() {
    if (!location.hash.startsWith("#/watch")) return;
    try { meta = await (await fetch(media(key, "meta.json"), {cache: "no-store"})).json(); } catch { }
    const curId = cur && cur.id;
    clips = meta.clips.filter(c => c.file);
    cur = clips.find(c => c.id === curId) || cur;
    renderStatus(); renderTimeline(); renderList();
    if (!cur && visible()[0]) play(visible()[0], false);
    if (meta.status === "recording") viewTimer = setTimeout(refresh, 3000);
  }

  renderStatus(); renderTimeline(); renderList();
  if (visible()[0]) play(visible()[0], false);
  if (meta.status === "recording") viewTimer = setTimeout(refresh, 3000);
}

/* ---------- export (demo build): glue, 9:16, watermark, Discord ---------- */
function exportModal(key, meta, ids) {
  // glued in match order, whatever order they were ticked in
  const order = Object.fromEntries(meta.clips.map((c, i) => [c.id, i]));
  ids = [...ids].sort((a, b) => order[a] - order[b]);
  const m = $("#modal");
  let vertical = false;
  const me = meta.player;
  m.innerHTML = `<div class="dialog wide"><h3>${esc(ids.length > 1 ? t("x_title_n", {n: ids.length}) : t("x_title_1"))}</h3>
    <p class="fine" style="margin-bottom:10px">${esc(t("x_wm"))}</p>
    <div class="fmt">
      <button data-v="0" class="on"><span class="shape" style="width:30px;height:18px"></span><span>${esc(t("x_h"))}<small>${esc(t("x_h_d"))}</small></span></button>
      <button data-v="1"><span class="shape" style="width:16px;height:28px"></span><span>${esc(t("x_v"))}<small>${esc(t("x_v_d"))}</small></span></button>
    </div>
    <div class="status" id="xStatus"></div>
    <div class="row"><button class="btn ghost" id="xCancel">${esc(t("cancel"))}</button>
      <button class="btn" id="xDiscord">${ICON.send}${esc(t("x_discord"))}</button>
      <button class="btn primary" id="xSave">${ICON.save}${esc(t("x_save"))}</button></div></div>`;
  m.hidden = false;
  const close = () => { m.hidden = true; m.innerHTML = ""; };
  m.onclick = e => { if (e.target === m && !busy) close(); };
  let busy = false;
  $("#xCancel").onclick = close;
  $$(".fmt button", m).forEach(b => b.onclick = () => {
    vertical = b.dataset.v === "1";
    $$(".fmt button", m).forEach(x => x.classList.toggle("on", x === b));
  });
  const status = s => { $("#xStatus").textContent = s; };
  async function run(discord) {
    if (discord && !(S.settings && S.settings.discord_webhook_set)) {
      close(); toast(t("x_no_hook"), "err", {label: t("nav_settings"), fn: () => go("settings")}); return;
    }
    busy = true;
    $$("button", m).forEach(b => b.disabled = true);
    status(discord ? t("x_working_d") : t("x_working"));
    let id;
    try {
      const text = `🎯 **${me.name}** · ${mapName(meta.map)}${meta.score ? ` ${meta.score[0]}:${meta.score[1]}` : ""} · ${t("x_from")}`;
      id = (await api("/api/export", {key, clips: ids, vertical, discord, text})).id;
    } catch (e) { busy = false; close(); return toast(errText(e), "err"); }
    let st;
    do {
      await new Promise(r => setTimeout(r, 800));
      st = await api("/api/export?id=" + id).catch(() => ({state: "working"}));
    } while (st.state === "working");
    busy = false;
    if (st.state === "error") { close(); return toast(errText(st.error), "err"); }
    if (discord) { close(); return toast(t("x_sent"), "ok"); }
    const name = `Killcam_${me.name}_${mapName(meta.map)}${vertical ? "_9x16" : ""}.mp4`.replace(/[^\w.\-]+/g, "_");
    const r = native() ? await native().save_export(id, name) : null;
    close();
    if (r && r.ok) toast(t("saved"), "ok", {label: t("show"), fn: () => native().show_in_folder(r.path)});
  }
  $("#xSave").onclick = () => run(false);
  $("#xDiscord").onclick = () => run(true);
}

/* ---------- settings ---------- */
async function pageSettings(main) {
  const s = S.settings = await api("/api/settings").catch(() => S.settings || {});
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>${esc(t("s_title"))}</h1></div></div>
    <div class="settings">
      <div class="panel setting"><div class="grow"><h4>${esc(t("s_lang"))}</h4><p>${esc(t("s_lang_d"))}</p></div>
        <div class="seg" id="lang"><button data-v="ru" class="${s.lang === "ru" ? "on" : ""}">Русский</button><button data-v="en" class="${s.lang === "en" ? "on" : ""}">English</button></div></div>
      <div class="panel setting"><div class="grow"><h4>${esc(t("s_fps"))}</h4><p>${esc(t("s_fps_d"))}</p></div>
        <div class="seg" id="fps"><button data-v="60" class="${s.fps === 60 ? "on" : ""}">${esc(t("s_fps60"))}</button><button data-v="144" class="${s.fps === 144 ? "on" : ""}">${esc(t("s_fps144"))}</button></div></div>
      <div class="panel setting"><div class="grow"><h4>${esc(t("upd_title"))}</h4>
          <p>${esc(t("upd_cur", {v: s.version}))} · <span id="updStatus">${esc(updText())}</span></p>
          <label class="switch ${s.auto_update !== false ? "on" : ""}" id="autoUpd" style="margin-top:10px"><i></i>${esc(t("upd_auto"))}</label></div>
        <div style="display:flex;gap:8px">
          ${S.update && S.update.available ? `<button class="btn primary" id="updGo">${ICON.up}${esc(t("upd_install", {v: S.update.latest}))}</button>` : ""}
          <button class="btn" id="updCheck">${esc(t("upd_check"))}</button></div></div>
      ${s.channel === "demo" ? `<div class="panel setting"><div class="grow"><h4>${esc(t("s_hook"))}</h4>
          <p style="margin-bottom:10px">${esc(t("s_hook_d"))}</p>
          <input class="text" id="hook" placeholder="https://discord.com/api/webhooks/…" value="${s.discord_webhook_set ? "••••••••••••" : ""}"></div>
        <button class="btn" id="hookSave">${esc(t("s_hook_save"))}</button></div>` : ""}
      <div class="panel setting"><div class="grow"><h4>${esc(t("s_folder"))}</h4><p class="path">${esc(s.data_dir)}</p></div>
        <button class="btn" id="openLib">${ICON.folder}${esc(t("s_open"))}</button></div>
      <div class="panel setting"><div class="grow"><h4>${esc(t("s_sys"))}</h4>
        <p>${esc(t("s_encoder"))}: <b>${esc(s.encoder || "—")}</b></p><p class="path">${esc(t("s_cs2"))}: ${esc(s.cs2_dir || "—")}</p></div></div>
      <div class="panel setting"><div class="grow"><h4>${esc(t("s_about"))}</h4><p>${esc(t("s_about_d", {v: s.version}))}</p></div>
        <button class="btn" id="gh">${ICON.github}${esc(t("s_github"))}</button></div>
    </div></div>`;
  $$("#lang button").forEach(b => b.onclick = async () => {
    S.settings = await api("/api/settings", {lang: b.dataset.v});
    LANG = S.settings.lang;
    renderShell(); route(); pollJob();
  });
  $$("#fps button").forEach(b => b.onclick = async () => {
    S.settings = await api("/api/settings", {fps: +b.dataset.v});
    $$("#fps button").forEach(x => x.classList.toggle("on", x === b));
  });
  $("#openLib").onclick = () => api("/api/open-folder", {}).catch(e => toast(errText(e), "err"));
  if ($("#hookSave")) $("#hookSave").onclick = async () => {
    const v = $("#hook").value.trim();
    if (v.startsWith("•")) return;
    try {
      S.settings = await api("/api/settings", {discord_webhook: v});
      toast(v ? t("s_hook_ok") : t("s_hook_off"), "ok");
      pageSettings(main);
    } catch (e) { toast(errText(e), "err"); }
  };
  $("#updCheck").onclick = async () => { $("#updStatus").textContent = "…"; await checkUpdates(true); pageSettings(main); };
  if ($("#updGo")) $("#updGo").onclick = () => { toast(t("upd_restart"), "ok"); $("#updGo").disabled = true; installUpdate(); };
  $("#autoUpd").onclick = async () => {
    S.settings = await api("/api/settings", {auto_update: !(S.settings.auto_update !== false)});
    $("#autoUpd").classList.toggle("on", S.settings.auto_update !== false);
  };
  $("#gh").onclick = () => native() && native().open_external(`https://github.com/${s.repo}`);
}

boot();
