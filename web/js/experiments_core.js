// experiments_core.js — pure logic for the "Experiments: every phoneme" page (web/experiments.html).
// No DOM, no physics, no network: grouping, word → phoneme tokenizer, convex hull, data validation.
// Data: web/data/sounds.json (CONTRACT §7c) and web/data/phonemes_experiment.json (docs/PHONEMES.md, FIXED schema).

export const CLASS_ORDER = ["vowel", "diphthong", "plosive", "nasal", "fricative", "affricate", "lateral", "approximant"];
export const CLASS_LABEL = {
  vowel: "Vowels", diphthong: "Diphthongs", plosive: "Plosives", nasal: "Nasals", fricative: "Fricatives",
  affricate: "Affricates", lateral: "Lateral", approximant: "Approximants",
};

const HEX = /^#[0-9a-fA-F]{6}$/;
export const isHex = (h) => typeof h === "string" && HEX.test(h);
export const safeHex = (h, fb = "#444444") => (isHex(h) ? h.toLowerCase() : fb);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);

/** The colour the site shows for a sound: full-band · realizable · reflected (same convention as `strip`). */
export function soundHex(s) {
  try { return safeHex(s.colours.full.realizable.R.hex); } catch (e) { return "#444444"; }
}

/** CSS linear-gradient over a list of hexes (bad entries → grey); one colour → that colour. */
export function gradientCss(hexes, dir = "90deg") {
  const h = (Array.isArray(hexes) ? hexes : []).map((x) => safeHex(x));
  if (!h.length) return "#333";
  if (h.length === 1) return h[0];
  return `linear-gradient(${dir}, ${h.map((c, i) => `${c} ${(100 * i / (h.length - 1)).toFixed(1)}%`).join(", ")})`;
}

/** Group items by `class`, in CLASS_ORDER (unknown classes appended alphabetically). Returns [{class,label,items}]. */
export function groupByClass(items) {
  const m = new Map();
  for (const it of Array.isArray(items) ? items : []) {
    if (!it || typeof it !== "object") continue;
    const c = typeof it.class === "string" ? it.class : "other";
    if (!m.has(c)) m.set(c, []);
    m.get(c).push(it);
  }
  const rank = (c) => { const i = CLASS_ORDER.indexOf(c); return i < 0 ? 100 : i; };
  return [...m.keys()].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .map((c) => ({ class: c, label: CLASS_LABEL[c] || c, items: m.get(c) }));
}

// ------------------------------------------------------------------ word → phonemes (APPROXIMATE, documented)
// English spelling is not phonemic; this is a deliberately small greedy longest-match table, good enough to
// "paint" a word. Ids are sounds.json ids. Whole-word exceptions first, then graphemes (longest first),
// IPA symbols typed directly are also accepted (e.g. "ʃ", "tʃ", "eɪ").
export const WORD_EXCEPTIONS = {
  the: ["dh", "schwa"], a: ["schwa"], i: ["ai"], you: ["j", "u"], to: ["t", "u"], do: ["d", "u"], of: ["schwa", "v"],
  is: ["ih", "z"], was: ["w", "schwa", "z"], one: ["w", "uh", "n"], two: ["t", "u"], eye: ["ai"], my: ["m", "ai"],
  by: ["b", "ai"], be: ["b", "i"], he: ["h", "i"], she: ["sh", "i"], we: ["w", "i"], me: ["m", "i"], no: ["n", "ou"],
  go: ["g", "ou"], so: ["s", "ou"], hello: ["h", "schwa", "l", "ou"], vowel: ["v", "au", "schwa", "l"],
  colour: ["k", "uh", "l", "schwa"], color: ["k", "uh", "l", "schwa"], butterfly: ["b", "uh", "t", "schwa", "f", "l", "ai"],
};
export const GRAPHEMES = {
  tch: ["ch"], igh: ["ai"], dge: ["jh"],
  sh: ["sh"], ch: ["ch"], th: ["th"], ng: ["ng"], ph: ["f"], ck: ["k"], qu: ["k", "w"], wh: ["w"], dg: ["jh"],
  ee: ["i"], ea: ["i"], oo: ["u"], ou: ["au"], ow: ["ou"], oi: ["oi"], oy: ["oi"], ai: ["ei"], ay: ["ei"],
  er: ["er"], ir: ["er"], ur: ["er"], ar: ["aa"], or: ["aw"], oa: ["ou"], ie: ["i"], ue: ["u"], ew: ["u"], au: ["aw"], aw: ["aw"],
  ss: ["s"], ll: ["l"], ff: ["f"], tt: ["t"], pp: ["p"], bb: ["b"], dd: ["d"], gg: ["g"], mm: ["m"], nn: ["n"], rr: ["r"], zz: ["z"],
  a: ["ae"], e: ["eh"], i: ["ih"], o: ["aa"], u: ["uh"],
  b: ["b"], c: ["k"], d: ["d"], f: ["f"], g: ["g"], h: ["h"], j: ["jh"], k: ["k"], l: ["l"], m: ["m"], n: ["n"], p: ["p"],
  q: ["k"], r: ["r"], s: ["s"], t: ["t"], v: ["v"], w: ["w"], x: ["k", "s"], z: ["z"],
};
const VOWEL_LETTERS = "aeiouy";
const MAGIC_E = { a: "ei", i: "ai", o: "ou", u: "u", e: "i" };

/**
 * Tokenize text into phoneme ids. Returns [{text, id|null, sep?:true}]: `text` = the letters (or IPA) that produced it,
 * `id` = a sounds.json id (null if it maps to a phoneme not available in `available`), `sep` marks a word gap.
 * `ipaMap` (optional) maps IPA symbols → id so typed IPA works. Unknown characters are skipped.
 */
export function tokenizeWord(text, available = null, ipaMap = null) {
  const out = [];
  const has = (id) => !available || (available.has ? available.has(id) : available.includes(id));
  const push = (t, id) => out.push({ text: t, id: has(id) ? id : null, want: id });
  const ipaKeys = ipaMap ? Object.keys(ipaMap).sort((a, b) => b.length - a.length) : [];
  const words = String(text || "").normalize("NFC").toLowerCase().slice(0, 200).split(/[\s,.;:!?\-_/]+/).filter(Boolean);
  words.forEach((w, wi) => {
    if (wi > 0 && out.length) out.push({ text: " ", id: null, sep: true });
    if (WORD_EXCEPTIONS[w]) { for (const id of WORD_EXCEPTIONS[w]) push(w, id); return; }
    let s = w;
    let longAt = -1, longId = null;
    // "magic e" (make, shine, home): drop the final e; a single vowel letter before ONE consonant becomes long
    if (s.length > 2 && s.endsWith("e") && !VOWEL_LETTERS.includes(s[s.length - 2]) && /[aeiouy]/.test(s.slice(0, -2))) {
      const v = s.length - 3;
      if (v >= 0 && MAGIC_E[s[v]] && (v === 0 || !VOWEL_LETTERS.includes(s[v - 1]))) { longAt = v; longId = MAGIC_E[s[v]]; }
      s = s.slice(0, -1);
    }
    let i = 0;
    while (i < s.length) {
      if (i === longAt) { push(s[i], longId); i += 1; continue; }
      let hit = false;
      for (const k of ipaKeys) {
        if (k && !/^[a-z]+$/.test(k) && s.startsWith(k, i)) { push(k, ipaMap[k]); i += k.length; hit = true; break; }
      }
      if (hit) continue;
      if (s[i] === "y") { push("y", i === 0 ? "j" : "i"); i += 1; continue; }
      for (const L of [3, 2, 1]) {
        const g = s.slice(i, i + L);
        if (g.length === L && GRAPHEMES[g]) { for (const id of GRAPHEMES[g]) push(g, id); i += L; hit = true; break; }
      }
      if (!hit) i += 1; // digits, punctuation, unknown letters: skipped
    }
  });
  return out;
}

// ------------------------------------------------------------------ geometry
/** Convex hull (Andrew's monotone chain) of [[x,y]…]; returns CCW polygon without repeated first point. */
export function convexHull(points) {
  const P = (Array.isArray(points) ? points : []).filter((p) => Array.isArray(p) && isNum(p[0]) && isNum(p[1]))
    .map((p) => [p[0], p[1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const pts = P.filter((p, i) => i === 0 || p[0] !== P[i - 1][0] || p[1] !== P[i - 1][1]);
  if (pts.length < 3) return pts;
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [], upper = [];
  for (const p of pts) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop(); lower.push(p); }
  for (let i = pts.length - 1; i >= 0; i--) { const p = pts[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop(); upper.push(p); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

/** Shoelace area of a polygon. */
export function polygonArea(poly) {
  let s = 0;
  for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; s += a[0] * b[1] - b[0] * a[1]; }
  return Math.abs(s) / 2;
}

/** Symmetric-ish padded bounds of many point lists: {xmin,xmax,ymin,ymax}. */
export function abBounds(lists, pad = 8) {
  let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
  for (const L of lists) for (const p of L || []) {
    if (!Array.isArray(p) || !isNum(p[0]) || !isNum(p[1])) continue;
    xmin = Math.min(xmin, p[0]); xmax = Math.max(xmax, p[0]); ymin = Math.min(ymin, p[1]); ymax = Math.max(ymax, p[1]);
  }
  if (!isFinite(xmin)) return { xmin: -60, xmax: 60, ymin: -60, ymax: 60 };
  return { xmin: Math.floor(xmin - pad), xmax: Math.ceil(xmax + pad), ymin: Math.floor(ymin - pad), ymax: Math.ceil(ymax + pad) };
}

/** Unique hexes sorted by hue then lightness (for the "all valid colours" mosaic). */
export function uniqueSortedHexes(hexes) {
  const u = [...new Set((hexes || []).filter(isHex).map((h) => h.toLowerCase()))];
  const key = (h) => {
    const r = parseInt(h.slice(1, 3), 16) / 255, g = parseInt(h.slice(3, 5), 16) / 255, b = parseInt(h.slice(5, 7), 16) / 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    let hue = 0;
    if (d > 1e-9) hue = mx === r ? ((g - b) / d + 6) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    const sat = mx > 0 ? d / mx : 0;
    return [sat < 0.08 ? 7 : hue, (r + g + b) / 3];
  };
  const K = new Map(u.map((h) => [h, key(h)]));
  return u.sort((a, b) => K.get(a)[0] - K.get(b)[0] || K.get(a)[1] - K.get(b)[1]);
}

/** "Sounds most like": the butterfly with the smallest voice log-spectral distance. {name, db} or null. */
export function bestVoice(lsd) {
  let best = null;
  if (lsd && typeof lsd === "object") for (const [k, v] of Object.entries(lsd)) if (isNum(v) && (!best || v < best.db)) best = { name: k, db: v };
  return best;
}

// ------------------------------------------------------------------ validation
/** Validate sounds.json (CONTRACT §7c, the fields this page uses). Returns {ok, errors, warnings, items}. */
export function validateSounds(d) {
  const errors = [], warnings = [];
  if (!d || !Array.isArray(d.items)) return { ok: false, errors: ["sounds.json: no items array"], warnings, items: [] };
  const items = [];
  for (const it of d.items) {
    if (!it || typeof it.id !== "string" || typeof it.ipa !== "string") { warnings.push("item without id/ipa skipped"); continue; }
    if (!isHex(it?.colours?.full?.realizable?.R?.hex)) warnings.push(`${it.id}: no full·realizable·R hex`);
    if (it.class === "diphthong" && !Array.isArray(it.trajectory)) warnings.push(`${it.id}: diphthong without trajectory`);
    items.push(it);
  }
  if (!items.length) errors.push("sounds.json: no usable items");
  return { ok: errors.length === 0, errors, warnings, items };
}

/**
 * Validate phonemes_experiment.json against the FIXED schema (docs/PHONEMES.md). Lenient: structural problems
 * that prevent rendering are errors; anything else is a warning and the field is simply not shown.
 */
export function validateExperiment(d) {
  const errors = [], warnings = [];
  if (!d || typeof d !== "object") return { ok: false, errors: ["not a JSON object"], warnings };
  if (!Array.isArray(d.classes)) errors.push("classes: missing array");
  if (!Array.isArray(d.items)) errors.push("items: missing array");
  if (errors.length) return { ok: false, errors, warnings };
  if (!Array.isArray(d.findings)) warnings.push("findings: missing");
  if (!Array.isArray(d.butterflies)) warnings.push("butterflies: missing");
  if (!Array.isArray(d.figures)) warnings.push("figures: missing");
  const angles = d?.settings?.angles_deg;
  if (!Array.isArray(angles) || !angles.every(isNum)) warnings.push("settings.angles_deg: missing (assuming 0,15,30,45,60)");
  d.classes.forEach((c, i) => {
    const n = c && typeof c.class === "string" ? c.class : `classes[${i}]`;
    if (!c || typeof c.class !== "string") { warnings.push(`${n}: no class name`); return; }
    if (c.verdict !== "few" && c.verdict !== "many") warnings.push(`${n}: verdict must be "few" or "many"`);
    const g = c.gamut || {};
    if (!Array.isArray(g.hexes) || !g.hexes.every(isHex)) warnings.push(`${n}: gamut.hexes missing or not all #rrggbb`);
    if (!Array.isArray(g.ab) || !g.ab.every((p) => Array.isArray(p) && isNum(p[0]) && isNum(p[1]))) warnings.push(`${n}: gamut.ab missing/invalid`);
    else if (Array.isArray(g.hexes) && g.hexes.length !== g.ab.length) warnings.push(`${n}: gamut.hexes and gamut.ab differ in length`);
    if (c.verdict === "few") {
      const p = c.proof;
      if (!p || typeof p !== "object") errors.push(`${n}: verdict "few" requires a proof`);
      else {
        if (typeof p.title !== "string" || typeof p.claim !== "string") warnings.push(`${n}: proof title/claim missing`);
        if (!Array.isArray(p.steps) || !p.steps.length) warnings.push(`${n}: proof has no steps`);
        if (typeof p.holds !== "boolean") warnings.push(`${n}: proof.holds is not boolean`);
      }
    }
  });
  const realNames = validateReal(d, warnings);
  d.items.forEach((it, i) => {
    const n = it && typeof it.id === "string" ? it.id : `items[${i}]`;
    if (!it || typeof it.id !== "string") { warnings.push(`${n}: no id`); return; }
    if (!isHex(it.hex)) warnings.push(`${n}: hex invalid`);
    if (it.angle_hexes != null && (!Array.isArray(it.angle_hexes) || !it.angle_hexes.every(isHex))) warnings.push(`${n}: angle_hexes invalid`);
    const nb = it.nearest_butterfly;
    if (nb && (typeof nb.name !== "string" || !isNum(nb.dE00))) warnings.push(`${n}: nearest_butterfly incomplete`);
    if (it.twin && !isHex(it.twin.hex)) warnings.push(`${n}: twin.hex invalid`);
    const nr = it.nearest_real_butterfly;
    if (nr != null && (typeof nr !== "object" || typeof nr.name !== "string" || !isNum(nr.dE00) || !isNum(nr.spectral_corr)))
      warnings.push(`${n}: nearest_real_butterfly incomplete`);
    else if (nr && realNames && !realNames.has(nr.name)) warnings.push(`${n}: nearest_real_butterfly "${nr.name}" not in real_butterflies`);
  });
  validateFluorescence(d, warnings);
  return { ok: errors.length === 0, errors, warnings };
}

// ------------------------------------------------------------------ optional additions: realistic scales + fluorescence
/** Check the optional `real_butterflies` list; returns a Set of valid names (or null when absent). */
function validateReal(d, warnings) {
  if (d.real_butterflies == null) return null;
  if (!Array.isArray(d.real_butterflies)) { warnings.push("real_butterflies: not an array"); return new Set(); }
  const names = new Set();
  d.real_butterflies.forEach((b, i) => {
    const n = b && typeof b.name === "string" ? b.name : `real_butterflies[${i}]`;
    if (!b || typeof b.name !== "string") { warnings.push(`${n}: no name`); return; }
    if (!isHex(b.hex)) warnings.push(`${n}: hex invalid`);
    if (b.angle_hexes != null && (!Array.isArray(b.angle_hexes) || !b.angle_hexes.every(isHex))) warnings.push(`${n}: angle_hexes invalid`);
    if (b.peak_nm != null && !isNum(b.peak_nm)) warnings.push(`${n}: peak_nm not a number`);
    names.add(b.name);
  });
  return names;
}

/** Check the optional `fluorescence` block and `fluorescence_proof` (pushes warnings only). */
export function validateFluorescence(d, warnings = []) {
  const fl = d && d.fluorescence;
  if (fl != null) {
    if (typeof fl !== "object" || !Array.isArray(fl.items)) warnings.push("fluorescence: items missing");
    else fl.items.forEach((f, i) => {
      const n = f && typeof f.id === "string" ? f.id : `fluorescence.items[${i}]`;
      if (!f || typeof f.id !== "string") { warnings.push(`${n}: no id`); return; }
      for (const k of ["hex_D65", "hex_UV", "hex_violet"]) if (!isHex(f[k])) warnings.push(`${n}: fluorescence ${k} invalid`);
      if (f.fluor_fraction_D65 != null && !(isNum(f.fluor_fraction_D65) && f.fluor_fraction_D65 >= 0 && f.fluor_fraction_D65 <= 1))
        warnings.push(`${n}: fluor_fraction_D65 outside [0,1]`);
    });
  }
  const p = d && d.fluorescence_proof;
  if (p != null) {
    if (typeof p !== "object") warnings.push("fluorescence_proof: not an object");
    else {
      if (typeof p.title !== "string" || typeof p.claim !== "string") warnings.push("fluorescence_proof: title/claim missing");
      if (!Array.isArray(p.steps) || !p.steps.length) warnings.push("fluorescence_proof: no steps");
      if (typeof p.holds !== "boolean") warnings.push("fluorescence_proof: holds is not boolean");
    }
  }
  return warnings;
}

export const FLUOR_MODES = { D65: "hex_D65", UV: "hex_UV", violet: "hex_violet" };
/** Display hex of a fluorescence item under one light ("D65" | "UV" | "violet"); grey fallback. */
export function fluorHex(f, mode = "D65") { return safeHex(f && f[FLUOR_MODES[mode] || "hex_D65"]); }

/** How often each nearest real species wins: [{name, n}] sorted by n desc, then name. */
export function realWinCounts(items) {
  const m = new Map();
  for (const it of Array.isArray(items) ? items : []) {
    const nm = it && it.nearest_real_butterfly && it.nearest_real_butterfly.name;
    if (typeof nm === "string") m.set(nm, (m.get(nm) || 0) + 1);
  }
  return [...m].map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
}

/** Allowed `?data=` override: a relative path, or an http(s) URL on this origin / localhost. Else null. */
export function safeDataUrl(raw, origin = "http://localhost") {
  if (typeof raw !== "string" || !raw || raw.length > 500) return null;
  try {
    const u = new URL(raw, origin + "/");
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    const o = new URL(origin);
    if (u.origin === o.origin || ["localhost", "127.0.0.1"].includes(u.hostname)) return u.href;
  } catch (e) { /* fallthrough */ }
  return null;
}
