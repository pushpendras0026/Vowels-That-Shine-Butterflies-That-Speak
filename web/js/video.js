// video.js — embeds web/video/explainer.mp4 (if present) and renders the narration markdown
// that tools/make_results_manifest.py copies into web/results/manifest.json.
import { renderMarkdown } from "./markdown.js";

const $ = (s) => document.querySelector(s);
const SRC = "video/explainer.mp4";

async function exists(url) {
  try {
    const r = await fetch(url, { method: "HEAD", cache: "no-store" });
    return r.ok ? +(r.headers.get("Content-Length") || 0) || -1 : 0;
  } catch (e) { return 0; }
}

async function main() {
  const size = await exists(SRC);
  if (size) {
    const v = document.createElement("video");
    v.controls = true; v.preload = "metadata"; v.playsInline = true; v.src = SRC;
    v.addEventListener("error", () => { $("#player").innerHTML = `<div class="empty">The browser could not play <code>${SRC}</code> (codec?). Open it directly: <a href="${SRC}">${SRC}</a></div>`; });
    v.addEventListener("loadedmetadata", () => {
      $("#vmeta").textContent = `${SRC} · ${Math.floor(v.duration / 60)}:${String(Math.round(v.duration % 60)).padStart(2, "0")} · ${v.videoWidth}×${v.videoHeight}` + (size > 0 ? ` · ${(size / 1e6).toFixed(1)} MB` : "");
    });
    $("#player").replaceChildren(v);
  } else {
    $("#player").innerHTML = `<div class="empty">The video has not been rendered yet.<br>Render it from <code>video/</code> (see README → “Video”);
      the final file is copied to <code>web/video/explainer.mp4</code>.</div>`;
  }

  let md = null;
  try {
    const r = await fetch("results/manifest.json", { cache: "no-store" });
    if (r.ok) md = (await r.json()).narration?.markdown || null;
  } catch (e) { /* ignore */ }
  $("#narration").innerHTML = md
    ? renderMarkdown(md, { img: () => null, link: (h) => (/^https?:|^#/.test(h) ? h : null) })
    : `<div class="empty">Narration not available yet (<code>video/NARRATION.md</code>). Run <code>python tools/make_results_manifest.py</code> after it is written.</div>`;
}
main();
