/**
 * physics.js — dependency-free ES-module port of the Python reference physics (core/*.py).
 *
 * Authoritative spec: docs/CONTRACT.md (§1 constants, §2 media vector / reflection coefficients /
 * D(z), §3 LPC sign convention, §4 tube f <-> film nu mapping, §5 Python API, §6 JS calling
 * convention and the exact numeric details reproduced here).  Python (core/) is the reference;
 * web/data/test_vectors.json is the conformance suite (run tools/node_test.mjs or web/tests.html).
 *
 * Calling convention: positional args in Python order, Python defaults as optional trailing args.
 * Python tuples -> named objects: levinson {a,k,err}, lpc {a,k,gain}, formantsFromPoly {F,B},
 * filmRT {R,T}, voiceOfFilm {a,gain}, filmColour {XYZ,Lab,rgb,hex,rgbAbs}, envelopeDb {f,dB}.
 * Array results are Float64Array (except tiny 3-vectors / lists, which are plain arrays).
 *
 * Colour functions need CIE data: `await loadPhysicsData("data/")` in the browser, or
 * `setPhysicsData(JSON.parse(fs.readFileSync("web/data/cie.json")))` in node.
 * Everything else works without data (constants are hard-coded from CONTRACT §1).
 *
 * Exactness: all §2–§5 physics is exact (lossless, non-dispersive). Not bit-identical to Python:
 * rosenberg/glottalSource with jitter != 0 (different RNG). display RGB is the labelled ARTISTIC
 * exposure normalisation (CONTRACT §8).
 */

// ----------------------------------------------------------------------------- constants (§1)
export const FS = 16000;
export const ORDER = 16;
export const C_SOUND = 350.0;
export const L_TRACT = ORDER * C_SOUND / (2 * FS);
export const C_LIGHT = 299792458.0;
export const NU_MIN = 400e12;
export const NU_MAX = 750e12;
export const DNU = NU_MAX - NU_MIN;
export const D_OPT_NM = C_LIGHT / (2 * DNU) * 1e9;
// Full-band mapping (CONTRACT §4b): period 750 THz, layers half-wave at 400 nm; visible = 0–7.47 kHz exactly once.
export const DNU_FULL = 750e12;
export const D_OPT_FULL_NM = C_LIGHT / (2 * DNU_FULL) * 1e9;
export const MAPPINGS = Object.freeze({ brief: { dnu: DNU, dOpt: D_OPT_NM }, full: { dnu: DNU_FULL, dOpt: D_OPT_FULL_NM } });
/** Period in nu (Hz) of a Goupillaud stack with optical thickness dOpt (nm) per layer. */
export function dnuOf(dOpt) { return C_LIGHT / (2 * dOpt * 1e-9); }
export const R_GLOTTIS = -0.9;
export const N_MIN = 1.0;
export const N_MAX = 2.5;
export const MATERIALS = Object.freeze({ air: 1.00, MgF2: 1.38, SiO2: 1.46, chitin: 1.56, Al2O3: 1.77, ZnS: 2.35, TiO2: 2.40 });
const MATERIAL_VALUES = Object.values(MATERIALS).slice().sort((x, y) => x - y);
const LOG_MATERIALS = MATERIAL_VALUES.map(Math.log);

// ----------------------------------------------------------------------------- small helpers
/** Python/numpy floored modulo (result has the sign of b). */
function pymod(a, b) {
  const m = a % b;
  return (m !== 0 && (m < 0) !== (b < 0)) ? m + b : m;
}
/** Python round() / np.round: round half to even. */
function roundHalfEven(x) {
  const r = Math.round(x);
  return (Math.abs(x % 1) === 0.5 && r % 2 !== 0) ? r - 1 : r;
}
function toF64(x) {
  if (x instanceof Float64Array) return x;
  if (typeof x === "number") return Float64Array.of(x);
  return Float64Array.from(x);
}
function linspace(a, b, n) {
  const out = new Float64Array(n);
  if (n === 1) { out[0] = a; return out; }
  const step = (b - a) / (n - 1);
  for (let i = 0; i < n; i++) out[i] = a + i * step;
  out[n - 1] = b;
  return out;
}
export { linspace, roundHalfEven };

// ----------------------------------------------------------------------------- LPC (§3, core/lpc.py)
export function autocorr(x, p) {
  const n = x.length;
  const r = new Float64Array(p + 1);
  for (let i = 0; i <= p; i++) {
    let s = 0;
    for (let j = 0; j < n - i; j++) s += x[j] * x[j + i];
    r[i] = s;
  }
  return r;
}

export function levinson(r, p) {
  const a = new Float64Array(p + 1);
  a[0] = 1;
  const k = new Float64Array(p);
  let err = r[0];
  if (!(err > 0)) return { a, k, err: 0 };
  const prev = new Float64Array(p + 1);
  for (let m = 1; m <= p; m++) {
    let acc = r[m];
    for (let i = 1; i < m; i++) acc += a[i] * r[m - i];
    const km = -acc / err;
    prev.set(a);
    for (let i = 1; i < m; i++) a[i] = prev[i] + km * prev[m - i];
    a[m] = km;
    k[m - 1] = km;
    err *= (1 - km * km);
    if (err <= 0) { err = 0; break; }
  }
  return { a, k, err };
}

export function lpc(x, p = ORDER, preemph = 0.97, window = "hamming") {
  const n = x.length;
  const y = new Float64Array(n);
  if (preemph) {
    y[0] = x[0];
    for (let i = 1; i < n; i++) y[i] = x[i] - preemph * x[i - 1];
  } else {
    for (let i = 0; i < n; i++) y[i] = x[i];
  }
  if (window === "hamming" && n > 1) {
    for (let i = 0; i < n; i++) y[i] *= 0.54 - 0.46 * Math.cos(2 * Math.PI * i / (n - 1));
  }
  const r = autocorr(y, p);
  r[0] *= 1 + 1e-9;
  const { a, k, err } = levinson(r, p);
  return { a, k, gain: Math.sqrt(Math.max(err, 0)) };
}

export function stepUp(k) {
  let a = Float64Array.of(1);
  for (let m = 0; m < k.length; m++) {
    const km = k[m];
    const L = a.length + 1;
    const ext = new Float64Array(L);
    ext.set(a);
    const out = new Float64Array(L);
    for (let i = 0; i < L; i++) out[i] = ext[i] + km * ext[L - 1 - i];
    a = out;
  }
  return a;
}

export function stepDown(aIn) {
  let a = Float64Array.from(aIn);
  if (Math.abs(a[0] - 1) > 1e-12) { const a0 = a[0]; for (let i = 0; i < a.length; i++) a[i] /= a0; }
  const p = a.length - 1;
  const k = new Float64Array(p);
  for (let m = p; m >= 1; m--) {
    const km = a[m];
    if (Math.abs(km) >= 1) throw new Error(`unstable polynomial: |k_${m}| = ${Math.abs(km).toFixed(6)} >= 1`);
    k[m - 1] = km;
    const nxt = new Float64Array(m);
    const den = 1 - km * km;
    for (let i = 0; i < m; i++) nxt[i] = (a[i] - km * a[m - i]) / den;
    a = nxt;
  }
  return k;
}

export function reflectionToAreas(k, A1 = 1.0) {
  const areas = new Float64Array(k.length + 1);
  areas[0] = A1;
  for (let m = 0; m < k.length; m++) areas[m + 1] = areas[m] * (1 + k[m]) / (1 - k[m]);
  return areas;
}

export function areasToReflection(A) {
  const k = new Float64Array(A.length - 1);
  for (let i = 0; i < k.length; i++) k[i] = (A[i + 1] - A[i]) / (A[i + 1] + A[i]);
  return k;
}

export function polyFromFormants(F, B, fs = FS) {
  let a = Float64Array.of(1);
  for (let j = 0; j < F.length; j++) {
    const r = Math.exp(-Math.PI * B[j] / fs);
    const th = 2 * Math.PI * F[j] / fs;
    const q = [1, -2 * r * Math.cos(th), r * r];
    const out = new Float64Array(a.length + 2);
    for (let i = 0; i < a.length; i++) for (let t = 0; t < 3; t++) out[i + t] += a[i] * q[t];
    a = out;
  }
  return a;
}

/**
 * Roots of a0 z^p + a1 z^{p-1} + ... + ap (like np.roots). Returns {re, im} Float64Arrays.
 * Aberth–Ehrlich iteration on the monic polynomial, then Newton polish on the original.
 */
export function polyRoots(coef) {
  let lo = 0, hi = coef.length - 1;
  while (lo <= hi && coef[lo] === 0) lo++;
  while (hi >= lo && coef[hi] === 0) hi--;
  const nZeroTail = coef.length - 1 - hi;
  if (lo > hi) return { re: new Float64Array(0), im: new Float64Array(0) };
  const c = Array.prototype.slice.call(coef, lo, hi + 1).map((v) => v / coef[lo]); // monic
  const n = c.length - 1;
  const re = new Float64Array(n + nZeroTail), im = new Float64Array(n + nZeroTail);
  if (n === 0) return { re, im };
  // Cauchy-type radius for initial guesses
  let rad = 0;
  for (let i = 1; i <= n; i++) rad = Math.max(rad, Math.pow(Math.abs(c[i]), 1 / i));
  rad = Math.max(rad, 1e-3);
  const zr = new Float64Array(n), zi = new Float64Array(n);
  for (let j = 0; j < n; j++) {
    const ang = 2 * Math.PI * j / n + 0.4;
    zr[j] = rad * Math.cos(ang); zi[j] = rad * Math.sin(ang);
  }
  const evalPD = (xr, xi, poly) => { // returns [pr, pi, dr, di] (Horner)
    let pr = poly[0], pi = 0, dr = 0, di = 0;
    for (let i = 1; i < poly.length; i++) {
      const ndr = dr * xr - di * xi + pr, ndi = dr * xi + di * xr + pi;
      dr = ndr; di = ndi;
      const npr = pr * xr - pi * xi + poly[i], npi = pr * xi + pi * xr;
      pr = npr; pi = npi;
    }
    return [pr, pi, dr, di];
  };
  for (let it = 0; it < 500; it++) {
    let maxCorr = 0;
    for (let j = 0; j < n; j++) {
      const [pr, pi, dr, di] = evalPD(zr[j], zi[j], c);
      // ratio = p/p'
      const dd = dr * dr + di * di;
      if (dd === 0 && pr === 0 && pi === 0) continue;
      let rr, ri;
      if (dd === 0) { rr = 1e-8; ri = 0; } else { rr = (pr * dr + pi * di) / dd; ri = (pi * dr - pr * di) / dd; }
      // sum 1/(zj - zk)
      let sr = 0, si = 0;
      for (let k = 0; k < n; k++) {
        if (k === j) continue;
        const ur = zr[j] - zr[k], ui = zi[j] - zi[k];
        const uu = ur * ur + ui * ui;
        if (uu === 0) continue;
        sr += ur / uu; si -= ui / uu;
      }
      // w = ratio / (1 - ratio * s)
      const tr = 1 - (rr * sr - ri * si), ti = -(rr * si + ri * sr);
      const tt = tr * tr + ti * ti;
      const wr = (rr * tr + ri * ti) / tt, wi = (ri * tr - rr * ti) / tt;
      zr[j] -= wr; zi[j] -= wi;
      const corr = Math.hypot(wr, wi) / Math.max(1, Math.hypot(zr[j], zi[j]));
      if (corr > maxCorr) maxCorr = corr;
    }
    if (maxCorr < 1e-15) break;
  }
  // Newton polish on the original (non-normalised) coefficients
  const orig = Array.prototype.slice.call(coef, lo, hi + 1);
  for (let j = 0; j < n; j++) {
    for (let it = 0; it < 3; it++) {
      const [pr, pi, dr, di] = evalPD(zr[j], zi[j], orig);
      const dd = dr * dr + di * di;
      if (dd === 0) break;
      const wr = (pr * dr + pi * di) / dd, wi = (pi * dr - pr * di) / dd;
      if (!Number.isFinite(wr) || !Number.isFinite(wi)) break;
      zr[j] -= wr; zi[j] -= wi;
      if (Math.hypot(wr, wi) <= 1e-16 * Math.max(1, Math.hypot(zr[j], zi[j]))) break;
    }
    re[j] = zr[j]; im[j] = zi[j];
  }
  return { re, im };
}

export function formantsFromPoly(a, fs = FS, fmin = 90.0, maxBw = 600.0) {
  const { re, im } = polyRoots(a);
  const pairs = [];
  for (let i = 0; i < re.length; i++) {
    if (!(im[i] > 1e-9)) continue;
    const F = Math.atan2(im[i], re[i]) * fs / (2 * Math.PI);
    const B = -Math.log(Math.max(Math.hypot(re[i], im[i]), 1e-12)) * fs / Math.PI;
    if (F > fmin && F < fs / 2 - 50 && B < maxBw) pairs.push([F, B]);
  }
  pairs.sort((x, y) => x[0] - y[0]);
  return { F: Float64Array.from(pairs, (q) => q[0]), B: Float64Array.from(pairs, (q) => q[1]) };
}

/** LPC envelope: |gain/A(e^{jw})| in dB on the rfft grid (nfft/2+1 points). Returns {f, dB}. */
export function envelopeDb(a, gain = 1.0, nfft = 1024, fs = FS) {
  const nb = (nfft >> 1) + 1;
  const L = Math.min(a.length, nfft);
  const f = new Float64Array(nb), dB = new Float64Array(nb);
  for (let k = 0; k < nb; k++) {
    let sr = 0, si = 0;
    for (let i = 0; i < L; i++) {
      const ph = 2 * Math.PI * ((i * k) % nfft) / nfft;
      sr += a[i] * Math.cos(ph); si -= a[i] * Math.sin(ph);
    }
    f[k] = k * fs / nfft;
    dB[k] = 20 * Math.log10(gain / Math.max(Math.hypot(sr, si), 1e-12));
  }
  return { f, dB };
}

// ----------------------------------------------------------------------------- mapping (§2, §4)
export function reflectionFromMedia(m) {
  const c = new Float64Array(m.length - 1);
  for (let i = 0; i < c.length; i++) c[i] = (m[i] - m[i + 1]) / (m[i] + m[i + 1]);
  return c;
}

export function mediaFromReflection(c, m0 = 1.0) {
  const m = new Float64Array(c.length + 1);
  m[0] = m0;
  for (let i = 0; i < c.length; i++) m[i + 1] = m[i] * (1 - c[i]) / (1 + c[i]);
  return m;
}

export function polyFromReflection(c) {
  let F = Float64Array.of(1), G = Float64Array.of(c[0]);
  for (let i = 1; i < c.length; i++) {
    const ci = c[i], L = F.length + 1;
    const nF = new Float64Array(L), nG = new Float64Array(L);
    for (let j = 0; j < L; j++) {
      const fe = j < L - 1 ? F[j] : 0;      // F padded at end
      const gs = j > 0 ? G[j - 1] : 0;      // z^-1 G
      nF[j] = fe + ci * gs;
      nG[j] = ci * fe + gs;
    }
    F = nF; G = nG;
  }
  return F;
}

export function powerTransfer(c, omega) {
  const D = polyFromReflection(c);
  let num = 1;
  for (let i = 0; i < c.length; i++) num *= 1 - c[i] * c[i];
  const om = toF64(omega);
  const P = new Float64Array(om.length);
  for (let j = 0; j < om.length; j++) {
    let sr = 0, si = 0;
    for (let k = 0; k < D.length; k++) { const ph = om[j] * k; sr += D[k] * Math.cos(ph); si -= D[k] * Math.sin(ph); }
    P[j] = num / (sr * sr + si * si);
  }
  return P;
}

export function omegaOfNu(nu, dOpt = D_OPT_NM) {
  const x = toF64(nu), out = new Float64Array(x.length);
  for (let i = 0; i < x.length; i++) out[i] = 4 * Math.PI * dOpt * 1e-9 * x[i] / C_LIGHT;
  return out;
}

export function fOfNu(nu, dnu = DNU) {
  const x = toF64(nu), out = new Float64Array(x.length);
  for (let i = 0; i < x.length; i++) { const t = x[i] / dnu; out[i] = FS * (t - Math.floor(t)); }
  return out;
}

/** All nu in [NU_MIN, NU_MAX) with fOfNu(nu) = ±f (mod FS); sorted unique (rounded to 1e-3 Hz). */
export function nuImages(f, dnu = DNU) {
  const out = [];
  for (const ff of [f, FS - f]) {
    const base = (ff / FS) * dnu;
    const kmin = Math.ceil((NU_MIN - base) / dnu);
    for (let k = kmin; k < kmin + 3; k++) {
      const nu = base + k * dnu;
      if (nu >= NU_MIN && nu < NU_MAX) out.push(Math.round(nu * 1000) / 1000);
    }
  }
  return Array.from(new Set(out)).sort((x, y) => x - y);
}

export function vowelMedia(a, rGlottis = R_GLOTTIS) {
  const k = stepDown(a);
  const areas = reflectionToAreas(k, 1.0);
  const m = new Float64Array(areas.length + 1);
  m[0] = areas[0] * (1 + rGlottis) / (1 - rGlottis);
  m.set(areas, 1);
  return m;
}

export function filmFromMedia(m, mode = "ideal") {
  let mn = Infinity;
  for (let i = 0; i < m.length; i++) if (m[i] < mn) mn = m[i];
  const ratio = new Float64Array(m.length);
  let rmax = -Infinity;
  for (let i = 0; i < m.length; i++) { ratio[i] = m[i] / mn; if (ratio[i] > rmax) rmax = ratio[i]; }
  if (mode === "ideal") { for (let i = 0; i < m.length; i++) ratio[i] *= N_MIN; return ratio; }
  const span = Math.log(rmax);
  const gamma = span <= 0 ? 1.0 : Math.min(1.0, Math.log(N_MAX / N_MIN) / span);
  const n = new Float64Array(m.length);
  for (let i = 0; i < m.length; i++) n[i] = N_MIN * Math.pow(ratio[i], gamma);
  if (mode === "realizable") return n;
  if (mode === "materials") {
    for (let i = 0; i < n.length; i++) {
      const ln = Math.log(n[i]);
      let best = 0, bd = Infinity;
      for (let j = 0; j < LOG_MATERIALS.length; j++) {
        const dd = Math.abs(ln - LOG_MATERIALS[j]);
        if (dd < bd) { bd = dd; best = j; }
      }
      n[i] = MATERIAL_VALUES[best];
    }
    return n;
  }
  throw new Error(`filmFromMedia: unknown mode ${mode}`);
}

export function goupillaudD(nLayers, dOpt = D_OPT_NM) {
  const x = toF64(nLayers), d = new Float64Array(x.length);
  for (let i = 0; i < x.length; i++) d[i] = dOpt / x[i];
  return d;
}

// ----------------------------------------------------------------------------- thin film (core/film.py)
// Complex refractive index may be given as a number or as {re, im} / [re, im].
function cplx(v) {
  if (typeof v === "number") return [v, 0];
  if (Array.isArray(v)) return [v[0], v[1] || 0];
  return [v.re, v.im || 0];
}
function csqrt(r, i) { // principal sqrt; for i === +0/-0 and r<0 numpy gives +i*sqrt(-r) when imag is +0
  if (i === 0) {
    if (r >= 0) return [Math.sqrt(r), 0];
    return [0, Object.is(i, -0) ? -Math.sqrt(-r) : Math.sqrt(-r)];
  }
  const m = Math.hypot(r, i);
  const sr = Math.sqrt((m + r) / 2);
  const si = Math.sqrt((m - r) / 2);
  return [sr, i < 0 ? -si : si];
}

/**
 * One polarisation. Writes R,T into Rout/Tout (Float64Array, length wl.length), adding with weight w.
 * Inline real/imag arithmetic, no allocation per sample.
 */
function rtPol(n, d, wl, thetaDeg, pol, Rout, Tout, w) {
  const NL = n.length;
  const nr = new Float64Array(NL), ni = new Float64Array(NL);
  for (let j = 0; j < NL; j++) { const z = cplx(n[j]); nr[j] = z[0]; ni[j] = z[1]; }
  const sth = Math.sin(thetaDeg * Math.PI / 180);
  const s0r = nr[0] * sth, s0i = ni[0] * sth;
  const er = new Float64Array(NL), ei = new Float64Array(NL);    // eta
  const ier = new Float64Array(NL), iei = new Float64Array(NL);  // 1/eta
  const Pr = new Float64Array(NL), Pi = new Float64Array(NL);    // 2*pi*n*d*cos (divide by wl -> delta)
  let allReal = true;
  for (let j = 0; j < NL; j++) {
    // q = s0 / n_j ; cos = sqrt(1 - q^2)
    const dd = nr[j] * nr[j] + ni[j] * ni[j];
    const qr = (s0r * nr[j] + s0i * ni[j]) / dd, qi = (s0i * nr[j] - s0r * ni[j]) / dd;
    const q2r = qr * qr - qi * qi, q2i = 2 * qr * qi;
    const [cr, ci] = csqrt(1 - q2r, 0 - q2i);
    let ar, ai;
    if (pol === "s") { ar = nr[j] * cr - ni[j] * ci; ai = nr[j] * ci + ni[j] * cr; }
    else { const cc = cr * cr + ci * ci; ar = (nr[j] * cr + ni[j] * ci) / cc; ai = (ni[j] * cr - nr[j] * ci) / cc; }
    er[j] = ar; ei[j] = ai;
    const ee = ar * ar + ai * ai;
    ier[j] = ar / ee; iei[j] = -ai / ee;
    if (j >= 1 && j <= NL - 2) {
      const dj = d[j - 1];
      // n * cos
      const ncr = nr[j] * cr - ni[j] * ci, nci = nr[j] * ci + ni[j] * cr;
      Pr[j] = 2 * Math.PI * dj * ncr; Pi[j] = 2 * Math.PI * dj * nci;
      if (Pi[j] !== 0 || ai !== 0) allReal = false;
    }
  }
  const e0r = er[0], e0i = ei[0], esr = er[NL - 1], esi = ei[NL - 1];
  const W = wl.length;
  for (let t = 0; t < W; t++) {
    const inv = 1 / wl[t];
    let Br = 1, Bi = 0, Cr = esr, Ci = esi;
    if (allReal) {
      for (let j = NL - 2; j >= 1; j--) {
        const dl = Pr[j] * inv;
        const cs = Math.cos(dl), sn = Math.sin(dl);
        const a = sn * ier[j], b = sn * er[j];
        // B' = cs B + i a C ; C' = i b B + cs C
        const nBr = cs * Br - a * Ci, nBi = cs * Bi + a * Cr;
        const nCr = cs * Cr - b * Bi, nCi = cs * Ci + b * Br;
        Br = nBr; Bi = nBi; Cr = nCr; Ci = nCi;
      }
    } else {
      for (let j = NL - 2; j >= 1; j--) {
        const x = Pr[j] * inv, y = Pi[j] * inv;
        let csr, csi, snr, sni;
        if (y === 0) { csr = Math.cos(x); csi = 0; snr = Math.sin(x); sni = 0; }
        else {
          const ch = Math.cosh(y), sh = Math.sinh(y), cx = Math.cos(x), sx = Math.sin(x);
          csr = cx * ch; csi = -sx * sh; snr = sx * ch; sni = cx * sh;
        }
        // i*sn/eta = i * (sn * ieta)
        const ur = snr * ier[j] - sni * iei[j], ui = snr * iei[j] + sni * ier[j];
        const Ar = -ui, Ai = ur;                // i*u
        const vr = snr * er[j] - sni * ei[j], vi = snr * ei[j] + sni * er[j];
        const Gr = -vi, Gi = vr;                // i*v
        const nBr = csr * Br - csi * Bi + Ar * Cr - Ai * Ci;
        const nBi = csr * Bi + csi * Br + Ar * Ci + Ai * Cr;
        const nCr = Gr * Br - Gi * Bi + csr * Cr - csi * Ci;
        const nCi = Gr * Bi + Gi * Br + csr * Ci + csi * Cr;
        Br = nBr; Bi = nBi; Cr = nCr; Ci = nCi;
      }
    }
    const xr = e0r * Br - e0i * Bi, xi = e0r * Bi + e0i * Br; // eta0*B
    const denr = xr + Cr, deni = xi + Ci, numr = xr - Cr, numi = xi - Ci;
    const den2 = denr * denr + deni * deni;
    Rout[t] += w * (numr * numr + numi * numi) / den2;
    Tout[t] += w * 4 * e0r * esr / den2;
  }
}

/** Abelès/Macleod. n = [incident, layers..., substrate]; d_nm per layer; wl_nm scalar or array. Returns {R,T}. */
export function filmRT(n, dNm, wlNm, thetaDeg = 0.0, pol = "u") {
  const wl = toF64(wlNm), d = toF64(dNm);
  const R = new Float64Array(wl.length), T = new Float64Array(wl.length);
  if (pol === "u" && thetaDeg === 0) rtPol(n, d, wl, 0, "s", R, T, 1);
  else if (pol === "u") { rtPol(n, d, wl, thetaDeg, "s", R, T, 0.5); rtPol(n, d, wl, thetaDeg, "p", R, T, 0.5); }
  else rtPol(n, d, wl, thetaDeg, pol, R, T, 1);
  return { R, T };
}

export function filmRTNu(n, dNm, nuHz, thetaDeg = 0.0, pol = "u") {
  const nu = toF64(nuHz), wl = new Float64Array(nu.length);
  for (let i = 0; i < nu.length; i++) wl[i] = C_LIGHT / nu[i] * 1e9;
  return filmRT(n, dNm, wl, thetaDeg, pol);
}

const _cosTables = new Map();
function cosTable(N) {
  let t = _cosTables.get(N);
  if (!t) { t = new Float64Array(N); for (let i = 0; i < N; i++) t[i] = Math.cos(2 * Math.PI * i / N); _cosTables.set(N, t); }
  return t;
}

/** Film -> all-pole voice (CONTRACT §5/§6). Returns {a, gain}. */
export function voiceOfFilm(n, dNm, thetaDeg = 0.0, p = ORDER, nFreq = 2048, dnu = DNU) {
  const off = pymod(NU_MIN / dnu, 1.0);
  const wl = new Float64Array(nFreq);
  for (let j = 0; j < nFreq; j++) {
    const f = j * FS / nFreq;
    const nu = NU_MIN + pymod(f / FS - off, 1.0) * dnu;
    wl[j] = C_LIGHT / nu * 1e9;
  }
  const { T } = filmRT(n, dNm, wl, thetaDeg, "u");
  const ct = cosTable(nFreq);
  const r = new Float64Array(p + 1);
  for (let k = 0; k <= p; k++) {
    let s = 0;
    for (let j = 0; j < nFreq; j++) s += T[j] * ct[(j * k) % nFreq];
    r[k] = s / nFreq;
  }
  const { a, err } = levinson(r, p);
  return { a, gain: Math.sqrt(Math.max(err, 0)) };
}

// ----------------------------------------------------------------------------- colour (core/colour.py)
let DATA = null;

/** Inject cie.json contents (node, or any pre-fetched object). Returns the cached data. */
export function setPhysicsData(obj) {
  const wl = Float64Array.from(obj.wl);
  const cmf = [Float64Array.from(obj.xbar), Float64Array.from(obj.ybar), Float64Array.from(obj.zbar)];
  const ill = {};
  for (const [name, E] of Object.entries(obj.illuminants)) {
    const e = Float64Array.from(E);
    let s = 0;
    for (let i = 0; i < e.length; i++) s += e[i] * cmf[1][i];
    const k = 100 / s;
    const wx = new Float64Array(e.length), wy = new Float64Array(e.length), wz = new Float64Array(e.length);
    for (let i = 0; i < e.length; i++) { wx[i] = k * e[i] * cmf[0][i]; wy[i] = k * e[i] * cmf[1][i]; wz[i] = k * e[i] * cmf[2][i]; }
    let X = 0, Y = 0, Z = 0;
    for (let i = 0; i < e.length; i++) { X += wx[i]; Y += wy[i]; Z += wz[i]; }
    ill[name] = { E: e, k, wx, wy, wz, white: [X, Y, Z] };
  }
  DATA = {
    wl, cmf, ill,
    M: obj.srgb_matrix ? obj.srgb_matrix.map((r) => r.slice()) : [[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560], [0.0556434, -0.2040259, 1.0572252]],
    materials: obj.materials, constants: obj.constants, source: obj.source,
  };
  return DATA;
}

let _loading = null;
/** Fetch `${base}cie.json` once and cache it. */
export function loadPhysicsData(base = "data/") {
  if (DATA) return Promise.resolve(DATA);
  if (!_loading) {
    _loading = fetch(base + "cie.json")
      .then((r) => { if (!r.ok) throw new Error(`cie.json: HTTP ${r.status}`); return r.json(); })
      .then(setPhysicsData)
      .catch((e) => { _loading = null; throw e; });
  }
  return _loading;
}
export function getPhysicsData() { return DATA; }
function need() {
  if (!DATA) throw new Error("physics.js: CIE data not loaded — call await loadPhysicsData() (or setPhysicsData) first");
  return DATA;
}
/** CIE wavelength grid (360..830 nm, 0.5 nm, 941 points). */
export function getWL() { return need().wl; }

export function spectrumToXYZ(S, illuminant = "D65") {
  const I = need().ill[illuminant];
  if (!I) throw new Error(`unknown illuminant ${illuminant}`);
  let X = 0, Y = 0, Z = 0;
  const { wx, wy, wz } = I;
  for (let i = 0; i < wx.length; i++) { const s = S[i]; X += s * wx[i]; Y += s * wy[i]; Z += s * wz[i]; }
  return [X, Y, Z];
}

export function whiteXYZ(illuminant = "D65") { return need().ill[illuminant].white.slice(); }

export function xyzToLab(XYZ, illuminant = "D65") {
  const W = need().ill[illuminant].white;
  const d = 6 / 29, d3 = d * d * d;
  const f = [0, 1, 2].map((i) => { const t = XYZ[i] / W[i]; return t > d3 ? Math.cbrt(t) : t / (3 * d * d) + 4 / 29; });
  return [116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])];
}

function gammaEnc(u) {
  u = Math.min(1, Math.max(0, u));
  return u <= 0.0031308 ? 12.92 * u : 1.055 * Math.pow(u, 1 / 2.4) - 0.055;
}
const M_DEFAULT = [[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560], [0.0556434, -0.2040259, 1.0572252]];
function matM() { return DATA ? DATA.M : M_DEFAULT; }

export function xyzToSRGB(XYZ) {
  const M = matM();
  return [0, 1, 2].map((i) => gammaEnc((M[i][0] * XYZ[0] + M[i][1] * XYZ[1] + M[i][2] * XYZ[2]) / 100));
}

/** ARTISTIC exposure normalisation (CONTRACT §8): scale to Y = targetY, sRGB, divide by max if > 1. */
export function displayRGB(XYZ, targetY = 50.0) {
  if (!(XYZ[1] > 1e-12)) return [0, 0, 0];
  const M = matM();
  const s = targetY / XYZ[1];
  const x = [XYZ[0] * s / 100, XYZ[1] * s / 100, XYZ[2] * s / 100];
  let lin = [0, 1, 2].map((i) => M[i][0] * x[0] + M[i][1] * x[1] + M[i][2] * x[2]);
  const m = Math.max(lin[0], lin[1], lin[2]);
  if (m > 1) lin = lin.map((v) => v / m);
  return lin.map(gammaEnc);
}

export function toHex(rgb) {
  return "#" + Array.from(rgb, (v) => roundHalfEven(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, "0")).join("");
}

export function deltaE00(lab1, lab2) {
  const [L1, a1, b1] = lab1, [L2, a2, b2] = lab2;
  const rad = Math.PI / 180, deg = 180 / Math.PI;
  const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2);
  const Cb = (C1 + C2) / 2;
  const G = 0.5 * (1 - Math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)));
  const a1p = (1 + G) * a1, a2p = (1 + G) * a2;
  const C1p = Math.hypot(a1p, b1), C2p = Math.hypot(a2p, b2);
  const h1p = pymod(Math.atan2(b1, a1p) * deg, 360);
  const h2p = pymod(Math.atan2(b2, a2p) * deg, 360);
  const dLp = L2 - L1, dCp = C2p - C1p;
  let dh = h2p - h1p;
  if (C1p * C2p === 0) dh = 0;
  else if (dh > 180) dh -= 360;
  else if (dh < -180) dh += 360;
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin(rad * dh / 2);
  const Lbp = (L1 + L2) / 2, Cbp = (C1p + C2p) / 2;
  let hbp;
  if (C1p * C2p === 0) hbp = h1p + h2p;
  else if (Math.abs(h1p - h2p) <= 180) hbp = (h1p + h2p) / 2;
  else if (h1p + h2p < 360) hbp = (h1p + h2p + 360) / 2;
  else hbp = (h1p + h2p - 360) / 2;
  const T = 1 - 0.17 * Math.cos(rad * (hbp - 30)) + 0.24 * Math.cos(rad * 2 * hbp)
    + 0.32 * Math.cos(rad * (3 * hbp + 6)) - 0.20 * Math.cos(rad * (4 * hbp - 63));
  const dtheta = 30 * Math.exp(-(((hbp - 275) / 25) ** 2));
  const Rc = 2 * Math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7));
  const Sl = 1 + 0.015 * (Lbp - 50) ** 2 / Math.sqrt(20 + (Lbp - 50) ** 2);
  const Sc = 1 + 0.045 * Cbp;
  const Sh = 1 + 0.015 * Cbp * T;
  const Rt = -Math.sin(rad * 2 * dtheta) * Rc;
  return Math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh));
}

/** Colour of a film on the CIE grid. Returns {XYZ, Lab, rgb (display), hex, rgbAbs (absolute sRGB)}. */
export function filmColour(n, dNm, thetaDeg = 0.0, illuminant = "D65", quantity = "T") {
  const { R, T } = filmRT(n, dNm, need().wl, thetaDeg, "u");
  const XYZ = spectrumToXYZ(quantity === "T" ? T : R, illuminant);
  const rgb = displayRGB(XYZ);
  return { XYZ, Lab: xyzToLab(XYZ, illuminant), rgb, hex: toHex(rgb), rgbAbs: xyzToSRGB(XYZ) };
}

// ----------------------------------------------------------------------------- synthesis (core/synth.py)
function makeGauss(seed) { // mulberry32 + Box–Muller (NOT numpy's RNG)
  let s = seed >>> 0;
  const u = () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  return () => Math.sqrt(-2 * Math.log(1 - u())) * Math.cos(2 * Math.PI * u());
}

/** Rosenberg type-B glottal flow. Identical to Python for jitter = 0. */
export function rosenberg(f0, fs = FS, dur = 1.0, oq = 0.6, sq = 2.0, jitter = 0.0, seed = 0) {
  const n = roundHalfEven(dur * fs);
  const u = new Float64Array(n);
  const gauss = jitter ? makeGauss(seed) : null;
  let t = 0;
  while (t < n) {
    const T0 = fs / (f0 * (1 + (jitter ? jitter * gauss() : 0)));
    const To = oq * T0, Tp = To * sq / (1 + sq), Tn = To - Tp;
    const L = roundHalfEven(T0);
    const m = Math.min(L, n - t);
    for (let k = 0; k < m; k++) {
      let v = 0;
      if (k < Tp) v = 0.5 * (1 - Math.cos(Math.PI * k / Tp));
      else if (k < To) v = Math.cos(Math.PI * (k - Tp) / (2 * Tn));
      u[t + k] = v;
    }
    t += L;
    if (L <= 0) break;
  }
  return u;
}

/** Derivative of Rosenberg flow (glottal flow + lip radiation), first difference with prepend 0. */
export function glottalSource(f0, fs = FS, dur = 1.0, oq = 0.6, sq = 2.0, jitter = 0.0, seed = 0) {
  const u = rosenberg(f0, fs, dur, oq, sq, jitter, seed);
  const out = new Float64Array(u.length);
  let prev = 0;
  for (let i = 0; i < u.length; i++) { out[i] = u[i] - prev; prev = u[i]; }
  return out;
}

/** y = lfilter([gain], a, source) (normalised by a[0]). */
export function synthAllpole(a, source, gain = 1.0) {
  const p = a.length - 1, a0 = a[0];
  const an = new Float64Array(p + 1);
  for (let i = 0; i <= p; i++) an[i] = a[i] / a0;
  const g = gain / a0;
  const N = source.length, y = new Float64Array(N);
  for (let t = 0; t < N; t++) {
    let acc = g * source[t];
    const lim = Math.min(p, t);
    for (let i = 1; i <= lim; i++) acc -= an[i] * y[t - i];
    y[t] = acc;
  }
  return y;
}

/**
 * Voice samples for an all-pole filter: glottalSource -> synthAllpole -> peak 0.9 -> 20 ms linear fades.
 * Returns Float32Array at FS. jitter defaults to 0 (deterministic; numpy's RNG is not reproducible).
 */
export function filmVoiceSamples(a, gain = 1.0, f0 = 140.0, dur = 1.2, jitter = 0.0, fs = FS) {
  const y = synthAllpole(a, glottalSource(f0, fs, dur, 0.6, 2.0, jitter), gain);
  let mx = 0;
  for (let i = 0; i < y.length; i++) mx = Math.max(mx, Math.abs(y[i]));
  const sc = mx > 0 ? 0.9 / mx : 1;
  const out = new Float32Array(y.length);
  for (let i = 0; i < y.length; i++) out[i] = y[i] * sc;
  const k = Math.min(y.length >> 1, Math.trunc(fs * 20 / 1000));
  if (k > 0) {
    for (let i = 0; i < k; i++) {
      const w = k === 1 ? 0 : i / (k - 1);
      out[i] *= w;                       // linspace(0,1,k)
      out[y.length - k + i] *= 1 - w;    // linspace(1,0,k)
    }
  }
  return out;
}

/** Web Audio buffer (mono, FS Hz) of filmVoiceSamples. */
export function filmVoiceBuffer(audioCtx, a, gain = 1.0, f0 = 140.0, dur = 1.2, jitter = 0.0) {
  const s = filmVoiceSamples(a, gain, f0, dur, jitter);
  const buf = audioCtx.createBuffer(1, s.length, FS);
  buf.copyToChannel ? buf.copyToChannel(s, 0) : buf.getChannelData(0).set(s);
  return buf;
}

// ----------------------------------------------------------------------------- UI helpers
/**
 * Vowel LPC polynomial -> film colour. a -> vowelMedia -> filmFromMedia(mode) -> goupillaudD -> filmColour.
 * Returns {XYZ, Lab, rgb, hex, rgbAbs, n, d, m}. (vowels.json `colours` = mode "ideal", `colours_real` = "realizable".)
 */
export function vowelColour(a, mode = "ideal", illuminant = "D65", quantity = "T", thetaDeg = 0.0, dOpt = D_OPT_NM) {
  const m = vowelMedia(a);
  const n = filmFromMedia(m, mode);
  const d = goupillaudD(n.subarray(1, n.length - 1), dOpt);
  return { ...filmColour(n, d, thetaDeg, illuminant, quantity), n, d, m };
}

/** R/T over nu in [NU_MIN, NU_MAX] (inclusive linspace). Returns {nu (Hz), wl (nm), R, T}. */
export function transmittanceCurve(n, d, nPoints = 351, thetaDeg = 0.0, pol = "u") {
  const nu = linspace(NU_MIN, NU_MAX, nPoints);
  const wl = new Float64Array(nPoints);
  for (let i = 0; i < nPoints; i++) wl[i] = C_LIGHT / nu[i] * 1e9;
  const { R, T } = filmRT(n, d, wl, thetaDeg, pol);
  return { nu, wl, R, T };
}

/**
 * Angle LUT of display colours: array of [r,g,b] in [0,1] (displayRGB) per angle.
 * Defaults match butterflies.json `lut` (quantity "R", D65, 0..80 step 2). Use toHex() for hex.
 */
export function buildLUT(n, d, quantity = "R", illuminant = "D65", angles = null) {
  const angs = angles || Array.from({ length: 41 }, (_, i) => 2 * i);
  const wl = need().wl;
  return Array.from(angs, (th) => {
    const { R, T } = filmRT(n, d, wl, th, "u");
    return displayRGB(spectrumToXYZ(quantity === "R" ? R : T, illuminant));
  });
}
