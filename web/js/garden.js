/**
 * garden.js — Butterfly Garden app (UI + scene wiring). Pure logic lives in garden_core.js, Three.js scene parts in
 * garden_scene.js, physics only in physics.js (CONTRACT §6/§9).
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import * as P from "./physics.js";
import * as G from "./garden_core.js";
import { makeButterflyMesh, writeLUT, buildGarden, makeRing, LUT_SIZE } from "./garden_scene.js";
import { runAutotest } from "./garden_autotest.js"; // side-effect free; runs only for garden.html?autotest

const $ = (id) => document.getElementById(id);
const ANGLES = Array.from({ length: LUT_SIZE }, (_, i) => i);
const nextFrame = () => new Promise((r) => setTimeout(r, 0));
const fmt = (x, k = 0) => (x == null || !Number.isFinite(x) ? "—" : x.toFixed(k));

const S = {
  butterflies: [], selected: null, ctx: null, src: null, singing: null, designer: null, uid: 0,
  vowels: null, atlas: null, presets: null, evoRng: null, autoTimer: null, refreshToken: 0,
};

// ----------------------------------------------------------------------------- settings
function cfg() {
  const mats = [...document.querySelectorAll("#matBox .chip.on")].map((c) => c.dataset.m);
  return {
    seed: $("seed").value.trim() || "0", count: +$("count").value, layers: +$("layers").value, mode: $("mode").value,
    materials: mats.length ? mats : null, thick: $("thick").value, scale: $("thick").value === "goup" ? 1 : +$("scale").value,
    ill: $("ill").value, qty: $("qty").value, ovOn: $("ovOn").checked, ov: +$("ov").value,
    sigma: +$("sigma").value, evoLayers: $("evoLayers").checked,
  };
}

// ----------------------------------------------------------------------------- three.js setup
const canvas = $("gl");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 200);
camera.position.set(0, 3.0, 10.5);
const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 2.0, 0);
controls.enableDamping = true;
controls.minDistance = 2; controls.maxDistance = 26; controls.maxPolarAngle = 1.52;
const garden = buildGarden(scene, G.makeRng("garden-scenery"));
const ring = makeRing();
scene.add(ring);

function resize() {
  const r = $("stage").getBoundingClientRect();
  const w = Math.max(50, r.width), h = Math.max(50, r.height);
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe($("stage"));

// ----------------------------------------------------------------------------- butterflies
function flightParams(rng, tight = null) {
  if (tight) {
    return { c: new THREE.Vector3(tight.x + rng.uniform(-1, 1), rng.uniform(1.6, 2.8), tight.z + rng.uniform(-1, 1)),
      A: new THREE.Vector3(rng.uniform(0.6, 1.4), rng.uniform(0.2, 0.5), rng.uniform(0.6, 1.4)),
      W: new THREE.Vector3(rng.uniform(0.25, 0.5), rng.uniform(0.4, 0.9), rng.uniform(0.25, 0.5)),
      Ph: new THREE.Vector3(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)) };
  }
  return { c: new THREE.Vector3(rng.uniform(-3.5, 3.5), rng.uniform(1.5, 3.0), rng.uniform(-3.5, 3.0)),
    A: new THREE.Vector3(rng.uniform(1.5, 3.5), rng.uniform(0.3, 0.9), rng.uniform(1.5, 3.5)),
    W: new THREE.Vector3(rng.uniform(0.12, 0.3), rng.uniform(0.3, 0.8), rng.uniform(0.12, 0.3)),
    Ph: new THREE.Vector3(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)) };
}

function addButterfly({ name, kind, n, d, label, source = "", mode = "realizable", goupScaled = true, tight = null, rng = null }) {
  const id = ++S.uid;
  const r = rng || G.makeRng(`fly:${id}:${name}`);
  const mesh = makeButterflyMesh(id);
  mesh.group.scale.setScalar(0.55);
  scene.add(mesh.group);
  const b = { id, name, kind, label, source, mode, n: Float64Array.from(n), d: Float64Array.from(d), goupScaled, mesh,
    flight: flightParams(r, tight), t: r.uniform(0, 100), flapF: r.uniform(2.0, 3.4), f0: Math.round(r.uniform(110, 230)),
    lineage: [], hex0: "#000000", Lab0: [0, 0, 0], speakUntil: 0 };
  for (const o of [...mesh.wings, mesh.body]) o.userData.b = b;
  mesh.group.traverse((o) => { if (o.userData.pickable) o.userData.b = b; });
  S.butterflies.push(b);
  return b;
}

function removeButterfly(b) {
  scene.remove(b.mesh.group);
  b.mesh.material.dispose(); b.mesh.lut.dispose(); b.mesh.lut2.dispose();
  S.butterflies = S.butterflies.filter((x) => x !== b);
  if (S.selected === b) select(null);
}

/** Exact wing colour: LUT of display RGB vs θ (TMM) + colour at normal incidence. */
function refreshColour(b) {
  const c = cfg();
  const rgb = P.buildLUT(b.n, b.d, c.qty, c.ill, ANGLES);
  writeLUT(b.mesh.lut, rgb);
  writeLUT(b.mesh.lut2, rgb);
  b.mesh.material.uniforms.uMix.value = 0;
  const col = P.filmColour(b.n, b.d, 0, c.ill, c.qty);
  b.hex0 = col.hex; b.Lab0 = col.Lab; b.hexAbs = P.toHex(col.rgbAbs);
}

async function refreshAll() {
  const token = ++S.refreshToken;
  for (const b of [...S.butterflies]) {
    if (token !== S.refreshToken) return;
    if (S.singing && S.singing.b === b) continue;
    refreshColour(b);
    await nextFrame();
  }
  if (S.selected) showInfo(S.selected);
}

function regrow() {
  const c = cfg();
  for (const b of S.butterflies.filter((x) => x.kind === "random")) removeButterfly(b);
  const rng = G.makeRng(`${c.seed}|${c.layers}|${c.mode}`);
  for (let i = 0; i < c.count; i++) {
    const n = G.randomStack(rng, c.layers, c.mode, { materials: c.materials });
    addButterfly({ name: `Garden #${i + 1}`, kind: "random", n, d: G.goupD(n, c.scale), mode: c.mode,
      label: c.mode === "ideal" ? "ideal n (not realizable)" : c.mode === "materials" ? "material palette" : "realizable",
      source: `seed "${c.seed}"`, rng: rng.fork(`f${i}`) });
  }
  return refreshAll();
}

function isExactThickness(b) { return G.isGoupillaud(b.n, b.d); }

// ----------------------------------------------------------------------------- picking & audio
const ray = new THREE.Raycaster();
let downXY = null;
canvas.addEventListener("pointerdown", (e) => { downXY = [e.clientX, e.clientY]; });
canvas.addEventListener("pointerup", (e) => {
  if (!downXY || Math.hypot(e.clientX - downXY[0], e.clientY - downXY[1]) > 6) return;
  pickAt(e.clientX, e.clientY);
});
/** Raycast click at client coordinates → select + speak. Returns the butterfly hit (or null). */
function pickAt(clientX, clientY) {
  const r = canvas.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1), camera);
  const objs = [];
  for (const b of S.butterflies) b.mesh.group.traverse((o) => { if (o.userData.pickable) objs.push(o); });
  const hit = ray.intersectObjects(objs, false)[0];
  if (!hit) return null;
  const b = hit.object.userData.b;
  select(b); speak(b);
  return b;
}

function audioCtx() {
  if (!S.ctx) S.ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (S.ctx.state === "suspended") S.ctx.resume();
  return S.ctx;
}
function play(buf, when = 0) {
  const ctx = audioCtx();
  if (S.src) { try { S.src.stop(); } catch (_) { /* already stopped */ } }
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const g = ctx.createGain(); g.gain.value = 0.8;
  src.connect(g).connect(ctx.destination);
  src.start(when || ctx.currentTime + 0.02);
  S.src = src;
  return src;
}

const _n = new THREE.Vector3(), _v = new THREE.Vector3();
/** Physical viewing angle of the (unbent) right wing w.r.t. the camera, or the fixed override. */
function currentTheta(b) {
  const c = cfg();
  if (c.ovOn) return c.ov;
  b.mesh.wings[0].updateWorldMatrix(true, false);
  _n.set(0, 1, 0).transformDirection(b.mesh.wings[0].matrixWorld);
  _v.copy(camera.position).sub(b.mesh.group.position).normalize();
  return Math.round(10 * THREE.MathUtils.radToDeg(Math.acos(Math.min(1, Math.abs(_n.dot(_v)))))) / 10;
}

function speak(b, thetaForce = null) {
  if (!b) return;
  if (S.singing) stopSinging();
  const th = thetaForce == null ? currentTheta(b) : thetaForce;
  const v = G.voiceOf(b.n, b.d, th);
  const buf = P.filmVoiceBuffer(audioCtx(), v.a, v.gain, b.f0, 1.2);
  play(buf);
  S.lastSpeak = { b, buf, v, theta: th };
  b.speakUntil = performance.now() + 1200;
  showInfo(b, th, v);
}

// ----------------------------------------------------------------------------- info panel
function select(b) {
  S.butterflies.forEach((x) => { x.mesh.material.uniforms.uSel.value = 0; });
  S.selected = b;
  ring.visible = !!b;
  $("infoEmpty").classList.toggle("hidden", !!b);
  $("infoBody").classList.toggle("hidden", !b);
  if (b) { b.mesh.material.uniforms.uSel.value = 1; showInfo(b); }
  renderLineage();
}

function badge(cls, text, title = "") { return `<span class="badge ${cls}" title="${title}">${text}</span>`; }

function showInfo(b, theta = null, voice = null) {
  if (!b || b !== S.selected) return;
  const c = cfg();
  const th = theta == null ? (c.ovOn ? c.ov : 0) : theta;
  const v = voice || G.voiceOf(b.n, b.d, th);
  const feat = G.voiceFeatures(v.a);
  const near = G.nearestVowel(feat.F1, feat.F2, S.vowels);
  const N = b.n.length - 2;
  $("bName").textContent = `${b.name} · N = ${N} layers`;
  const goup = isExactThickness(b);
  $("bBadges").innerHTML = [
    b.kind === "preset" ? badge("approx", b.label, b.source) : b.kind === "metamer" ? badge("exact", "inverse-designed metamer") : b.kind === "random" ? badge("exact", "random Goupillaud stack", b.source) : b.kind === "speaker" ? badge("exact", "Goupillaud speaker (butterflies.json)", b.source) : badge("approx", b.label || b.kind),
    goup ? badge("exact", "n·d = 428.27 nm (Goupillaud)") : badge("approx", "non-Goupillaud thickness"),
    b.mode === "ideal" ? badge("approx", "ideal n (unrealizable)") : b.mode === "materials" ? badge("approx", "material palette") : "",
    badge("art", "display exposure Y→50"),
  ].join("");
  $("bSw").style.background = b.hex0;
  $("bHex").textContent = `${b.hex0}`;
  $("bLab").textContent = `Lab ${b.Lab0.map((x) => x.toFixed(1)).join(", ")} (${c.qty}, ${c.ill}) · abs sRGB ${b.hexAbs || ""}`;
  $("bVoice").innerHTML = `${v.exact ? badge("exact", "exact") : badge("approx", "approx (LPC fit)")} <span class="small">${v.method}; f0 ${b.f0} Hz</span>`;
  const fl = feat.F.slice(0, 4).map((f, i) => `F${i + 1} ${fmt(f)} <span class="muted">(B ${fmt(feat.B[i])})</span>`).join(", ");
  $("bF").innerHTML = feat.strict ? fl
    : `${fl || "none sharp"} ${badge("approx", "broad")} <span class="small">envelope peaks ${feat.peaks.map((x) => fmt(x)).join(", ") || "—"} Hz</span>`;
  $("bVowel").innerHTML = near ? `/${near.item.ipa}/ “${near.item.example}” (${near.item.group}, F1 ${fmt(near.item.F1)}, F2 ${fmt(near.item.F2)}) ${badge("approx", `log-dist ${near.dist.toFixed(2)}`)}` : "—";
  drawStack($("cStack"), b.n, b.d);
  drawSpectrum($("cSpec"), b.n, b.d, th);
  $("specTh").textContent = `θ = ${th}°`;
  $("envBadge").innerHTML = v.exact ? badge("exact", "|1/D|², Goupillaud θ=0") : badge("approx", "LPC fit");
  drawEnvelope($("cEnv"), v.a, v.gain, feat, near);
}

function nColour(n) { // n → colour ramp (n = 1 deep blue … 2.5 warm yellow); ideal n beyond clamps
  const t = Math.min(1, Math.max(0, (n - 1) / 1.5));
  const stops = [[27, 42, 107], [47, 181, 176], [245, 215, 110]];
  const s = t < 0.5 ? 0 : 1, u = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
  const a = stops[s], z = stops[s + 1];
  return `rgb(${a.map((x, i) => Math.round(x + (z[i] - x) * u)).join(",")})`;
}

function drawStack(cv, n, d) {
  const g = cv.getContext("2d"), W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  const end = 16, inner = W - 2 * end - 2;
  const sum = d.reduce((p, q) => p + q, 0);
  const nmax = Math.max(2.5, ...n);
  const hOf = (x) => 8 + (H - 22) * (x - 0.9) / (nmax - 0.9);
  let x = 1;
  const bar = (w, ni, dim) => {
    const h = hOf(ni);
    g.fillStyle = nColour(ni); g.globalAlpha = dim ? 0.35 : 1;
    g.fillRect(x, H - 12 - h, Math.max(1, w - 0.5), h);
    g.globalAlpha = 1; x += w;
  };
  bar(end, n[0], true);
  for (let i = 0; i < d.length; i++) bar(inner * d[i] / sum, n[i + 1], false);
  bar(end, n[n.length - 1], true);
  g.fillStyle = "#9aa1b5"; g.font = "10px sans-serif";
  g.fillText("in", 2, H - 2); g.fillText("sub", W - end - 2, H - 2);
  g.fillText(`n ${Math.min(...n).toFixed(2)}–${Math.max(...n).toFixed(2)}, total d ${sum.toFixed(0)} nm`, end + 6, H - 2);
}

function lambdaRGB(lam) {
  const D = P.getPhysicsData();
  const i = Math.round((lam - D.wl[0]) / (D.wl[1] - D.wl[0]));
  if (i < 0 || i >= D.wl.length) return "#000";
  const XYZ = [D.cmf[0][i] * 100, D.cmf[1][i] * 100, D.cmf[2][i] * 100];
  return P.toHex(P.displayRGB(XYZ, 25));
}

function drawSpectrum(cv, n, d, th) {
  const g = cv.getContext("2d"), W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  const tc = P.transmittanceCurve(n, d, 351, th);
  const L0 = 400, L1 = 750, pad = 4, ph = H - 26;
  const X = (lam) => pad + (W - 2 * pad) * (lam - L0) / (L1 - L0);
  for (let lam = L0; lam < L1; lam += 2) { g.fillStyle = lambdaRGB(lam); g.fillRect(X(lam), H - 14, X(lam + 2) - X(lam) + 0.5, 6); }
  const line = (arr, col) => {
    g.strokeStyle = col; g.lineWidth = 1.5; g.beginPath();
    for (let i = 0; i < tc.wl.length; i++) { const x = X(tc.wl[i]), y = 4 + ph * (1 - arr[i]); i ? g.lineTo(x, y) : g.moveTo(x, y); }
    g.stroke();
  };
  line(tc.T, "#3fd6c6"); line(tc.R, "#c58bff");
  g.fillStyle = "#9aa1b5"; g.font = "10px sans-serif";
  g.fillText("T", W - 22, 12); g.fillStyle = "#c58bff"; g.fillText("R", W - 12, 12);
  g.fillStyle = "#9aa1b5"; g.fillText("400 nm", 2, H - 1); g.fillText("750 nm", W - 38, H - 1);
}

function drawEnvelope(cv, a, gain, feat, near) {
  const g = cv.getContext("2d"), W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  const { f, dB } = P.envelopeDb(a, gain, 512);
  const mx = Math.max(...dB);
  const X = (hz) => 4 + (W - 8) * hz / (P.FS / 2), Y = (db) => 6 + (H - 22) * Math.min(1, (mx - db) / 50);
  const vline = (hz, col, dash) => { g.strokeStyle = col; g.setLineDash(dash); g.beginPath(); g.moveTo(X(hz), 4); g.lineTo(X(hz), H - 16); g.stroke(); g.setLineDash([]); };
  if (near) { vline(near.item.F1, "rgba(143,123,255,0.8)", [2, 3]); vline(near.item.F2, "rgba(143,123,255,0.8)", [2, 3]); }
  (feat.strict ? feat.F : feat.peaks).slice(0, 5).forEach((hz) => vline(hz, feat.strict ? "rgba(79,209,139,0.7)" : "rgba(255,181,71,0.7)", [4, 3]));
  g.strokeStyle = "#e9ecf5"; g.lineWidth = 1.5; g.beginPath();
  for (let i = 0; i < f.length; i++) { const x = X(f[i]), y = Y(dB[i]); i ? g.lineTo(x, y) : g.moveTo(x, y); }
  g.stroke();
  g.fillStyle = "#9aa1b5"; g.font = "10px sans-serif";
  g.fillText("0", 2, H - 3); g.fillText("8 kHz", W - 32, H - 3); g.fillText("50 dB", W - 34, 12);
  g.fillStyle = "rgba(143,123,255,0.9)"; g.fillText("nearest vowel F1/F2", 40, H - 3);
}

// ----------------------------------------------------------------------------- presets
function buildPresets() {
  const box = $("presets");
  box.innerHTML = "";
  for (const it of S.presets.items) {
    const bt = document.createElement("button");
    bt.className = "chip";
    bt.innerHTML = `<span class="dot" style="background:${it.lut.rgb[0]}"></span>${it.name}`;
    bt.title = `${it.label} — ${it.source}`;
    bt.onclick = () => {
      for (const b of S.butterflies.filter((x) => x.name === it.name)) removeButterfly(b);
      const goup = G.isGoupillaud(it.n, it.d_nm);
      const b = addButterfly({ name: it.name, kind: goup ? "speaker" : "preset", n: it.n, d: it.d_nm, label: it.label, source: it.source,
        goupScaled: false, tight: { x: 0, z: 3 } });
      refreshColour(b);
      select(b); speak(b);
    };
    box.appendChild(bt);
  }
}

// ----------------------------------------------------------------------------- metamers (inverse design)
function buildAtlasSwatches() {
  const c = cfg();
  const box = $("atlasSw");
  box.innerHTML = "";
  const cand = S.atlas.items.map((it, i) => ({ it, i })).filter(({ it }) => it.F1 != null);
  for (let k = 0; k < 16; k++) {
    const { it, i } = cand[Math.floor((k + 0.5) * cand.length / 16)];
    const bt = document.createElement("button");
    const hex = c.qty === "R" ? it.rgbR : it.rgb;
    bt.style.background = hex;
    bt.title = `atlas #${i} (${c.qty} colour, display)`;
    bt.onclick = () => {
      const cc = cfg();
      const lab = cc.ill === "D65" ? (cc.qty === "R" ? it.LabR : it.Lab) : P.filmColour(it.n, G.goupD(it.n, 1), 0, cc.ill, cc.qty).Lab;
      runDesign(lab, `atlas #${i}`, [i], hex);
    };
    box.appendChild(bt);
  }
}

function runDesign(targetLab, what, exclude = [], showHex = null) {
  const c = cfg();
  if (S.designer) S.designer.cancelled = true;
  const D = G.createDesigner({ targetLab, nLayers: c.layers, mode: c.mode, illuminant: c.ill, quantity: c.qty, scale: c.scale,
    seed: `${c.seed}|${what}`, atlas: S.atlas, excludeAtlas: exclude, nSolutions: 5, restarts: 80, materials: c.materials });
  S.designer = D;
  $("metaList").innerHTML = "";
  const msg = $("designMsg");
  const t0 = performance.now();
  const tick = () => {
    if (D.cancelled) return;
    const done = D.step(25);
    const pg = D.progress;
    msg.textContent = `designing for ${what}: restart ${pg.restarts}/${pg.of}, ${pg.found} hits, best ΔE00 ${fmt(pg.bestDE, 2)}…`;
    if (!done) { setTimeout(tick, 0); return; }
    finishDesign(D, what, showHex, performance.now() - t0);
  };
  setTimeout(tick, 0);
}

function finishDesign(D, what, showHex, ms) {
  const c = cfg();
  for (const b of S.butterflies.filter((x) => x.kind === "metamer")) removeButterfly(b);
  const res = D.results;
  const msg = $("designMsg");
  const tgtNote = D.retargeted
    ? `Target not reachable with N=${c.layers}, ${c.mode} (best ΔE00 to it ${fmt(D.retargetDE, 1)}); designing metamers of the <b>nearest reachable colour</b> instead. `
    : "";
  if (!res.length) { msg.innerHTML = `No stack within ΔE00 < 2 found (${(ms / 1000).toFixed(1)} s). Try another colour or more layers.`; return; }
  msg.innerHTML = `${tgtNote}${res.length} metamers (ΔE00 < 2 at θ = 0, ${c.qty}, ${c.ill}; re-checked with TMM) in ${(ms / 1000).toFixed(1)} s.
    ${badge("exact", "colour match")} At other angles their iridescence differs.`;
  const rng = G.makeRng(`meta:${what}`);
  const letters = "ABCDEFGH";
  res.forEach((r, i) => {
    const b = addButterfly({ name: `Metamer ${letters[i]}`, kind: "metamer", n: r.n, d: r.d, mode: c.mode, label: "metamer",
      source: `inverse design for ${what}`, goupScaled: true, tight: { x: 0, z: 2.5 }, rng: rng.fork(String(i)) });
    refreshColour(b);
    b.design = r;
    const near = G.nearestVowel(r.voice.F1, r.voice.F2, S.vowels);
    const row = document.createElement("div");
    row.className = "meta";
    row.innerHTML = `<span class="sw" style="background:${b.hex0}"></span>
      <span><b>${b.name}</b> ΔE00 ${r.dE.toFixed(2)} · F1/F2 ${fmt(r.voice.F1)}/${fmt(r.voice.F2)} Hz${r.voice.strict ? "" : "*"}
      ${near ? `· ≈ /${near.item.ipa}/` : ""}</span><button class="btn sm">play</button>`;
    row.title = r.voice.strict ? "formants (B < 600 Hz)" : "* broad resonances: envelope peaks";
    row.onclick = () => { select(b); speak(b, 0); };
    $("metaList").appendChild(row);
  });
  if (showHex) $("pick").value = showHex;
}

// ----------------------------------------------------------------------------- evolve
function evolveOnce() {
  const b = S.selected || S.butterflies[0];
  if (!b) return;
  if (!S.selected) select(b);
  const c = cfg();
  if (!S.evoRng) S.evoRng = G.makeRng(`evolve|${c.seed}`);
  if (!b.lineage.length) b.lineage.push({ n: b.n, d: b.d, hex: b.hex0 });
  const n2 = G.evolveStep(b.n, S.evoRng, { sigma: c.sigma, mode: b.mode, mutateLayers: c.evoLayers, materials: c.materials });
  // presets with their own (non-Goupillaud) thicknesses keep d; Goupillaud stacks stay Goupillaud
  const keepD = !b.goupScaled && n2.length === b.n.length && !G.isGoupillaud(b.n, b.d);
  b.n = n2;
  b.d = keepD ? b.d : G.goupD(n2, c.scale);
  if (!keepD) b.goupScaled = true;
  refreshColour(b);
  b.lineage.push({ n: b.n, d: b.d, hex: b.hex0 });
  if (b.lineage.length > 60) b.lineage.splice(1, 1);
  renderLineage();
  showInfo(b);
}

function renderLineage() {
  const box = $("lineage");
  box.innerHTML = "";
  const b = S.selected;
  if (!b) return;
  b.lineage.forEach((g, i) => {
    const s = document.createElement("span");
    s.style.background = g.hex;
    s.title = `generation ${i}: ${g.hex}, N=${g.n.length - 2}`;
    s.onclick = () => { b.n = g.n; b.d = g.d; refreshColour(b); showInfo(b); speak(b); };
    box.appendChild(s);
  });
}

// ----------------------------------------------------------------------------- sing a word
function stopSinging() {
  const s = S.singing;
  if (!s) return;
  S.singing = null;
  refreshColour(s.b);
  document.querySelectorAll("#seq .chip").forEach((c) => c.classList.remove("now"));
  if (S.selected === s.b) showInfo(s.b);
}

function sing() {
  const b = S.selected || S.butterflies[0];
  if (!b) return;
  if (!S.selected) select(b);
  if (S.singing) stopSinging();
  const c = cfg();
  const toks = G.parseWord($("word").value, S.vowels);
  if (!toks.length) { $("seq").textContent = "no vowels recognised"; return; }
  const group = $("group").value;
  const items = toks.map((t) => G.vowelItem(S.vowels, t.code, group));
  const films = items.map((it) => G.vowelFilm(it.a, "realizable"));
  const polys = $("src").value === "film" ? films.map((f) => G.voiceOf(f.n, f.d, 0).a) : items.map((it) => it.a);
  const luts = films.map((f) => P.buildLUT(f.n, f.d, c.qty, c.ill, ANGLES));
  const hexes = films.map((f) => P.filmColour(f.n, f.d, 0, c.ill, c.qty).hex);
  const f0 = items.reduce((p, it) => p + it.F0, 0) / items.length;
  const seg = 0.42, trans = 0.09;
  const { samples, segments } = G.singSamples(polys, { f0, seg, trans });
  const ctx = audioCtx();
  const buf = ctx.createBuffer(1, samples.length, P.FS);
  buf.getChannelData(0).set(samples);
  const when = ctx.currentTime + 0.08;
  play(buf, when);
  $("seq").innerHTML = toks.map((t, i) => `<span class="chip" title="${t.how}: ${t.token}"><span class="dot" style="background:${hexes[i]}"></span>/${items[i].ipa}/ ${items[i].example}</span>`).join("");
  S.singing = { b, luts, films, items, buf, start: when, perfStart: performance.now() + 80, seg, trans, total: segments.length * seg, idx: -2 };
}

function updateSinging() {
  const s = S.singing;
  if (!s) return;
  // follow the audio clock, but never lag the wall clock by > 0.25 s: a suspended/blocked/stalled AudioContext must not
  // freeze the wing animation (and singing must always finish)
  const tWall = (performance.now() - s.perfStart) / 1000;
  const tAudio = S.ctx && S.ctx.state === "running" ? S.ctx.currentTime - s.start : -Infinity;
  const t = Math.max(tAudio, tWall - 0.25);
  if (t > s.total + 0.05) { stopSinging(); return; }
  if (t < 0) return;
  const i = Math.min(s.luts.length - 1, Math.floor(t / s.seg));
  const local = t - i * s.seg;
  const u = s.b.mesh.material.uniforms;
  if (i !== s.idx) {
    s.idx = i;
    writeLUT(s.b.mesh.lut, s.luts[Math.max(0, i - 1)]);
    writeLUT(s.b.mesh.lut2, s.luts[i]);
    document.querySelectorAll("#seq .chip").forEach((c, k) => c.classList.toggle("now", k === i));
    if (S.selected === s.b) {
      const f = s.films[i];
      $("bName").textContent = `${s.b.name} singing /${s.items[i].ipa}/ (${s.items[i].example})`;
      drawStack($("cStack"), f.n, f.d);
      drawSpectrum($("cSpec"), f.n, f.d, 0);
    }
  }
  const w = i > 0 && local < s.trans ? local / s.trans : 1;
  u.uMix.value = w * w * (3 - 2 * w);
}

// ----------------------------------------------------------------------------- animation
const clock = new THREE.Clock();
const _p = new THREE.Vector3(), _vel = new THREE.Vector3(), _tg = new THREE.Vector3();
function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(0.05, clock.getDelta());
  const T = clock.elapsedTime;
  const c = cfg();
  const now = performance.now();
  for (const b of S.butterflies) {
    const sel = b === S.selected;
    b.t += dt * (sel ? 0.3 : 1);
    const { c: C, A, W, Ph } = b.flight, t = b.t;
    _p.set(C.x + A.x * Math.sin(W.x * t + Ph.x), C.y + A.y * Math.sin(W.y * t + Ph.y), C.z + A.z * Math.sin(W.z * t + Ph.z));
    _vel.set(A.x * W.x * Math.cos(W.x * t + Ph.x), 0.3 * A.y * W.y * Math.cos(W.y * t + Ph.y), A.z * W.z * Math.cos(W.z * t + Ph.z));
    const g = b.mesh.group;
    g.position.copy(_p);
    g.lookAt(_tg.copy(_p).add(_vel));
    const fast = now < b.speakUntil || (S.singing && S.singing.b === b) ? 1.9 : 1;
    b.phase = (b.phase || 0) + dt * 2 * Math.PI * b.flapF * fast;
    const flap = S.freezeFlap != null ? S.freezeFlap : 0.3 + 0.8 * Math.sin(b.phase); // freezeFlap: autotest only
    b.mesh.pivots[0].rotation.z = flap;
    b.mesh.pivots[1].rotation.z = -flap;
    const u = b.mesh.material.uniforms;
    u.uBend.value = 0.06 + 0.12 * Math.cos(b.phase);
    u.uTwist.value = 0.12 * Math.sin(0.5 * b.phase + b.id);
    u.uOverride.value = c.ovOn ? c.ov : -1;
    if (sel) { ring.position.copy(_p); ring.position.y -= 0.35; ring.rotation.z = T; }
  }
  updateSinging();
  garden.update(T);
  controls.update();
  if (S.selected) $("hudAngle").textContent = `${S.selected.name}: wing θ ≈ ${currentTheta(S.selected)}°${c.ovOn ? " (fixed)" : ""}`;
  else $("hudAngle").textContent = "";
  renderer.render(scene, camera);
}

// ----------------------------------------------------------------------------- UI wiring
function wire() {
  const matBox = $("matBox");
  for (const [k, v] of Object.entries(P.MATERIALS)) {
    const bt = document.createElement("button");
    bt.className = "chip on"; bt.dataset.m = k; bt.textContent = `${k} ${v.toFixed(2)}`;
    bt.onclick = () => { bt.classList.toggle("on"); if ($("mode").value === "materials") regrow(); };
    matBox.appendChild(bt);
  }
  const label = (id, f = (x) => x) => { const el = $(id), out = $(id + "V") || $(id.replace(/$/, "V")); el.addEventListener("input", () => { if (out) out.textContent = f(el.value); }); };
  label("count"); label("layers"); label("sigma"); label("ov");
  $("scale").addEventListener("input", () => { $("scaleV").textContent = (+$("scale").value).toFixed(2); $("ndV").textContent = (428.27 * $("scale").value).toFixed(0); });
  $("count").addEventListener("change", regrow);
  $("layers").addEventListener("change", regrow);
  $("regrow").onclick = regrow;
  $("seedRand").onclick = () => { $("seed").value = Math.random().toString(36).slice(2, 8); S.evoRng = null; regrow(); };
  $("seed").addEventListener("change", () => { S.evoRng = null; regrow(); });
  $("mode").addEventListener("change", () => { matBox.classList.toggle("hidden", $("mode").value !== "materials"); regrow(); });
  const rethick = () => {
    $("scaleRow").classList.toggle("hidden", $("thick").value !== "custom");
    const c = cfg();
    for (const b of S.butterflies) if (b.goupScaled) b.d = G.goupD(b.n, c.scale);
    refreshAll();
  };
  $("thick").addEventListener("change", rethick);
  $("scale").addEventListener("change", rethick);
  $("ill").addEventListener("change", refreshAll);
  $("qty").addEventListener("change", () => { buildAtlasSwatches(); refreshAll(); });
  $("ov").addEventListener("change", () => S.selected && showInfo(S.selected));
  $("ovOn").addEventListener("change", () => S.selected && showInfo(S.selected));
  $("speak").onclick = () => speak(S.selected);
  $("speak0").onclick = () => speak(S.selected, 0);
  $("design").onclick = () => runDesign(G.hexToLab($("pick").value, cfg().ill), $("pick").value);
  $("evolve").onclick = evolveOnce;
  $("autoEvo").addEventListener("change", () => {
    clearInterval(S.autoTimer);
    if ($("autoEvo").checked) S.autoTimer = setInterval(evolveOnce, 900);
  });
  $("sing").onclick = sing;
  $("word").addEventListener("keydown", (e) => { if (e.key === "Enter") sing(); });
}

// ----------------------------------------------------------------------------- boot
async function boot() {
  const getJSON = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`); return r.json(); });
  try {
    resize();
    animate();
    const [, vowels, atlas, presets] = await Promise.all([P.loadPhysicsData("data/"), getJSON("data/vowels.json"),
      getJSON("data/atlas_sample.json"), getJSON("data/butterflies.json")]);
    S.vowels = vowels; S.atlas = atlas; S.presets = presets;
    wire();
    buildPresets();
    buildAtlasSwatches();
    await regrow();
    $("loading").classList.add("hidden");
    if (new URLSearchParams(location.search).has("autotest")) {
      runAutotest({ S, THREE, P, G, $, cfg, camera, controls, renderer, scene, canvas, pickAt, select, speak });
    }
  } catch (e) {
    $("loading").textContent = `Error: ${e.message}`;
    console.error(e);
    if (new URLSearchParams(location.search).has("autotest")) console.log(`AUTOTEST FAIL garden boot: ${e.message}`);
  }
}
boot();
