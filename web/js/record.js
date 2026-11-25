// Phoneme recorder: raw PCM (no browser DSP) -> 16-bit mono WAV -> POST /api/voice/<id> (tools/serve.py).
const $ = (id) => document.getElementById(id);
let prompts = [], have = new Set(), cur = 0;
let ctx = null, stream = null, node = null, src = null, chunks = [], recording = false, timer = null, peakHold = 0;

function encodeWav(samples, sr) {
  const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
  const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

function show() {
  const p = prompts[cur];
  $("pos").textContent = `${cur + 1} / ${prompts.length} · ${p.group}${p.example ? " · as in “" + p.example + "”" : ""}`;
  $("ipa").textContent = p.ipa ? `/${p.ipa}/` : "Sentence";
  $("say").textContent = p.say;
  $("how").textContent = p.how;
  $("btn-play").disabled = !have.has(p.id);
  $("status").textContent = have.has(p.id) ? "✓ recorded. Play it back, or record again to replace it." : "";
  $("chips").innerHTML = prompts.map((q, i) =>
    `<span class="chip${have.has(q.id) ? " done" : ""}${i === cur ? " cur" : ""}" data-i="${i}">${q.ipa || "✎" + (i - prompts.findIndex(x => x.group === "sentence") + 1)}</span>`).join("");
}

async function ensureMic() {
  if (stream) return;
  stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } });
  ctx = new AudioContext();
  src = ctx.createMediaStreamSource(stream);
  node = ctx.createScriptProcessor(4096, 1, 1);
  node.onaudioprocess = (e) => {
    const x = e.inputBuffer.getChannelData(0);
    let pk = 0; for (let i = 0; i < x.length; i++) pk = Math.max(pk, Math.abs(x[i]));
    peakHold = Math.max(pk, peakHold * 0.85);
    const m = $("meter"); m.firstElementChild.style.width = Math.min(100, peakHold * 100) + "%";
    m.classList.toggle("clip", peakHold > 0.97);
    if (recording) chunks.push(new Float32Array(x));
  };
  src.connect(node); node.connect(ctx.destination);
}

async function start() {
  try { await ensureMic(); } catch (e) {
    $("status").innerHTML = `<span class="warn">Microphone blocked: ${e.message}. Open this page as http://localhost:8000/record.html in Chrome and allow the mic.</span>`;
    return;
  }
  await ctx.resume();
  chunks = []; recording = true;
  $("btn-rec").classList.add("on"); $("btn-rec").textContent = "■ Stop";
  const secs = prompts[cur].seconds + 1;
  let left = secs;
  $("status").textContent = `Recording… ${left}s (auto-stops)`;
  timer = setInterval(() => { left--; $("status").textContent = `Recording… ${left}s (tap Stop when done)`; if (left <= 0) stop(); }, 1000);
}

async function stop() {
  clearInterval(timer); recording = false;
  $("btn-rec").classList.remove("on"); $("btn-rec").textContent = "● Record";
  const n = chunks.reduce((s, c) => s + c.length, 0), all = new Float32Array(n);
  let o = 0; for (const c of chunks) { all.set(c, o); o += c.length; }
  let pk = 0; for (const v of all) pk = Math.max(pk, Math.abs(v));
  if (n < ctx.sampleRate * 0.5 || pk < 0.01) { $("status").innerHTML = `<span class="warn">Too short or too quiet. Try again, a bit closer.</span>`; return; }
  const id = prompts[cur].id;
  $("status").textContent = "Saving…";
  const r = await fetch(`/api/voice/${id}`, { method: "POST", body: encodeWav(all, ctx.sampleRate) });
  if (!r.ok) { $("status").innerHTML = `<span class="warn">Save failed (${r.status}). Is tools/serve.py running?</span>`; return; }
  have.add(id);
  const clip = pk > 0.97 ? ` <span class="warn">⚠ clipped. Please record again, a bit further away.</span>` : "";
  show();
  $("status").innerHTML = `✓ saved ${(n / ctx.sampleRate).toFixed(1)} s, peak ${(pk * 100).toFixed(0)}%.${clip}`;
  if (!clip && cur < prompts.length - 1) setTimeout(() => { cur++; show(); }, 900);
}

$("btn-rec").onclick = () => (recording ? stop() : start());
$("btn-play").onclick = () => new Audio(`/api/voice/${prompts[cur].id}.wav?t=${Date.now()}`).play();
$("btn-prev").onclick = () => { if (cur > 0 && !recording) { cur--; show(); } };
$("btn-next").onclick = () => { if (cur < prompts.length - 1 && !recording) { cur++; show(); } };
$("chips").onclick = (e) => { const i = e.target.dataset?.i; if (i != null && !recording) { cur = +i; show(); } };

(async () => {
  prompts = (await (await fetch("data/record_script.json")).json()).prompts;
  try { have = new Set((await (await fetch("/api/voice")).json()).have); } catch { /* static server: no API */ }
  cur = Math.max(0, prompts.findIndex(p => !have.has(p.id)));
  show();
})();
