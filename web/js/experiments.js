// experiments.js — "Experiments: every phoneme" page. Reads web/data/sounds.json (CONTRACT §7c) and
// web/data/phonemes_experiment.json (docs/PHONEMES.md FIXED schema; override with ?data=<url> for testing).
// Never fatal: a missing/invalid experiment file only blanks the research panels with a note.
import { fitCanvas, axes } from "./plot.js";
import * as C from "./experiments_core.js";

const $ = (s) => document.querySelector(s);
const esc = (x) => String(x == null ? "" : x).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (x, d = 1) => (typeof x === "number" && Number.isFinite(x) ? x.toFixed(d) : "—");

const state = { sounds: [], byId: new Map(), exp: null, expErr: null, voice: "rec", bflyAudio: new Map(), sel: null };
const NOT_BUILT = (what) => `<div class="empty">Research data not built yet (<span class="mono">web/data/phonemes_experiment.json</span>${what ? ": " + esc(what) : ""}).<br>
  Run <code>python -m research.run_all</code> (section 10, <span class="mono">research/r10_phonemes.py</span>). The chart above and "Paint a word" below already work from sounds.json.</div>`;

// ------------------------------------------------------------------ audio (one shared element)
const audio = new Audio();
audio.preload = "none";
let playingTile = null, wordTimer = null, wordRun = 0;
function clipFor(s) {
  if (!s) return null;
  return state.voice === "synth" ? s.audio_synth || s.audio : s.audio || s.audio_synth;
}
function play(src, tile = null) {
  stopWord();
  if (!src) return;
  if (playingTile) playingTile.classList.remove("playing");
  playingTile = tile; if (tile) tile.classList.add("playing");
  audio.src = src; audio.currentTime = 0;
  audio.play().catch(() => {});
}
audio.addEventListener("ended", () => { if (playingTile) playingTile.classList.remove("playing"); playingTile = null; });

// ------------------------------------------------------------------ 2. IPA chart
const tileOf = new Map();
function tileSwatch(s) {
  if (s.class === "diphthong" && Array.isArray(s.trajectory) && s.trajectory.length > 1) {
    const t = s.trajectory.map((h) => C.safeHex(h));
    // forward + backward so the sliding animation loops smoothly
    return `<div class="sw traj" style="background:${C.gradientCss(t.concat(t.slice(0, -1).reverse()))}" title="colour trajectory ${esc(t[0])} → ${esc(t[t.length - 1])}"></div>`;
  }
  return `<div class="sw" style="background:${C.soundHex(s)}"></div>`;
}
function renderChart() {
  const box = $("#chart");
  box.innerHTML = "";
  for (const g of C.groupByClass(state.sounds)) {
    const h = document.createElement("div");
    h.className = "cls-h";
    const nMod = g.items.filter((s) => s.modelled).length;
    h.innerHTML = `<h3>${esc(g.label)}</h3><span class="muted">${g.items.length} item${g.items.length > 1 ? "s" : ""}${nMod ? ` · ${nMod} modelled` : ""}</span>` +
      (g.class === "diphthong" ? ` <span class="badge approx">interpolated, animated trajectory</span>` : "");
    box.appendChild(h);
    const grid = document.createElement("div");
    grid.className = "tiles";
    for (const s of g.items) {
      const b = document.createElement("button");
      b.className = "tile" + (state.sel === s ? " on" : "");
      b.innerHTML = tileSwatch(s) + `<div class="sym">${esc(s.ipa)}</div><div class="ex">${esc(s.example)}</div>` +
        (s.modelled ? `<span class="badge approx">modelled</span>` : s.rule === "fallback" ? `<span class="badge approx">fallback</span>` : "");
      b.title = `[${s.ipa}] ${s.name || ""}: ${C.soundHex(s)}`;
      tileOf.set(s, b);
      b.addEventListener("click", () => { select(s); play(clipFor(s), b); });
      grid.appendChild(b);
    }
    box.appendChild(grid);
  }
}
function select(s) {
  state.sel = s;
  for (const t of document.querySelectorAll("#chart .tile")) t.classList.remove("on");
  const box = $("#detail");
  const src = clipFor(s);
  const isRec = src === s.audio && s.audio !== s.audio_synth;
  const ex = state.exp && (state.exp.items || []).find((x) => x && x.id === s.id);
  let flags = [];
  if (s.modelled) flags.push(`modelled (${esc(s.source || "model")}${Array.isArray(s.modelled_from) ? " from " + s.modelled_from.map(esc).join(", ") : ""}), so there is no recording`);
  if (s.rule === "fallback") flags.push("fallback rule: context vowel averaged in");
  if (s.class === "diphthong" && s.endpoints) flags.push(`${esc(s.endpoints.start?.ipa)} → ${esc(s.endpoints.end?.ipa)} (LAR interpolation)`);
  const F = (s.lpc_formants || []).filter((f) => f < 5000).map((f) => Math.round(f));
  box.innerHTML = `<div class="snd-detail"><div class="pair big"><i style="background:${C.soundHex(s)}"></i></div><div class="snd-info">` +
    `<b>[${esc(s.ipa)}]</b> ${esc(s.name || "")}, as in “${esc(s.example)}” · <span class="badge">${esc(s.class)}${s.voiced ? ", voiced" : s.voiced === false ? ", voiceless" : ""}</span>` +
    ` <span class="badge ${isRec ? "exact" : "approx"}">${isRec ? "playing the recording" : "playing the film's voice"}</span><br>` +
    `<span class="muted">full-band · realizable · reflected <span class="mono">${C.soundHex(s)}</span>` +
    `${F.length ? " · LPC peaks ≈ " + F.join(", ") + " Hz" : ""}${flags.length ? " · " + flags.join(" · ") : ""}` +
    `${ex && ex.nearest_butterfly ? ` · nearest butterfly: ${esc(ex.nearest_butterfly.name)} (ΔE₀₀ ${num(ex.nearest_butterfly.dE00)})` : ""}</span>` +
    `<div class="snd-strip wide" style="background:${C.gradientCss(s.strip || s.trajectory || [C.soundHex(s)])}" title="frame colours in time order"></div></div></div>`;
  tileOf.get(s)?.classList.add("on");
}
function wireVoice() {
  $("#voice-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.voice = b.dataset.v;
    for (const x of $("#voice-seg").querySelectorAll("button")) x.classList.toggle("on", x === b);
    $("#voice-badge").textContent = state.voice === "synth" ? "film's own voice (synthetic)" : "real recording";
    if (state.sel) select(state.sel);
  });
}

// ------------------------------------------------------------------ 3. per-class verdicts
function classAb(c) { return Array.isArray(c?.gamut?.ab) ? c.gamut.ab.filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])) : []; }
function classHull(c) {
  const h = c?.gamut?.hull_ab;
  return Array.isArray(h) && h.length >= 3 ? h : C.convexHull(classAb(c));
}
function meanHex(hexes) {
  const H = (hexes || []).filter(C.isHex);
  if (!H.length) return "#888888";
  const m = [1, 3, 5].map((i) => Math.round(H.reduce((s, h) => s + parseInt(h.slice(i, i + 2), 16), 0) / H.length));
  return "#" + m.map((v) => v.toString(16).padStart(2, "0")).join("");
}
const canvases = []; // [{cv, draw}]
function addCanvas(cv, draw) { canvases.push({ cv, draw }); draw(cv); }

function drawAbFrame(cv, lists) {
  const { ctx, w, h } = fitCanvas(cv);
  const B = C.abBounds(lists);
  const box = { x: 44, y: 10, w: Math.max(40, w - 54), h: Math.max(40, h - 50) };
  const ax = axes(ctx, box, { ...B, xlabel: "a*  (green → red)", ylabel: "b*  (blue → yellow)", xticks: Math.max(3, Math.floor(box.w / 60)) });
  ctx.save(); ctx.beginPath(); ctx.rect(box.x, box.y, box.w, box.h); ctx.clip();
  ctx.strokeStyle = "rgba(255,255,255,.25)"; ctx.setLineDash([3, 3]);
  if (B.xmin < 0 && B.xmax > 0) { ctx.beginPath(); ctx.moveTo(ax.X(0), box.y); ctx.lineTo(ax.X(0), box.y + box.h); ctx.stroke(); }
  if (B.ymin < 0 && B.ymax > 0) { ctx.beginPath(); ctx.moveTo(box.x, ax.Y(0)); ctx.lineTo(box.x + box.w, ax.Y(0)); ctx.stroke(); }
  ctx.restore();
  return { ctx, ax, box };
}
function polyPath(ctx, ax, poly) {
  ctx.beginPath();
  poly.forEach((p, i) => (i ? ctx.lineTo(ax.X(p[0]), ax.Y(p[1])) : ctx.moveTo(ax.X(p[0]), ax.Y(p[1]))));
  ctx.closePath();
}
function drawScatter(cv, c) {
  const ab = classAb(c), hexes = c.gamut?.hexes || [], hull = classHull(c);
  const { ctx, ax, box } = drawAbFrame(cv, [ab, hull]);
  ctx.save(); ctx.beginPath(); ctx.rect(box.x, box.y, box.w, box.h); ctx.clip();
  if (hull.length >= 3) { polyPath(ctx, ax, hull); ctx.fillStyle = "rgba(143,123,255,.10)"; ctx.fill(); ctx.strokeStyle = "#b7a8ff"; ctx.lineWidth = 1.5; ctx.stroke(); }
  const r = ab.length > 1500 ? 2 : 3;
  ab.forEach((p, i) => {
    ctx.beginPath(); ctx.arc(ax.X(p[0]), ax.Y(p[1]), r, 0, 2 * Math.PI);
    ctx.fillStyle = C.safeHex(hexes[i], "#888888"); ctx.fill();
  });
  ctx.restore();
}
function drawMosaic(cv, hexes) {
  const H = C.uniqueSortedHexes(hexes);
  const w = Math.max(50, cv.clientWidth || 300);
  const cell = Math.max(5, Math.min(22, Math.floor(Math.sqrt((w * 150) / Math.max(1, H.length)))));
  const cols = Math.max(1, Math.floor(w / cell)), rows = Math.max(1, Math.ceil(H.length / cols));
  cv.style.height = rows * cell + "px";
  const { ctx } = fitCanvas(cv);
  H.forEach((h, i) => { ctx.fillStyle = h; ctx.fillRect((i % cols) * cell, Math.floor(i / cols) * cell, cell - (cell > 8 ? 1 : 0), cell - (cell > 8 ? 1 : 0)); });
}
function drawOverview(cv, classes) {
  const all = classes.map((c) => ({ c, hull: classHull(c), ab: classAb(c) }));
  const { ctx, ax, box } = drawAbFrame(cv, all.map((x) => x.hull.length ? x.hull : x.ab));
  ctx.save(); ctx.beginPath(); ctx.rect(box.x, box.y, box.w, box.h); ctx.clip();
  ctx.font = "12px Segoe UI, system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (const { c, hull, ab } of all) {
    const col = meanHex(c.gamut?.hexes);
    if (hull.length >= 3) {
      polyPath(ctx, ax, hull); ctx.globalAlpha = .22; ctx.fillStyle = col; ctx.fill(); ctx.globalAlpha = 1;
      ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.stroke();
    } else for (const p of ab) { ctx.beginPath(); ctx.arc(ax.X(p[0]), ax.Y(p[1]), 4, 0, 2 * Math.PI); ctx.fillStyle = col; ctx.fill(); }
    const pts = hull.length ? hull : ab;
    if (pts.length) {
      const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
      ctx.fillStyle = "#e9ecf5"; ctx.fillText(c.label || c.class, ax.X(cx), ax.Y(cy));
    }
  }
  ctx.restore();
}

function renderClasses() {
  const box = $("#classes");
  const ex = state.exp;
  if (!ex) { box.innerHTML = NOT_BUILT(state.expErr); return; }
  box.innerHTML = "";
  const classes = [...ex.classes].filter((c) => c && typeof c.class === "string")
    .sort((a, b) => (C.CLASS_ORDER.indexOf(a.class) + 100) % 100 - (C.CLASS_ORDER.indexOf(b.class) + 100) % 100);
  const ov = document.createElement("div");
  ov.className = "panel";
  ov.innerHTML = `<b>All classes in the a*b* plane</b> <span class="badge exact">CIELAB, D65</span>
    <p class="muted" style="margin:4px 0 8px;font-size:.85rem">Each region is the convex hull of all the valid colours one class produced. Where regions are far apart, those classes look different.</p>
    <canvas class="plot" id="overview"></canvas>`;
  box.appendChild(ov);
  addCanvas(ov.querySelector("canvas"), (cv) => drawOverview(cv, classes));
  for (const c of classes) {
    const d = document.createElement("div");
    d.className = "panel verdict";
    const few = c.verdict === "few";
    const nAb = classAb(c).length, hull = classHull(c);
    let head = `<div class="row"><h3>${esc(c.label || c.class)}</h3>` +
      `<span class="badge ${few ? "approx" : "exact"}">${few ? "one or two colours" : "many colours"}</span>` +
      `<span class="muted" style="font-size:.85rem">${esc(c.n_items)} item(s) · ${esc(c.distinct_colours)} distinct colour(s)` +
      `${ex.settings && ex.settings.cluster_dE00 != null ? ` at ΔE₀₀ ≥ ${esc(ex.settings.cluster_dE00)}` : ""} · ${nAb} colour samples` +
      `${hull.length >= 3 ? ` · hull area ${num(C.polygonArea(hull), 0)} (a*b* units²)` : ""}</span></div>` +
      (c.note ? `<p class="muted" style="margin:6px 0 0;font-size:.88rem">${esc(c.note)}</p>` : "");
    let body = "";
    if (few) {
      const p = c.proof;
      if (p) {
        body += `<div class="proof" style="margin-top:10px"><b>Proof: ${esc(p.title)}</b> <span class="badge exact">derivation</span>` +
          `<p class="claim">${esc(p.claim)}</p><ol>${(p.steps || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` +
          `<div class="check"><span class="badge ${p.holds === true ? "pass" : "fail"}">${p.holds === true ? "numeric check: holds" : "numeric check: FAILS"}</span> ${esc(p.numeric_check)}</div></div>`;
      } else body += `<div class="note" style="margin-top:10px">Verdict "few" but no proof in the data. This is a data error and is reported here as one.</div>`;
    }
    body += `<div class="two"><div><div class="kv" style="margin-bottom:4px">${few ? "Its colours" : "Every valid colour"} (sorted by hue)</div><canvas class="mosaic"></canvas></div>` +
      `<div><div class="kv" style="margin-bottom:4px">a*b* scatter + convex hull</div><canvas class="plot ab"></canvas></div></div>`;
    d.innerHTML = head + body;
    box.appendChild(d);
    addCanvas(d.querySelector("canvas.mosaic"), (cv) => drawMosaic(cv, c.gamut?.hexes || []));
    addCanvas(d.querySelector("canvas.ab"), (cv) => drawScatter(cv, c));
  }
}

// ------------------------------------------------------------------ 4. butterfly comparison
function renderBfly() {
  const box = $("#bfly");
  const ex = state.exp;
  if (!ex) { box.innerHTML = NOT_BUILT(state.expErr); return; }
  const sel = $("#bfly-class");
  if (sel.options.length <= 1) for (const g of C.groupByClass(ex.items)) sel.add(new Option(g.label, g.class));
  const bHex = new Map((ex.butterflies || []).filter((b) => b && b.name).map((b) => [b.name, C.safeHex(b.hex, "#555555")]));
  const angles = Array.isArray(ex.settings?.angles_deg) ? ex.settings.angles_deg : [0, 15, 30, 45, 60];
  const items = ex.items.filter((it) => it && typeof it.id === "string" && (!sel.value || it.class === sel.value));
  const order = (it) => { const i = C.CLASS_ORDER.indexOf(it.class); return i < 0 ? 99 : i; };
  items.sort((a, b) => order(a) - order(b));
  if (!items.length) { box.innerHTML = `<div class="empty">No items.</div>`; return; }
  box.innerHTML = `<div class="bcards">${items.map((it) => {
    const nb = it.nearest_butterfly || {}, tw = it.twin || {}, best = C.bestVoice(it.voice_lsd_db);
    const ah = Array.isArray(it.angle_hexes) ? it.angle_hexes : [];
    const bAudio = best && state.bflyAudio.get(best.name);
    return `<div class="bcard"><div class="top"><span class="sym">${esc(it.ipa)}</span><span class="muted">${esc(it.example)} · ${esc(it.class)}</span>` +
      (it.modelled ? ` <span class="badge approx">modelled</span>` : "") + `</div>` +
      `<div class="cmp"><div><i style="background:${C.safeHex(it.hex)}"></i>film<br><span class="mono">${esc(C.safeHex(it.hex))}</span></div>` +
      `<div><i style="background:${bHex.get(nb.name) || "#555"}"></i>${esc(nb.name || "—")}<br>ΔE₀₀ ${num(nb.dE00)} · r ${num(nb.spectral_corr, 2)}</div>` +
      `<div><i style="background:${C.safeHex(tw.hex, "#555555")}"></i>twin: ${esc(tw.materials || "—")}${tw.n_layers ? `, ${esc(tw.n_layers)} layers` : ""}<br>ΔE₀₀ ${num(tw.dE00)}</div></div>` +
      (ah.length ? `<div class="angles" style="background:${C.gradientCss(ah)}" title="colour at ${angles.join(", ")}°"></div>` +
        `<div class="angle-lbl">${angles.map((a) => `<span>${esc(a)}°</span>`).join("")}</div>` : "") +
      (it.nearest_real_butterfly && typeof it.nearest_real_butterfly.name === "string" ? `<div class="kv" style="margin-top:4px">nearest realistic scale: <b>${esc(it.nearest_real_butterfly.name)}</b> (r ${num(it.nearest_real_butterfly.spectral_corr, 2)}, ΔE₀₀ ${num(it.nearest_real_butterfly.dE00, 0)}) <span class="badge approx">approx</span></div>` : "") +
      `<div class="kv" style="margin-top:4px">sounds most like: <b>${best ? esc(best.name) : "—"}</b>${best ? ` (${num(best.db)} dB LSD)` : ""}` +
      `${bAudio ? ` <button class="btn" style="padding:2px 8px;font-size:.78rem" data-bplay="${esc(bAudio)}">▶ butterfly</button>` : ""}` +
      ` <button class="btn" style="padding:2px 8px;font-size:.78rem" data-pplay="${esc(it.id)}">▶ phoneme</button></div></div>`;
  }).join("")}</div>`;
}
function wireBfly() {
  $("#bfly-class").addEventListener("change", renderBfly);
  $("#bfly").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.bplay) play(b.dataset.bplay);
    else if (b.dataset.pplay) play(clipFor(state.byId.get(b.dataset.pplay)));
  });
}

// ------------------------------------------------------------------ 4b. realistic butterfly scales (optional data)
function renderReal() {
  const sec = $("#sec-real"), ex = state.exp;
  if (!ex) { $("#real-species").innerHTML = NOT_BUILT(state.expErr); $("#real-phonemes").innerHTML = ""; return; }
  const RB = (Array.isArray(ex.real_butterflies) ? ex.real_butterflies : []).filter((b) => b && typeof b.name === "string");
  if (!RB.length) { sec.hidden = true; return; }
  sec.hidden = false;
  const angles = Array.isArray(ex.settings?.angles_deg) ? ex.settings.angles_deg : [0, 15, 30, 45, 60];
  const wins = new Map(C.realWinCounts(ex.items).map((w) => [w.name, w.n]));
  $("#real-species").innerHTML = `<div class="bcards">${RB.map((b) => {
    const ah = Array.isArray(b.angle_hexes) ? b.angle_hexes : [];
    return `<div class="bcard"><div class="top"><b><i>${esc(b.name)}</i></b><span class="muted">${esc(b.kind || "")}</span></div>` +
      `<div class="cmp" style="grid-template-columns:1fr 2fr"><div><i style="background:${C.safeHex(b.hex)}"></i>0°<br><span class="mono">${esc(C.safeHex(b.hex))}</span></div>` +
      `<div style="text-align:left">peak ${num(b.peak_nm, 0)} nm${b.R_peak != null ? ` · R<sub>max</sub> ${num(b.R_peak, 2)}` : ""}<br>` +
      `nearest species for <b>${wins.get(b.name) || 0}</b> of ${ex.items.length} phonemes</div></div>` +
      (ah.length ? `<div class="angles" style="background:${C.gradientCss(ah)}" title="colour at ${angles.join(", ")}°"></div>` +
        `<div class="angle-lbl">${angles.slice(0, ah.length).map((a) => `<span>${esc(a)}°</span>`).join("")}</div>` : "") +
      (b.published ? `<div class="kv" style="margin-top:4px">published: ${esc(b.published)}</div>` : "") +
      (b.source ? `<div class="kv" style="margin-top:2px;font-size:.72rem">${esc(b.source)}</div>` : "") + `</div>`;
  }).join("")}</div>`;
  const bHex = new Map(RB.map((b) => [b.name, C.safeHex(b.hex)]));
  const items = ex.items.filter((it) => it && it.nearest_real_butterfly && typeof it.nearest_real_butterfly.name === "string");
  $("#real-phonemes").innerHTML = items.length ? `<div class="chips">${items.map((it) => {
    const nr = it.nearest_real_butterfly;
    return `<span class="chip" title="[${esc(it.ipa)}] vs ${esc(nr.name)}: r ${num(nr.spectral_corr, 2)}, ΔE₀₀ ${num(nr.dE00, 0)}" style="min-width:86px">` +
      `<span style="display:flex;gap:2px"><i style="width:30px;background:${C.safeHex(it.hex)}"></i><i style="width:30px;background:${bHex.get(nr.name) || "#555"}"></i></span>` +
      `<b>${esc(it.ipa)}</b>${esc(nr.name.split(" ")[0][0] + ". " + (nr.name.split(" ")[1] || ""))}<br>r ${num(nr.spectral_corr, 2)} · ΔE ${num(nr.dE00, 0)}</span>`;
  }).join("")}</div>` : `<div class="empty">No per-phoneme comparison in the data.</div>`;
}

// ------------------------------------------------------------------ 4c. fluorescence (optional data)
let fluorMode = "D65";
function proofHtml(p, label = "derivation") {
  return `<div class="proof" style="margin-top:10px"><b>Proof: ${esc(p.title)}</b> <span class="badge exact">${esc(label)}</span>` +
    `<p class="claim">${esc(p.claim)}</p><ol>${(p.steps || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` +
    `<div class="check"><span class="badge ${p.holds === true ? "pass" : "fail"}">${p.holds === true ? "numeric check: holds" : "numeric check: FAILS"}</span> ${esc(p.numeric_check)}</div></div>`;
}
function renderFluor() {
  const sec = $("#sec-fluor"), ex = state.exp;
  if (!ex) { $("#fluor-tiles").innerHTML = NOT_BUILT(state.expErr); return; }
  const fl = ex.fluorescence;
  const F = fl && Array.isArray(fl.items) ? fl.items.filter((f) => f && typeof f.id === "string") : [];
  if (!F.length) { sec.hidden = true; return; }
  sec.hidden = false;
  const st = fl.stats || {};
  $("#fluor-note").textContent = fluorMode === "D65"
    ? "film reflection + fluorescence; % = share of luminance from the dye"
    : fluorMode === "UV" ? `only the dye's glow is visible: ${st.distinct_UV ?? fl.distinct_colours_UV ?? "?"} distinct colour(s), max ΔE₀₀ ${num(st.max_dE00_UV, 1)}`
      : "violet light: reflection of 405 nm + glow";
  $("#fluor-tiles").innerHTML = C.groupByClass(F).map((g) => `<div class="cls-h"><h3>${esc(g.label)}</h3></div><div class="tiles">${g.items.map((f) =>
    `<div class="tile" style="cursor:default" title="[${esc(f.ipa)}] D65 ${esc(C.fluorHex(f, "D65"))} · 405 ${esc(C.fluorHex(f, "violet"))} · 365 ${esc(C.fluorHex(f, "UV"))}">` +
    `<div class="sw" style="background:${C.fluorHex(f, fluorMode)}"></div><div class="sym">${esc(f.ipa)}</div>` +
    `<div class="ex">${fluorMode === "D65" && typeof f.fluor_fraction_D65 === "number" ? Math.round(100 * f.fluor_fraction_D65) + " % glow" : "peak " + num(f.peak_emission_nm, 0) + " nm"}</div></div>`).join("")}</div>`).join("");
  const p = ex.fluorescence_proof;
  $("#fluor-proof").innerHTML = p && typeof p === "object"
    ? `<div class="panel verdict"><div class="row"><h3>Blacklight: one colour</h3><span class="badge approx">one colour</span>` +
      `<span class="muted" style="font-size:.85rem">${F.length} films · fluorophore ${esc(fl.fluorophore?.name || "")}</span></div>${proofHtml(p)}</div>`
    : "";
}
function wireFluor() {
  $("#fluor-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    fluorMode = b.dataset.m;
    for (const x of $("#fluor-seg").querySelectorAll("button")) x.classList.toggle("on", x === b);
    renderFluor();
  });
}

// ------------------------------------------------------------------ 5. findings + figures
function renderFindings() {
  const ex = state.exp;
  if (!ex) { $("#findings").innerHTML = NOT_BUILT(state.expErr); $("#figs").innerHTML = ""; return; }
  const F = (ex.findings || []).filter((x) => typeof x === "string");
  $("#findings").innerHTML = F.length ? `<ul class="findings panel" style="padding-left:2em">${F.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : `<div class="empty">No findings listed.</div>`;
  const figs = (ex.figures || []).filter((f) => f && typeof f.file === "string" && /^[\w./-]+$/.test(f.file) && !f.file.includes(".."));
  const box = $("#figs");
  if (!figs.length) { box.innerHTML = `<div class="empty">No figures listed.</div>`; return; }
  box.innerHTML = `<div class="figs">${figs.map((f) => `<figure class="fig"><a href="${esc(f.file)}" target="_blank" rel="noopener"><img src="${esc(f.file)}" alt="${esc(f.caption)}" loading="lazy"></a>` +
    `<figcaption><b>${esc(f.file.split("/").pop())}</b><br>${esc(f.caption)}</figcaption></figure>`).join("")}</div>`;
  for (const img of box.querySelectorAll("img")) img.addEventListener("error", (e) => {
    e.target.closest("a").replaceWith(Object.assign(document.createElement("div"), { className: "empty", textContent: "image not copied to web/ yet: " + e.target.getAttribute("src") + " (run python tools/make_results_manifest.py)" }));
  });
}

// ------------------------------------------------------------------ 6. paint a word
let ipaMap = null;
function wordTokens() {
  if (!ipaMap) { ipaMap = {}; for (const s of state.sounds) ipaMap[s.ipa] = s.id; }
  return C.tokenizeWord($("#word").value, new Set(state.byId.keys()), ipaMap);
}
function renderWord() {
  const toks = wordTokens();
  const cols = toks.filter((t) => t.id).map((t) => C.soundHex(state.byId.get(t.id)));
  $("#word-bar").style.background = cols.length ? C.gradientCss(cols) : "#222";
  $("#word-chips").innerHTML = toks.map((t, i) => {
    if (t.sep) return `<span class="chip gap"></span>`;
    const s = t.id && state.byId.get(t.id);
    return s ? `<span class="chip" data-i="${i}"><i style="background:${C.soundHex(s)}"></i><b>${esc(s.ipa)}</b>${esc(t.text)}</span>`
      : `<span class="chip miss" data-i="${i}" title="${esc(t.want)} not in sounds.json"><i></i><b>?</b>${esc(t.text)}</span>`;
  }).join("") || `<span class="muted">Type a word.</span>`;
}
function stopWord() {
  wordRun++; clearTimeout(wordTimer);
  for (const c of document.querySelectorAll(".chip.now")) c.classList.remove("now");
}
function playWord() {
  stopWord();
  const run = wordRun;
  const toks = wordTokens().map((t, i) => ({ ...t, i })).filter((t) => t.id || t.sep);
  let k = 0;
  const step = () => {
    if (run !== wordRun) return;
    for (const c of document.querySelectorAll(".chip.now")) c.classList.remove("now");
    if (k >= toks.length) { audio.pause(); return; }
    const t = toks[k++];
    if (t.sep) { audio.pause(); wordTimer = setTimeout(step, 200); return; }
    document.querySelector(`.chip[data-i="${t.i}"]`)?.classList.add("now");
    const src = clipFor(state.byId.get(t.id));
    if (src) { audio.src = src; audio.currentTime = 0; audio.play().catch(() => {}); }
    wordTimer = setTimeout(step, 450);
  };
  step();
}
function wireWord() {
  $("#word").addEventListener("input", renderWord);
  $("#word").addEventListener("keydown", (e) => { if (e.key === "Enter") playWord(); });
  $("#word-play").addEventListener("click", playWord);
  $("#word-stop").addEventListener("click", () => { stopWord(); audio.pause(); });
}

// ------------------------------------------------------------------ main
async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
let resizeT = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeT);
  resizeT = setTimeout(() => { for (const { cv, draw } of canvases) if (cv.isConnected) draw(cv); }, 150);
});

// ?voice=user -> the author's own recordings (web/record.html -> tools.build_sounds --source user -> r10 --user)
const USER = new URLSearchParams(location.search).get("voice") === "user";
const SND = USER ? "data/sounds_user.json" : "data/sounds.json";

function renderSentences(list) {
  const el = document.getElementById("sentences");
  if (!el) return;
  if (!list || !list.length) { el.closest("section").hidden = true; return; }
  el.closest("section").hidden = false;
  el.innerHTML = list.map((s) => `<div class="sent"><button class="btn" data-a="${esc(s.audio)}">▶</button>
    <span class="mono">${esc(s.id.replace(/^sent_/, ""))}</span> · ${esc(s.duration_s)} s
    <div class="ribbon">${s.ribbon.map((h) => `<i style="background:${esc(h)}"></i>`).join("")}</div></div>`).join("");
  el.onclick = (e) => { const a = e.target.dataset?.a; if (a) new Audio(a).play(); };
}

async function main() {
  wireVoice(); wireBfly(); wireWord(); wireFluor();
  const meta = [];
  const tg = document.getElementById("voice-toggle");
  if (tg) tg.innerHTML = USER
    ? `Showing <b>your own voice</b> · <a href="experiments.html">switch to the IPA-chart recordings</a>`
    : `Showing the IPA-chart recordings · <a href="experiments.html?voice=user">switch to your own voice</a> (after <a href="record.html">recording</a>)`;
  try {
    const sj = await getJSON(SND);
    renderSentences(sj.sentences);
    const v = C.validateSounds(sj);
    if (!v.ok) throw new Error(v.errors.join("; "));
    state.sounds = v.items;
    state.byId = new Map(v.items.map((s) => [s.id, s]));
    meta.push(`${v.items.length} sounds (${v.items.filter((s) => s.modelled).length} modelled)`);
    renderChart();
    renderWord();
  } catch (e) {
    $("#chart").innerHTML = `<div class="empty">Could not load <span class="mono">${SND}</span> (${esc(e.message)}). Run <code>python -m tools.build_sounds</code>.</div>`;
  }
  try {
    const bj = await getJSON("data/butterflies.json");
    for (const b of bj.items || []) if (b && b.name && typeof b.audio === "string") state.bflyAudio.set(b.name, b.audio);
  } catch (e) { /* butterfly voices are optional */ }

  const q = new URLSearchParams(location.search).get("data");
  const expUrl = q ? C.safeDataUrl(q, location.origin) : (USER ? "data/phonemes_experiment_user.json" : "data/phonemes_experiment.json");
  let warnings = [];
  if (!expUrl) state.expErr = "the ?data= override was rejected (use a relative path or a localhost URL)";
  else {
    try {
      const d = await getJSON(expUrl);
      const v = C.validateExperiment(d);
      warnings = v.warnings;
      if (v.ok) state.exp = d;
      else state.expErr = "invalid: " + v.errors.slice(0, 3).join("; ");
    } catch (e) { state.expErr = e.message === "HTTP 404" ? "file not found" : e.message; }
  }
  if (state.exp) meta.push(`experiment data: ${esc(state.exp.generated_by || "?")}, ${esc(state.exp.date || "")}${q ? " (override: " + esc(expUrl) + ")" : ""}` +
    (state.exp.settings?.view ? ` · view ${esc(state.exp.settings.view)}` : ""));
  else meta.push(`experiment data: not available (${esc(state.expErr)})`);
  $("#meta").innerHTML = meta.join(" · ") + (warnings.length
    ? `<details class="warn"><summary>${warnings.length} data warning(s)</summary><ul>${warnings.slice(0, 40).map((w) => `<li>${esc(w)}</li>`).join("")}</ul></details>` : "");
  renderClasses(); renderBfly(); renderReal(); renderFluor(); renderFindings();
  if (state.sel) select(state.sel);
}
main();
