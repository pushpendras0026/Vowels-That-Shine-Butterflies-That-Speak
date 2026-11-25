/**
 * garden_core.js — pure (DOM-free, three-free) logic for the Butterfly Garden (web/garden.html).
 * Node-testable: tools/test_garden_core.mjs.  Physics only from ./physics.js (CONTRACT §6).
 *
 *  - makeRng(seed)             deterministic PRNG (mulberry32 + Box–Muller), seed = number or string
 *  - randomStack(rng, N, mode) random Goupillaud stack like core/stacks.random_goupillaud (incident n0 = 1)
 *  - colourEvaluator(...)      FAST exact normal-incidence colour of a Goupillaud stack via the isomorphism
 *                              T(ν) = Π(1−c_i²)/|D(e^{jω})|², ω = 4π·s·D_OPT·ν/c (CONTRACT §2) — identical to
 *                              Abelès TMM at θ = 0 (checked in the node test against physics.filmColour)
 *  - createDesigner(opts)      port of core/inverse.design_stacks (random restarts + atlas seeds + projected
 *                              gradient on log n in bounds, cost ΔE00 at normal incidence; greedy farthest-point
 *                              selection in (F1,F2) so metamers sound different). Stepped: step(budgetMs).
 *  - evolveStep(...)           mutation of log n (and optionally the layer count), always kept in bounds
 *  - parseWord / singSamples   word → Hillenbrand vowel sequence → films → sung audio (reflection-coefficient
 *                              interpolation, glottal source, all-pole filter with state carried across blocks)
 *  - voiceOf / voiceFeatures / nearestVowel
 */
import {
  FS, ORDER, D_OPT_NM, N_MIN, N_MAX, MATERIALS,
  reflectionFromMedia, polyFromReflection, formantsFromPoly, voiceOfFilm, filmColour,
  xyzToLab, deltaE00, getPhysicsData, stepDown, stepUp, glottalSource, vowelMedia, filmFromMedia,
} from "./physics.js";

// ----------------------------------------------------------------------------- PRNG
function hashSeed(seed) {
  if (typeof seed === "number" && Number.isFinite(seed)) return (Math.floor(seed) >>> 0) ^ 0x9E3779B9;
  const s = String(seed);
  let h = 2166136261 >>> 0; // FNV-1a
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}

/** Deterministic PRNG: same seed ⇒ same sequence (mulberry32). */
export function makeRng(seed = 1) {
  let s = hashSeed(seed);
  const random = () => {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const rng = {
    random,
    uniform: (a, b) => a + (b - a) * random(),
    int: (n) => Math.floor(random() * n),
    gauss: () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random()),
    choice: (arr) => arr[Math.floor(random() * arr.length)],
    fork: (tag = "") => makeRng(`${Math.floor(random() * 4294967296)}:${tag}`),
  };
  return rng;
}

// ----------------------------------------------------------------------------- stacks
export const MODES = ["realizable", "materials", "ideal"];
export const IDEAL_LO = 0.2, IDEAL_HI = 20.0; // design_stacks bounds for mode "ideal"
export const LAYERS_MIN = 2, LAYERS_MAX = 24;

export function boundsFor(mode) {
  return mode === "ideal" ? [IDEAL_LO, IDEAL_HI] : [N_MIN, N_MAX];
}

export function materialValues(names = null) {
  const ent = Object.entries(MATERIALS).filter(([k]) => !names || names.includes(k));
  const v = ent.map(([, x]) => x).sort((a, b) => a - b);
  return v.length ? v : Object.values(MATERIALS).sort((a, b) => a - b);
}

/**
 * Random stack n (length N+2, n[0] = 1 incident air). arm: "bimodal" (each layer low 1.0–1.25 or high 2.1–2.5,
 * like the atlas high-contrast arm — more often ≥2 formants), "loguniform", or "mixed" (50/50).
 * mode "materials": each layer/substrate from the materials palette; "ideal": log-uniform in [0.5, 8].
 */
export function randomStack(rng, N = ORDER, mode = "realizable", { arm = "mixed", materials = null } = {}) {
  const n = new Float64Array(N + 2);
  n[0] = 1.0;
  if (mode === "materials") {
    const vals = materialValues(materials);
    for (let i = 1; i < N + 2; i++) n[i] = rng.choice(vals);
    return n;
  }
  if (mode === "ideal") {
    for (let i = 1; i < N + 2; i++) n[i] = Math.exp(rng.uniform(Math.log(0.5), Math.log(8)));
    return n;
  }
  const a = arm === "mixed" ? (rng.random() < 0.5 ? "bimodal" : "loguniform") : arm;
  for (let i = 1; i < N + 2; i++) {
    n[i] = a === "bimodal"
      ? (rng.random() < 0.5 ? rng.uniform(2.1, N_MAX) : rng.uniform(N_MIN, 1.25))
      : Math.exp(rng.uniform(Math.log(N_MIN), Math.log(N_MAX)));
  }
  return n;
}

/** Physical layer thicknesses for equal optical thickness scale·D_OPT (scale = 1 ⇒ Goupillaud, CONTRACT §1). */
export function goupD(n, scale = 1.0) {
  const N = n.length - 2, d = new Float64Array(N);
  for (let i = 0; i < N; i++) d[i] = scale * D_OPT_NM / n[i + 1];
  return d;
}

/** true iff every layer has optical thickness D_OPT (the canonical mapping ⇒ the voice is exact at θ = 0). */
export function isGoupillaud(n, d) {
  if (d.length !== n.length - 2) return false;
  for (let i = 0; i < d.length; i++) {
    const nr = typeof n[i + 1] === "number" ? n[i + 1] : NaN;
    if (!(Math.abs(nr * d[i] - D_OPT_NM) <= 1e-6 * D_OPT_NM)) return false;
  }
  return true;
}

// ----------------------------------------------------------------------------- voice
/**
 * Voice of a film at angle θ. Exact (characteristic polynomial D(z), gain √Π(1−c²)) for a Goupillaud stack at
 * θ = 0; otherwise physics.voiceOfFilm (all-pole LPC fit of T, order max(16, N)) ⇒ approximate.
 */
export function voiceOf(n, d, thetaDeg = 0) {
  const N = n.length - 2;
  if (isGoupillaud(n, d) && Math.abs(thetaDeg) < 1e-9) {
    const c = reflectionFromMedia(n);
    let g = 1;
    for (let i = 0; i < c.length; i++) g *= 1 - c[i] * c[i];
    return { a: polyFromReflection(c), gain: Math.sqrt(g), exact: true, method: "exact D(z) (Goupillaud, θ=0)" };
  }
  const p = Math.max(ORDER, N);
  const { a, gain } = voiceOfFilm(n, d, thetaDeg, p);
  return { a, gain, exact: false, method: `LPC fit of T(ν) at θ=${(+thetaDeg).toFixed(1)}° (order ${p})` };
}

/** First two maxima of the all-pole envelope 1/|A(e^{jω})|² above 90 Hz (Hz; null if absent). */
export function envelopePeaks(a, nPts = 512) {
  const env = new Float64Array(nPts + 1);
  for (let j = 0; j <= nPts; j++) {
    const w = Math.PI * j / nPts;
    let re = 0, im = 0;
    for (let k = 0; k < a.length; k++) { re += a[k] * Math.cos(w * k); im -= a[k] * Math.sin(w * k); }
    env[j] = 1 / Math.max(re * re + im * im, 1e-300);
  }
  const peaks = [];
  for (let j = 1; j < nPts; j++) {
    const f = j * (FS / 2) / nPts;
    if (f > 90 && env[j] > env[j - 1] && env[j] >= env[j + 1]) peaks.push(f);
    if (peaks.length === 2) break;
  }
  return peaks;
}

/**
 * Formants (CONTRACT §6 formantsFromPoly: B < 600 Hz) and envelope peaks. F1/F2 = strict formants when ≥2 exist
 * (strict = true), else envelope peaks (broad resonances ⇒ approximate).
 */
export function voiceFeatures(a) {
  const { F, B } = formantsFromPoly(a, FS);
  const peaks = envelopePeaks(a);
  const strict = F.length >= 2;
  const F1 = strict ? F[0] : (peaks[0] ?? null);
  const F2 = strict ? F[1] : (peaks[1] ?? null);
  return { F: Array.from(F), B: Array.from(B), peaks, F1, F2, strict };
}

/** Nearest Hillenbrand vowel by log-F1/F2 distance (approximate perceptual proxy). */
export function nearestVowel(F1, F2, vowels, group = null) {
  if (!(F1 > 0) || !(F2 > 0)) return null;
  let best = null, bd = Infinity;
  for (const v of vowels.items) {
    if (group && v.group !== group) continue;
    const d = Math.hypot(Math.log(F1 / v.F1), Math.log(F2 / v.F2));
    if (d < bd) { bd = d; best = v; }
  }
  return best ? { item: best, dist: bd } : null;
}

// ----------------------------------------------------------------------------- fast colour (normal incidence)
const _evalCache = new Map();
/**
 * Returns colourOf(n) -> {XYZ, Lab} for a stack with equal optical thickness scale·D_OPT at θ = 0, via
 * T = Π(1−c²)/|D(e^{jω})|² (exact isomorphism), R = 1 − T (lossless). stride: use every stride-th CIE sample
 * (weights ×stride) for the optimiser; stride 1 = the full 0.5 nm grid (same numbers as physics.filmColour).
 */
export function colourEvaluator(illuminant = "D65", quantity = "R", scale = 1.0, stride = 1, maxN = LAYERS_MAX) {
  const key = `${illuminant}|${quantity}|${scale}|${stride}|${maxN}`;
  if (_evalCache.has(key)) return _evalCache.get(key);
  const P = getPhysicsData();
  if (!P) throw new Error("garden_core: call loadPhysicsData()/setPhysicsData() first");
  const I = P.ill[illuminant];
  if (!I) throw new Error(`unknown illuminant ${illuminant}`);
  const idx = [];
  for (let i = 0; i < P.wl.length; i += stride) idx.push(i);
  const M = idx.length, K = maxN + 1;
  const cosT = new Float64Array(M * K), sinT = new Float64Array(M * K);
  const wx = new Float64Array(M), wy = new Float64Array(M), wz = new Float64Array(M);
  let sx = 0, sy = 0, sz = 0;
  for (let j = 0; j < M; j++) {
    const i = idx[j];
    const w = 4 * Math.PI * scale * D_OPT_NM / P.wl[i]; // ω = 2δ (nm cancel)
    for (let k = 0; k < K; k++) { cosT[j * K + k] = Math.cos(w * k); sinT[j * K + k] = Math.sin(w * k); }
    wx[j] = I.wx[i] * stride; wy[j] = I.wy[i] * stride; wz[j] = I.wz[i] * stride;
    sx += wx[j]; sy += wy[j]; sz += wz[j];
  }
  const isT = quantity === "T";
  const fn = (n) => {
    const c = reflectionFromMedia(n);
    const D = polyFromReflection(c);
    if (D.length > K) throw new Error("colourEvaluator: too many layers");
    let num = 1;
    for (let i = 0; i < c.length; i++) num *= 1 - c[i] * c[i];
    let X = 0, Y = 0, Z = 0;
    const L = D.length;
    for (let j = 0; j < M; j++) {
      let re = 0, im = 0;
      const o = j * K;
      for (let k = 0; k < L; k++) { re += D[k] * cosT[o + k]; im -= D[k] * sinT[o + k]; }
      const T = num / (re * re + im * im);
      X += T * wx[j]; Y += T * wy[j]; Z += T * wz[j];
    }
    const XYZ = isT ? [X, Y, Z] : [sx - X, sy - Y, sz - Z];
    return { XYZ, Lab: xyzToLab(XYZ, illuminant) };
  };
  _evalCache.set(key, fn);
  return fn;
}

/** sRGB hex (absolute, D65-referred sRGB) → XYZ (Y ≤ 100) → CIELAB under `illuminant`'s white. */
export function hexToLab(hex, illuminant = "D65") {
  const h = hex.replace("#", "");
  const rgb = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  const lin = rgb.map((u) => (u <= 0.04045 ? u / 12.92 : Math.pow((u + 0.055) / 1.055, 2.4)));
  const P = getPhysicsData();
  const Mi = inv3(P && P.M ? P.M : [[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560], [0.0556434, -0.2040259, 1.0572252]]);
  const XYZ = [0, 1, 2].map((i) => 100 * (Mi[i][0] * lin[0] + Mi[i][1] * lin[1] + Mi[i][2] * lin[2]));
  return xyzToLab(XYZ, illuminant);
}
function inv3(m) {
  const [a, b, c] = m[0], [d, e, f] = m[1], [g, h, i] = m[2];
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
    [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
    [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]];
}

// ----------------------------------------------------------------------------- inverse design
/** Atlas entries nearest to targetLab (ΔE00; uses LabR for quantity R, Lab for T). Returns [{index, dE}]. */
export function nearestAtlas(atlas, targetLab, quantity = "R", k = 8, exclude = []) {
  if (!atlas || !atlas.items) return [];
  const key = quantity === "T" ? "Lab" : "LabR";
  const out = [];
  atlas.items.forEach((it, index) => {
    if (exclude.includes(index) || !it[key]) return;
    out.push({ index, dE: deltaE00(it[key], targetLab) });
  });
  out.sort((x, y) => x.dE - y.dE);
  return out.slice(0, k);
}

function projectedGradient(cost, x0, lo, hi, { maxIter = 160, stopAt = 0.6, h = 1e-5 } = {}) {
  const n = x0.length;
  let x = Float64Array.from(x0, (v) => Math.min(hi, Math.max(lo, v)));
  let f = cost(x);
  let step = 0.05, evals = 1;
  const g = new Float64Array(n), xt = new Float64Array(n);
  let gPrev = null, xPrev = null;
  for (let it = 0; it < maxIter && f > stopAt; it++) {
    for (let i = 0; i < n; i++) { // forward differences, stepping inward at the upper bound
      const hi_ = x[i] + h > hi ? -h : h;
      xt.set(x); xt[i] += hi_;
      g[i] = (cost(xt) - f) / hi_;
      evals++;
    }
    if (gPrev) { // Barzilai–Borwein step
      let sy = 0, ss = 0;
      for (let i = 0; i < n; i++) { const s = x[i] - xPrev[i], y = g[i] - gPrev[i]; sy += s * y; ss += s * s; }
      if (sy > 1e-12) step = Math.min(1.0, Math.max(1e-4, ss / sy));
    }
    let gn = 0;
    for (let i = 0; i < n; i++) gn += g[i] * g[i];
    if (gn < 1e-14) break;
    let accepted = false;
    for (let bt = 0; bt < 12; bt++) {
      let dec = 0;
      for (let i = 0; i < n; i++) { xt[i] = Math.min(hi, Math.max(lo, x[i] - step * g[i])); dec += g[i] * (x[i] - xt[i]); }
      const ft = cost(xt); evals++;
      if (ft <= f - 1e-4 * dec) { xPrev = Float64Array.from(x); gPrev = Float64Array.from(g); x = Float64Array.from(xt); f = ft; accepted = true; break; }
      step *= 0.35;
    }
    if (!accepted) break;
  }
  return { x, f, evals };
}

function discreteDescent(cost, x0, vals, rng, maxSweeps = 6) {
  const x = Float64Array.from(x0);
  let f = cost(x), evals = 1;
  for (let sw = 0; sw < maxSweeps; sw++) {
    let improved = false;
    const order = Array.from(x, (_, i) => i).sort(() => rng.random() - 0.5);
    for (const i of order) {
      const keep = x[i];
      let bv = keep, bf = f;
      for (const v of vals) {
        if (v === keep) continue;
        x[i] = v; const fv = cost(x); evals++;
        if (fv < bf - 1e-9) { bf = fv; bv = v; }
      }
      x[i] = bv;
      if (bv !== keep) { f = bf; improved = true; }
    }
    if (!improved) break;
  }
  return { x, f, evals };
}

/** Greedy farthest-point selection in (F1,F2) (port of core/inverse._diverse); prefers ≥2 strict formants. */
export function diverse(found, k) {
  if (found.length <= k) return found.slice();
  const strictPool = found.filter((s) => s.voice.strict);
  const pool = strictPool.length >= k ? strictPool : found;
  const pts = pool.map((s) => [s.voice.F1 || 0, s.voice.F2 || 0]);
  let first = 0;
  pool.forEach((s, i) => { if (s.dE < pool[first].dE) first = i; });
  const chosen = [first];
  while (chosen.length < k) {
    let bi = -1, bd = -1;
    for (let i = 0; i < pool.length; i++) {
      if (chosen.includes(i)) continue;
      let dmin = Infinity;
      for (const c of chosen) dmin = Math.min(dmin, Math.hypot(pts[i][0] - pts[c][0], pts[i][1] - pts[c][1]));
      if (dmin > bd) { bd = dmin; bi = i; }
    }
    if (bi < 0) break;
    chosen.push(bi);
  }
  return chosen.map((i) => pool[i]);
}

/**
 * Inverse designer (port of core/inverse.design_stacks). Usage:
 *   const D = createDesigner({targetLab, nLayers:16, mode:"realizable", illuminant:"D65", quantity:"R", seed:1,
 *                             atlas, excludeAtlas:[i], nSolutions:5});
 *   while (!D.step(30)) {}   // ~30 ms chunks (setTimeout / requestIdleCallback in the browser)
 *   D.results  -> [{n, d, Lab, dE (full-grid physics.filmColour ΔE00), a, gain, voice:{F,B,F1,F2,peaks,strict}}]
 * If nothing reaches tol after `retargetAfter` restarts and autoRetarget, the target becomes the best reachable
 * colour (D.retargeted = true) and metamers of that colour are collected.
 */
export function createDesigner(opts) {
  const o = {
    nLayers: ORDER, mode: "realizable", illuminant: "D65", quantity: "R", scale: 1.0, seed: 0,
    nSolutions: 5, tol: 2.0, restarts: 60, maxIter: 160, atlas: null, atlasSeeds: 8, excludeAtlas: [],
    materials: null, autoRetarget: true, retargetAfter: 14, stride: 4, ...opts,
  };
  const N = o.nLayers;
  const rng = makeRng(`design:${o.seed}`);
  const [nlo, nhi] = boundsFor(o.mode);
  const lo = Math.log(nlo), hi = Math.log(nhi);
  const coarse = colourEvaluator(o.illuminant, o.quantity, o.scale, o.stride);
  const fine = colourEvaluator(o.illuminant, o.quantity, o.scale, 1);
  const st = {
    target: Float64Array.from(o.targetLab), originalTarget: Array.from(o.targetLab), retargeted: false,
    starts: [], restartsDone: 0, found: [], strict: 0, best: null, evals: 0, done: false, results: [], t0: Date.now(),
  };
  const unpack = (x) => { const n = new Float64Array(N + 2); n[0] = 1; for (let i = 0; i <= N; i++) n[i + 1] = Math.exp(x[i]); return n; };
  const unpackLin = (x) => { const n = new Float64Array(N + 2); n[0] = 1; n.set(x, 1); return n; };

  // queue of starting points: nearest atlas entries (only when compatible: 16 layers, realizable bounds) first
  if (o.atlas && N === 16 && o.mode === "realizable") {
    for (const { index } of nearestAtlas(o.atlas, o.targetLab, o.quantity, o.atlasSeeds, o.excludeAtlas)) {
      const nn = o.atlas.items[index].n;
      if (nn.length === N + 2) st.starts.push({ kind: "atlas", index, n: Float64Array.from(nn) });
    }
  }
  const nextStart = () => {
    if (st.starts.length) return st.starts.shift();
    return { kind: "random", n: randomStack(rng, N, o.mode, { materials: o.materials }) };
  };

  function runOne() {
    const s = nextStart();
    let n, f;
    if (o.mode === "materials") {
      const vals = materialValues(o.materials);
      const cost = (x) => deltaE00(coarse(unpackLin(x)).Lab, st.target);
      const r = discreteDescent(cost, s.n.subarray(1), vals, rng);
      n = unpackLin(r.x); f = r.f; st.evals += r.evals;
    } else {
      const cost = (x) => deltaE00(coarse(unpack(x)).Lab, st.target);
      const x0 = Float64Array.from(s.n.subarray(1), Math.log);
      let r = projectedGradient(cost, x0, lo, hi, { maxIter: o.maxIter });
      st.evals += r.evals;
      // confirm on the full grid; polish there if needed
      let fx = deltaE00(fine(unpack(r.x)).Lab, st.target);
      if (fx >= 0.9 * o.tol && r.f < 3 * o.tol) {
        const costF = (x) => deltaE00(fine(unpack(x)).Lab, st.target);
        const r2 = projectedGradient(costF, r.x, lo, hi, { maxIter: 40, stopAt: 0.5 });
        st.evals += r2.evals; r = r2; fx = r2.f;
      }
      n = unpack(r.x); f = fx;
    }
    st.restartsDone++;
    const cand = { n, f, start: s.kind, atlasIndex: s.index };
    if (!st.best || f < st.best.f) st.best = cand;
    if (f < o.tol) {
      cand.strict = formantsFromPoly(polyFromReflection(reflectionFromMedia(n)), FS).F.length >= 2;
      if (cand.strict) st.strict++;
      st.found.push(cand);
    }
  }
  const enough = () => (st.found.length >= 3 * o.nSolutions && st.strict >= o.nSolutions) || st.found.length >= 8 * o.nSolutions;

  function finalize() {
    const d = (n) => goupD(n, o.scale);
    let pool = st.found.map((c) => {
      const dd = d(c.n);
      const col = filmColour(c.n, dd, 0, o.illuminant, o.quantity); // independent check: Abelès TMM, full grid
      const v = voiceOf(c.n, dd, 0);
      return { n: c.n, d: dd, Lab: col.Lab, hex: col.hex, rgbAbs: col.rgbAbs, dE: deltaE00(col.Lab, st.target),
        a: v.a, gain: v.gain, exact: v.exact, voice: voiceFeatures(v.a), start: c.start, atlasIndex: c.atlasIndex };
    }).filter((s) => s.dE < o.tol);
    // drop near-duplicates (same voice) before diversity selection
    const uniq = [];
    for (const s of pool) {
      if (!uniq.some((u) => Math.abs((u.voice.F1 || 0) - (s.voice.F1 || 0)) < 15 && Math.abs((u.voice.F2 || 0) - (s.voice.F2 || 0)) < 15)) uniq.push(s);
    }
    st.results = diverse(uniq, o.nSolutions);
    st.done = true;
  }

  return {
    get results() { return st.results; },
    get target() { return Array.from(st.target); },
    get originalTarget() { return st.originalTarget; },
    get retargeted() { return st.retargeted; },
    get retargetDE() { return st.retargetDE ?? null; },
    get best() { return st.best; },
    get progress() { return { restarts: st.restartsDone, of: o.restarts, found: st.found.length, evals: st.evals, ms: Date.now() - st.t0, bestDE: st.best ? st.best.f : null }; },
    get done() { return st.done; },
    /** Run restarts for about budgetMs; returns true when finished. */
    step(budgetMs = 30) {
      if (st.done) return true;
      const t0 = Date.now();
      do {
        if (st.restartsDone >= o.restarts || enough()) { finalize(); return true; }
        runOne();
        if (o.autoRetarget && !st.retargeted && st.found.length === 0 && st.restartsDone >= o.retargetAfter && st.best) {
          // target unreachable: aim at the best reachable colour instead (reported to the user)
          st.target = Float64Array.from(fine(st.best.n).Lab);
          st.retargeted = true;
          st.retargetDE = st.best.f; // ΔE00 of the best reachable colour to the original target
          st.best.f = 0;
          st.found.push(st.best);
        }
      } while (Date.now() - t0 < budgetMs);
      return false;
    },
    runSync(maxMs = 1e9) { const t0 = Date.now(); while (!this.step(50)) { if (Date.now() - t0 > maxMs) { finalize(); break; } } return st.results; },
  };
}

// ----------------------------------------------------------------------------- evolution
/**
 * One mutation: Gaussian step σ on log n of every layer + substrate (incident n0 kept), clamped to the mode's
 * bounds; materials mode re-draws ~1/4 of the layers from the palette. mutateLayers: with probability pLayer
 * insert (copy of a neighbour) or delete one layer, keeping N in [LAYERS_MIN, LAYERS_MAX].
 */
export function evolveStep(n, rng, { sigma = 0.08, mode = "realizable", mutateLayers = false, pLayer = 0.35, materials = null } = {}) {
  const [lo, hi] = boundsFor(mode);
  let arr = Array.from(n);
  if (mode === "materials") {
    const vals = materialValues(materials);
    for (let i = 1; i < arr.length; i++) if (rng.random() < 0.25) arr[i] = rng.choice(vals);
  } else {
    for (let i = 1; i < arr.length; i++) arr[i] = Math.min(hi, Math.max(lo, arr[i] * Math.exp(sigma * rng.gauss())));
  }
  if (mutateLayers && rng.random() < pLayer) {
    const N = arr.length - 2;
    const grow = N <= LAYERS_MIN ? true : N >= LAYERS_MAX ? false : rng.random() < 0.5;
    const pos = 1 + rng.int(N); // a layer index
    if (grow) arr.splice(pos, 0, arr[pos]); else arr.splice(pos, 1);
  }
  return Float64Array.from(arr);
}

// ----------------------------------------------------------------------------- words → vowels → song
const LETTER_GUESS = [ // rough spelling → Hillenbrand vowel guesses (ARTISTIC fallback for free text)
  ["ee", "iy"], ["ea", "iy"], ["ie", "iy"], ["oo", "uw"], ["ou", "aw"], ["ow", "oa"], ["oa", "oa"], ["ai", "ei"],
  ["ay", "ei"], ["ei", "ei"], ["er", "er"], ["ir", "er"], ["ur", "er"], ["au", "aw"], ["aw", "aw"], ["oi", "oa"],
  ["a", "ae"], ["e", "eh"], ["i", "ih"], ["o", "ah"], ["u", "uh"], ["y", "iy"],
];
const SINGLE = { a: "ah", e: "ei", i: "iy", o: "oa", u: "uw" }; // "a e i o u" as continental vowels

/**
 * Text → vowel codes (vowels.json `vowel`). Each token may be an example word (heed, hid, …), an ARPAbet-like
 * code (iy, ih, ei, eh, ae, ah, aw, oa, oo, uw, uh, er), an IPA symbol, a single letter a/e/i/o/u, or any word
 * (vowel letters guessed from spelling — artistic). Returns [{code, token, how}].
 */
export function parseWord(text, vowels) {
  const items = vowels.items;
  const codes = [...new Set(items.map((v) => v.vowel))];
  const byExample = new Map(), byIpa = new Map();
  for (const v of items) { byExample.set(v.example.toLowerCase().replace(/[^a-z]/g, ""), v.vowel); byIpa.set(v.ipa, v.vowel); }
  const out = [];
  for (const raw of String(text).split(/[\s,;/\-]+/)) {
    const tok = raw.trim();
    if (!tok) continue;
    const low = tok.toLowerCase();
    const plain = low.replace(/[^a-z]/g, "");
    if (byIpa.has(tok)) { out.push({ code: byIpa.get(tok), token: tok, how: "ipa" }); continue; }
    if (codes.includes(low)) { out.push({ code: low, token: tok, how: "code" }); continue; }
    if (byExample.has(plain)) { out.push({ code: byExample.get(plain), token: tok, how: "word" }); continue; }
    if (plain.length === 1 && SINGLE[plain]) { out.push({ code: SINGLE[plain], token: tok, how: "letter" }); continue; }
    let i = 0, any = false;
    while (i < plain.length) {
      const hit = LETTER_GUESS.find(([g]) => plain.startsWith(g, i));
      if (hit && codes.includes(hit[1])) {
        if (!(hit[0] === "y" && i === 0)) { out.push({ code: hit[1], token: tok, how: "spelling" }); any = true; }
        i += hit[0].length;
      } else i++;
    }
    if (!any && plain.length) out.push({ code: "uh", token: tok, how: "spelling" });
  }
  return out;
}

/** Vowel item for code & speaker group (vowels.json). */
export function vowelItem(vowels, code, group = "women") {
  return vowels.items.find((v) => v.vowel === code && v.group === group) || vowels.items.find((v) => v.vowel === code);
}

/** Hillenbrand vowel LPC → finite-glottis media → film (mode) with Goupillaud thicknesses. */
export function vowelFilm(a, mode = "realizable") {
  const n = filmFromMedia(vowelMedia(a), mode);
  return { n, d: goupD(n, 1.0) };
}

function unitGain(a) { // gain that gives the all-pole filter unit mean power (so vowels sound equally loud)
  let s = 0; const M = 256;
  for (let j = 0; j < M; j++) {
    const w = Math.PI * (j + 0.5) / M;
    let re = 0, im = 0;
    for (let k = 0; k < a.length; k++) { re += a[k] * Math.cos(w * k); im -= a[k] * Math.sin(w * k); }
    s += 1 / (re * re + im * im);
  }
  return 1 / Math.sqrt(s / M);
}

/**
 * Sing a sequence of all-pole polynomials: glottal source (Rosenberg derivative, CONTRACT §5) through an all-pole
 * filter whose reflection coefficients k = stepDown(a) are interpolated (smoothstep) between consecutive vowels
 * during `trans` seconds — always stable. Filter state is carried across 5 ms blocks (no clicks).
 * Returns {samples: Float32Array (FS), segments: [{t0, t1}], fs}.
 */
export function singSamples(polys, { f0 = 160, seg = 0.42, trans = 0.09, block = 80 } = {}) {
  const S = polys.length;
  if (!S) return { samples: new Float32Array(0), segments: [], fs: FS };
  const ks = polys.map((a) => Array.from(stepDown(Float64Array.from(a, (v) => v / a[0]))));
  const p = Math.max(...ks.map((k) => k.length));
  for (const k of ks) while (k.length < p) k.push(0);
  const lg = polys.map((a) => Math.log(unitGain(a)));
  const total = Math.round(S * seg * FS);
  const src = glottalSource(f0, FS, total / FS);
  const y = new Float64Array(src.length);
  const hist = new Float64Array(p); // y[t-1..t-p]
  const kk = new Float64Array(p);
  for (let b0 = 0; b0 < y.length; b0 += block) {
    const t = b0 / FS;
    const i = Math.min(S - 1, Math.floor(t / seg));
    const local = t - i * seg;
    let w = 1, prev = i;
    if (i > 0 && local < trans) { prev = i - 1; const u = local / trans; w = u * u * (3 - 2 * u); }
    for (let m = 0; m < p; m++) kk[m] = (1 - w) * ks[prev][m] + w * ks[i][m];
    const a = stepUp(kk);
    const g = Math.exp((1 - w) * lg[prev] + w * lg[i]);
    const end = Math.min(y.length, b0 + block);
    for (let tt = b0; tt < end; tt++) {
      let acc = g * src[tt];
      for (let m = 1; m <= p; m++) acc -= a[m] * hist[m - 1];
      for (let m = p - 1; m > 0; m--) hist[m] = hist[m - 1];
      hist[0] = acc;
      y[tt] = acc;
    }
  }
  let mx = 0;
  for (let i = 0; i < y.length; i++) mx = Math.max(mx, Math.abs(y[i]));
  const out = new Float32Array(y.length);
  const sc = mx > 0 ? 0.9 / mx : 1;
  const fade = Math.min(y.length >> 1, Math.round(0.02 * FS));
  for (let i = 0; i < y.length; i++) {
    let e = 1;
    if (i < fade) e = i / fade; else if (i >= y.length - fade) e = (y.length - 1 - i) / fade;
    out[i] = y[i] * sc * e;
  }
  return { samples: out, segments: polys.map((_, i) => ({ t0: i * seg, t1: (i + 1) * seg })), fs: FS };
}
