// Shared bits for both pages.
function $(sel) { return document.querySelector(sel); }
function esc(s) { return String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])); }
let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 6000);
}
function segment(el, onChange) {
  el.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b || b.disabled) return;
    el.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    if (onChange) onChange(b.dataset.v);
  });
  return () => { const on = el.querySelector('button.on'); return on ? on.dataset.v : null; };
}
// Downloads go through fetch first so a missing PDF shows a message instead of an error page.
async function download(url) {
  const r = await fetch(url, {method: 'GET'});
  if (!r.ok) {
    let msg = 'That file could not be made.';
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    toast(msg); return;
  }
  const blob = await r.blob();
  const cd = r.headers.get('content-disposition') || '';
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = m ? decodeURIComponent(m[1]) : 'download';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 60000);
}
const HORN_NAMES = {soprano: 'Soprano', alto: 'Alto', tenor: 'Tenor', baritone: 'Baritone', concert: 'Concert'};

// Solo clip: while on, an <audio> plays only the transcribed solo (clip = {start, end} in seconds of the
// record, a few seconds padded each side). The record itself is untouched; this only moves the playhead.
// Returns {on, set(on), span()}; when the solo is most of the track the switch isn't worth showing.
function soloClip(audio, clip) {
  const c = {on: !!clip, clip};
  const outside = () => audio.currentTime < c.clip.start - 0.05 || audio.currentTime >= c.clip.end - 0.05;
  audio.addEventListener('play', () => { if (c.on && outside()) audio.currentTime = c.clip.start; });
  audio.addEventListener('timeupdate', () => {
    if (c.on && audio.currentTime >= c.clip.end) { audio.pause(); audio.currentTime = c.clip.start; }
  });
  audio.addEventListener('loadedmetadata', () => { if (c.on && audio.currentTime < c.clip.start) audio.currentTime = c.clip.start; });
  audio.addEventListener('seeked', () => { if (c.on && outside()) audio.currentTime = c.clip.start; });
  c.set = on => {
    c.on = !!(on && clip);
    if (c.on && outside()) audio.currentTime = c.clip.start;
  };
  c.worth = duration => !!clip && !(duration > 0 && clip.end - clip.start >= 0.9 * duration);
  c.span = () => c.on ? [c.clip.start, Math.min(c.clip.end, audio.duration || c.clip.end)] : [0, audio.duration || 0];
  return c;
}
function clipLabel(clip) {
  const m = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  return `${m(clip.first_note ?? clip.start)}–${m(clip.last_note ?? clip.end)}`;
}
// Check in with the app every minute while this page is open. When the app was started
// from Lift, it quits once no page has checked in for a while (see idle_watch in server.py).
function checkIn() { fetch('/api/alive', {method: 'POST'}).catch(() => {}); }
checkIn();
setInterval(checkIn, 60000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkIn(); });

// Line icons, one stroke weight (the .ico class sets size and stroke).
const ICONS = {
  transcribe: '<path d="M12 15V4"/><path d="M7 9l5-5 5 5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  library: '<path d="M5 4v16"/><path d="M9 4v16"/><circle cx="16" cy="12" r="5"/><circle cx="16" cy="12" r="1.2"/>',
  results: '<path d="M4 20h16"/><path d="M7 16v-4"/><path d="M12 16V7"/><path d="M17 16v-6"/>',
  review: '<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>',
  play: '<path d="M7 5l12 7-12 7z"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  auto: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>',
};
function icon(name) { return `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`; }

// The record motif: a small disc with grooves. With done (0..1) an orange arc fills around its
// edge to show progress.
function recordIcon(done = null) {
  const C = 2 * Math.PI * 21;
  const arc = done == null ? '' :
    `<circle class="arc" cx="24" cy="24" r="21" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${(C * (1 - done)).toFixed(1)}" transform="rotate(-90 24 24)"/>`;
  return `<svg class="record" viewBox="0 0 48 48" aria-hidden="true">` +
    '<circle class="disc" cx="24" cy="24" r="19"/><circle class="groove" cx="24" cy="24" r="8"/>' +
    '<circle class="groove" cx="24" cy="24" r="11.5"/><circle class="groove" cx="24" cy="24" r="15"/>' +
    `<circle class="label" cx="24" cy="24" r="4.4"/>${arc}</svg>`;
}

// Light or dark: Auto follows the Mac (or iPad); Light and Dark stick until changed. The head of each
// page applies the saved choice before it draws, so there is no flash.
const THEMES = [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']];
function savedTheme() { try { return localStorage.getItem('lift-theme') || 'auto'; } catch (e) { return 'auto'; } }
function applyTheme(t) {
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  try { if (t === 'auto') localStorage.removeItem('lift-theme'); else localStorage.setItem('lift-theme', t); } catch (e) {}
  const b = document.getElementById('liftTheme');
  if (b) {
    const name = THEMES.find(x => x[0] === t)[1];
    b.innerHTML = icon(t === 'light' ? 'sun' : t === 'dark' ? 'moon' : 'auto') + ' ' + name;
    b.setAttribute('aria-label', `Appearance: ${name}. Tap to change.`);
  }
}
function nextTheme() {
  const i = THEMES.findIndex(x => x[0] === savedTheme());
  applyTheme(THEMES[(i + 1) % THEMES.length][0]);
}

// Lift top bar: the same bar on every page that sets <body data-page="...">. The Review tab shows
// how many review questions are waiting (GET /api/review/inbox -> {left}), hidden at zero.
const LIFT_PAGES = [['transcribe', '/', 'Transcribe'], ['library', '/library', 'Library'],
  ['results', '/results', 'Results'], ['review', '/review', 'Review']];
function liftBar() {
  const page = document.body.dataset.page;
  if (!page || document.querySelector('.liftbar')) return;
  const bar = document.createElement('header');
  bar.className = 'liftbar';
  bar.innerHTML = `<div class="in"><a class="brand" href="/library" aria-label="Lift: Library">` +
    `<img src="/static/brand/logo-dark.svg" alt="Lift" width="99" height="32"></a><nav aria-label="Pages">` +
    LIFT_PAGES.map(([id, href, name]) => `<a href="${href}"${id === page ? ' aria-current="page"' : ''}>${icon(id)}${name}` +
      (id === 'review' ? ' <span class="count" id="liftReviewCount" hidden></span>' : '') + '</a>').join('') +
    '</nav><div class="tools"><button type="button" class="theme" id="liftTheme"></button>' +
    '<button type="button" class="quit" id="liftQuit">Quit</button></div></div>';
  document.body.prepend(bar);
  applyTheme(savedTheme());
  bar.querySelector('#liftTheme').addEventListener('click', nextTheme);
  bar.querySelector('#liftQuit').addEventListener('click', quitLift);
  fetch('/api/review/inbox').then(r => r.ok ? r.json() : null).then(d => {
    const n = d && d.left, el = document.getElementById('liftReviewCount');
    if (el && n > 0) { el.textContent = n; el.hidden = false; }
  }).catch(() => {});
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', liftBar); else liftBar();

// Quit: stop the app on this Mac, so the next double-click on Lift starts it fresh.
async function quitLift() {
  let r = await fetch('/api/quit', {method: 'POST'}).catch(() => null);
  if (r && r.status === 409) {
    if (!confirm('A transcription is still running. Quit anyway and stop it?')) return;
    r = await fetch('/api/quit?force=true', {method: 'POST'}).catch(() => null);
  }
  if (r && !r.ok) { toast('Lift could not quit.'); return; }
  document.body.innerHTML = '<div class="wrap"><h1>Lift has quit</h1>' +
    '<p class="quiet">Double-click Lift on your Desktop to open it again.</p></div>';
}
