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
