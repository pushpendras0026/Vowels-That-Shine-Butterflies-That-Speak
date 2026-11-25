// results.js — renders web/results/manifest.json (written by tools/make_results_manifest.py).
// Degrades gracefully: missing manifest / summary / report / audio are reported, never fatal.
import { renderMarkdown } from "./markdown.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const GROUPS = {
  1: "Isomorphism: tube = film = polynomial",
  2: "Vowel palettes (men / women / children, several illuminants)",
  3: "Fidelity: ideal vs realizable films",
  4: "Butterfly-like stacks → nearest vowels",
  5: "Metamers both ways",
  6: "Angle sweep: iridescence = diphthong",
  7: "Atlas of random stacks",
};

const get = (o, path) => path.split(".").reduce((x, k) => (x == null ? undefined : x[k]), o);
const sci = (x) => (typeof x === "number" ? x.toExponential(1) : "—");
const STATS = [
  ["r1.all36_max_abs_film_minus_poly", "film T vs shared polynomial, all 36 vowels (max abs error)", sci, "exact"],
  ["r1.all36_max_abs_tube_minus_poly", "independent acoustic tube (ABCD) vs polynomial (max abs error)", sci, "exact"],
  ["r1.kl_lattice_max_abs_vs_poly", "Kelly–Lochbaum time-domain lattice vs polynomial", sci, "exact"],
  ["r1.random200_max_abs", "200 random stacks, film vs polynomial", sci, "exact"],
  ["r2.dE00_pairs.ideal_eqY_men.median", "median ΔE₀₀ between vowels, men (equal luminance)", (x) => x.toFixed(1), "exact"],
  ["r2.dE00_pairs.ideal_eqY_women.median", "… women", (x) => x.toFixed(1), "exact"],
  ["r2.dE00_pairs.ideal_eqY_children.median", "… children", (x) => x.toFixed(1), "exact"],
  ["r2.hue_ideal_deg", "hue range of all vowel colours (ideal) — all violet", (h) => `${h.min.toFixed(0)}°–${h.max.toFixed(0)}°`, "exact"],
  ["r2.Y_T_ideal.median", "median luminous transmittance of ideal vowel films", (x) => x.toFixed(2) + " %", "exact"],
  ["r3.ideal.lsd_vs_lpc_dB.median", "spectral distance film-voice vs vowel LPC, ideal (dB)", (x) => x.toFixed(2), "approx"],
  ["r3.realizable.lsd_vs_lpc_dB.median", "… realizable 1.0–2.5 indices (dB)", (x) => x.toFixed(1), "approx"],
  ["r3.ideal_index_max.max", "largest refractive index an ideal vowel film needs", (x) => x.toFixed(0), "exact"],
];

function renderStats(sum) {
  const box = $("#stats");
  const cards = [];
  for (const [path, label, fmt, kind] of STATS) {
    const v = get(sum, path);
    if (v == null) continue;
    let txt;
    try { txt = fmt(v); } catch (e) { continue; }
    cards.push(`<div class="stat"><div class="v">${esc(txt)}</div><div class="k">${esc(label)} <span class="badge ${kind}">${kind}</span></div></div>`);
  }
  if (cards.length) { box.innerHTML = cards.join(""); $("#sec-stats").hidden = false; }
}

function figNum(name) { const m = /^fig_?(\d+)/.exec(name); return m ? +m[1] : 99; }

function renderFigures(figs) {
  const box = $("#figs");
  if (!figs.length) {
    box.innerHTML = `<div class="empty">No figures yet. Run <code>python -m research.run_all</code> (writes results/ and copies figures to web/results/),
      then <code>python tools/make_results_manifest.py</code>.</div>`;
    return;
  }
  const groups = new Map();
  for (const f of figs) {
    const k = figNum(f.name);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(f);
  }
  box.innerHTML = "";
  for (const [k, list] of [...groups.entries()].sort((a, b) => a[0] - b[0])) {
    const h = document.createElement("div");
    h.className = "grp-h";
    const sec = list.find((f) => f.section)?.section;
    h.innerHTML = `<h3>${k < 99 ? k + ". " : ""}${esc(GROUPS[k] || sec || "Other figures")}</h3>`;
    box.appendChild(h);
    const grid = document.createElement("div");
    grid.className = "figs";
    for (const f of list) {
      const fig = document.createElement("figure");
      fig.className = "fig";
      fig.innerHTML = `<button aria-label="enlarge ${esc(f.name)}"><img src="${esc(f.file)}" alt="${esc(f.caption)}" loading="lazy"></button>` +
        `<figcaption><b>${esc(f.name)}</b><br>${esc(f.caption)}</figcaption>`;
      fig.querySelector("img").addEventListener("error", (e) => { e.target.replaceWith(Object.assign(document.createElement("div"), { className: "empty", textContent: "image missing: " + f.file })); });
      fig.querySelector("button").addEventListener("click", () => openLB(f.file, f.caption));
      grid.appendChild(fig);
    }
    box.appendChild(grid);
  }
}

function openLB(src, cap) {
  const d = $("#lb");
  $("#lb-img").src = src; $("#lb-img").alt = cap; $("#lb-cap").textContent = cap;
  if (d.showModal) d.showModal(); else window.open(src, "_blank");
}

function renderAudio(list) {
  if (!list.length) return;
  $("#audios").innerHTML = list.map((a) =>
    `<div class="aud"><b>${esc(a.caption)}</b><br><span class="muted mono" style="font-size:.78rem">${esc(a.file)}</span>` +
    `<audio controls preload="none" src="${esc(a.file)}"></audio></div>`).join("");
  $("#sec-audio").hidden = false;
}

function renderReport(rep, figs, audio) {
  if (!rep || !rep.markdown) return;
  const figByName = new Map(figs.map((f) => [f.file.split("/").pop(), f.file]));
  const audByName = new Map(audio.map((a) => [a.file.split("/").pop(), a.file]));
  const base = (u) => u.split(/[\\/]/).pop().split("?")[0];
  const html = renderMarkdown(rep.markdown, {
    img: (src) => (/^https?:/i.test(src) ? null : figByName.get(base(src)) || null),
    link: (href) => {
      if (/^https?:|^#|^mailto:/i.test(href)) return href;
      const b = base(href);
      return figByName.get(b) || audByName.get(b) || (/(^|\/)web\//.test(href) ? href.replace(/^.*?web\//, "") : null);
    },
  });
  $("#report").innerHTML = html;
  $("#sec-report").hidden = false;
}

async function main() {
  let man;
  try {
    const r = await fetch("results/manifest.json", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    man = await r.json();
  } catch (e) {
    $("#figs").innerHTML = `<div class="empty">No results manifest found (<code>web/results/manifest.json</code>).<br>
      Run <code>python -m research.run_all</code> and then <code>python tools/make_results_manifest.py</code>
      (or just restart <code>start_demo.bat</code>, which refreshes it).</div>`;
    return;
  }
  const figs = man.figures || [], audio = man.audio || [];
  $("#meta").textContent = `Manifest generated ${man.generated || "?"} · ${figs.length} figures · ${audio.length} audio clips` +
    (man.summary ? " · summary.json included" : " · no summary.json yet") + (man.report ? " · REPORT.md included" : " · REPORT.md not written yet");
  if (man.summary) {
    renderStats(man.summary);
    $("#raw").textContent = JSON.stringify(man.summary, null, 1);
    $("#sec-raw").hidden = false;
  }
  renderFigures(figs);
  renderAudio(audio);
  renderReport(man.report, figs, audio);
}
main();
