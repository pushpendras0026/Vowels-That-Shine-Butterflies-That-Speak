/**
 * Shared conformance logic for web/js/physics.js (used by web/tests.html and tools/node_test.mjs,
 * so both runners apply the identical rule). Rule (docs/CONTRACT.md §7): per element
 * err = |got - expect| / max(1, |expect|) must be <= tol; strings must match exactly;
 * only keys present in `expect` are compared; formantsFromPoly is compared after sorting (F,B) pairs by F.
 */

const isArr = (v) => Array.isArray(v) || ArrayBuffer.isView(v);

/** Max error between got and expect (recursive). Returns {err, msg}. err = Infinity on mismatch. */
export function compareValue(got, exp, sort = false) {
  if (typeof exp === "string") return got === exp ? { err: 0, msg: "" } : { err: Infinity, msg: `got "${got}" want "${exp}"` };
  if (typeof exp === "number") {
    if (typeof got !== "number" || !Number.isFinite(got)) return { err: Infinity, msg: `got ${got}` };
    return { err: Math.abs(got - exp) / Math.max(1, Math.abs(exp)), msg: "" };
  }
  if (isArr(exp)) {
    if (!isArr(got)) return { err: Infinity, msg: "not an array" };
    if (got.length !== exp.length) return { err: Infinity, msg: `length ${got.length} != ${exp.length}` };
    let g = Array.from(got), e = Array.from(exp);
    if (sort && typeof e[0] === "number") { g.sort((x, y) => x - y); e.sort((x, y) => x - y); }
    let worst = { err: 0, msg: "" };
    for (let i = 0; i < e.length; i++) {
      const r = compareValue(g[i], e[i], sort);
      if (!(r.err <= worst.err)) worst = { err: r.err, msg: r.msg || `worst at [${i}]` };
    }
    return worst;
  }
  if (exp && typeof exp === "object") {
    if (!got || typeof got !== "object") return { err: Infinity, msg: "not an object" };
    let worst = { err: 0, msg: "" };
    for (const key of Object.keys(exp)) {
      if (!(key in got)) return { err: Infinity, msg: `missing key ${key}` };
      const r = compareValue(got[key], exp[key], sort);
      if (!(r.err <= worst.err)) worst = { err: r.err, msg: `${key}: ${r.msg}` };
    }
    return worst;
  }
  return { err: Infinity, msg: `unsupported expect type ${typeof exp}` };
}

/** Run every test_vectors.json case against the physics module P. Returns [{name, fn, err, tol, pass, msg, ms}]. */
export function runVectorCases(P, vectors) {
  const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());
  return vectors.cases.map((c) => {
    const t0 = now();
    try {
      const fn = P[c.fn];
      if (typeof fn !== "function") throw new Error(`no export ${c.fn}`);
      let got = fn(...c.args);
      if (c.fn === "formantsFromPoly" && got && got.F) { // sort (F,B) pairs by F, keeping them paired
        const idx = Array.from(got.F, (_, i) => i).sort((i, j) => got.F[i] - got.F[j]);
        got = { F: idx.map((i) => got.F[i]), B: idx.map((i) => got.B[i]) };
      }
      const r = compareValue(got, c.expect);
      return { name: c.name, fn: c.fn, err: r.err, tol: c.tol, pass: r.err <= c.tol, msg: r.msg, ms: now() - t0 };
    } catch (e) {
      return { name: c.name, fn: c.fn, err: Infinity, tol: c.tol, pass: false, msg: String(e && e.message || e), ms: now() - t0 };
    }
  });
}

function hexDiff(h1, h2) {
  let m = 0;
  for (let i = 1; i < 7; i += 2) m = Math.max(m, Math.abs(parseInt(h1.slice(i, i + 2), 16) - parseInt(h2.slice(i, i + 2), 16)));
  return m;
}

/**
 * Extra consistency checks of the UI helpers against the generated data files (inputs there are rounded,
 * so tolerances are loose: hex ±1 per channel, Lab 1e-3, formants 0.05 Hz).
 */
export function runExtraChecks(P, vowels, butterflies) {
  const out = [];
  const add = (name, err, tol, msg = "") => out.push({ name, fn: "extra", err, tol, pass: err <= tol, msg });
  const safe = (name, tol, f) => { try { const [e, m] = f(); add(name, e, tol, m); } catch (e) { add(name, Infinity, tol, String(e.message || e)); } };
  if (vowels) {
    safe("vowelColour ideal D65 vs vowels.json (hex T,R; ±1/255)", 1, () => {
      let w = 0, wm = "";
      for (const it of vowels.items) {
        const cT = P.vowelColour(it.a, "ideal", "D65", "T"), cR = P.vowelColour(it.a, "ideal", "D65", "R");
        const e = Math.max(hexDiff(cT.hex, it.colours.D65.T), hexDiff(cR.hex, it.colours.D65.R));
        if (e > w) { w = e; wm = `${it.group}/${it.vowel}`; }
      }
      return [w, wm];
    });
    safe("vowelColour realizable, all illuminants (hex T; ±1/255)", 1, () => {
      let w = 0, wm = "";
      for (const it of vowels.items) for (const ill of Object.keys(it.colours_real)) {
        const e = hexDiff(P.vowelColour(it.a, "realizable", ill, "T").hex, it.colours_real[ill].T);
        if (e > w) { w = e; wm = `${it.group}/${it.vowel}/${ill}`; }
      }
      return [w, wm];
    });
    safe("vowelColour Lab (T, ideal, D65) vs vowels.json", 1e-3, () => {
      let w = 0;
      for (const it of vowels.items) {
        const L = P.vowelColour(it.a, "ideal", "D65", "T").Lab;
        for (let i = 0; i < 3; i++) w = Math.max(w, Math.abs(L[i] - it.colours.D65.Lab[i]));
      }
      return [w, ""];
    });
    safe("formantsFromPoly(degree-16 vowel a) vs lpc_formants (Hz)", 0.05, () => {
      let w = 0, wm = "";
      for (const it of vowels.items) {
        const F = P.formantsFromPoly(it.a).F.slice(0, 4);
        if (F.length !== it.lpc_formants.length) return [Infinity, `count ${it.group}/${it.vowel}`];
        for (let i = 0; i < F.length; i++) { const e = Math.abs(F[i] - it.lpc_formants[i]); if (e > w) { w = e; wm = `${it.group}/${it.vowel}`; } }
      }
      return [w, wm];
    });
    safe("vowelMedia∘reflection round trip (|m - m_json|/m)", 1e-6, () => {
      let w = 0;
      for (const it of vowels.items) {
        const m = P.vowelMedia(it.a);
        for (let i = 0; i < m.length; i++) w = Math.max(w, Math.abs(m[i] - it.m[i]) / it.m[i]);
      }
      return [w, ""];
    });
  }
  if (butterflies) {
    safe("buildLUT vs butterflies.json lut (hex R, 0..80°; ±1/255)", 1, () => {
      let w = 0, wm = "";
      for (const b of butterflies.items) {
        const lut = P.buildLUT(b.n, b.d_nm, b.lut.quantity || "R", b.lut.illuminant || "D65", b.lut.angles);
        lut.forEach((rgb, i) => { const e = hexDiff(P.toHex(rgb), b.lut.rgb[i]); if (e > w) { w = e; wm = `${b.name} @${b.lut.angles[i]}°`; } });
      }
      return [w, wm];
    });
    safe("voiceOfFilm(butterfly) vs butterflies.json a", 1e-6, () => {
      let w = 0;
      for (const b of butterflies.items) {
        const { a } = P.voiceOfFilm(b.n, b.d_nm);
        for (let i = 0; i < a.length; i++) w = Math.max(w, Math.abs(a[i] - b.a[i]) / Math.max(1, Math.abs(b.a[i])));
      }
      return [w, ""];
    });
  }
  return out;
}

/** Timing of the hot path (ms per call): filmRT on the 941-point CIE grid, 45°, unpolarised. */
export function timeFilmRT(P, n, d, reps = 500) {
  const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());
  const wl = P.getWL();
  for (let i = 0; i < 50; i++) P.filmRT(n, d, wl, 45, "u");
  const t0 = now();
  for (let i = 0; i < reps; i++) P.filmRT(n, d, wl, 45, "u");
  return (now() - t0) / reps;
}
