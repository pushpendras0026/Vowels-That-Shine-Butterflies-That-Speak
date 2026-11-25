// Node test for web/js/experiments_core.js (Experiments page pure logic).
// Run:  node tools/test_experiments_core.mjs [path/to/phonemes_experiment.json]     Exit code 0 iff every check passes.
// Without an argument, web/data/phonemes_experiment.json is validated if it exists (skipped otherwise).
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "web");
const C = await import(pathToFileURL(join(web, "js", "experiments_core.js")).href);
const sounds = JSON.parse(readFileSync(join(web, "data", "sounds.json"), "utf8"));

const results = [];
const check = (name, pass, msg = "") => results.push({ name, pass: !!pass, msg });
const ids = (toks) => toks.filter((t) => !t.sep).map((t) => t.id).join(" ");

// 1. sounds.json validation + grouping
const vs = C.validateSounds(sounds);
check("sounds.json validates", vs.ok, vs.errors.join("; "));
check("sounds.json: every item has a full·realizable·R hex", !vs.warnings.some((w) => w.includes("hex")), vs.warnings.join("; "));
const groups = C.groupByClass(vs.items);
check("groupByClass keeps every item", groups.reduce((s, g) => s + g.items.length, 0) === vs.items.length);
check("groupByClass order follows CLASS_ORDER", groups.map((g) => g.class).join() ===
  C.CLASS_ORDER.filter((c) => groups.some((g) => g.class === c)).join(), groups.map((g) => g.class).join());
check("groupByClass: unknown class appended, junk ignored",
  JSON.stringify(C.groupByClass([{ class: "zz" }, null, { class: "vowel" }, 5]).map((g) => g.class)) === '["vowel","zz"]');
check("diphthongs have 30-step trajectories", vs.items.filter((s) => s.class === "diphthong").every((s) => s.trajectory.length === 30 && s.trajectory.every(C.isHex)));
check("soundHex falls back on broken item", C.soundHex({}) === "#444444" && C.soundHex(vs.items[0]) === vs.items[0].colours.full.realizable.R.hex.toLowerCase());
check("gradientCss: 0/1/n colours", C.gradientCss([]) === "#333" && C.gradientCss(["#ABCDEF"]) === "#abcdef" &&
  C.gradientCss(["#000000", "#ffffff"]) === "linear-gradient(90deg, #000000 0.0%, #ffffff 100.0%)");

// 2. tokenizer
const avail = new Set(vs.items.map((s) => s.id));
const ipaMap = Object.fromEntries(vs.items.map((s) => [s.ipa, s.id]));
const T = (w) => ids(C.tokenizeWord(w, avail, ipaMap));
check("tokenize 'ship'", T("ship") === "sh ih p", T("ship"));
check("tokenize 'church' (ch, ur)", T("church") === "ch er ch", T("church"));
check("tokenize 'sing' (ng)", T("sing") === "s ih ng", T("sing"));
check("tokenize 'shine' (magic e)", T("shine") === "sh ai n", T("shine"));
check("tokenize 'make' / 'home'", T("make") === "m ei k" && T("home") === "h ou m", T("make") + " | " + T("home"));
check("tokenize 'phone' (ph, magic e)", T("phone") === "f ou n", T("phone"));
check("tokenize 'thick' (th, ck)", T("thick") === "th ih k", T("thick"));
check("tokenize 'night' (igh)", T("night") === "n ai t", T("night"));
check("tokenize 'yes' (initial y = j)", T("yes") === "j eh s", T("yes"));
check("tokenize 'box' (x = k s)", T("box") === "b aa k s", T("box"));
check("tokenize exceptions 'the' / 'you'", T("the") === "dh schwa" && T("you") === "j u");
check("tokenize typed IPA 'ʃip', 'tʃeɪ'", T("ʃip") === "sh ih p" && T("tʃeɪ") === "ch ei", T("ʃip") + " | " + T("tʃeɪ"));
const two = C.tokenizeWord("hi there", avail, ipaMap);
check("word gap token between words", two.some((t) => t.sep) && !two[0].sep);
check("unknown chars skipped, empty input ok", T("123 !!") === "" && C.tokenizeWord("", avail).length === 0 && C.tokenizeWord(null).length === 0);
const miss = C.tokenizeWord("sh", new Set(["s"]));
check("missing phoneme → id null, want kept", miss.length === 1 && miss[0].id === null && miss[0].want === "sh");
check("every grapheme maps to an existing sounds.json id",
  Object.values(C.GRAPHEMES).flat().concat(Object.values(C.WORD_EXCEPTIONS).flat()).every((id) => avail.has(id)),
  Object.values(C.GRAPHEMES).flat().concat(Object.values(C.WORD_EXCEPTIONS).flat()).filter((id) => !avail.has(id)).join(","));
check("long input is capped (no hang)", C.tokenizeWord("a".repeat(100000)).length <= 200);

// 3. hull
const sq = [[0, 0], [2, 0], [2, 2], [0, 2], [1, 1], [1, 0], [0, 0], [NaN, 3], "x"];
const h = C.convexHull(sq);
check("hull of square + interior/collinear/duplicate/junk = 4 corners", h.length === 4 && C.polygonArea(h) === 4, JSON.stringify(h));
check("hull degenerate inputs", C.convexHull([]).length === 0 && C.convexHull([[1, 1], [1, 1]]).length === 1 && C.convexHull([[0, 0], [1, 1], [2, 2]]).length === 2);
{
  let s = 7; const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const pts = Array.from({ length: 500 }, () => [rnd() * 100 - 50, rnd() * 80 - 40]);
  const H = C.convexHull(pts);
  const inside = (p) => H.every((a, i) => { const b = H[(i + 1) % H.length]; return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9; });
  check("hull (500 random pts) is CCW and contains every point", pts.every(inside) && H.length >= 3);
}
const B = C.abBounds([[[0, 0], [10, -5]], [[3, 20]]], 2);
check("abBounds pads and covers all lists", B.xmin === -2 && B.xmax === 12 && B.ymin === -7 && B.ymax === 22, JSON.stringify(B));
check("abBounds empty → default", C.abBounds([[]]).xmin === -60);
check("uniqueSortedHexes dedupes, drops junk, sorts", JSON.stringify(C.uniqueSortedHexes(["#0000ff", "#FF0000", "#ff0000", "bad", "#00ff00", "#808080"])) ===
  '["#ff0000","#00ff00","#0000ff","#808080"]');
check("bestVoice picks min dB, ignores junk", JSON.stringify(C.bestVoice({ A: 9, B: 3.5, C: NaN, D: "1" })) === '{"name":"B","db":3.5}' && C.bestVoice(null) === null);

// 4. experiment validation (schema in docs/PHONEMES.md)
const good = {
  settings: { angles_deg: [0, 15, 30, 45, 60] }, findings: ["x"], butterflies: [{ name: "M", hex: "#112233" }], figures: [],
  classes: [
    { class: "nasal", verdict: "few", gamut: { hexes: ["#ff00ff"], ab: [[50, -20]], hull_ab: [] },
      proof: { title: "t", claim: "c", steps: ["s1"], numeric_check: "n", holds: true } },
    { class: "fricative", verdict: "many", gamut: { hexes: ["#aa00ff", "#bb11ee"], ab: [[30, -40], [20, -30]], hull_ab: [] }, proof: null }],
  items: [{ id: "m", hex: "#ff00ff", angle_hexes: ["#ff00ff", "#ff00ff", "#ff00ff", "#ff00ff", "#ff00ff"], nearest_butterfly: { name: "M", dE00: 3, spectral_corr: 0.5 }, twin: { hex: "#ff00ff" } }],
};
const vg = C.validateExperiment(good);
check("valid experiment → ok, no warnings", vg.ok && vg.warnings.length === 0, vg.errors.concat(vg.warnings).join("; "));
const noProof = structuredClone(good); noProof.classes[0].proof = null;
check("verdict few without proof → error", !C.validateExperiment(noProof).ok);
check("missing classes/items → error", !C.validateExperiment({}).ok && !C.validateExperiment(null).ok && !C.validateExperiment({ classes: [] }).ok);
const badHex = structuredClone(good); badHex.items[0].hex = "red"; badHex.classes[1].gamut.ab.pop();
const vb = C.validateExperiment(badHex);
check("bad hex / length mismatch → warnings, still ok", vb.ok && vb.warnings.length === 2, vb.warnings.join("; "));
check("safeDataUrl: relative + localhost ok, foreign/js rejected",
  C.safeDataUrl("data/x.json", "http://127.0.0.1:8123") === "http://127.0.0.1:8123/data/x.json" &&
  C.safeDataUrl("http://localhost:9000/f.json", "http://127.0.0.1:8123") !== null &&
  C.safeDataUrl("https://evil.example/f.json", "http://127.0.0.1:8123") === null &&
  C.safeDataUrl("javascript:alert(1)", "http://127.0.0.1:8123") === null && C.safeDataUrl("", "http://x") === null);

// 4b. optional additions: realistic butterflies + fluorescence
const baseExp = { classes: [], items: [{ id: "i", hex: "#112233", nearest_real_butterfly: { name: "Morpho didius", dE00: 30, spectral_corr: 0.1 } }],
  findings: [], butterflies: [], figures: [], settings: { angles_deg: [0] } };
const vNo = C.validateExperiment(baseExp);
check("optional fields absent → no extra warnings", vNo.ok && vNo.warnings.length === 0, vNo.warnings.join("; "));
const goodG = { ...baseExp, real_butterflies: [{ name: "Morpho didius", hex: "#56a1ff", angle_hexes: ["#56a1ff", "#8cb8ff"], peak_nm: 432 }],
  fluorescence: { items: [{ id: "i", hex_D65: "#aabbcc", hex_UV: "#00de74", hex_violet: "#00d9a0", fluor_fraction_D65: 0.4 }] },
  fluorescence_proof: { title: "t", claim: "c", steps: ["s"], numeric_check: "n", holds: true } };
const vgG = C.validateExperiment(goodG);
check("valid real_butterflies + fluorescence + proof → no warnings", vgG.ok && vgG.warnings.length === 0, vgG.warnings.join("; "));
const badG = { ...goodG, items: [{ id: "i", hex: "#112233", nearest_real_butterfly: { name: "Nope", dE00: 1, spectral_corr: 0 } },
  { id: "j", hex: "#112233", nearest_real_butterfly: { name: "x" } }],
  real_butterflies: [{ name: "Morpho didius", hex: "blue", angle_hexes: ["#zz0000"] }],
  fluorescence: { items: [{ id: "i", hex_D65: "#aabbcc", hex_UV: "nope", hex_violet: "#00d9a0", fluor_fraction_D65: 1.5 }] },
  fluorescence_proof: { title: "t", steps: [], holds: "yes" } };
const vbad = C.validateExperiment(badG);
const W = vbad.warnings.join(" | ");
check("bad optional fields → warnings only (page still renders)", vbad.ok && ["not in real_butterflies", "nearest_real_butterfly incomplete",
  "hex invalid", "angle_hexes invalid", "hex_UV invalid", "fluor_fraction_D65", "title/claim", "no steps", "holds"].every((k) => W.includes(k)), W);
check("fluorHex modes + fallback", C.fluorHex(goodG.fluorescence.items[0], "UV") === "#00de74" &&
  C.fluorHex(goodG.fluorescence.items[0], "violet") === "#00d9a0" && C.fluorHex({}, "UV") === "#444444" &&
  C.fluorHex(goodG.fluorescence.items[0], "junk") === "#aabbcc");
check("realWinCounts sorts by count", JSON.stringify(C.realWinCounts([{ nearest_real_butterfly: { name: "B" } }, { nearest_real_butterfly: { name: "A" } },
  { nearest_real_butterfly: { name: "B" } }, {}, null])) === '[{"name":"B","n":2},{"name":"A","n":1}]');

// 5. the real (or given) experiment file, if present
const expPath = process.argv[2] || join(web, "data", "phonemes_experiment.json");
if (existsSync(expPath)) {
  const d = JSON.parse(readFileSync(expPath, "utf8"));
  const v = C.validateExperiment(d);
  check(`experiment file validates (${expPath.split("/").pop()})`, v.ok, v.errors.join("; "));
  console.log(`  ${v.warnings.length} warning(s)${v.warnings.length ? ": " + v.warnings.slice(0, 8).join("; ") : ""}`);
  const few = d.classes.filter((c) => c.verdict === "few");
  check("every 'few' class has a proof with steps", few.every((c) => c.proof && Array.isArray(c.proof.steps) && c.proof.steps.length));
  if (d.fluorescence) check("fluorescence covers every item", d.items.every((it) => d.fluorescence.items.some((f) => f.id === it.id)));
  if (d.fluorescence_proof) check("fluorescence_proof holds (numeric check)", d.fluorescence_proof.holds === true, d.fluorescence_proof.numeric_check);
  if (d.real_butterflies) check("every nearest_real_butterfly is a listed species", d.items.every((it) => !it.nearest_real_butterfly ||
    d.real_butterflies.some((b) => b.name === it.nearest_real_butterfly.name)));
  check("every experiment item id exists in sounds.json", d.items.every((it) => avail.has(it.id)), d.items.filter((it) => !avail.has(it.id)).map((it) => it.id).join(","));
  for (const c of d.classes) {
    const ab = (c.gamut?.ab || []).filter((p) => Array.isArray(p));
    if (ab.length >= 3) {
      const H = C.convexHull(ab);
      check(`hull of ${c.class} has ≥ 3 vertices (${ab.length} pts)`, H.length >= 3 || new Set(ab.map(String)).size < 3);
    }
  }
} else console.log(`  (no ${expPath}; experiment-file checks skipped)`);

for (const r of results) console.log(`${r.pass ? "PASS" : "FAIL"}  ${r.name}${r.msg && !r.pass ? "   " + r.msg : ""}`);
const n = results.filter((r) => r.pass).length;
console.log(`experiments_core: ${n}/${results.length} pass`);
process.exit(n === results.length ? 0 : 1);
