// One Library song (GET /api/library/<id>, app/catalog.py): the chart's pages as images, the recording
// the match used (or its sax-only stem), the answer key as soft tones, and the match facts.

const songId = decodeURIComponent(location.pathname.split('/').pop());
const api = `/api/library/${encodeURIComponent(songId)}`;
const audio = $('#audio');
let clip = null;
const USE = {training: 'In training: a model learned from this song', benchmark: 'Benchmark: held out, used only to score the model'};
const AUDIT = {low: 'Low', medium: 'Medium', high: 'High'};
const pct = v => v == null ? '–' : `${Math.round(100 * v)}%`;
const clockOf = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

function stat(k, v) { return `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`; }

async function main() {
  const r = await fetch(api);
  if (!r.ok) { $('#title').textContent = 'This song isn’t in the Library'; return; }
  const s = await r.json();
  document.title = `${s.title} · Saxscribe`;
  $('#title').textContent = s.title;
  $('#crumb').textContent = `› ${s.player || ''}`;
  $('#sub').textContent = [s.player, s.year, HORN_NAMES[s.horn], s.played_by && `played by ${s.played_by}`].filter(Boolean).join(' · ');
  $('#openPdf').href = `${api}/pdf`;
  // the play-along on the engraved answer key needs both the key and the record
  if (s.has_key && s.has_audio) { $('#playAlong').href = `${location.pathname.replace(/\/$/, '')}/play`; $('#playAlong').hidden = false; }
  else { $('#noPlay').textContent = s.has_key ? 'No recording to play along with' : 'No answer key to play along with'; $('#noPlay').hidden = false; }

  // the chart, page by page
  const box = $('#pages');
  if (!s.pages) box.innerHTML = `<p class="quiet card">${esc(s.pdf_error || 'This PDF has no pages to show.')}</p>`;
  for (let n = 1; n <= s.pages; n++) {
    const img = el('img', {src: `${api}/page/${n}`, alt: `Page ${n} of ${s.pages}`, loading: n > 2 ? 'lazy' : 'eager'});
    const fig = el('figure', {class: 'page'}); fig.append(img, el('figcaption', {class: 'quiet small'}, `Page ${n} of ${s.pages}`));
    box.append(fig);
  }

  // the recording
  if (s.has_audio) {
    audio.src = `${api}/audio/record`;
    $('#whichField').hidden = !s.has_stem;
    if (s.has_stem) segment($('#which'), v => {
      const t = audio.currentTime, playing = !audio.paused;
      audio.src = `${api}/audio/${v}`;
      audio.addEventListener('loadedmetadata', () => { audio.currentTime = t; setSpeed(); if (playing) audio.play(); }, {once: true});
    });
    $('#keyLabel').hidden = !s.has_key;
    // just the transcribed solo by default, with a few seconds either side; Full track plays it all
    clip = soloClip(audio, s.clip);
    if (s.clip) {
      $('#clipNote').textContent = `Solo ${clipLabel(s.clip)}`;
      segment($('#clipSel'), v => clip.set(v === 'solo'));
      audio.addEventListener('loadedmetadata', () => {
        const show = clip.worth(audio.duration);
        $('#clipField').hidden = !show;
        if (!show) clip.set(false);
      }, {once: true});
    }
  } else {
    audio.hidden = true; $('#noAudio').hidden = false;
  }

  // the match facts
  const m = s.match || {};
  $('#stats').innerHTML = stat('Key heard', pct(s.heard)) + stat('Sax covered', pct(s.coverage)) +
    stat('Page-reading risk', AUDIT[s.audit] || '–');
  const facts = [
    ['Status', '<span class="chip key">Matched</span>' + (s.use ? ` <span class="chip">${s.use === 'training' ? 'In training' : 'Benchmark'}</span>` : '')],
    ['Record', esc(s.record || '–')],
    s.book ? ['Book', esc(s.book)] : null,
    ['Horn', esc(HORN_NAMES[s.horn] || 'not set')],
    ['Chart', esc(s.kind_name)],
    s.use ? ['Model use', esc(USE[s.use])] : null,
    m.length_s ? ['Length', clockOf(m.length_s)] : null,
    m.reason ? ['Match check', esc(m.reason)] : null,
    m.austin ? ['Your verdict', esc(m.austin)] : null,
  ].filter(Boolean);
  $('#facts').innerHTML = facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}

function el(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}

function setSpeed() { audio.playbackRate = Number($('#speed').value); audio.preservesPitch = true; audio.webkitPreservesPitch = true; }
$('#speed').addEventListener('change', setSpeed);

// The answer key as soft sine tones, scheduled against the recording's clock (and its speed).
let actx = null, notes = null, timer = null, voices = [];
function stopTones() { clearInterval(timer); timer = null; voices.forEach(v => { try { v.stop(); } catch (_) {} }); voices = []; }
async function startTones() {
  stopTones();
  if (!$('#keyAlong').checked || audio.paused) return;
  if (!notes) { try { notes = (await (await fetch(`${api}/key`)).json()).notes || []; } catch (_) { notes = []; } }
  actx = actx || new (window.AudioContext || window.webkitAudioContext)();
  if (actx.state === 'suspended') await actx.resume();
  let next = notes.findIndex(n => n.offset > audio.currentTime);
  if (next < 0) return;
  const tick = () => {
    const now = audio.currentTime, rate = audio.playbackRate || 1, ahead = now + 0.6 * rate;
    while (next < notes.length && notes[next].onset < ahead) {
      const n = notes[next++];
      const t0 = actx.currentTime + Math.max(0, (n.onset - now) / rate), t1 = actx.currentTime + Math.max(0.05, (n.offset - now) / rate);
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = 'sine'; o.frequency.value = 440 * Math.pow(2, (n.pitch - 69) / 12);
      g.gain.setValueAtTime(0, t0); g.gain.linearRampToValueAtTime(0.12, t0 + 0.02);
      g.gain.setValueAtTime(0.12, Math.max(t0 + 0.02, t1 - 0.04)); g.gain.linearRampToValueAtTime(0, t1);
      o.connect(g).connect(actx.destination); o.start(t0); o.stop(t1 + 0.02);
      voices.push(o); o.onended = () => { voices = voices.filter(v => v !== o); };
    }
  };
  tick(); timer = setInterval(tick, 200);
}
for (const ev of ['play', 'seeked', 'ratechange']) audio.addEventListener(ev, startTones);
for (const ev of ['pause', 'ended', 'emptied']) audio.addEventListener(ev, stopTones);
$('#keyAlong').addEventListener('change', startTones);

main();
