// theory.js — interactive tube ⟷ film theory page. All physics from physics.js (CONTRACT §2–§4).
import {
  FS, NU_MIN, NU_MAX, C_LIGHT, MAPPINGS, loadPhysicsData, reflectionFromMedia, mediaFromReflection,
  polyFromReflection, powerTransfer, omegaOfNu, fOfNu, nuImages, filmFromMedia, goupillaudD, filmRTNu,
  filmColour, stepUp, linspace,
} from "./physics.js";
import { fitCanvas, axes, line, wavelengthRGB, ramp } from "./plot.js";

const $ = (s) => document.querySelector(s);
const S = {
  N: 16, c: new Float64Array(17), fmode: "ideal", ill: "D65", morph: 0, playing: false,
  db: false, hoverNu: null, vowels: [], stage: 16, F: null, G: null, log: [], auto: null, colourOK: false,
  map: "full", // CONTRACT §4b: site-wide display default = full-band; ?mapping=brief|full
};
const MAP_LABEL = { brief: "brief (Δν = 350 THz, d = 428.27 nm)", full: "full-band (Δν = 750 THz, d = 199.86 nm)" };
const dOpt = () => MAPPINGS[S.map].dOpt;   // nm, common optical thickness n·d of every layer
const dnu = () => MAPPINGS[S.map].dnu;     // Hz, period of the film response = c / (2 dOpt)
const fold = (f) => Math.min(f, FS - f);
let D = null; // derived quantities

// ------------------------------------------------------------------ derived physics
const fGrid = linspace(0, FS / 2, 801);
const omGrid = Float64Array.from(fGrid, (f) => 2 * Math.PI * f / FS);
const nuGrid = linspace(NU_MIN, NU_MAX, 701);

function derive() {
  const c = S.c;
  const m = mediaFromReflection(c, 1.0);
  const n = filmFromMedia(m, S.fmode);
  const d = goupillaudD(n.subarray(1, n.length - 1), dOpt());
  const P = powerTransfer(c, omGrid);
  const T = filmRTNu(n, d, nuGrid).T;                       // transfer-matrix film, independent of the tube formula
  const Pnu = powerTransfer(c, omegaOfNu(nuGrid, dOpt()));  // tube P at ω = 2δ, δ = 2π dOpt ν / c
  let maxDiff = 0, maxRel = 0;
  for (let i = 0; i < T.length; i++) {
    const e = Math.abs(T[i] - Pnu[i]);
    maxDiff = Math.max(maxDiff, e);
    maxRel = Math.max(maxRel, e / Math.max(Pnu[i], 1e-300));
  }
  // closed-glottis link to LPC: polyFromReflection([-1, c1..cN]) == stepUp(k), k = -c
  const k = Array.from(c.subarray(1), (x) => -x);
  const a = stepUp(k);
  const Dc = polyFromReflection([-1, ...c.subarray(1)]);
  let lpcDiff = 0;
  for (let i = 0; i < a.length; i++) lpcDiff = Math.max(lpcDiff, Math.abs(a[i] - Dc[i]));
  D = { m, n, d, P, T, Pnu, maxDiff, maxRel, lpcDiff };
}

// ------------------------------------------------------------------ controls
function setC(arr) {
  S.N = arr.length - 1;
  S.c = Float64Array.from(arr, (x) => Math.max(-0.99, Math.min(0.99, x)));
  $("#N").value = S.N;
  buildSliders();
  resetSteps(S.N);
  update();
}

function buildSliders() {
  $("#N-val").textContent = S.N;
  const box = $("#coefs");
  box.innerHTML = "";
  for (let i = 1; i < S.N; i++) {
    const wrap = document.createElement("div");
    wrap.innerHTML = `<label><span>c<sub>${i}</sub></span><span class="mono" id="cv${i}">${S.c[i].toFixed(3)}</span></label>` +
      `<input type="range" min="-0.99" max="0.99" step="0.001" value="${S.c[i]}" data-i="${i}" aria-label="c${i}">`;
    box.appendChild(wrap);
  }
  $("#c0").value = S.c[0];
  $("#cN").value = S.c[S.N];
  showEnds();
}
function showEnds() {
  $("#c0-val").textContent = S.c[0].toFixed(3);
  $("#cN-val").textContent = S.c[S.N].toFixed(3);
}

function preset(name) {
  const N = S.N;
  if (["ah", "iy", "uw"].includes(name)) {
    const v = S.vowels.find((x) => x.group === "men" && x.vowel === name);
    if (v) return setC(Array.from(reflectionFromMedia(v.m)));
    name = "bragg";
  }
  const c = new Array(N + 1).fill(0);
  if (name === "bragg") for (let i = 0; i <= N; i++) c[i] = (i % 2 ? 0.4 : -0.4);
  if (name === "random") for (let i = 0; i <= N; i++) c[i] = (Math.random() * 2 - 1) * (i === 0 || i === N ? 0.9 : 0.6);
  setC(c);
}

let pending = false;
function update() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => { pending = false; derive(); drawAll(); });
}

// ------------------------------------------------------------------ drawing: tube / film / morph
const TUBE_COL = [143, 123, 255];
function nColour(ni, lnMax) { return ramp(lnMax > 0 ? Math.log(ni) / lnMax : 0.15); }

function tubeRects(w, h, pad = 16) {
  const m = D.m, K = m.length;
  const rMax = Math.sqrt(Math.max(...m));
  const endW = 0.5;                         // terminations drawn half width
  const total = K - 2 + 2 * endW;
  const unit = (w - 2 * pad) / total;
  const cy = h / 2, R = h * 0.42;
  const rects = [];
  let x = pad;
  for (let i = 0; i < K; i++) {
    const ww = (i === 0 || i === K - 1 ? endW : 1) * unit;
    const r = Math.max(1, R * Math.sqrt(m[i]) / rMax);
    rects.push({ x, y: cy - r, w: ww, h: 2 * r });
    x += ww;
  }
  return rects;
}

function filmRects(w, h, padY = 14, widthFrac = 0.62) {
  const n = D.n, d = D.d, K = n.length;
  const endH = 0.12 * (h - 2 * padY);
  const avail = h - 2 * padY - 2 * endH;
  const minH = Math.max(1.5, avail * 0.012);
  const dd = Array.from(d);
  const sum = dd.reduce((a, b) => a + b, 0);
  let hs = dd.map((x) => Math.max(minH, avail * x / sum));
  const s2 = hs.reduce((a, b) => a + b, 0);
  hs = hs.map((x) => x * avail / s2);
  const W = w * widthFrac, x0 = (w - W) / 2;
  const rects = [{ x: x0, y: padY, w: W, h: endH }];
  let y = padY + endH;
  for (let i = 0; i < hs.length; i++) { rects.push({ x: x0, y, w: W, h: hs[i] }); y += hs[i]; }
  rects.push({ x: x0, y, w: W, h: endH });
  void K;
  return rects;
}

function drawTube() {
  const { ctx, w, h } = fitCanvas($("#cv-tube"));
  const rects = tubeRects(w, h);
  ctx.save();
  ctx.shadowColor = "rgba(143,123,255,0.8)"; ctx.shadowBlur = 14;
  rects.forEach((r, i) => {
    const end = i === 0 || i === rects.length - 1;
    ctx.fillStyle = end ? "rgba(143,123,255,0.18)" : "rgba(143,123,255,0.55)";
    ctx.fillRect(r.x, r.y, r.w - (end ? 0 : 1), r.h);
  });
  ctx.restore();
  ctx.fillStyle = "#9aa1b5"; ctx.font = "11px Segoe UI, sans-serif";
  ctx.textAlign = "left"; ctx.fillText("glottis", 6, h - 6);
  ctx.textAlign = "right"; ctx.fillText("lips → outside", w - 6, h - 6);
}

function drawFilm() {
  const { ctx, w, h } = fitCanvas($("#cv-film"));
  const rects = filmRects(w, h);
  const lnMax = Math.log(Math.max(...D.n));
  rects.forEach((r, i) => {
    const end = i === 0 || i === rects.length - 1;
    ctx.globalAlpha = end ? 0.3 : 1;
    ctx.fillStyle = nColour(D.n[i], lnMax);
    ctx.fillRect(r.x, r.y, r.w, Math.max(1, r.h - (end ? 0 : 0.6)));
  });
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#9aa1b5"; ctx.font = "11px Segoe UI, sans-serif"; ctx.textAlign = "left";
  const r0 = rects[0], rL = rects[rects.length - 1];
  ctx.fillText(`incident n=${D.n[0].toFixed(2)}`, 6, r0.y + 12);
  ctx.fillText(`substrate n=${D.n[D.n.length - 1].toFixed(2)}`, 6, rL.y + rL.h - 4);
  ctx.textAlign = "right";
  const nl = Array.from(D.n.subarray(1, D.n.length - 1));
  ctx.fillText(`layer n: ${Math.min(...nl).toFixed(2)} … ${Math.max(...nl).toFixed(nl.some((x) => x > 10) ? 0 : 2)}`, w - 6, r0.y + 12);
  ctx.fillText(`d: ${Math.min(...D.d).toFixed(1)} … ${Math.max(...D.d).toFixed(1)} nm`, w - 6, rL.y + rL.h - 4);
}

const ease = (t) => t * t * (3 - 2 * t);
function drawMorph() {
  const { ctx, w, h } = fitCanvas($("#cv-morph"));
  const t = ease(S.morph);
  const A = tubeRects(w, h, 30), B = filmRects(w, h, 12, 0.42);
  const lnMax = Math.log(Math.max(...D.n));
  const lerp = (a, b) => a + (b - a) * t;
  for (let i = 0; i < A.length; i++) {
    const a = A[i], b = B[i];
    const r = { x: lerp(a.x, b.x), y: lerp(a.y, b.y), w: lerp(a.w, b.w), h: lerp(a.h, b.h) };
    const end = i === 0 || i === A.length - 1;
    const gap = end ? 0 : lerp(1, 0.6);
    ctx.globalAlpha = (end ? 0.25 : 0.75) * (1 - t);
    ctx.fillStyle = `rgb(${TUBE_COL.join(",")})`;
    ctx.fillRect(r.x, r.y, Math.max(0.5, r.w - gap * (1 - t)), Math.max(0.5, r.h - gap * t));
    ctx.globalAlpha = (end ? 0.3 : 1) * t;
    ctx.fillStyle = nColour(D.n[i], lnMax);
    ctx.fillRect(r.x, r.y, Math.max(0.5, r.w - gap * (1 - t)), Math.max(0.5, r.h - gap * t));
  }
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#9aa1b5"; ctx.font = "12px Segoe UI, sans-serif"; ctx.textAlign = "left";
  ctx.fillText(t < 0.5 ? "tube: section i has area A_i (radius ∝ √A_i)" : `film: layer i has index n_i ∝ A_i, thickness ${dOpt().toFixed(2)}/n_i nm`, 10, 18);
  $("#morph-val").textContent = S.morph.toFixed(2);
}

// ------------------------------------------------------------------ plots
const fmtE = (x) => (x === 0 ? "0" : x.toExponential(1));
function yOf(arr) { return S.db ? Array.from(arr, (v) => 10 * Math.log10(Math.max(v, 1e-12))) : arr; }
function yRange(...arrs) {
  let mx = -Infinity;
  for (const a of arrs) for (const v of a) mx = Math.max(mx, v);
  if (S.db) return [Math.max(-60, mx - 50), mx + 3];
  return [0, Math.max(1e-6, mx) * 1.08];
}
const BOX = (w, h) => ({ x: 52, y: 12, w: w - 64, h: h - 58 });

function drawP() {
  const { ctx, w, h } = fitCanvas($("#cv-P"));
  const y = yOf(D.P);
  const [y0, y1] = yRange(y);
  const ax = axes(ctx, BOX(w, h), { xmin: 0, xmax: FS / 2, ymin: y0, ymax: y1, xlabel: "tube frequency f (kHz)", ylabel: S.db ? "P (dB)" : "P",
    fmtX: (v) => (v / 1000).toFixed(0), fmtY: (v) => (S.db ? v.toFixed(0) : +v.toPrecision(2) + "") });
  line(ctx, ax, fGrid, y, { color: "#8f7bff", width: 2 });
  if (S.hoverNu != null) {
    const fe = fold(fOfNu(S.hoverNu, dnu())[0]);
    marker(ctx, ax, fe, `${Math.round(fe)} Hz`);
  } else if (S.hoverF != null) marker(ctx, ax, S.hoverF, `${Math.round(S.hoverF)} Hz`);
}

function marker(ctx, ax, xv, label) {
  const { y, h } = ax.box;
  const px = ax.X(xv);
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(px, y); ctx.lineTo(px, y + h); ctx.stroke();
  ctx.fillStyle = "#e9ecf5"; ctx.font = "11px Segoe UI, sans-serif"; ctx.textAlign = px > ax.box.x + ax.box.w - 60 ? "right" : "left";
  ctx.fillText(label, px + (ctx.textAlign === "left" ? 4 : -4), y + 12);
  ctx.restore();
}

function drawT() {
  const { ctx, w, h } = fitCanvas($("#cv-T"));
  const nuT = Float64Array.from(nuGrid, (v) => v / 1e12);
  const yT = yOf(D.T), yP = yOf(D.Pnu);
  const [y0, y1] = yRange(yT, yP);
  const box = BOX(w, h);
  box.h -= 8;
  const ax = axes(ctx, box, { xmin: 400, xmax: 750, ymin: y0, ymax: y1, xlabel: "light frequency ν (THz)", ylabel: S.db ? "T (dB)" : "T",
    fmtX: (v) => v.toFixed(0), fmtY: (v) => (S.db ? v.toFixed(0) : +v.toPrecision(2) + "") });
  // spectrum strip (artistic rendering of monochromatic colours)
  for (let px = 0; px < box.w; px++) {
    const nu = 400 + 350 * px / box.w;
    ctx.fillStyle = wavelengthRGB(C_LIGHT / (nu * 1e12) * 1e9);
    ctx.fillRect(box.x + px, box.y + box.h + 1, 1.5, 5);
  }
  line(ctx, ax, nuT, yT, { color: "#3fd6c6", width: 3.5, alpha: 0.85 });
  line(ctx, ax, nuT, yP, { color: "#ffb547", width: 1.6, dash: [6, 4] });
  if (S.hoverNu != null) marker(ctx, ax, S.hoverNu / 1e12, `${(S.hoverNu / 1e12).toFixed(0)} THz · ${(C_LIGHT / S.hoverNu * 1e9).toFixed(0)} nm`);
  else if (S.hoverF != null) for (const nu of nuImages(S.hoverF, dnu())) marker(ctx, ax, nu / 1e12, `${(nu / 1e12).toFixed(0)}`);
}

function mapPoints() {
  // special points of the folded mapping inside [400, 750] THz: band edges + images of 0 Hz and FS/2
  const pts = [NU_MIN, NU_MAX, ...nuImages(0, dnu()), ...nuImages(FS / 2, dnu())];
  const out = [];
  for (const nu of pts) {
    if (out.some((p) => Math.abs(p.nu - nu) < 1e9)) continue;
    out.push({ nu, f: fold(fOfNu(nu, dnu())[0]) });
  }
  return out.sort((x, y) => x.nu - y.nu);
}

function drawMap() {
  const { ctx, w, h } = fitCanvas($("#cv-map"));
  const ax = axes(ctx, { x: 52, y: 10, w: w - 64, h: h - 52 }, { xmin: 400, xmax: 750, ymin: 0, ymax: FS, xlabel: "ν (THz)", ylabel: "f (kHz)",
    fmtX: (v) => v.toFixed(0), fmtY: (v) => (v / 1000).toFixed(0), yticks: 4 });
  // vowel band 0..2.3 kHz: shade every ν whose folded f ≤ 2300 Hz
  ctx.fillStyle = "rgba(143,123,255,0.12)";
  for (let px = 0; px < ax.box.w; px++) {
    const nu = (400 + 350 * (px + 0.5) / ax.box.w) * 1e12;
    if (fold(fOfNu(nu, dnu())[0]) <= 2300) ctx.fillRect(ax.box.x + px, ax.box.y, 1, ax.box.h);
  }
  const nu = linspace(NU_MIN, NU_MAX, 1401);
  const raw = fOfNu(nu, dnu());
  const xs = Array.from(nu, (v) => v / 1e12);
  // raw sawtooth: break at the wrap
  const ys = Array.from(raw);
  let start = 0;
  for (let i = 1; i <= ys.length; i++) {
    if (i === ys.length || ys[i] < ys[i - 1] - FS / 2) { line(ctx, ax, xs.slice(start, i), ys.slice(start, i), { color: "#9aa1b5", width: 1.2, dash: [5, 4] }); start = i; }
  }
  line(ctx, ax, xs, ys.map(fold), { color: "#8f7bff", width: 2.4 });
  ctx.fillStyle = "#e9ecf5"; ctx.font = "11px Segoe UI, sans-serif";
  for (const p of mapPoints()) {
    const x = p.nu / 1e12, y = p.f, right = x > 650;
    ctx.beginPath(); ctx.arc(ax.X(x), ax.Y(y), 3.5, 0, 7); ctx.fill();
    ctx.textAlign = right ? "right" : "left";
    ctx.fillText(`${Math.round(y)} Hz`, ax.X(x) + (right ? -6 : 6), ax.Y(y) + (y < FS / 4 ? -8 : 12));
  }
  if (S.hoverNu != null) marker(ctx, ax, S.hoverNu / 1e12, "");
}

function mapText() {
  for (const el of document.querySelectorAll(".dopt")) el.textContent = dOpt().toFixed(2);
  const brief = S.map === "brief";
  $("#map-cap").innerHTML = brief
    ? `Δν = 350 THz (d<sub>opt</sub> = 428.27 nm, the brief). Because |D|² is even in ω, the dashed raw sawtooth folds into the solid curve: ` +
      `0–8 kHz appears twice, mirrored about 525 THz (8 kHz) and 700 THz (0 Hz). The vowel-carrying 0–2.3 kHz (shaded) lands at 650–750 THz: violet.`
    : `Δν = 750 THz (d<sub>opt</sub> = 199.86 nm, every layer half-wave at 400 nm). f = 0 sits exactly at 750 THz, so 400–750 THz shows ` +
      `|f| = 7467 → 0 Hz <b>once</b> (no mirror image). Formants (0.3–3 kHz) land at ≈ 400–500 nm, fricative energy (3–7.5 kHz) at 500–750 nm; ` +
      `shaded = 0–2.3 kHz.`;
  $("#eq-map").textContent = brief
    ? "Exact phase identity ω = 2δ (mod 2π). Brief: 400 THz ↦ 2286 Hz, 525 THz ↦ 8 kHz, 700 THz ↦ 0 Hz."
    : "Exact phase identity ω = 2δ (mod 2π). Full-band: 400 THz ↦ 7467 Hz, 750 THz ↦ 0 Hz, monotonic in between.";
  $("#col-map").innerHTML = `Mapping: <b>${MAP_LABEL[S.map]}</b>. The layer thicknesses d = ${dOpt().toFixed(2)} nm / n change with the mapping, so the colour does too. ` +
    `Reflected = how a wing is seen; transmitted = the light that passes (the film's “voice”).`;
  for (const b of $("#mapsel").querySelectorAll("button")) b.classList.toggle("on", b.dataset.v === S.map);
}

function drawColour() {
  if (!S.colourOK) {
    $("#kv-T").textContent = "colour data (data/cie.json) not loaded";
    return;
  }
  for (const q of ["T", "R"]) {
    const col = filmColour(D.n, D.d, 0, S.ill, q);
    $(`#sw-${q}`).style.background = col.hex;
    $(`#sw-${q}`).style.boxShadow = `0 0 30px ${col.hex}66`;
    $(`#kv-${q}`).innerHTML = `<b>${q === "T" ? "transmitted T" : "reflected R"}</b> <span class="mono">${col.hex}</span><br>` +
      `Y = ${col.XYZ[1].toFixed(col.XYZ[1] < 1 ? 3 : 1)} % · Lab (${col.Lab.map((v) => v.toFixed(1)).join(", ")})`;
  }
}

function drawChecks() {
  const ideal = S.fmode === "ideal";
  const cls = D.maxDiff < 1e-9 ? "good" : "meh";
  $("#iso-check").innerHTML = ideal
    ? `max |T<sub>film</sub>(ν) − P<sub>tube</sub>(f(ν))| over 701 frequencies = <span class="${cls}">${fmtE(D.maxDiff)}</span> ` +
      `(${D.maxDiff < 1e-9 ? "identical to floating-point precision" : "check precision"}) · N = ${S.N}, layer d = ${dOpt().toFixed(2)}/n nm, ${S.map === "full" ? "full-band" : "brief"} mapping`
    : `realizable film: max |T − P| = <span class="meh">${D.maxDiff.toFixed(3)}</span> — indices compressed into 1.0–2.5 change the coefficients, ` +
      `so the curves no longer coincide <span class="badge approx">approximation</span>`;
}

// ------------------------------------------------------------------ step-up / layer peeling
function resetSteps(stage = 0) {
  S.F = Float64Array.of(1); S.G = Float64Array.of(S.c[0]);
  S.stage = 0; S.log = [`start: [F, G] = [1, c₀] = [1, ${S.c[0].toFixed(3)}]`];
  for (let i = 1; i <= stage; i++) stepUpOnce(true);
  if (stage) S.log.push(`… built all ${stage} layers: F = D(z), degree ${stage}`);
}
function stepUpOnce(quiet = false) {
  if (S.stage >= S.N) return false;
  const ci = S.c[S.stage + 1], F = S.F, G = S.G, L = F.length + 1;
  const nF = new Float64Array(L), nG = new Float64Array(L);
  for (let j = 0; j < L; j++) {
    const fe = j < L - 1 ? F[j] : 0, gs = j > 0 ? G[j - 1] : 0;
    nF[j] = fe + ci * gs; nG[j] = ci * fe + gs;
  }
  S.F = nF; S.G = nG; S.stage++;
  if (!quiet) S.log.push(`step-up with c${sub(S.stage)} = ${ci.toFixed(4)} → F has degree ${S.stage}`);
  return true;
}
function stepDownOnce() {
  const F = S.F, G = S.G;
  const c = G[0];                        // first echo = next interface
  const den = 1 - c * c;
  if (S.stage === 0) {
    S.log.push(`peel last interface: c₀ = G[0] = ${c.toFixed(4)} (true ${S.c[0].toFixed(4)}) — nothing left`);
    return false;
  }
  const L = F.length - 1;
  const nF = new Float64Array(L), nG = new Float64Array(L);
  let resid = 0;
  for (let j = 0; j < L; j++) nF[j] = (F[j] - c * G[j]) / den;
  resid = Math.abs((F[L] - c * G[L]) / den);       // should vanish
  for (let j = 0; j < L; j++) nG[j] = (G[j + 1] - c * F[j + 1]) / den;
  resid = Math.max(resid, Math.abs((G[0] - c * F[0]) / den));
  const truth = S.c[S.stage];
  S.log.push(`peel: c${sub(S.stage)} = G[0] = ${c.toFixed(6)}  (true ${truth.toFixed(6)}, |err| ${fmtE(Math.abs(c - truth))}, residual ${fmtE(resid)})`);
  S.F = nF; S.G = nG; S.stage--;
  return true;
}
const sub = (i) => String(i).split("").map((d) => "₀₁₂₃₄₅₆₇₈₉"[+d]).join("");

function drawStep() {
  const { ctx, w, h } = fitCanvas($("#cv-step"));
  const K = S.N + 2, s = S.stage;
  const lnMax = Math.log(Math.max(...D.n));
  // top: media row (built = media 0..s+1)
  const bw = (w - 20) / K;
  for (let i = 0; i < K; i++) {
    const built = i <= s + 1;
    ctx.globalAlpha = built ? 1 : 0.15;
    ctx.fillStyle = nColour(D.n[i], lnMax);
    ctx.fillRect(10 + i * bw, 8, bw - 2, 26);
  }
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#e9ecf5"; ctx.font = "11px Segoe UI, sans-serif"; ctx.textAlign = "center";
  for (let i = 0; i <= S.N; i++) {
    const x = 10 + (i + 1) * bw - 1;
    ctx.fillStyle = i <= s ? "#e9ecf5" : "rgba(233,236,245,0.25)";
    ctx.fillRect(x - 0.5, 6, 1.5, 30);
    if (bw > 22 || i % 2 === 0) ctx.fillText("c" + sub(i), x, 48);
  }
  // bottom-left: coefficients of F_s
  const by = 60, bh = h - by - 8, half = (w - 30) / 2;
  const F = S.F;
  const amp = Math.max(1, ...Array.from(F, Math.abs));
  ctx.strokeStyle = "rgba(255,255,255,0.15)"; ctx.strokeRect(10.5, by + 0.5, half, bh);
  const zero = by + bh / 2;
  ctx.beginPath(); ctx.moveTo(10, zero); ctx.lineTo(10 + half, zero); ctx.stroke();
  const cw = half / (S.N + 1);
  for (let j = 0; j < F.length; j++) {
    const v = F[j] / amp * (bh / 2 - 12);
    ctx.fillStyle = j === 0 ? "#3fd6c6" : "#8f7bff";
    ctx.fillRect(10 + j * cw + 2, v > 0 ? zero - v : zero, cw - 4, Math.abs(v));
  }
  ctx.fillStyle = "#9aa1b5"; ctx.textAlign = "left";
  ctx.fillText(`F${sub(s)}(z) coefficients (z⁰ … z⁻${s}), scale ±${amp.toFixed(2)}`, 14, by + 12);
  // bottom-right: partial power transfer
  let num = 1;
  for (let i = 0; i <= s; i++) num *= 1 - S.c[i] * S.c[i];
  const Pp = new Float64Array(fGrid.length);
  for (let j = 0; j < fGrid.length; j++) {
    let sr = 0, si = 0;
    for (let k = 0; k < F.length; k++) { sr += F[k] * Math.cos(omGrid[j] * k); si -= F[k] * Math.sin(omGrid[j] * k); }
    Pp[j] = num / (sr * sr + si * si);
  }
  const yP = yOf(Pp), yF = yOf(D.P);
  const [y0, y1] = yRange(yP, yF);
  const ax = axes(ctx, { x: 20 + half + 10, y: by, w: half - 10, h: bh - 18 }, { xmin: 0, xmax: FS / 2, ymin: y0, ymax: y1,
    fmtX: (v) => (v / 1000).toFixed(0) + "k", fmtY: () => "", yticks: 3 });
  line(ctx, ax, fGrid, yF, { color: "#9aa1b5", width: 1.2, alpha: 0.6 });
  line(ctx, ax, fGrid, yP, { color: "#8f7bff", width: 2 });
  $("#st-label").textContent = `stage ${s} / ${S.N} · interfaces used c₀…c${sub(s)}`;
  const lg = $("#step-log");
  lg.textContent = S.log.slice(-40).join("\n");
  lg.scrollTop = lg.scrollHeight;
  $("#lpc-check").innerHTML = `closed glottis check: max |polyFromReflection([−1, c₁…c_N]) − stepUp(−c₁…−c_N)| = ` +
    `<span class="${D.lpcDiff < 1e-12 ? "good" : "meh"}">${fmtE(D.lpcDiff)}</span> — the LPC (Levinson) recursion is this recursion with k<sub>m</sub> = −c<sub>m</sub>.`;
}

function drawAll() {
  showEnds();
  mapText();
  drawTube(); drawFilm(); drawMorph(); drawP(); drawT(); drawMap(); drawColour(); drawChecks(); drawStep();
}

// ------------------------------------------------------------------ events
function wire() {
  $("#N").addEventListener("input", (e) => {
    const N = +e.target.value, old = S.c;
    const c = new Array(N + 1).fill(0);
    c[0] = old[0]; c[N] = old[old.length - 1];
    for (let i = 1; i < N; i++) c[i] = i < old.length - 1 ? old[i] : 0;
    setC(c);
  });
  $("#coefs").addEventListener("input", (e) => {
    const i = +e.target.dataset.i; if (!i) return;
    S.c[i] = +e.target.value;
    $(`#cv${i}`).textContent = S.c[i].toFixed(3);
    resetSteps(S.stage); update();
  });
  $("#c0").addEventListener("input", (e) => { S.c[0] = +e.target.value; resetSteps(S.stage); update(); });
  $("#cN").addEventListener("input", (e) => { S.c[S.N] = +e.target.value; resetSteps(S.stage); update(); });
  $("#apply").addEventListener("click", () => preset($("#preset").value));
  $("#preset").addEventListener("change", () => preset($("#preset").value));
  $("#fmode").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    for (const x of $("#fmode").querySelectorAll("button")) x.classList.toggle("on", x === b);
    S.fmode = b.dataset.v; update();
  });
  $("#mapsel").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    setMap(b.dataset.v);
  });
  $("#ill").addEventListener("change", (e) => { S.ill = e.target.value; update(); });
  $("#morph").addEventListener("input", (e) => { S.morph = +e.target.value; stopMorph(); drawMorph(); });
  $("#morph-play").addEventListener("click", () => (S.playing ? stopMorph() : startMorph()));
  $("#scale").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    for (const x of $("#scale").querySelectorAll("button")) x.classList.toggle("on", x === b);
    S.db = b.dataset.v === "db"; update();
  });
  // hover linking
  const hov = (id, fn) => {
    const cv = $(id);
    cv.addEventListener("mousemove", (e) => {
      const r = cv.getBoundingClientRect(), box = BOX(r.width, r.height);
      const u = (e.clientX - r.left - box.x) / box.w;
      if (u < 0 || u > 1) { S.hoverNu = S.hoverF = null; } else fn(u);
      drawP(); drawT(); drawMap();
    });
    cv.addEventListener("mouseleave", () => { S.hoverNu = S.hoverF = null; drawP(); drawT(); drawMap(); });
  };
  hov("#cv-T", (u) => { S.hoverNu = (400 + 350 * u) * 1e12; S.hoverF = null; });
  hov("#cv-P", (u) => { S.hoverF = u * FS / 2; S.hoverNu = null; });
  // steps
  $("#st-reset").addEventListener("click", () => { stopAuto(); resetSteps(0); drawStep(); });
  $("#st-up").addEventListener("click", () => { stopAuto(); stepUpOnce(); drawStep(); });
  $("#st-down").addEventListener("click", () => { stopAuto(); stepDownOnce(); drawStep(); });
  $("#st-auto").addEventListener("click", () => {
    if (S.auto) return stopAuto();
    const dir = S.stage >= S.N ? -1 : 1;
    $("#st-auto").textContent = "■ stop";
    S.auto = setInterval(() => {
      const ok = dir > 0 ? stepUpOnce() : stepDownOnce();
      drawStep();
      if (!ok || (dir < 0 && S.stage === 0) || (dir > 0 && S.stage === S.N)) stopAuto();
    }, 650);
  });
  window.addEventListener("resize", () => update());
}
function setMap(m) {
  if (!MAPPINGS[m]) return;
  S.map = m;
  try { const u = new URL(location.href); u.searchParams.set("mapping", m); history.replaceState(null, "", u); } catch (e) { /* file:// etc. */ }
  update();
}
function stopAuto() { if (S.auto) clearInterval(S.auto); S.auto = null; $("#st-auto").textContent = "▶ auto"; }

let raf = 0, tStart = 0;
function startMorph() {
  S.playing = true; $("#morph-play").textContent = "■ stop";
  tStart = performance.now() - Math.acos(1 - 2 * S.morph) / Math.PI * 2600;
  const loop = (now) => {
    if (!S.playing) return;
    S.morph = 0.5 - 0.5 * Math.cos(Math.PI * (now - tStart) / 2600);
    $("#morph").value = S.morph;
    drawMorph();
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
}
function stopMorph() { S.playing = false; cancelAnimationFrame(raf); $("#morph-play").textContent = "▶ animate"; }

async function main() {
  const qm = new URLSearchParams(location.search).get("mapping");
  if (qm && MAPPINGS[qm]) S.map = qm;
  wire();
  try { await loadPhysicsData("data/"); S.colourOK = true; } catch (e) { S.colourOK = false; }
  try { S.vowels = (await (await fetch("data/vowels.json")).json()).items || []; } catch (e) { S.vowels = []; }
  preset("ah");
}
main();
