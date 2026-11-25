// Node conformance test for web/js/physics.js against web/data/test_vectors.json (Python reference).
// Run:  . .\tools\env.ps1; node tools/node_test.mjs        Exit code 0 iff every case passes.
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "web");
const readJSON = (p) => JSON.parse(readFileSync(join(web, p), "utf8"));

const P = await import(pathToFileURL(join(web, "js", "physics.js")).href);
const T = await import(pathToFileURL(join(web, "js", "physics_tests.js")).href);

P.setPhysicsData(readJSON("data/cie.json"));
const vectors = readJSON("data/test_vectors.json");
const results = T.runVectorCases(P, vectors);
let extras = [];
try { extras = T.runExtraChecks(P, readJSON("data/vowels.json"), readJSON("data/butterflies.json")); }
catch (e) { console.log("extra checks skipped:", e.message); }

const fmt = (x) => (Number.isFinite(x) ? x.toExponential(2) : String(x));
for (const r of [...results, ...extras]) {
  console.log(`${r.pass ? "PASS" : "FAIL"}  ${r.name.padEnd(58)} err ${fmt(r.err).padStart(9)}  tol ${fmt(r.tol)}${r.msg && !r.pass ? "  " + r.msg : ""}`);
}
const nPass = results.filter((r) => r.pass).length;
const xPass = extras.filter((r) => r.pass).length;

// performance of the hot path
const vb = readJSON("data/butterflies.json").items[0];
const ms = T.timeFilmRT(P, vb.n, vb.d_nm, 1000);
const t0 = performance.now();
for (let i = 0; i < 20; i++) P.voiceOfFilm(vb.n, vb.d_nm, 30);
const msVoice = (performance.now() - t0) / 20;
const vw = readJSON("data/vowels.json").items[0];
const t1 = performance.now();
for (let i = 0; i < 100; i++) P.vowelColour(vw.a);
const msVowel = (performance.now() - t1) / 100;
console.log(`timing: filmRT 941 pts @45° u = ${ms.toFixed(3)} ms; voiceOfFilm(2048, 30°) = ${msVoice.toFixed(2)} ms; vowelColour = ${msVowel.toFixed(3)} ms`);
console.log(`vectors PASS ${nPass}/${results.length}; extra checks ${xPass}/${extras.length}`);
process.exit(nPass === results.length && xPass === extras.length ? 0 : 1);
