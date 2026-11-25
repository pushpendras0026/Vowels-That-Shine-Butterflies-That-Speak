/**
 * lab_core.js — pure (DOM-free, three-free) signal pipeline of the Live Voice Lab.
 * Node-testable: tools/test_lab_core.mjs. Physics only from ./physics.js (CONTRACT §6).
 *
 *   capture (any rate) -> StreamResampler (windowed-sinc, anti-aliased) -> 16 kHz
 *   -> Framer (512-sample frames = 32 ms, hop 256 = 16 ms)
 *   -> frameFeatures (RMS dBFS, zero-crossing rate, normalised-autocorrelation periodicity)
 *   -> VoiceGate (auto-calibrated noise floor, hysteresis, voicing check, hangover, fade level; an
 *      "energetic but aperiodic" path lets fricatives such as /s ʃ f/ update the shape too, flagged `unvoiced`)
 *   -> physics.lpc(frame, 16, 0.97) -> reflection coefficients k (LPC sign, CONTRACT §3)
 *   -> LarSmoother (exponential smoothing of log-area ratios 2·atanh(k) = log-area domain; always stable)
 *   -> a = stepUp(k_s) -> vowelMedia -> filmFromMedia(mode) -> film colour pair R/T + F1/F2 + iso curves,
 *      all at the layer optical thickness of the chosen frequency mapping (CONTRACT §4b: "full" d_opt = 199.86 nm,
 *      Δν = 750 THz, default; "brief" d_opt = 428.27 nm, Δν = 350 THz). The isomorphism is exact for both.
 *
 * Exact vs approximate (CONTRACT §8): everything after `a` is exact physics given the model; the area
 * function of a real voice from LPC is an estimate (lossless tube, pre-emphasis), R_GLOTTIS is illustrative,
 * realizable/materials modes are approximations. Gate & smoothing are signal processing choices.
 */
import * as P from "./physics.js";

export const FRAME = 512;          // 32 ms at 16 kHz
export const HOP = 256;            // 16 ms
export const LPC_ORDER = P.ORDER;  // 16
export const PREEMPH = 0.97;

// ----------------------------------------------------------------------------- WAV
/** Parse a RIFF/WAVE file (PCM 8/16/24/32-bit or IEEE float 32). Returns {sampleRate, data: Float32Array (channel 0)}. */
export function parseWav(buf) {
  const ab = buf instanceof ArrayBuffer ? buf : buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  const v = new DataView(ab);
  const tag = (o) => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3));
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a RIFF/WAVE file");
  let off = 12, fmt = null;
  while (off + 8 <= v.byteLength) {
    const id = tag(off), size = v.getUint32(off + 4, true), body = off + 8;
    if (id === "fmt ") {
      fmt = { format: v.getUint16(body, true), ch: v.getUint16(body + 2, true), sr: v.getUint32(body + 4, true), bits: v.getUint16(body + 14, true) };
      if (fmt.format === 0xfffe && size >= 26) fmt.format = v.getUint16(body + 24, true);
    } else if (id === "data") {
      if (!fmt) throw new Error("WAV: data before fmt");
      const bps = fmt.bits >> 3, frameBytes = bps * fmt.ch;
      const n = Math.floor(Math.min(size, v.byteLength - body) / frameBytes);
      const out = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const p = body + i * frameBytes;
        let s;
        if (fmt.format === 3 && fmt.bits === 32) s = v.getFloat32(p, true);
        else if (fmt.bits === 16) s = v.getInt16(p, true) / 32768;
        else if (fmt.bits === 8) s = (v.getUint8(p) - 128) / 128;
        else if (fmt.bits === 24) { let x = v.getUint8(p) | (v.getUint8(p + 1) << 8) | (v.getUint8(p + 2) << 16); if (x & 0x800000) x |= ~0xffffff; s = x / 8388608; }
        else if (fmt.bits === 32) s = v.getInt32(p, true) / 2147483648;
        else throw new Error(`WAV: unsupported ${fmt.bits}-bit`);
        out[i] = s;
      }
      return { sampleRate: fmt.sr, data: out };
    }
    off = body + size + (size & 1);
  }
  throw new Error("WAV: no data chunk");
}

/** Concatenate clips (Float32Array at fs) separated/surrounded by `gapSec` of digital silence. */
export function concatWithGaps(clips, gapSec = 0.4, fs = P.FS, leadSec = 0.3) {
  const gap = Math.round(gapSec * fs), lead = Math.round(leadSec * fs);
  let total = lead;
  for (const c of clips) total += c.length + gap;
  const out = new Float32Array(total);
  let o = lead;
  const marks = [];
  for (const c of clips) { marks.push([o / fs, (o + c.length) / fs]); out.set(c, o); o += c.length + gap; }
  return { data: out, marks };
}

// ----------------------------------------------------------------------------- resampling
/**
 * Streaming band-limited resampler (windowed sinc, Blackman window, `zeros` zero crossings per side).
 * Cut-off 0.9 × the lower Nyquist, so energy above ~7.2 kHz cannot alias into the 16 kHz LPC band.
 * push(chunk) -> Float32Array of new output samples. Ratio 1 is a pass-through copy.
 */
export class StreamResampler {
  constructor(srcRate, dstRate = P.FS, zeros = 8) {
    this.src = srcRate; this.dst = dstRate;
    this.step = srcRate / dstRate;                         // input samples per output sample
    this.fc = 0.5 * Math.min(1, dstRate / srcRate) * 0.9;  // cycles per input sample
    this.hw = Math.ceil(zeros / (2 * this.fc));            // half-width in input samples
    this.buf = new Float64Array(4096); this.len = 0;       // pending input; buf[0] is absolute index `base`
    this.base = 0; this.t = 0;                             // absolute input time of the next output sample
  }
  push(chunk) {
    if (this.src === this.dst) return Float32Array.from(chunk);
    if (this.len + chunk.length > this.buf.length) {
      const nb = new Float64Array(Math.max(this.buf.length * 2, this.len + chunk.length));
      nb.set(this.buf.subarray(0, this.len)); this.buf = nb;
    }
    this.buf.set(chunk, this.len); this.len += chunk.length;
    const out = [];
    const hw = this.hw, fc2 = 2 * this.fc, buf = this.buf, base = this.base;
    while (this.t + hw < base + this.len) {
      const t = this.t, lo = Math.max(Math.ceil(t - hw), base), hi = Math.floor(t + hw);
      let acc = 0, wsum = 0;
      for (let j = lo; j <= hi; j++) {
        const x = j - t;
        const sx = fc2 * x;
        const sinc = sx === 0 ? 1 : Math.sin(Math.PI * sx) / (Math.PI * sx);
        const u = x / hw;
        const w = 0.42 + 0.5 * Math.cos(Math.PI * u) + 0.08 * Math.cos(2 * Math.PI * u);
        const h = sinc * w;
        acc += h * buf[j - base]; wsum += h;
      }
      out.push(wsum !== 0 ? acc / wsum : 0);
      this.t += this.step;
    }
    const keepFrom = Math.max(base, Math.floor(this.t - hw) - 1);
    const drop = keepFrom - base;
    if (drop > 0) { buf.copyWithin(0, drop, this.len); this.len -= drop; this.base = keepFrom; }
    return Float32Array.from(out);
  }
}

/** Replace non-finite samples by 0 and hard-clip to ±1 (returns the input itself when nothing needs fixing). */
export function sanitize(chunk) {
  let bad = false;
  for (let i = 0; i < chunk.length; i++) { const v = chunk[i]; if (!(v >= -1 && v <= 1)) { bad = true; break; } }
  if (!bad) return chunk;
  const out = new Float32Array(chunk.length);
  for (let i = 0; i < chunk.length; i++) { const v = chunk[i]; out[i] = Number.isFinite(v) ? Math.max(-1, Math.min(1, v)) : 0; }
  return out;
}

// ----------------------------------------------------------------------------- framing
/** Overlapping frames: push(samples, cb) calls cb(Float64Array(frame)) every `hop` samples once `frame` are buffered. */
export class Framer {
  constructor(frame = FRAME, hop = HOP) { this.frame = frame; this.hop = hop; this.buf = new Float64Array(frame); this.n = 0; }
  push(x, cb) {
    for (let i = 0; i < x.length; i++) {
      this.buf[this.n++] = x[i];
      if (this.n === this.frame) {
        const fr = Float64Array.from(this.buf);
        this.buf.copyWithin(0, this.hop, this.frame);
        this.n = this.frame - this.hop;   // state advanced BEFORE the callback: a throwing cb cannot stall framing
        cb(fr);
      }
    }
  }
  reset() { this.n = 0; }
}

// ----------------------------------------------------------------------------- features
/**
 * RMS (dBFS, DC removed), zero-crossing rate (fraction of sample pairs), periodicity = max normalised
 * autocorrelation over pitch lags (fs/500 .. fs/60, i.e. 60–500 Hz).
 */
export function frameFeatures(x, fs = P.FS) {
  const N = x.length;
  let mean = 0;
  for (let i = 0; i < N; i++) mean += x[i];
  mean /= N;
  const y = new Float64Array(N);
  let e = 0, zc = 0;
  for (let i = 0; i < N; i++) { y[i] = x[i] - mean; e += y[i] * y[i]; if (i && (y[i] >= 0) !== (y[i - 1] >= 0)) zc++; }
  const rms = Math.sqrt(e / N);
  let rmsDb = Math.max(-120, 20 * Math.log10(rms + 1e-12));
  if (!Number.isFinite(rmsDb)) rmsDb = -120;
  let periodicity = 0, lagBest = 0;
  if (e > 1e-14) {
    const lmin = Math.floor(fs / 500), lmax = Math.min(Math.ceil(fs / 60), N - 64);
    // energies of the leading/trailing windows for each lag (running sums)
    let e0 = 0, e1 = 0;
    for (let i = 0; i < N - lmin; i++) e0 += y[i] * y[i];
    for (let i = lmin; i < N; i++) e1 += y[i] * y[i];
    for (let L = lmin; L <= lmax; L++) {
      let r = 0;
      for (let i = 0; i < N - L; i++) r += y[i] * y[i + L];
      const nr = r / Math.sqrt(e0 * e1 + 1e-30);
      if (nr > periodicity) { periodicity = nr; lagBest = L; }
      e0 -= y[N - L - 1] * y[N - L - 1];   // window [0, N-L-2] for lag L+1
      e1 -= y[L] * y[L];                   // window [L+1, N-1]
    }
  }
  return { rms, rmsDb, zcr: zc / (N - 1), periodicity, f0: lagBest ? fs / lagBest : 0 };
}

// ----------------------------------------------------------------------------- gate
export const GATE_DEFAULTS = Object.freeze({
  marginOnDb: 12,      // open when RMS > floor + marginOn …
  marginOffDb: 7,      // … stay open while RMS > floor + marginOff (hysteresis)
  absMinDb: -58,       // never open below this level (dBFS)
  minPeriodicity: 0.45,
  maxZcr: 0.30,
  hangover: 4,         // hops (≈64 ms) the gate stays "voiced" after voicing stops (shape held, not updated)
  unvoiced: true,      // energetic but aperiodic frames (fricatives s, ʃ, f …) also update the shape (flag `unvoiced`)
  uvMinFrames: 4,      // … only after ≥ 4 consecutive such hops: an event ≤ 16 ms (click, pop) touches ≤ 3 overlapping
                       //   32 ms frames, so it never paints; a fricative (≥ ~50 ms) paints after ≈ 48 ms
  uvHangover: 3,       // hops the lights stay on after the fricative ends (shape held)
  attack: 0.45, release: 0.09,   // per-hop fade rates of `level` (lights)
  floorInitDb: -70, floorMinDb: -100, floorMaxDb: -25,
});

/** Silence / voicing gate with an auto-calibrated noise floor. update(features) -> state. */
export class VoiceGate {
  constructor(opts = {}) { this.o = { ...GATE_DEFAULTS, ...opts }; this.reset(); }
  set(opts) { Object.assign(this.o, opts); }
  reset() { this.floor = null; this.open = false; this.hang = 0; this.uvRun = 0; this.uvHang = 0; this.level = 0; this.nFrames = 0; this.calib = []; }
  /**
   * Returns {voiced (periodic, incl. hangover), unvoiced (this hop updates via the aperiodic path), active (lights on:
   * voiced or fricative incl. its hangover), update (this hop updates the shape), energyOpen, periodic, floorDb, thrOnDb,
   * thrOffDb, level}. Energy hysteresis (open > floor+marginOn, stay open > floor+marginOff) applies to both paths, so
   * background noise below the threshold never paints; stationary noise is absorbed into the tracked floor.
   */
  update(ftIn) {
    const o = this.o;
    const ft = Number.isFinite(ftIn.rmsDb) ? ftIn : { ...ftIn, rmsDb: -120, periodicity: 0, zcr: 0 };
    this.nFrames++;
    // --- noise floor: first ~0.25 s = calibration (low percentile), then fast-down / slow-up tracking
    if (this.nFrames <= 16) {
      this.calib.push(ft.rmsDb);
      const s = this.calib.slice().sort((a, b) => a - b);
      this.floor = s[Math.floor(0.2 * (s.length - 1))];
    } else {
      const d = ft.rmsDb - this.floor;
      const rate = d < 0 ? 0.25 : (this.open ? 0.0015 : 0.02);
      this.floor += rate * d;
    }
    this.floor = Math.min(o.floorMaxDb, Math.max(o.floorMinDb, this.floor));
    const floor = this.floor;
    const thrOn = Math.max(floor + o.marginOnDb, o.absMinDb);
    const thrOff = Math.max(floor + o.marginOffDb, o.absMinDb - 4);
    const energyOpen = this.open ? ft.rmsDb > thrOff : ft.rmsDb > thrOn;
    const periodic = ft.periodicity >= o.minPeriodicity && ft.zcr <= o.maxZcr;
    const voicedNow = energyOpen && periodic;
    let voiced = voicedNow;
    if (voicedNow) this.hang = o.hangover;
    else if (this.hang > 0) { this.hang--; voiced = true; }
    this.open = energyOpen;
    // aperiodic path: energetic, not periodic, persistent; never while the voiced hangover holds a vowel (breathy
    // vowel tails/onsets must not overwrite the vowel shape)
    const aper = o.unvoiced && energyOpen && !periodic;
    this.uvRun = aper ? this.uvRun + 1 : 0;
    const unvoiced = aper && this.uvRun >= o.uvMinFrames && !voiced;
    if (unvoiced) this.uvHang = o.uvHangover;
    else if (voiced) this.uvHang = 0;
    else if (this.uvHang > 0) this.uvHang--;
    const active = voiced || unvoiced || this.uvHang > 0;
    const target = active ? 1 : 0;
    this.level += (target - this.level) * (target > this.level ? o.attack : o.release);
    if (this.level < 1e-4) this.level = 0;
    return { voiced, unvoiced, active, update: voicedNow || unvoiced, energyOpen, periodic, floorDb: floor, thrOnDb: thrOn, thrOffDb: thrOff, level: this.level };
  }
}

// ----------------------------------------------------------------------------- smoothing
/**
 * Exponential smoothing in the log-area-ratio domain: LAR_m = ln(A_{m+1}/A_m) = 2·atanh(k_m) (CONTRACT §3),
 * i.e. smoothing the log-area profile with A_1 fixed. Any average of LARs maps back to |k| < 1 ⇒ always stable.
 * The gain is smoothed in log. NOT done on raw LPC coefficients (that can produce unstable filters).
 */
export class LarSmoother {
  constructor(alpha = 0.35, kMax = 0.995) { this.alpha = alpha; this.kMax = kMax; this.lar = null; this.lg = 0; this.since = 1e9; }
  reset() { this.lar = null; this.since = 1e9; }
  tick() { this.since++; }                      // call on hops that do not update
  update(k, gain) {
    const p = k.length;
    const snap = this.lar === null || this.since > 30;   // after ≥0.5 s of silence start fresh
    if (snap) this.lar = new Float64Array(p);
    const a = snap ? 1 : this.alpha;
    for (let m = 0; m < p; m++) {
      const km = Math.max(-this.kMax, Math.min(this.kMax, k[m]));
      const L = Math.log((1 + km) / (1 - km));
      this.lar[m] += a * (L - this.lar[m]);
    }
    const lg = Math.log(Math.max(gain, 1e-12));
    this.lg = snap ? lg : this.lg + a * (lg - this.lg);
    this.since = 0;
    return this.current();
  }
  current() {
    if (!this.lar) return null;
    const k = new Float64Array(this.lar.length);
    for (let m = 0; m < k.length; m++) k[m] = Math.tanh(this.lar[m] / 2);
    return { k, a: P.stepUp(k), gain: Math.exp(this.lg) };
  }
}

// ----------------------------------------------------------------------------- physics of one frame
/**
 * Isomorphism curves on a ν grid (Hz) over the visible band, for layers of common optical thickness `dOpt` (nm):
 * every layer d_i = dOpt/n_i (Goupillaud) and ω(ν) = 4π·dOpt·ν/c, i.e. f(ν) = FS·frac(ν/Δν), Δν = c/(2·dOpt).
 *  film  = filmRTNu(n, d, ν).T                       (Abelès transfer matrices on the film of this mode)
 *  tube  = powerTransfer(c(n), ω(ν))                 (tube with the SAME media; exact identity ⇒ coincides)
 *  vowel = powerTransfer(c(m), ω(ν))                 (the voice's finite-glottis tube; = tube in ideal mode)
 *  lpc   = |g/A(e^{jω})|² (closed glottis), scaled to the peak of `vowel` (shape comparison only)
 */
export function isoCurves(a, gain, m, mode = "ideal", nPts = 351, dOpt = P.D_OPT_NM) {
  const nu = P.linspace(P.NU_MIN, P.NU_MAX, nPts);
  const n = P.filmFromMedia(m, mode);
  const d = P.goupillaudD(n.subarray(1, n.length - 1), dOpt);
  const { T } = P.filmRTNu(n, d, nu, 0, "u");
  const om = P.omegaOfNu(nu, dOpt);
  const tube = P.powerTransfer(P.reflectionFromMedia(n), om);
  const vowel = mode === "ideal" ? tube : P.powerTransfer(P.reflectionFromMedia(m), om);
  const lpcEnv = new Float64Array(nPts);
  let maxV = 0, maxL = 0, maxDiff = 0, maxFid = 0;
  for (let j = 0; j < nPts; j++) {
    let sr = 0, si = 0;
    for (let i = 0; i < a.length; i++) { const ph = om[j] * i; sr += a[i] * Math.cos(ph); si -= a[i] * Math.sin(ph); }
    lpcEnv[j] = gain * gain / Math.max(sr * sr + si * si, 1e-30);
    if (lpcEnv[j] > maxL) maxL = lpcEnv[j];
    if (vowel[j] > maxV) maxV = vowel[j];
    maxDiff = Math.max(maxDiff, Math.abs(T[j] - tube[j]));
    maxFid = Math.max(maxFid, Math.abs(T[j] - vowel[j]));
  }
  const sc = maxL > 0 ? maxV / maxL : 1;
  for (let j = 0; j < nPts; j++) lpcEnv[j] *= sc;
  const dnu = P.dnuOf(dOpt);
  return { nu, f: P.fOfNu(nu, dnu), dnu, dOpt, film: T, tube, vowel, lpc: lpcEnv, maxDiff, maxFidelity: maxFid, n, d };
}

/**
 * Reflected AND transmitted colour of the vowel film (CONTRACT §4b pair) from ONE Abelès evaluation.
 * Identical to physics.vowelColour(a, mode, illuminant, "R"|"T", 0, dOpt). Returns {R, T, n, d, m};
 * R/T = {XYZ, Lab, rgb (display, exposure-normalised), hex}.
 */
export function colourPair(a, mode = "realizable", illuminant = "D65", dOpt = P.D_OPT_FULL_NM) {
  const m = P.vowelMedia(a);
  const n = P.filmFromMedia(m, mode);
  const d = P.goupillaudD(n.subarray(1, n.length - 1), dOpt);
  const { R, T } = P.filmRT(n, d, P.getWL(), 0, "u");
  const mk = (S) => { const XYZ = P.spectrumToXYZ(S, illuminant); const rgb = P.displayRGB(XYZ); return { XYZ, Lab: P.xyzToLab(XYZ, illuminant), rgb, hex: P.toHex(rgb) }; };
  return { R: mk(R), T: mk(T), n, d, m };
}

/** {dnu (Hz), dOpt (nm)} of a mapping name ("full" | "brief"), CONTRACT §4b. */
export function mappingOf(name) {
  const mp = P.MAPPINGS[name];
  if (!mp) throw new Error(`unknown mapping ${name}`);
  return mp;
}

/** F1, F2 (Hz) of an LPC polynomial via physics.formantsFromPoly; null when missing. */
export function f1f2(a) {
  try {
    const { F } = P.formantsFromPoly(a, P.FS);
    return [F.length > 0 ? F[0] : null, F.length > 1 ? F[1] : null];
  } catch { return [null, null]; }
}

// ----------------------------------------------------------------------------- full pipeline
function isFiniteResult(r) {
  if (!r.areas || !r.areas.every((v) => Number.isFinite(v) && v > 0)) return false;
  for (const c of [r.colour, r.colourR, r.colourT]) if (c && !(c.XYZ.every(Number.isFinite) && c.Lab.every(Number.isFinite))) return false;
  if (r.iso && !Number.isFinite(r.iso.maxDiff)) return false;
  return true;
}

/**
 * mapping: "full" (default, CONTRACT §4b) | "brief"; mode: film mode; quantity: which of the pair is the main
 * colour (`colour`): "R" reflected (default: realizable R under full-band is the most distinct) | "T" transmitted.
 */
export const PIPE_DEFAULTS = Object.freeze({ mode: "realizable", quantity: "R", mapping: "full", illuminant: "D65", alpha: 0.35, iso: true, isoPoints: 351, colour: true });

/**
 * Whole lab pipeline. pushSamples(chunk at srcRate) -> array of per-hop results (also given to onHop).
 * Result: {t, feat, gate, voiced, unvoiced, active, level, updated, raw:{a,k,gain}|null, sm:{a,k,gain}|null, m, areas,
 *          F1, F2, colour (main view = colourR or colourT), colourR, colourT: {rgb,hex,Lab,XYZ}|null, mapping, iso|null}
 * `unvoiced`: this hop updated the shape through the aperiodic (fricative) path. `active`: lights on.
 * Fields after `updated` describe the most recent updated (smoothed) shape: held while silent, so lights fade.
 */
export class LabPipeline {
  constructor(srcRate = P.FS, opts = {}, gateOpts = {}) {
    this.opts = { ...PIPE_DEFAULTS, ...opts };
    this.gate = new VoiceGate(gateOpts);
    this.smoother = new LarSmoother(this.opts.alpha);
    this.framer = new Framer(FRAME, HOP);
    this.setSourceRate(srcRate);
    this.hop = 0; this.last = null; this.onHop = null;
  }
  setSourceRate(sr) { this.srcRate = sr; this.resampler = new StreamResampler(sr, P.FS); this.framer.reset(); }
  setOptions(o) {
    Object.assign(this.opts, o);
    this.smoother.alpha = this.opts.alpha;
    if (this.last && this.last.sm && ["mode", "illuminant", "mapping", "quantity"].some((k) => k in o)) this.last = this._physics(this.last, this.last.sm, true);
  }
  reset() { this.gate.reset(); this.smoother.reset(); this.framer.reset(); this.resampler = new StreamResampler(this.srcRate, P.FS); this.hop = 0; this.last = null; }
  pushSamples(chunk) {
    const y = this.resampler.push(sanitize(chunk));   // NaN/Inf -> 0, |x| > 1 clipped: one bad sample cannot poison the gate
    const out = [];
    this.framer.push(y, (fr) => { const r = this.processFrame(fr); out.push(r); if (this.onHop) this.onHop(r); });
    return out;
  }
  processFrame(frame) {
    const t = (this.hop * HOP + FRAME) / P.FS;
    this.hop++;
    const feat = frameFeatures(frame);
    const gate = this.gate.update(feat);
    let raw = null, res = null;
    const base = { t, feat, gate, voiced: gate.voiced, unvoiced: false, active: gate.active, level: gate.level, updated: false, raw: null };
    if (gate.update) {
      // Guarded: pathological input (pure sines, clipping, hum) can give |k| -> 1 / overflow. On any failure
      // the smoother state is restored and the last good shape is held.
      const saved = this.smoother.lar ? { lar: Float64Array.from(this.smoother.lar), lg: this.smoother.lg, since: this.smoother.since } : null;
      try {
        let mean = 0;
        for (let i = 0; i < frame.length; i++) mean += frame[i];
        mean /= frame.length;
        const x = new Float64Array(frame.length);
        for (let i = 0; i < frame.length; i++) x[i] = frame[i] - mean;   // DC offset (mic bias) removed per frame
        const r = P.lpc(x, LPC_ORDER, PREEMPH);
        let ok = r.gain > 0 && Number.isFinite(r.gain);
        for (let i = 0; ok && i < r.k.length; i++) if (!(Math.abs(r.k[i]) < 1)) ok = false;
        if (ok) {
          raw = r;
          const sm = this.smoother.update(r.k, r.gain);
          const cand = this._physics({ ...base, unvoiced: gate.unvoiced, updated: true, raw }, sm, false);
          if (isFiniteResult(cand)) res = cand;
          else throw new Error("non-finite physics");
        }
      } catch {
        res = null;
        if (saved) { this.smoother.lar = saved.lar; this.smoother.lg = saved.lg; this.smoother.since = saved.since; } else this.smoother.reset();
      }
    }
    if (!res) {
      this.smoother.tick();
      if (this.last) res = { ...this.last, ...base };       // hold the last shape/colour while fading
      else res = { ...base, sm: null, m: null, areas: null, F1: null, F2: null, colour: null, colourR: null, colourT: null, mapping: this.opts.mapping, iso: null };
    }
    this.last = res;
    return res;
  }
  _physics(base, sm, keepMeta) {
    const o = this.opts;
    const { dOpt } = mappingOf(o.mapping);
    const m = P.vowelMedia(sm.a);
    const [F1, F2] = f1f2(sm.a);
    let colourR = null, colourT = null;
    if (o.colour) ({ R: colourR, T: colourT } = colourPair(sm.a, o.mode, o.illuminant, dOpt));
    const colour = o.quantity === "T" ? colourT : colourR;
    const iso = o.iso ? isoCurves(sm.a, sm.gain, m, o.mode, o.isoPoints, dOpt) : null;
    const out = { ...base, sm, m, areas: Array.from(m.subarray(1, m.length - 1)), F1, F2, colour, colourR, colourT, mapping: o.mapping, iso };
    if (keepMeta) out.updated = base.updated;
    return out;
  }
}
