/**
 * lab.js — Live Voice Lab page (DOM, Web Audio, Three.js, canvases).
 * Signal processing + physics live in ./lab_core.js (node-tested by tools/test_lab_core.mjs);
 * physics only from ./physics.js. Badges: colours/curves exact given the model; glow/room artistic.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import * as P from "./physics.js";
import * as L from "./lab_core.js";

const $ = (id) => document.getElementById(id);
const NSEC = P.ORDER;
const VOWEL_ORDER = ["iy", "ih", "ei", "eh", "ae", "ah", "aw", "oa", "oo", "uw", "uh", "er"];
const DEMOS = [
  { id: "sentence", label: "sentence: i · a · u · e · o", seq: ["iy", "ah", "uw", "eh", "oa"] },
  { id: "all", label: "all 12 vowels", seq: VOWEL_ORDER },
  { id: "alt", label: "i ↔ a ↔ u (corners)", seq: ["iy", "ah", "uw", "iy", "ah", "uw"] },
  ...VOWEL_ORDER.map((v) => ({ id: v, label: null, seq: [v] })),
];

const S = { mode: "ideal", illuminant: "D65", group: "women", alpha: 0.35, gateMargin: 12 };
let VOWELS = [];
let refPoints = [];
let idle = null;                  // uniform tube (schwa) — exact colour of the neutral tract
const pipe = new L.LabPipeline(48000, { mode: S.mode, illuminant: S.illuminant, alpha: S.alpha });
let cur = null;                   // latest hop result
let isoDirty = true;
const trail = [];                 // {F1, F2, hex, time}
const history = [];               // {a, areas, rgb, hex}
let histTick = 0;
let recording = false;
const rec = [];                   // {voiced, hex}
let srcKind = null;               // "mic" | "demo" | null
let demoInfo = null;

const status = (msg, cls = "") => { const el = $("status"); el.innerHTML = msg; el.className = "status " + (cls || "muted"); };

// ============================================================================ audio
let ctx = null, cap = null, capKind = "";
let micStream = null, micNode = null, demoNode = null, demoGain = null;
const wavCache = new Map();

async function ensureAudio() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.audioWorklet && window.AudioWorkletNode) {
      try {
        await ctx.audioWorklet.addModule("js/lab_worklet.js");
        cap = new AudioWorkletNode(ctx, "lab-capture", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
        cap.port.onmessage = (e) => onSamples(e.data);
        capKind = "AudioWorklet";
      } catch (e) { console.warn("AudioWorklet unavailable, falling back", e); cap = null; }
    }
    if (!cap) {
      cap = ctx.createScriptProcessor(2048, 1, 1);
      cap.onaudioprocess = (e) => { if (srcKind) onSamples(new Float32Array(e.inputBuffer.getChannelData(0))); };
      capKind = "ScriptProcessor";
    }
    const mute = ctx.createGain();
    mute.gain.value = 0;
    cap.connect(mute); mute.connect(ctx.destination);
    pipe.setSourceRate(ctx.sampleRate);
  }
  if (ctx.state !== "running") await ctx.resume();
}

function stopSources() {
  if (micNode) { try { micNode.disconnect(); } catch { /* ignore */ } micNode = null; }
  if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
  if (demoNode) { demoNode.onended = null; try { demoNode.stop(); } catch { /* ignore */ } try { demoNode.disconnect(); } catch { /* ignore */ } demoNode = null; }
  if (demoGain) { try { demoGain.disconnect(); } catch { /* ignore */ } demoGain = null; }
  srcKind = null; demoInfo = null;
  $("btn-stop").disabled = true;
  $("btn-mic").textContent = "Start microphone";
}

async function startMic() {
  if (srcKind === "mic") { stopSources(); status("Microphone stopped."); return; }
  try {
    await ensureAudio();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error("getUserMedia not available (open the page via http://localhost, not file://)");
    stopSources();
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
    micNode = ctx.createMediaStreamSource(micStream);
    micNode.connect(cap);
    pipe.reset();
    srcKind = "mic";
    $("btn-stop").disabled = false;
    $("btn-mic").textContent = "Stop microphone";
    status(`Microphone live · ${ctx.sampleRate} Hz → 16 kHz (${capKind}) · first ~0.25 s calibrates the noise floor, so stay quiet, then sing a long vowel.`, "live");
  } catch (e) {
    stopSources();
    status(`Microphone unavailable: ${e.message || e}. Use <b>Play demo</b> instead.`, "err");
  }
}

async function loadVowelWav(group, v) {
  const key = `${group}_${v}`;
  if (!wavCache.has(key)) {
    const r = await fetch(`audio/vowel_${key}.wav`);
    if (!r.ok) throw new Error(`audio/vowel_${key}.wav: HTTP ${r.status}`);
    const w = L.parseWav(await r.arrayBuffer());
    if (w.sampleRate !== P.FS) throw new Error("expected 16 kHz WAV");
    wavCache.set(key, w.data);
  }
  return wavCache.get(key);
}

async function playDemo() {
  try {
    await ensureAudio();
    stopSources();
    const demo = DEMOS.find((d) => d.id === $("sel-demo").value) || DEMOS[0];
    const clips = await Promise.all(demo.seq.map((v) => loadVowelWav(S.group, v)));
    const { data, marks } = L.concatWithGaps(clips, 0.35, P.FS, 0.4);
    const buf = ctx.createBuffer(1, data.length, P.FS);
    buf.getChannelData(0).set(data);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = $("chk-loop").checked;
    src.connect(cap);
    demoGain = ctx.createGain();
    demoGain.gain.value = $("chk-hear").checked ? 0.8 : 0;
    src.connect(demoGain); demoGain.connect(ctx.destination);
    pipe.reset();
    src.onended = () => { if (demoNode === src) { stopSources(); status("Demo finished. Play again, or start the microphone."); } };
    src.start();
    demoNode = src; srcKind = "demo";
    demoInfo = { start: ctx.currentTime, dur: buf.duration, marks, seq: demo.seq, group: S.group, loop: src.loop };
    $("btn-stop").disabled = false;
    status(`Demo: bundled ${S.group} vowel WAVs (Rosenberg-excited LPC-16 synthesis of Hillenbrand means) → same pipeline as the mic (${capKind}, ${ctx.sampleRate} Hz → 16 kHz).`, "live");
  } catch (e) {
    stopSources();
    status(`Demo failed: ${e.message || e}`, "err");
  }
}

function onSamples(chunk) {
  if (!srcKind) return;
  const hops = pipe.pushSamples(chunk);
  for (const h of hops) handleHop(h);
}

const hopListeners = [];          // only used by ?autotest
function handleHop(h) {
  cur = h;
  for (const fn of hopListeners) fn(h);
  if (h.updated) {
    isoDirty = true;
    if (h.F1 && h.F2 && h.colour) trail.push({ F1: h.F1, F2: h.F2, hex: h.colour.hex, time: performance.now() });
    if (trail.length > 400) trail.splice(0, trail.length - 400);
    if (++histTick % 6 === 0 && h.colour) {
      history.unshift({ a: h.sm.a, areas: h.areas, rgb: h.colour.rgb, hex: h.colour.hex });
      if (history.length > ROOM_TUBES.length) history.length = ROOM_TUBES.length;
      assignHistory();
    }
  }
  if (recording) rec.push({ voiced: !!(h.voiced && h.colour), hex: h.colour ? h.colour.hex : null });
}

// ============================================================================ settings
function refreshRefs() {
  refPoints = VOWELS.filter((it) => it.group === S.group).map((it) => ({
    F1: it.F1, F2: it.F2, ipa: it.ipa, example: it.example, vowel: it.vowel,
    hex: P.vowelColour(Float64Array.from(it.a), S.mode, S.illuminant).hex,
  }));
  const a0 = new Float64Array(NSEC + 1); a0[0] = 1;   // k = 0: uniform tube (schwa)
  const c = P.vowelColour(a0, S.mode, S.illuminant);
  idle = { a: a0, areas: new Array(NSEC).fill(1), rgb: c.rgb, hex: c.hex };
  for (const hItem of history) { const cc = P.vowelColour(hItem.a, S.mode, S.illuminant); hItem.rgb = cc.rgb; hItem.hex = cc.hex; }
  assignHistory();
}

function fillDemoSelect() {
  const sel = $("sel-demo"), keep = sel.value;
  sel.innerHTML = "";
  for (const d of DEMOS) {
    let label = d.label;
    if (!label) {
      const it = VOWELS.find((x) => x.group === S.group && x.vowel === d.id);
      label = it ? `single: /${it.ipa}/ as in “${it.example}”` : d.id;
    }
    const o = document.createElement("option");
    o.value = d.id; o.textContent = label; sel.appendChild(o);
  }
  if (keep) sel.value = keep;
}

function bindUI() {
  $("btn-mic").onclick = startMic;
  $("btn-demo").onclick = playDemo;
  $("btn-stop").onclick = () => { stopSources(); status("Stopped."); };
  $("sel-mode").onchange = (e) => { S.mode = e.target.value; pipe.setOptions({ mode: S.mode }); if (pipe.last) cur = pipe.last; refreshRefs(); isoDirty = true; };
  $("sel-ill").onchange = (e) => { S.illuminant = e.target.value; pipe.setOptions({ illuminant: S.illuminant }); if (pipe.last) cur = pipe.last; refreshRefs(); isoDirty = true; };
  $("sel-group").onchange = (e) => { S.group = e.target.value; refreshRefs(); fillDemoSelect(); };
  $("rng-alpha").oninput = (e) => { S.alpha = +e.target.value; pipe.setOptions({ alpha: S.alpha }); };
  $("rng-gate").oninput = (e) => { S.gateMargin = +e.target.value; $("gate-val").textContent = S.gateMargin; pipe.gate.set({ marginOnDb: S.gateMargin, marginOffDb: Math.max(2, S.gateMargin - 5) }); };
  $("chk-hear").onchange = (e) => { if (demoGain) demoGain.gain.value = e.target.checked ? 0.8 : 0; };
  $("chk-loop").onchange = (e) => { if (demoNode) { demoNode.loop = e.target.checked; if (demoInfo) demoInfo.loop = e.target.checked; } };
  $("btn-rec").onclick = toggleRec;
  $("btn-clear").onclick = () => { rec.length = 0; $("btn-png").disabled = true; updateRecInfo(); };
  $("btn-png").onclick = downloadPNG;
  $("btn-view-tract").onclick = () => flyTo(VIEWS.tract);
  $("btn-view-room").onclick = () => flyTo(VIEWS.room);
  $("chk-rotate").onchange = (e) => { controls.autoRotate = e.target.checked; };
}

// ============================================================================ 2D helpers
function prep(cv) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  return { g, W: w, H: h };
}
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#999";
const COL = {};
function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// ---------------------------------------------------------------------------- F1–F2 chart
const CH = { f2: [500, 3600], f1: [150, 1250] };
function drawChart() {
  const { g, W, H } = prep($("chart"));
  const l = 52, r = 14, t = 14, b = 40, pw = W - l - r, ph = H - t - b;
  const X = (F2) => l + (CH.f2[1] - F2) / (CH.f2[1] - CH.f2[0]) * pw;
  const Y = (F1) => t + (F1 - CH.f1[0]) / (CH.f1[1] - CH.f1[0]) * ph;
  g.font = "11px " + COL.mono; g.lineWidth = 1;
  for (let f = 500; f <= 3500; f += 500) { g.strokeStyle = COL.line; g.beginPath(); g.moveTo(X(f), t); g.lineTo(X(f), t + ph); g.stroke(); g.fillStyle = COL.muted; g.textAlign = "center"; g.fillText(f, X(f), t + ph + 14); }
  for (let f = 200; f <= 1200; f += 200) { g.strokeStyle = COL.line; g.beginPath(); g.moveTo(l, Y(f)); g.lineTo(l + pw, Y(f)); g.stroke(); g.fillStyle = COL.muted; g.textAlign = "right"; g.fillText(f, l - 6, Y(f) + 4); }
  g.fillStyle = COL.muted; g.textAlign = "center"; g.fillText("F2 (Hz) ←", l + pw / 2, H - 6);
  g.save(); g.translate(13, t + ph / 2); g.rotate(-Math.PI / 2); g.fillText("F1 (Hz) →", 0, 0); g.restore();
  g.save(); g.beginPath(); g.rect(l, t, pw, ph); g.clip();
  // reference vowels
  g.font = "12px " + COL.font;
  for (const p of refPoints) {
    const x = X(p.F2), y = Y(p.F1);
    g.fillStyle = p.hex; g.strokeStyle = "rgba(255,255,255,0.7)";
    g.beginPath(); g.arc(x, y, 7, 0, 2 * Math.PI); g.fill(); g.stroke();
    g.fillStyle = COL.text; g.textAlign = "left";
    g.fillText(`/${p.ipa}/ ${p.example}`, x + 10, y + 4);
  }
  // trail (fades over 3 s)
  const now = performance.now(), life = 3000;
  let prev = null;
  for (const q of trail) {
    const age = now - q.time;
    if (age > life) { prev = null; continue; }
    const a = 1 - age / life, x = X(q.F2), y = Y(q.F1);
    if (prev && q.time - prev.time < 120) { g.strokeStyle = hexA(q.hex, 0.5 * a); g.lineWidth = 2; g.beginPath(); g.moveTo(prev.x, prev.y); g.lineTo(x, y); g.stroke(); }
    g.fillStyle = hexA(q.hex, a); g.beginPath(); g.arc(x, y, 3.2, 0, 2 * Math.PI); g.fill();
    prev = { x, y, time: q.time };
  }
  if (cur && cur.voiced && cur.F1 && cur.F2 && cur.colour) {
    const x = X(cur.F2), y = Y(cur.F1);
    g.strokeStyle = "#fff"; g.lineWidth = 2; g.beginPath(); g.arc(x, y, 11, 0, 2 * Math.PI); g.stroke();
    g.fillStyle = cur.colour.hex; g.beginPath(); g.arc(x, y, 7, 0, 2 * Math.PI); g.fill();
  }
  g.restore();
  g.strokeStyle = COL.line; g.strokeRect(l, t, pw, ph);
}

// ---------------------------------------------------------------------------- isomorphism panel
let specCache = { w: 0, cols: null };
function spectrumColours(n) {
  if (specCache.w === n) return specCache.cols;
  const D = P.getPhysicsData();
  const cols = [];
  for (let i = 0; i < n; i++) {
    const nu = P.NU_MIN + (i + 0.5) / n * P.DNU, wl = P.C_LIGHT / nu * 1e9;
    const j = Math.max(0, Math.min(D.wl.length - 1, Math.round((wl - D.wl[0]) / (D.wl[1] - D.wl[0]))));
    const rgb = P.displayRGB([D.cmf[0][j], D.cmf[1][j], D.cmf[2][j]], 35);
    cols.push(P.toHex(rgb));
  }
  specCache = { w: n, cols };
  return cols;
}

function drawIso() {
  const { g, W, H } = prep($("iso"));
  const l = 50, r = 12, t = 26, b = 58, pw = W - l - r, ph = H - t - b;
  const X = (nu) => l + (nu - P.NU_MIN) / P.DNU * pw;
  g.font = "11px " + COL.mono;
  const it = cur && cur.iso;
  const dB = (v) => 10 * Math.log10(Math.max(v, 1e-9));
  let top = -10;
  if (it) { let m = -200; for (const arr of [it.film, it.tube, it.vowel]) for (let i = 0; i < arr.length; i++) m = Math.max(m, dB(arr[i])); top = Math.min(0, Math.ceil(m / 5) * 5); }
  const bot = top - 40;
  const Y = (v) => t + (top - Math.max(bot, Math.min(top, dB(v)))) / (top - bot) * ph;
  // grid
  for (let d = top; d >= bot; d -= 10) {
    const y = t + (top - d) / (top - bot) * ph;
    g.strokeStyle = COL.line; g.beginPath(); g.moveTo(l, y); g.lineTo(l + pw, y); g.stroke();
    g.fillStyle = COL.muted; g.textAlign = "right"; g.fillText(`${d}`, l - 6, y + 4);
  }
  g.save(); g.translate(12, t + ph / 2); g.rotate(-Math.PI / 2); g.textAlign = "center"; g.fillText("dB (power)", 0, 0); g.restore();
  // spectrum strip
  const cols = spectrumColours(Math.max(2, Math.round(pw)));
  for (let i = 0; i < cols.length; i++) { g.fillStyle = cols[i]; g.fillRect(l + i, t + ph + 2, 1.5, 7); }
  // ticks: nu (THz), lambda (nm), f(nu) (kHz, folded: |D|^2 is even)
  g.textAlign = "center";
  for (let nuT = 400; nuT <= 750; nuT += 50) {
    const nu = nuT * 1e12, x = X(nu);
    g.strokeStyle = COL.line; g.beginPath(); g.moveTo(x, t); g.lineTo(x, t + ph); g.stroke();
    let f = P.fOfNu([nu])[0]; f = Math.min(f, P.FS - f);
    g.fillStyle = COL.text; g.fillText(`${nuT}`, x, t + ph + 21);
    g.fillStyle = COL.muted; g.fillText(`${(f / 1000).toFixed(1)}k`, x, t + ph + 34);
  }
  g.fillStyle = COL.muted; g.textAlign = "left";
  g.fillText("ν (THz)", l, H - 6); g.textAlign = "right"; g.fillText("tube f(ν) in Hz, folded ±f ↑", l + pw, H - 6);
  if (!it) { g.fillStyle = COL.muted; g.textAlign = "center"; g.fillText("waiting for a voiced frame…", l + pw / 2, t + ph / 2); $("iso-read").textContent = "—"; return; }
  // formant images
  g.setLineDash([3, 4]); g.lineWidth = 1;
  for (const [F, lab] of [[cur.F1, "F1"], [cur.F2, "F2"]]) {
    if (!F) continue;
    for (const nu of P.nuImages(F)) {
      const x = X(nu); g.strokeStyle = "rgba(255,255,255,0.35)"; g.beginPath(); g.moveTo(x, t); g.lineTo(x, t + ph); g.stroke();
      g.fillStyle = COL.muted; g.textAlign = "center"; g.fillText(lab, x, t - 4);
    }
  }
  g.setLineDash([]);
  const curve = (arr, style, lw, dash) => {
    g.strokeStyle = style; g.lineWidth = lw; g.setLineDash(dash || []);
    g.beginPath();
    for (let i = 0; i < arr.length; i++) { const x = X(it.nu[i]), y = Y(arr[i]); if (i) g.lineTo(x, y); else g.moveTo(x, y); }
    g.stroke(); g.setLineDash([]);
  };
  g.save(); g.beginPath(); g.rect(l, t, pw, ph); g.clip();
  curve(it.lpc, "rgba(190,180,255,0.35)", 1.2);
  if (S.mode !== "ideal") curve(it.vowel, "rgba(255,181,71,0.75)", 1.4);
  curve(it.film, "#a993ff", 3);
  curve(it.tube, "#ffffff", 1.4, [7, 6]);
  g.restore();
  // legend
  const leg = [["#a993ff", "film T(ν), Abelès", 3, null], ["#ffffff", "tube P, same media", 1.4, [7, 6]], ["rgba(190,180,255,0.6)", "raw LPC |g/A|²", 1.2, null]];
  if (S.mode !== "ideal") leg.push(["rgba(255,181,71,0.9)", "voice tube (finite glottis)", 1.4, null]);
  g.font = "11px " + COL.font; g.textAlign = "left";
  let lx = l + 8;
  for (const [c, txt, lw, dash] of leg) {
    g.strokeStyle = c; g.lineWidth = lw; g.setLineDash(dash || []); g.beginPath(); g.moveTo(lx, 12); g.lineTo(lx + 18, 12); g.stroke(); g.setLineDash([]);
    g.fillStyle = COL.text; g.fillText(txt, lx + 22, 16);
    lx += 30 + g.measureText(txt).width;
  }
  const ok = it.maxDiff < 1e-9;
  let html = `max |T<sub>film</sub> − P<sub>tube</sub>| = <span class="${ok ? "ok" : "warn"}">${it.maxDiff.toExponential(2)}</span> ${ok ? "(identical to rounding error)" : ""}`;
  if (S.mode !== "ideal") html += ` · fidelity loss vs the voice's own tube: max |ΔT| = <span class="warn">${it.maxFidelity.toFixed(3)}</span>`;
  $("iso-read").innerHTML = html;
}

// ---------------------------------------------------------------------------- side panels
function drawAreas() {
  const { g, W, H } = prep($("areas"));
  const areas = cur && cur.areas ? cur.areas : idle.areas;
  const hex = cur && cur.colour ? cur.colour.hex : idle.hex;
  const amax = Math.max(...areas);
  const l = 8, r = 8, pw = W - l - r, mid = H / 2 - 6, hmax = H / 2 - 16;
  const sw = pw / areas.length;
  g.fillStyle = hexA(hex, 0.25 + 0.6 * (cur ? cur.level : 0.2));
  g.strokeStyle = hex; g.lineWidth = 1;
  for (let i = 0; i < areas.length; i++) {
    const hh = Math.max(1, hmax * Math.sqrt(areas[i] / amax));
    g.fillRect(l + i * sw + 1, mid - hh, sw - 2, 2 * hh);
  }
  g.fillStyle = COL.muted; g.font = "10px " + COL.mono;
  g.textAlign = "left"; g.fillText("glottis", l, H - 3);
  g.textAlign = "right"; g.fillText("lips", W - r, H - 3);
  g.textAlign = "center"; g.fillText(`half-height ∝ √A · A_max/A_min = ${(amax / Math.min(...areas)).toFixed(1)}`, W / 2, H - 3);
}

function drawGate() {
  const { g, W, H } = prep($("gate"));
  const lo = -100, hi = 0, l = 6, r = 46, pw = W - l - r;
  const X = (d) => l + (Math.max(lo, Math.min(hi, d)) - lo) / (hi - lo) * pw;
  g.fillStyle = "#141725"; g.fillRect(l, 14, pw, 18);
  if (cur) {
    const gt = cur.gate, ft = cur.feat;
    g.fillStyle = cur.voiced ? COL.ok : "#5a6075"; g.fillRect(l, 14, X(ft.rmsDb) - l, 18);
    const mark = (d, c, lab) => { g.fillStyle = c; g.fillRect(X(d) - 1, 10, 2, 26); g.font = "10px " + COL.mono; g.textAlign = "center"; g.fillText(lab, X(d), 46); };
    mark(gt.floorDb, COL.muted, "floor"); mark(gt.thrOnDb, COL.warn, "open");
    g.beginPath(); g.arc(W - 20, 23, 9, 0, 2 * Math.PI); g.fillStyle = cur.voiced ? COL.ok : "#2a2e3d"; g.fill();
    $("gate-read").textContent = `RMS ${ft.rmsDb.toFixed(1)} dBFS · floor ${gt.floorDb.toFixed(1)} · open > ${gt.thrOnDb.toFixed(1)} · periodicity ${ft.periodicity.toFixed(2)} · ZCR ${ft.zcr.toFixed(2)}${ft.f0 && cur.voiced ? ` · F0 ≈ ${ft.f0.toFixed(0)} Hz` : ""} · ${cur.voiced ? "VOICED" : "silent / unvoiced"}`;
  }
  g.fillStyle = COL.muted; g.font = "10px " + COL.mono; g.textAlign = "left"; g.fillText("-100 dBFS", l, 9); g.textAlign = "right"; g.fillText("0", l + pw, 9);
}

function updateReadout() {
  const sw = $("swatch");
  const c = cur && cur.colour ? cur.colour : null;
  const lvl = cur ? cur.level : 0;
  sw.style.backgroundColor = c ? c.hex : idle.hex;
  sw.style.opacity = (0.25 + 0.75 * lvl).toFixed(3);
  if (!c) { $("readout").textContent = `idle: uniform tube (schwa)\nhex ${idle.hex}\nmode ${S.mode} · ${S.illuminant}`; return; }
  const f = (x) => (x ? `${x.toFixed(0)} Hz` : "—");
  $("readout").textContent =
    `F1 ${f(cur.F1)}   F2 ${f(cur.F2)}\n` +
    `hex ${c.hex}\n` +
    `Lab ${c.Lab.map((v) => v.toFixed(1)).join(", ")}\n` +
    `film Y = ${c.XYZ[1].toFixed(2)} (of 100)\n` +
    `mode ${S.mode} · ${S.illuminant}${cur.voiced ? "" : " · (held)"}`;
}

// ---------------------------------------------------------------------------- paint your sentence
function toggleRec() {
  recording = !recording;
  const b = $("btn-rec");
  b.textContent = recording ? "■ Stop recording" : "● Record";
  b.classList.toggle("rec-on", recording);
  if (!recording) $("btn-png").disabled = rec.length === 0;
  updateRecInfo();
}
function updateRecInfo() {
  const n = rec.length, v = rec.filter((q) => q.voiced).length;
  $("rec-info").textContent = n ? `${(n * L.HOP / P.FS).toFixed(1)} s recorded · ${v} voiced frames (${(100 * v / n).toFixed(0)} %)${recording ? " · recording…" : ""}`
    : (recording ? "recording… speak or play the demo" : "Records the colour of every voiced 16 ms frame. Silent frames leave dark gaps.");
}
function paintStrip(g, x0, y0, w, h, recs) {
  g.fillStyle = COL.bg; g.fillRect(x0, y0, w, h);
  if (!recs.length) return;
  const cw = w / recs.length;
  for (let i = 0; i < recs.length; i++) if (recs[i].voiced) { g.fillStyle = recs[i].hex; g.fillRect(x0 + i * cw, y0, cw + 0.6, h); }
}
let lastRecLen = -1;
function drawStrip() {
  if (rec.length === lastRecLen && !recording) return;
  lastRecLen = rec.length;
  const { g, W, H } = prep($("strip"));
  const minCol = 3, n = rec.length;
  const w = Math.min(W, Math.max(n * minCol, 1));
  paintStrip(g, 0, 0, w, H, rec);
  if (!n) { g.fillStyle = COL.muted; g.font = "12px " + COL.font; g.textAlign = "center"; g.fillText("press ● Record, then speak or sing (or play the demo)", W / 2, H / 2 + 4); }
  if (recording) { g.fillStyle = COL.bad; g.fillRect(Math.min(W - 2, w), 0, 2, H); }
  if (recording && n % 8 === 0) updateRecInfo();
}
function renderPNGCanvas() {
  const n = rec.length, col = Math.max(2, Math.min(8, Math.round(2400 / n))), pad = 24;
  const sw = n * col, W = Math.max(sw + 2 * pad, 960), H = 210;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const g = cv.getContext("2d");
  g.fillStyle = COL.bg; g.fillRect(0, 0, W, H);
  g.fillStyle = COL.text; g.font = "600 15px " + COL.font; g.textAlign = "left";
  g.fillText("Paint your sentence: the colour of every voiced 16 ms frame", pad, 24);
  paintStrip(g, pad, 38, sw, 110, rec);
  g.strokeStyle = COL.line; g.strokeRect(pad - 0.5, 37.5, sw + 1, 111);
  g.fillStyle = COL.muted; g.font = "11px " + COL.mono; g.textAlign = "center";
  const hopsPerSec = P.FS / L.HOP;
  for (let s = 0; s * hopsPerSec <= n; s += (n > 1200 ? 5 : 1)) { const x = pad + s * hopsPerSec * col; g.fillRect(x, 150, 1, 6); g.fillText(`${s}s`, x, 168); }
  g.textAlign = "left";
  g.fillText(`film transmittance colour · mode ${S.mode} · illuminant ${S.illuminant} · LPC-16 at 16 kHz · display exposure-normalised (artistic) · dark = silence`, pad, 192);
  g.fillText("DA321 · Vowels That Shine, Butterflies That Speak · Live Voice Lab", pad, 205);
  return cv;
}
function downloadPNG() {
  if (!rec.length) return;
  renderPNGCanvas().toBlob((blob) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `sentence_colours_${S.mode}_${S.illuminant}.png`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }, "image/png");
}

// ============================================================================ 3D: neon tube lights in a room
const stage = $("stage");
const renderer = new THREE.WebGLRenderer({ canvas: $("three"), antialias: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
renderer.toneMapping = THREE.NoToneMapping;
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x020206);
const camera = new THREE.PerspectiveCamera(48, 1, 0.05, 100);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.maxPolarAngle = Math.PI * 0.495; controls.minDistance = 1.2; controls.maxDistance = 16;
controls.autoRotateSpeed = 0.6;
const VIEWS = {
  tract: { pos: new THREE.Vector3(0.3, 1.9, 4.3), target: new THREE.Vector3(0.05, 1.5, 0) },
  room: { pos: new THREE.Vector3(0.0, 3.1, 10.5), target: new THREE.Vector3(0, 2.2, -0.5) },
};
camera.position.copy(VIEWS.room.pos); controls.target.copy(VIEWS.room.target);
let fly = null;
function flyTo(v) { fly = { p0: camera.position.clone(), t0: controls.target.clone(), v, start: performance.now() }; }

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.95, 0.55, 0.1);
composer.addPass(bloom);
composer.addPass(new OutputPass());

scene.add(new THREE.HemisphereLight(0x8890b0, 0x050508, 0.12));
// room (artistic)
const RX = 6, RY = 5, RZ = 5;
const wallMat = new THREE.MeshStandardMaterial({ color: 0x14161f, roughness: 0.88, metalness: 0.0 });
const addPlane = (w, h, pos, rot) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), wallMat); m.position.set(...pos); m.rotation.set(...rot); scene.add(m); return m; };
addPlane(2 * RX, RY, [0, RY / 2, -RZ], [0, 0, 0]);
addPlane(2 * RZ, RY, [-RX, RY / 2, 0], [0, Math.PI / 2, 0]);
addPlane(2 * RZ, RY, [RX, RY / 2, 0], [0, -Math.PI / 2, 0]);
addPlane(2 * RX, 2 * RZ, [0, RY, 0], [Math.PI / 2, 0, 0]);
const floor = new THREE.Mesh(new THREE.PlaneGeometry(2 * RX, 2 * RZ),
  new THREE.MeshStandardMaterial({ color: 0x08090e, roughness: 0.3, metalness: 0.6, transparent: true, opacity: 0.84 }));
floor.rotation.x = -Math.PI / 2; floor.renderOrder = 1; scene.add(floor);
const mirror = new THREE.Group(); mirror.scale.y = -1; scene.add(mirror);   // fake floor reflection (artistic)

const WHITE = new THREE.Color(1, 1, 1);
const smooth01 = (x) => x * x * (3 - 2 * x);

/** Radius profile along the tube: piecewise-constant sections (Kelly–Lochbaum) with short smooth junctions. */
function radiiFromLogAreas(logA, rings, rMax, rMin) {
  let lmax = -Infinity;
  for (const v of logA) lmax = Math.max(lmax, v);
  const n = logA.length, out = new Float32Array(rings), w = 0.15;
  const rad = (i) => Math.max(rMin, rMax * Math.exp(0.5 * (logA[i] - lmax)));   // r ∝ √A
  for (let i = 0; i < rings; i++) {
    const s = i / (rings - 1) * n, idx = Math.min(n - 1, Math.floor(s)), fr = s - idx;
    let r = rad(idx);
    if (fr > 1 - w && idx < n - 1) r += (rad(idx + 1) - r) * smooth01((fr - (1 - w)) / (2 * w));
    else if (fr < w && idx > 0) r = rad(idx - 1) + (r - rad(idx - 1)) * smooth01(0.5 + fr / (2 * w));
    out[i] = r;
  }
  return out;
}

class TubeLight {
  constructor(curve, { rMax = 0.3, rMinFrac = 0.06, perSection = 8, radial = 24, light = 1.0, lightDist = 7 } = {}) {
    this.rings = NSEC * perSection + 1; this.radial = radial; this.rMax = rMax; this.rMin = rMax * rMinFrac;
    const fr = curve.computeFrenetFrames(this.rings - 1, false);
    this.P = []; this.N = fr.normals; this.B = fr.binormals;
    for (let i = 0; i < this.rings; i++) this.P.push(curve.getPointAt(i / (this.rings - 1)));
    this.gOuter = this._geom(); this.gCore = this._geom();
    const add = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide };
    this.mOuter = new THREE.MeshBasicMaterial({ ...add, opacity: 0.55 });
    this.mCore = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
    this.mmOuter = new THREE.MeshBasicMaterial({ ...add, opacity: 0.18 });
    this.mmCore = new THREE.MeshBasicMaterial({ ...add, opacity: 0.35 });
    this.meshes = [new THREE.Mesh(this.gOuter, this.mOuter), new THREE.Mesh(this.gCore, this.mCore)];
    this.mirrors = [new THREE.Mesh(this.gOuter, this.mmOuter), new THREE.Mesh(this.gCore, this.mmCore)];
    for (const m of [...this.meshes, ...this.mirrors]) m.frustumCulled = false;
    for (const m of this.mirrors) m.renderOrder = 0;   // below the floor: drawn first, then the floor (1)
    for (const m of this.meshes) m.renderOrder = 2;    // above the floor: drawn after it, never dimmed by it
    scene.add(...this.meshes); mirror.add(...this.mirrors);
    this.light = new THREE.PointLight(0xffffff, 0, lightDist, 1.5);
    this.light.position.copy(curve.getPointAt(0.5));
    this.lightBase = light;
    scene.add(this.light);
    this.logA = null; this.target = null; this.col = new THREE.Color(); this.colTarget = new THREE.Color();
  }
  _geom() {
    const R = this.rings, C = this.radial, g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(R * C * 3), 3).setUsage(THREE.DynamicDrawUsage));
    const idx = [];
    for (let i = 0; i < R - 1; i++) for (let j = 0; j < C; j++) {
      const a = i * C + j, b = i * C + (j + 1) % C, c = (i + 1) * C + j, d = (i + 1) * C + (j + 1) % C;
      idx.push(a, c, b, b, c, d);
    }
    g.setIndex(idx);
    return g;
  }
  setTarget(areas, rgb) {
    this.target = areas.map((a) => Math.log(Math.max(a, 1e-9)));
    if (!this.logA) this.logA = this.target.slice();
    this.colTarget.setRGB(rgb[0], rgb[1], rgb[2], THREE.SRGBColorSpace);
  }
  update(dt, intensity) {
    if (!this.target) return;
    const k = 1 - Math.exp(-dt * 14);   // display easing (artistic)
    for (let i = 0; i < this.logA.length; i++) this.logA[i] += (this.target[i] - this.logA[i]) * k;
    this.col.lerp(this.colTarget, 1 - Math.exp(-dt * 18));
    const r = radiiFromLogAreas(this.logA, this.rings, this.rMax, this.rMin);
    this._write(this.gOuter, r, 1.0); this._write(this.gCore, r, 0.42);
    this.mOuter.color.copy(this.col).multiplyScalar(1.3 * intensity);
    this.mCore.color.copy(this.col).lerp(WHITE, 0.35).multiplyScalar(2.4 * intensity);
    this.mmOuter.color.copy(this.col).multiplyScalar(0.8 * intensity);
    this.mmCore.color.copy(this.col).multiplyScalar(1.2 * intensity);
    this.light.color.copy(this.col);
    this.light.intensity = this.lightBase * 14 * intensity;   // r160 physical light units
  }
  _write(geo, radii, scale) {
    const pos = geo.attributes.position.array, C = this.radial;
    for (let i = 0; i < this.rings; i++) {
      const p = this.P[i], n = this.N[i], b = this.B[i], r = radii[i] * scale;
      for (let j = 0; j < C; j++) {
        const th = 2 * Math.PI * j / C, cs = Math.cos(th) * r, sn = Math.sin(th) * r, o = 3 * (i * C + j);
        pos[o] = p.x + n.x * cs + b.x * sn; pos[o + 1] = p.y + n.y * cs + b.y * sn; pos[o + 2] = p.z + n.z * cs + b.z * sn;
      }
    }
    geo.attributes.position.needsUpdate = true;
  }
}

// hero: the vocal tract (pharynx up, bend, oral cavity forward) — path shape artistic, profile exact
const tractCurve = new THREE.CatmullRomCurve3([
  new THREE.Vector3(-0.8, 0.55, 0), new THREE.Vector3(-0.8, 1.2, 0), new THREE.Vector3(-0.78, 1.75, 0),
  new THREE.Vector3(-0.58, 2.2, 0), new THREE.Vector3(-0.15, 2.42, 0), new THREE.Vector3(0.45, 2.46, 0), new THREE.Vector3(1.05, 2.45, 0),
], false, "centripetal");
const hero = new TubeLight(tractCurve, { rMax: 0.36, rMinFrac: 0.07, perSection: 10, radial: 32, light: 1.6, lightDist: 9 });
hero.light.position.set(0, 1.6, 0.6);

function makeLabel(text) {
  const cv = document.createElement("canvas"); cv.width = 256; cv.height = 64;
  const g = cv.getContext("2d"); g.font = "28px Segoe UI, sans-serif"; g.fillStyle = "rgba(200,205,225,0.85)"; g.textAlign = "center"; g.fillText(text, 128, 42);
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  s.scale.set(0.8, 0.2, 1); scene.add(s); return s;
}
makeLabel("glottis").position.set(-0.8, 0.25, 0);
makeLabel("lips").position.set(1.45, 2.45, 0);

// the room: history tubes (newest first), glottis → lips along each tube
const ROOM_TUBES = [
  [[-4.2, 2.6, -4.85], [4.2, 2.6, -4.85]], [[-4.2, 1.35, -4.85], [4.2, 1.35, -4.85]], [[-4.2, 3.85, -4.85], [4.2, 3.85, -4.85]],
  [[-5.85, 1.9, -3.6], [-5.85, 1.9, 3.6]], [[5.85, 1.9, -3.6], [5.85, 1.9, 3.6]],
  [[-5.85, 3.5, -3.6], [-5.85, 3.5, 3.6]], [[5.85, 3.5, -3.6], [5.85, 3.5, 3.6]],
  [[-2.4, 4.85, -3.8], [-2.4, 4.85, 3.8]], [[2.4, 4.85, -3.8], [2.4, 4.85, 3.8]],
];
const roomTubes = ROOM_TUBES.map(([a, b]) => new TubeLight(new THREE.LineCurve3(new THREE.Vector3(...a), new THREE.Vector3(...b)),
  { rMax: 0.15, rMinFrac: 0.1, perSection: 4, radial: 16, light: 0.7, lightDist: 6 }));
for (const t of roomTubes) {   // pull each light slightly into the room so it lights the floor
  const p = t.light.position; p.set(p.x * 0.9, p.y * 0.9, p.z * 0.9);
}
function assignHistory() {
  for (let i = 0; i < roomTubes.length; i++) {
    const h = history[i] || idle;
    if (h) roomTubes[i].setTarget(h.areas, h.rgb);
  }
}

function resize3D() {
  const w = stage.clientWidth, h = stage.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false); composer.setSize(w, h); bloom.resolution.set(w, h);
  camera.aspect = w / h; camera.updateProjectionMatrix();
}
new ResizeObserver(resize3D).observe(stage);
window.addEventListener("resize", () => { isoDirty = true; lastRecLen = -1; });

// ============================================================================ main loop
let lastT = performance.now();
function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - lastT) / 1000); lastT = now;
  if (!idle) return;
  // 3D
  const level = cur ? cur.level : 0;
  if (cur && cur.areas && cur.colour) hero.setTarget(cur.areas, cur.colour.rgb);
  else hero.setTarget(idle.areas, idle.rgb);
  hero.update(dt, 0.14 + 0.86 * level);
  for (let i = 0; i < roomTubes.length; i++) roomTubes[i].update(dt, (history[i] ? 0.18 + 0.82 * level : 0.08) * (1 - 0.05 * i));
  if (fly) {
    const u = Math.min(1, (now - fly.start) / 900), e = smooth01(u);
    camera.position.lerpVectors(fly.p0, fly.v.pos, e); controls.target.lerpVectors(fly.t0, fly.v.target, e);
    if (u >= 1) fly = null;
  }
  controls.update();
  composer.render();
  // 2D
  drawChart();
  if (isoDirty) { drawIso(); isoDirty = false; }
  drawAreas(); drawGate(); updateReadout(); drawStrip();
  // demo: which vowel is playing now
  if (srcKind === "demo" && demoInfo && ctx) {
    let tt = ctx.currentTime - demoInfo.start;
    if (demoInfo.loop) tt %= demoInfo.dur;
    const i = demoInfo.marks.findIndex(([a, b]) => tt >= a && tt <= b);
    const note = $("stage-note");
    if (i >= 0) { const it = VOWELS.find((x) => x.group === demoInfo.group && x.vowel === demoInfo.seq[i]); note.textContent = it ? `demo: /${it.ipa}/ as in “${it.example}” (${demoInfo.group})` : ""; }
    else note.textContent = "demo: (gap: silence)";
  } else $("stage-note").textContent = "drag to orbit · scroll to zoom";
}

// ============================================================================ boot
async function boot() {
  COL.line = css("--line"); COL.muted = css("--muted"); COL.text = css("--text"); COL.bg = css("--bg");
  COL.ok = css("--ok"); COL.warn = css("--warn"); COL.bad = css("--bad"); COL.mono = css("--mono"); COL.font = css("--font");
  try {
    await P.loadPhysicsData("data/");
    const r = await fetch("data/vowels.json");
    if (!r.ok) throw new Error(`vowels.json: HTTP ${r.status}`);
    VOWELS = (await r.json()).items;
  } catch (e) {
    status(`Could not load data (${e.message}). Serve the folder: <code>python -m http.server 8000 --directory web</code>.`, "err");
    return;
  }
  S.group = $("sel-group").value;
  refreshRefs(); fillDemoSelect(); bindUI(); resize3D();
  requestAnimationFrame(frame);
  if (new URLSearchParams(location.search).has("autotest")) {   // headless self-test only; no effect otherwise
    const m = await import("./lab_autotest.js");
    m.runAutotest({
      $, S, VOWELS, hero, hopListeners, rec, playDemo, toggleRec, renderPNGCanvas,
      getCur: () => cur, getSrcKind: () => srcKind, isRecording: () => recording, getCtx: () => ctx, getCapKind: () => capKind,
      redrawStrip: () => { lastRecLen = -1; drawStrip(); },
      selectDemo: (group, id) => { $("sel-group").value = group; $("sel-group").dispatchEvent(new Event("change")); $("sel-demo").value = id; },
    });
  }
}
boot();
