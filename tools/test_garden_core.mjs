// Node test for web/js/garden_core.js (Butterfly Garden pure logic).
// Run:  . .\tools\env.ps1; node tools/test_garden_core.mjs        Exit code 0 iff every check passes.
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "web");
const readJSON = (p) => JSON.parse(readFileSync(join(web, p), "utf8"));
const P = await import(pathToFileURL(join(web, "js", "physics.js")).href);
const G = await import(pathToFileURL(join(web, "js", "garden_core.js")).href);
P.setPhysicsData(readJSON("data/cie.json"));
const atlas = readJSON("data/atlas_sample.json");
const vowels = readJSON("data/vowels.json");

const results = [];
function check(name, pass, msg = "") { results.push({ name, pass: !!pass, msg }); }

// 1. PRNG determinism
{
  const a = G.makeRng(42), b = G.makeRng(42), c = G.makeRng(43), s = G.makeRng("garden"), s2 = G.makeRng("garden");
  const xa = Array.from({ length: 1000 }, a.random), xb = Array.from({ length: 1000 }, b.random);
  const xc = Array.from({ length: 1000 }, c.random);
  const same = xa.every((v, i) => v === xb[i]);
  const diff = xa.some((v, i) => v !== xc[i]);
  const inRange = xa.every((v) => v >= 0 && v < 1);
  const n1 = G.randomStack(s, 16, "realizable"), n2 = G.randomStack(s2, 16, "realizable");
  check("PRNG: same seed ⇒ identical sequence & identical stack", same && n1.every((v, i) => v === n2[i]));
  check("PRNG: different seed ⇒ different sequence; values in [0,1)", diff && inRange);
  const mean = xa.reduce((p, q) => p + q, 0) / xa.length;
  check("PRNG: mean of 1000 uniforms ≈ 0.5", Math.abs(mean - 0.5) < 0.04, `mean ${mean.toFixed(3)}`);
}

// 2. fast colour path == Abelès TMM (physics.filmColour) at normal incidence
{
  const rng = G.makeRng(7);
  let worst = 0;
  for (const [N, mode, q, ill, scale] of [[16, "realizable", "R", "D65", 1], [5, "ideal", "T", "A", 1], [24, "materials", "R", "F11", 1], [10, "realizable", "T", "LED", 0.7]]) {
    const n = G.randomStack(rng, N, mode);
    const d = G.goupD(n, scale);
    const fast = G.colourEvaluator(ill, q, scale, 1)(n).Lab;
    const ref = P.filmColour(n, d, 0, ill, q).Lab;
    worst = Math.max(worst, ...fast.map((v, i) => Math.abs(v - ref[i])));
  }
  check("fast colour (isomorphism T=Π(1−c²)/|D|²) == filmColour TMM", worst < 1e-6, `max |ΔLab| ${worst.toExponential(2)}`);
}

// 3. voice: exact D(z) equals physics.voiceOfFilm for a Goupillaud stack (N ≤ 16, θ = 0)
{
  const n = G.randomStack(G.makeRng(3), 12, "realizable", { arm: "bimodal" });
  const d = G.goupD(n);
  const ex = G.voiceOf(n, d, 0), fit = P.voiceOfFilm(n, d, 0, 16);
  let err = 0;
  for (let i = 0; i < fit.a.length; i++) err = Math.max(err, Math.abs((ex.a[i] || 0) - fit.a[i]));
  check("voiceOf exact D(z) == voiceOfFilm (Goupillaud, θ=0)", ex.exact && err < 1e-6, `max |Δa| ${err.toExponential(2)}`);
  check("voiceOf at θ=30° is flagged approximate", G.voiceOf(n, d, 30).exact === false);
}

// 4. inverse design: 3 atlas targets (own entry excluded from the seeds), ΔE00 < 2, distinct voices, time budget
{
  const cand = atlas.items.map((it, i) => ({ it, i })).filter(({ it }) => it.F1 != null && it.F2 != null);
  const picks = [cand[3], cand[Math.floor(cand.length / 2)], cand[cand.length - 5]];
  const budgetMs = 15000;
  picks.forEach(({ it, i }, t) => {
    const useAtlas = t !== 1; // target #2: pure random restarts (no atlas seeding at all)
    const t0 = Date.now();
    const D = G.createDesigner({ targetLab: it.LabR, nLayers: 16, mode: "realizable", illuminant: "D65", quantity: "R",
      seed: 100 + t, atlas: useAtlas ? atlas : null, excludeAtlas: [i], nSolutions: 4, autoRetarget: false });
    const res = D.runSync(budgetMs);
    const ms = Date.now() - t0;
    const maxDE = Math.max(...res.map((r) => r.dE));
    // independent re-check of every metamer with the TMM colour
    const recheck = Math.max(...res.map((r) => P.deltaE00(P.filmColour(r.n, r.d, 0, "D65", "R").Lab, it.LabR)));
    const inBounds = res.every((r) => r.n.every((v, k) => (k === 0 ? v === 1 : v >= 1 - 1e-12 && v <= 2.5 + 1e-12)));
    check(`inverse #${t + 1} (atlas ${i}${useAtlas ? ", seeds excl. self" : ", random only"}): ≥3 metamers, ΔE00<2, ≤${budgetMs / 1000}s`,
      res.length >= 3 && maxDE < 2 && recheck < 2 && ms <= budgetMs && inBounds,
      `${res.length} sols, max ΔE ${maxDE.toFixed(2)} (TMM ${recheck.toFixed(2)}), ${ms} ms, restarts ${D.progress.restarts}`);
    let minSep = Infinity;
    for (let a = 0; a < res.length; a++) for (let b = a + 1; b < res.length; b++) {
      minSep = Math.min(minSep, Math.hypot(res[a].voice.F1 - res[b].voice.F1, res[a].voice.F2 - res[b].voice.F2));
    }
    check(`inverse #${t + 1}: metamers have distinct F1/F2 (min pair sep > 50 Hz)`, res.length >= 2 && minSep > 50,
      `F1/F2: ${res.map((r) => `${Math.round(r.voice.F1)}/${Math.round(r.voice.F2)}${r.voice.strict ? "" : "*"}`).join(" ")}; min sep ${minSep.toFixed(0)} Hz`);
  });
}

// 5. evolve keeps n in bounds (all modes) and N in [2, 24]
{
  const rng = G.makeRng("evolve");
  let ok = true, msg = "";
  for (const mode of ["realizable", "ideal", "materials"]) {
    const [lo, hi] = G.boundsFor(mode);
    let n = G.randomStack(rng, 3, mode);
    let minN = 99, maxN = 0;
    for (let g = 0; g < 400; g++) {
      n = G.evolveStep(n, rng, { sigma: 0.3, mode, mutateLayers: true, pLayer: 0.6 });
      const N = n.length - 2;
      minN = Math.min(minN, N); maxN = Math.max(maxN, N);
      if (n[0] !== 1 || N < 2 || N > 24 || n.some((v, k) => k > 0 && !(v >= lo - 1e-12 && v <= hi + 1e-12))) { ok = false; msg = `${mode} gen ${g}`; break; }
    }
    msg += `${mode}: N∈[${minN},${maxN}] `;
  }
  check("evolve keeps n in mode bounds, n0 = 1, N in [2,24] (400 gens × 3 modes)", ok, msg);
  const a = G.evolveStep(G.randomStack(G.makeRng(1), 16), G.makeRng(9)), b = G.evolveStep(G.randomStack(G.makeRng(1), 16), G.makeRng(9));
  check("evolve deterministic for a given seed", a.every((v, i) => v === b[i]));
}

// 6. word → vowel sequence → films → song
{
  const seq1 = G.parseWord("heed hid had", vowels).map((x) => x.code).join(" ");
  const seq2 = G.parseWord("a e i o u", vowels).map((x) => x.code).join(" ");
  const seq3 = G.parseWord("iy ɑ who'd", vowels).map((x) => x.code).join(" ");
  check("parseWord: example words / letters / codes+IPA", seq1 === "iy ih ae" && seq2 === "ah ei iy oa uw" && seq3 === "iy ah uw",
    `${seq1} | ${seq2} | ${seq3}`);
  const codes = G.parseWord("hello world", vowels);
  const polys = codes.map((c) => { const v = G.vowelItem(vowels, c.code, "women"); const f = G.vowelFilm(v.a); return G.voiceOf(f.n, f.d, 0).a; });
  const films = codes.map((c) => G.vowelFilm(G.vowelItem(vowels, c.code, "women").a));
  const inb = films.every((f) => Array.from(f.n).every((v) => v >= 1 - 1e-9 && v <= 2.5 + 1e-9));
  const s = G.singSamples(polys, { f0: 200 });
  const finite = s.samples.every(Number.isFinite);
  const peak = Math.max(...Array.from(s.samples, Math.abs));
  check("sing: free text → realizable films (n∈[1,2.5]) → stable finite audio, peak 0.9", codes.length >= 2 && inb && finite && Math.abs(peak - 0.9) < 1e-3,
    `${codes.map((c) => c.code).join(" ")}; ${s.samples.length} samples, peak ${peak.toFixed(3)}`);
}

let nPass = 0;
for (const r of results) { if (r.pass) nPass++; console.log(`${r.pass ? "PASS" : "FAIL"}  ${r.name}${r.msg ? "  — " + r.msg : ""}`); }
console.log(`\n${nPass}/${results.length} garden_core checks passed`);
process.exit(nPass === results.length ? 0 : 1);
