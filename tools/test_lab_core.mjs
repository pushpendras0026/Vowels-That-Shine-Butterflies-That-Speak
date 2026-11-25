// Node test for web/js/lab_core.js (Live Voice Lab pipeline): resampler, gate, smoothing, isomorphism,
// F1/F2 of the bundled vowel WAVs vs Hillenbrand.   Run:  . .\tools\env.ps1; node tools/test_lab_core.mjs
// Exit code 0 iff every check passes.
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "web");
const P = await import(pathToFileURL(join(web, "js", "physics.js")).href);
const L = await import(pathToFileURL(join(web, "js", "lab_core.js")).href);
P.setPhysicsData(JSON.parse(readFileSync(join(web, "data", "cie.json"), "utf8")));
const vowels = JSON.parse(readFileSync(join(web, "data", "vowels.json"), "utf8")).items;

const results = [], info = [];
const check = (name, pass, info = "") => { results.push({ name, pass, info }); };
const median = (xs) => { const s = xs.filter((x) => x != null && Number.isFinite(x)).sort((a, b) => a - b); return s.length ? s[s.length >> 1] : NaN; };
const wav = (name) => L.parseWav(readFileSync(join(web, "audio", name)));

// deterministic LCG noise
let seed = 12345;
const rnd = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296 - 0.5; };
const noise = (n, ampDb) => { const a = Math.pow(10, ampDb / 20) * Math.sqrt(12); return Float32Array.from({ length: n }, () => a * rnd()); };

/** Zero-stuffing ×3 + windowed-sinc low-pass (independent of the code under test) to fake a 48 kHz capture. */
function upsample3(x) {
  const N = x.length * 3, y = new Float64Array(N), hw = 48;
  for (let i = 0; i < N; i++) {
    let acc = 0;
    const t = i / 3;
    for (let j = Math.ceil(t - hw / 3); j <= Math.floor(t + hw / 3); j++) {
      if (j < 0 || j >= x.length) continue;
      const d = t - j, s = d === 0 ? 1 : Math.sin(Math.PI * d) / (Math.PI * d);
      const w = 0.5 + 0.5 * Math.cos(Math.PI * d / (hw / 3));
      acc += x[j] * s * w;
    }
    y[i] = acc;
  }
  return Float32Array.from(y);
}

function runPipeline(samples, srcRate, opts = {}, chunk = 1024) {
  const pipe = new L.LabPipeline(srcRate, opts);
  const hops = [];
  for (let i = 0; i < samples.length; i += chunk) hops.push(...pipe.pushSamples(samples.subarray(i, Math.min(samples.length, i + chunk))));
  return hops;
}

// ---------------------------------------------------------------- 1. WAV + resampler
{
  const w = wav("vowel_men_iy.wav");
  check("parseWav: 16 kHz mono, 0.7 s", w.sampleRate === 16000 && w.data.length === 11200, `sr ${w.sampleRate}, n ${w.data.length}`);

  const fs = 48000, n = fs;   // 1 s tones
  const tone = (f) => Float32Array.from({ length: n }, (_, i) => Math.sin(2 * Math.PI * f * i / fs));
  const rs = (x) => { const r = new L.StreamResampler(fs, 16000); const parts = []; for (let i = 0; i < x.length; i += 480) parts.push(r.push(x.subarray(i, i + 480))); return Float64Array.from(parts.flatMap((p) => Array.from(p))); };
  const y1 = rs(tone(1000)), y12 = rs(tone(12000));
  const rmsMid = (y) => { let s = 0, c = 0; for (let i = 2000; i < y.length - 2000; i++) { s += y[i] * y[i]; c++; } return Math.sqrt(s / c); };
  // 1 kHz: amplitude kept and phase-exact vs ideal 16 kHz sine (latency 0)
  let errMax = 0;
  for (let i = 2000; i < y1.length - 2000; i++) errMax = Math.max(errMax, Math.abs(y1[i] - Math.sin(2 * Math.PI * 1000 * i / 16000)));
  check("resampler 48k->16k: length", Math.abs(y1.length - 16000) <= 40, `${y1.length}`);
  check("resampler: 1 kHz tone preserved (max err < 1e-2)", errMax < 1e-2, `err ${errMax.toExponential(2)}`);
  const att = 20 * Math.log10(rmsMid(y12) / (Math.SQRT1_2));
  check("resampler: 12 kHz tone rejected (< -50 dB, no aliasing to 4 kHz)", att < -50, `${att.toFixed(1)} dB`);
  const r44 = new L.StreamResampler(44100, 16000);
  const y44 = r44.push(Float32Array.from({ length: 44100 }, (_, i) => Math.sin(2 * Math.PI * 440 * i / 44100)));
  let e44 = 0;
  for (let i = 1000; i < y44.length - 1000; i++) e44 = Math.max(e44, Math.abs(y44[i] - Math.sin(2 * Math.PI * 440 * i / 16000)));
  check("resampler 44.1k->16k (fractional): 440 Hz preserved", e44 < 1e-2, `err ${e44.toExponential(2)}`);
}

// ---------------------------------------------------------------- 2. gate on silence / noise
{
  const zeros = new Float32Array(16000 * 2);
  const hz = runPipeline(zeros, 16000);
  check("gate: digital silence never voiced/active", hz.every((h) => !h.voiced && !h.active && !h.updated && h.level === 0), `${hz.filter((h) => h.active).length}/${hz.length}`);
  const nz = noise(16000 * 3, -55);
  const hn = runPipeline(nz, 16000);
  check("gate: white noise at -55 dBFS never voiced/active (never paints)", hn.every((h) => !h.voiced && !h.active && !h.updated), `${hn.filter((h) => h.active).length}/${hn.length}`);
  const loud = noise(16000 * 2, -20);
  const hl = runPipeline(loud, 16000);
  // stationary noise present from the start is absorbed by the calibrated floor (it is "background", not a fricative)
  check("gate: stationary loud white noise from t=0 (-20 dBFS) absorbed by floor: never voiced/active", hl.every((h) => !h.voiced && !h.active && !h.updated), `${hl.filter((h) => h.active).length}/${hl.length}`);
}

// ---------------------------------------------------------------- 3. vowels through the full pipeline (16k and fake 48k)
const groups = ["men", "women"];
const targets = ["iy", "ah", "uw"];
for (const g of groups) {
  for (const v of targets) {
    const item = vowels.find((it) => it.group === g && it.vowel === v);
    const w = wav(`vowel_${g}_${v}.wav`);
    const { data, marks } = L.concatWithGaps([w.data], 0.6, 16000, 0.6);
    // add a -65 dBFS noise floor so the auto-calibration has something to track
    const nz = noise(data.length, -65);
    const x = Float32Array.from(data, (s, i) => s + nz[i]);
    for (const [label, sig, sr] of [["16k", x, 16000], ["48k", upsample3(x), 48000]]) {
      const hops = runPipeline(sig, sr);
      const [t0, t1] = marks[0];
      const inside = hops.filter((h) => h.t - 0.032 >= t0 + 0.02 && h.t <= t1 - 0.02);   // frames fully inside the vowel
      const outside = hops.filter((h) => h.t < t0 - 0.01 || h.t - 0.032 > t1 + 0.12);   // pure noise (allow hangover)
      const vf = inside.filter((h) => h.updated).length / Math.max(1, inside.length);
      const falsePos = outside.filter((h) => h.voiced).length;
      check(`${g}/${v} ${label}: voiced >= 90% inside vowel`, vf >= 0.9, `${(100 * vf).toFixed(0)}%`);
      check(`${g}/${v} ${label}: no voiced frames in noise`, falsePos === 0, `${falsePos}`);
      const uvIn = inside.filter((h) => h.unvoiced).length, actOut = outside.filter((h) => h.active || h.updated).length;
      check(`${g}/${v} ${label}: vowel not taken for a fricative, noise never paints`, uvIn === 0 && actOut === 0, `unvoiced inside ${uvIn}, active outside ${actOut}`);
      const F1 = median(inside.map((h) => h.F1)), F2 = median(inside.map((h) => h.F2));
      const [l1, l2] = item.lpc_formants;
      const e1 = Math.abs(F1 / item.F1 - 1), e2 = Math.abs(F2 / item.F2 - 1);
      // 32 ms frames: for low-F0 male voices LPC-16 F1 is pulled toward a harmonic (known LPC bias) => 20% on F1
      const ok = e1 < 0.20 && e2 < 0.10 && Math.abs(F1 / l1 - 1) < 0.12 && Math.abs(F2 / l2 - 1) < 0.06;
      check(`${g}/${v} ${label}: F1/F2 ~ Hillenbrand (20%/10%) & ~ build LPC (12%/6%)`, ok,
        `F1 ${F1.toFixed(0)} (H ${item.F1.toFixed(0)}, lpc ${l1.toFixed(0)})  F2 ${F2.toFixed(0)} (H ${item.F2.toFixed(0)}, lpc ${l2.toFixed(0)})`);
      if (label === "16k") {
        // colour vs vowels.json (built from the synthesis polynomial; ours is from the WAV) — reported, loose
        const labs = inside.filter((h) => h.colourR).map((h) => h.colourR.Lab);
        const mid = labs[labs.length >> 1];
        const dE = P.deltaE00(mid, item.colours_full_real.D65.LabR);
        info.push(`${g}/${v}: live full-band realizable R vs vowels.json colours_full_real (synthesis polynomial): dE00 ${dE.toFixed(2)}  hex ${inside[inside.length >> 1].colourR.hex} vs ${item.colours_full_real.D65.R}`);
        // smoothing: flicker between consecutive voiced frames is small and smaller than without smoothing
        const step = (arr) => { let s = 0, c = 0; for (let i = 1; i < arr.length; i++) { s += P.deltaE00(arr[i - 1], arr[i]); c++; } return c ? s / c : 0; };
        // steady part only (after the smoother has settled), with -30 dBFS noise so raw frames fluctuate
        const nz2 = noise(x.length, -30);
        const xn = Float32Array.from(x, (s, i) => s + nz2[i]);
        const steady = (hs) => hs.filter((h) => h.t - 0.032 >= t0 + 0.15 && h.t <= t1 - 0.02 && h.colour).map((h) => h.colour.Lab);
        const sS = step(steady(runPipeline(xn, 16000, { iso: false }))), sR = step(steady(runPipeline(xn, 16000, { alpha: 1.0, iso: false })));
        check(`${g}/${v}: smoothing reduces frame-to-frame colour jitter`, sS < sR, `mean dE00/hop smoothed ${sS.toFixed(3)} vs raw ${sR.toFixed(3)}`);
        // stability of smoothed filters
        const stable = inside.every((h) => h.sm && h.sm.k.every((k) => Math.abs(k) < 1));
        check(`${g}/${v}: smoothed reflection coeffs |k| < 1`, stable);
        // isomorphism in all modes, under BOTH exact mappings (CONTRACT §4b)
        const h = inside[inside.length >> 1];
        let worst = 0;
        for (const mp of ["brief", "full"]) for (const mode of ["ideal", "realizable", "materials"]) worst = Math.max(worst, L.isoCurves(h.sm.a, h.sm.gain, h.m, mode, 351, P.MAPPINGS[mp].dOpt).maxDiff);
        check(`${g}/${v}: film T == tube P (all modes, brief & full mapping) max|diff| < 1e-9`, worst < 1e-9, worst.toExponential(2));
        // the pipeline's iso curves use the mapping's d_opt and Δν: full-band puts f = 0 at 750 THz
        const fEnd = h.iso.f[h.iso.f.length - 1], fFold = Math.min(fEnd, P.FS - fEnd);
        check(`${g}/${v}: pipeline iso uses full-band d_opt/Δν (f(750 THz) = 0)`, Math.abs(h.iso.dOpt - P.D_OPT_FULL_NM) < 1e-9 && fFold < 1e-3 && h.iso.maxDiff < 1e-9,
          `d_opt ${h.iso.dOpt.toFixed(2)} nm, |f(750 THz)| ${fFold.toExponential(1)} Hz, maxDiff ${h.iso.maxDiff.toExponential(1)}`);
        // R/T pair from one Abelès evaluation == physics.vowelColour for both quantities and mappings
        let pe = 0;
        for (const mp of ["brief", "full"]) for (const mode of ["ideal", "realizable"]) {
          const pr = L.colourPair(h.sm.a, mode, "D65", P.MAPPINGS[mp].dOpt);
          for (const q of ["R", "T"]) { const vc = P.vowelColour(h.sm.a, mode, "D65", q, 0, P.MAPPINGS[mp].dOpt); pe = Math.max(pe, ...vc.XYZ.map((x, i) => Math.abs(x - pr[q].XYZ[i]))); if (vc.hex !== pr[q].hex) pe = Infinity; }
        }
        check(`${g}/${v}: colourPair R/T == physics.vowelColour (both mappings)`, pe < 1e-9, pe.toExponential(2));
      }
    }
  }
}

// ---------------------------------------------------------------- 4. demo sentence: gate opens/closes per vowel, lights fade
{
  const clips = ["iy", "ah", "uw", "eh"].map((v) => wav(`vowel_women_${v}.wav`).data);
  const { data, marks } = L.concatWithGaps(clips, 0.4, 16000, 0.3);
  const hops = runPipeline(data, 16000);
  let segs = 0, prev = false;
  for (const h of hops) { if (h.voiced && !prev) segs++; prev = h.voiced; }
  check("demo sentence (4 vowels, 0.4 s gaps): exactly 4 voiced segments", segs === 4, `${segs}`);
  let aseg = 0, ap = false;
  for (const h of hops) { if (h.active && !ap) aseg++; ap = h.active; }
  check("demo sentence: exactly 4 active (lit) segments, no fricative false alarms", aseg === 4 && hops.every((h) => !h.unvoiced), `${aseg} segments, ${hops.filter((h) => h.unvoiced).length} unvoiced hops`);
  // in every gap the light level decays monotonically (gentle fade, no flicker) and is < 0.3 before the next vowel
  let fadeOk = true; const ends = [];
  for (let i = 0; i + 1 < marks.length; i++) {
    const gp = hops.filter((h) => h.t - 0.032 > marks[i][1] && h.t < marks[i + 1][0]);
    for (let j = 1; j < gp.length; j++) if (gp[j].level > gp[j - 1].level + 1e-12) fadeOk = false;
    const last = gp[gp.length - 1].level; ends.push(last.toFixed(2)); if (!(last < 0.3)) fadeOk = false;
  }
  check("demo sentence: lights fade monotonically in gaps, < 0.3 before next vowel", fadeOk, ends.join(","));
  // timing
  const t0 = performance.now();
  const n = runPipeline(data, 16000).length;
  const ms = (performance.now() - t0) / n;
  check("performance: full pipeline per 16 ms hop < 4 ms", ms < 4, `${ms.toFixed(3)} ms/hop`);
}

// ---------------------------------------------------------------- 5. robustness: pathological input never stalls the pipeline
{
  const fs = 16000, n = fs;
  const vow = wav("vowel_women_ah.wav").data;
  const item = vowels.find((it) => it.group === "women" && it.vowel === "ah");
  const cases = {
    "800 Hz sine -15 dBFS": Float32Array.from({ length: n }, (_, i) => 0.178 * Math.sin(2 * Math.PI * 800 * i / fs)),
    "120 Hz square": Float32Array.from({ length: n }, (_, i) => (Math.sin(2 * Math.PI * 120 * i / fs) >= 0 ? 0.5 : -0.5)),
    "hard-clipped vowel x20": Float32Array.from(vow, (s) => Math.max(-1, Math.min(1, 20 * s))),
  };
  for (const [name, bad] of Object.entries(cases)) {
    const { data, marks } = L.concatWithGaps([bad, vow], 0.4, fs, 0.3);
    let hops, err = null;
    try { hops = runPipeline(data, fs); } catch (e) { err = e; }
    const expected = Math.floor((data.length - L.FRAME) / L.HOP) + 1;
    check(`robust (${name}): no throw, all hops emitted`, !err && hops.length === expected, err ? err.message : `${hops.length}/${expected}`);
    if (err) continue;
    const finite = hops.every((h) => !h.colour || (h.colour.XYZ.every(Number.isFinite) && (!h.iso || Number.isFinite(h.iso.maxDiff))));
    check(`robust (${name}): every colour / iso value finite`, finite);
    const [t0, t1] = marks[1];
    const inside = hops.filter((h) => h.t - 0.032 >= t0 + 0.02 && h.t <= t1 - 0.02);
    const F1 = median(inside.filter((h) => h.updated).map((h) => h.F1)), F2 = median(inside.filter((h) => h.updated).map((h) => h.F2));
    const ok = inside.filter((h) => h.updated).length >= 0.9 * inside.length && Math.abs(F1 / item.F1 - 1) < 0.15 && Math.abs(F2 / item.F2 - 1) < 0.1;
    check(`robust (${name}): following /a/ detected again with sane F1/F2`, ok, `F1 ${F1.toFixed(0)} F2 ${F2.toFixed(0)}`);
  }
  // a throwing consumer must not stall framing
  const fr = new L.Framer(); let calls = 0;
  for (let i = 0; i < 5; i++) { try { fr.push(new Float64Array(256), () => { calls++; throw new Error("x"); }); } catch { /* expected */ } }
  check("Framer: a throwing callback does not stall framing", calls === 4, `${calls} callbacks`);
}

// ---------------------------------------------------------------- 6. consonants: energetic aperiodic frames update (flag unvoiced)
{
  const fs = 16000;
  const sec = (s) => Math.round(s * fs);
  /** cascade of first differences (+18 dB/oct): crude /s/-like high-pass noise */
  const highpass = (x, order = 3) => { let y = Float64Array.from(x); for (let r = 0; r < order; r++) { const z = new Float64Array(y.length); for (let i = 1; i < y.length; i++) z[i] = y[i] - y[i - 1]; y = z; } return y; };
  const atDb = (x, db) => { let e = 0; for (const v of x) e += v * v; const g = Math.pow(10, db / 20) / Math.sqrt(e / x.length + 1e-30); return Float32Array.from(x, (v) => v * g); };
  const sNoise = (dur, db) => atDb(highpass(noise(sec(dur), 0)), db);
  const join = (...parts) => { const n = parts.reduce((a, q) => a + q.length, 0), o = new Float32Array(n); let k = 0; for (const q of parts) { o.set(q, k); k += q.length; } return o; };
  const quiet = (dur) => noise(sec(dur), -65);
  const within = (hops, t0, t1, pad = 0.02) => hops.filter((h) => h.t - 0.032 >= t0 + pad && h.t <= t1 - pad);
  const medLab = (hs, key = "colour") => [0, 1, 2].map((i) => median(hs.map((h) => h[key].Lab[i])));

  // (a) white-noise burst well above the floor: updates through the aperiodic path
  {
    const x = join(quiet(1.0), noise(sec(0.5), -25), quiet(1.0));
    const hops = runPipeline(x, fs);
    const burst = within(hops, 1.0, 1.5, 0.05), lead = hops.filter((h) => h.t < 0.98), after = hops.filter((h) => h.t - 0.032 > 1.5 + 0.12);
    const up = burst.filter((h) => h.updated && h.unvoiced && !h.voiced).length;
    check("unvoiced: white-noise burst (-25 dBFS over -65 floor) updates shape, flagged unvoiced", up >= 0.85 * burst.length && burst.every((h) => h.active),
      `${up}/${burst.length} burst hops updated+unvoiced`);
    check("unvoiced: no update/paint before the burst or after it (+0.12 s)", lead.every((h) => !h.updated && !h.active) && after.every((h) => !h.updated && !h.active),
      `lead ${lead.filter((h) => h.active).length}, after ${after.filter((h) => h.active).length}`);
    const fin = hops.every((h) => !h.colour || (h.colour.Lab.every(Number.isFinite) && h.colourT.Lab.every(Number.isFinite)));
    const fade = after.every((h, i) => h.colour && (i === 0 || h.level <= after[i - 1].level + 1e-12));
    check("unvoiced: burst colours finite, shape held while the lights fade monotonically", fin && after.length > 0 && fade && hops[hops.length - 1].level < 0.05, `level at end ${hops[hops.length - 1].level.toFixed(3)}`);
    const pipeOff = new L.LabPipeline(fs, {}, { unvoiced: false }); const ho = [];
    for (let i = 0; i < x.length; i += 1024) ho.push(...pipeOff.pushSamples(x.subarray(i, i + 1024)));
    check("unvoiced: same burst with the aperiodic path disabled does not update (old behaviour)", ho.every((h) => !h.updated), `${ho.filter((h) => h.updated).length}`);
  }
  // (b) low noise: +6 dB above the floor (below the 12 dB margin) never paints; a 12 ms click never paints
  {
    const click = new Float32Array(sec(0.012)); for (let i = 0; i < click.length; i++) click[i] = 0.5 * (i % 2 ? 1 : -1) * Math.exp(-i / 40);
    const x = join(quiet(1.0), noise(sec(0.8), -59), quiet(0.5), click, quiet(0.8));
    const hops = runPipeline(x, fs);
    check("unvoiced: low noise (+6 dB over floor) and a 12 ms click never update/paint", hops.every((h) => !h.updated && !h.active), `${hops.filter((h) => h.active).length} active hops`);
  }
  // (c) synthetic /s/ (high-pass noise) vs a vowel: clearly different colours; vowel -> s without a gap also works
  {
    const vow = wav("vowel_women_ah.wav").data;
    const s = sNoise(0.5, -24);
    const x = join(quiet(0.8), vow, quiet(0.5), s, quiet(0.5), vow, s, quiet(0.6));
    const t = (n) => n / fs;
    const v1 = [0.8, 0.8 + t(vow.length)], s1 = [v1[1] + 0.5, v1[1] + 1.0];
    const v2 = [s1[1] + 0.5, s1[1] + 0.5 + t(vow.length)], s2 = [v2[1], v2[1] + 0.5];
    const hops = runPipeline(x, fs);
    const hv = within(hops, ...v1).filter((h) => h.updated), hs = within(hops, ...s1, 0.08).filter((h) => h.updated);
    const sIn = within(hops, ...s1, 0.05), uvFrac = sIn.filter((h) => h.unvoiced).length / Math.max(1, sIn.length);
    check("consonant: synthetic /s/ frames flagged unvoiced (>= 85%), vowel frames voiced", uvFrac >= 0.85 && hv.length > 20 && hv.every((h) => !h.unvoiced), `s unvoiced ${(100 * uvFrac).toFixed(0)}%, vowel hops ${hv.length}`);
    const dR = P.deltaE00(medLab(hv), medLab(hs)), dT = P.deltaE00(medLab(hv, "colourT"), medLab(hs, "colourT"));
    check("consonant: /s/ vs /ɑ/ colours differ clearly (full-band, realizable R, dE00 > 10)", dR > 10, `dE00 R ${dR.toFixed(1)} (T ${dT.toFixed(1)}): ${hv[hv.length >> 1].colour.hex} vs ${hs[hs.length >> 1].colour.hex}`);
    const hs2 = within(hops, s2[0] + 0.12, s2[1]).filter((h) => h.updated && h.unvoiced);
    const d2 = hs2.length ? P.deltaE00(medLab(hs2), medLab(hs)) : Infinity;
    check("consonant: /ɑ/ -> /s/ with no gap: s updates after the vowel hangover, ~ colour of isolated /s/", hs2.length >= 15 && d2 < 6, `${hs2.length} hops, dE00 vs isolated s ${d2.toFixed(1)}`);
    const hb = runPipeline(x, fs, { mapping: "brief", iso: false });
    const dB = P.deltaE00(medLab(within(hb, ...v1).filter((h) => h.updated)), medLab(within(hb, ...s1, 0.08).filter((h) => h.updated)));
    info.push(`/s/ vs /ɑ/ under the brief mapping (realizable R): dE00 ${dB.toFixed(1)}; full-band T: ${dT.toFixed(1)}`);
  }
  // (d) robustness of the consonant path: NaN / Inf / overdrive / DC offset
  {
    const vow = wav("vowel_women_ah.wav").data;
    const item = vowels.find((it) => it.group === "women" && it.vowel === "ah");
    const s = sNoise(0.5, -24);
    const nanBurst = Float32Array.from({ length: sec(0.2) }, (_, i) => (i % 7 === 0 ? NaN : i % 11 === 0 ? Infinity : 0.1 * Math.sin(i)));
    const cases = {
      "NaN/Inf burst": join(quiet(0.8), nanBurst, quiet(0.4), vow, quiet(0.4), s, quiet(0.5)),
      "x30 overdrive, |x| up to ~20 (clipped)": join(quiet(0.8), Float32Array.from(vow, (v) => 30 * v), quiet(0.4), vow, quiet(0.4), Float32Array.from(s, (v) => 30 * v), quiet(0.4), s, quiet(0.5)),
      "DC offset +0.3": Float32Array.from(join(quiet(0.8), vow, quiet(0.4), vow, quiet(0.4), s, quiet(0.4), s, quiet(0.5)), (v) => v + 0.3),
    };
    for (const [name, x] of Object.entries(cases)) {
      let hops, err = null;
      try { hops = runPipeline(x, fs); } catch (e) { err = e; }
      const expected = Math.floor((x.length - L.FRAME) / L.HOP) + 1;
      check(`robust consonant (${name}): no throw, all hops`, !err && hops.length === expected, err ? err.message : `${hops.length}/${expected}`);
      if (err) continue;
      const fin = hops.every((h) => Number.isFinite(h.feat.rmsDb) && Number.isFinite(h.gate.floorDb) && (!h.colour || (h.colour.Lab.every(Number.isFinite) && (!h.iso || Number.isFinite(h.iso.maxDiff)))));
      const tail = hops.slice(-Math.round((0.5 + 0.4 + 0.5) * fs / L.HOP));
      const vowHops = hops.filter((h) => h.updated && !h.unvoiced);
      const F1 = median(vowHops.map((h) => h.F1)), F2 = median(vowHops.map((h) => h.F2));
      const ok = fin && tail.some((h) => h.updated && h.unvoiced) && Math.abs(F1 / item.F1 - 1) < 0.2 && Math.abs(F2 / item.F2 - 1) < 0.15;
      check(`robust consonant (${name}): finite floor/colours, vowel F1/F2 sane, final /s/ still updates`, ok, `F1 ${F1.toFixed(0)} F2 ${F2.toFixed(0)}, floor ${hops[hops.length - 1].gate.floorDb.toFixed(1)} dB`);
    }
  }
}

let nPass = 0;
for (const r of results) { if (r.pass) nPass++; console.log(`${r.pass ? "PASS" : "FAIL"}  ${r.name.padEnd(72)} ${r.info}`); }
for (const s of info) console.log(`INFO  ${s}`);
console.log(`\n${nPass}/${results.length} checks passed`);
process.exit(nPass === results.length ? 0 : 1);
