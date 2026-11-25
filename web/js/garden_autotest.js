/**
 * garden_autotest.js — in-browser end-to-end test of the Butterfly Garden. Loaded ONLY for garden.html?autotest
 * (dynamic import from garden.js). Drives the real UI flows and logs one line per check, then
 * "AUTOTEST PASS garden …" or "AUTOTEST FAIL garden <reason>". Run headless:
 *   . .\tools\env.ps1; python -m tools.browser_check "garden.html?autotest" --budget 60000
 */
export async function runAutotest(api) {
  const { S, THREE, P, $, cfg, camera, controls, renderer, canvas, pickAt, select } = api;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const results = [];
  const check = (name, ok, msg = "") => {
    results.push({ name, ok: !!ok });
    console.log(`AUTOTEST garden ${ok ? "PASS" : "FAIL"} ${name} — ${msg}`);
  };
  const waitFor = async (fn, ms, step = 50) => {
    const t0 = performance.now();
    while (performance.now() - t0 < ms) { if (fn()) return true; await sleep(step); }
    return !!fn();
  };
  const hsv = (r, g, b) => { // 0..255 → [hue°, sat, val]
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    let h = 0;
    if (d > 0) h = mx === r ? 60 * (((g - b) / d) % 6) : mx === g ? 60 * ((b - r) / d + 2) : 60 * ((r - g) / d + 4);
    return [(h + 360) % 360, mx ? d / mx : 0, mx / 255];
  };
  const peak = (buf) => { const x = buf.getChannelData(0); let m = 0; for (let i = 0; i < x.length; i++) m = Math.max(m, Math.abs(x[i])); return m; };
  const lutHex = (tex, i = 0) => { const d = tex.image.data; return "#" + [d[4 * i], d[4 * i + 1], d[4 * i + 2]].map((v) => v.toString(16).padStart(2, "0")).join(""); };

  async function main() {
    // ---------------------------------------------------------------- 1. Morpho preset: blue LUT + renders
    const chip = [...document.querySelectorAll("#presets .chip")].find((c) => /Morpho/.test(c.textContent));
    if (!chip) throw new Error("Morpho-like preset chip missing");
    chip.click();
    const b = S.selected;
    const d0 = b.mesh.lut.image.data;
    const [h0, s0] = hsv(d0[0], d0[1], d0[2]);
    check("1a Morpho-like LUT at θ=0 is blue-ish", b && /Morpho/.test(b.name) && h0 >= 170 && h0 <= 260 && s0 > 0.2,
      `LUT[0] ${lutHex(b.mesh.lut)} hue ${h0.toFixed(0)}° sat ${s0.toFixed(2)} (${cfg().qty}, ${cfg().ill})`);
    // hold it still under a top-down camera and read back pixels
    const target = new THREE.Vector3(0, 2, 0);
    b.flight = { c: target.clone(), A: new THREE.Vector3(1e-3, 0, 0), W: new THREE.Vector3(1, 1, 1), Ph: new THREE.Vector3(0, 0, 0) };
    S.freezeFlap = 0;
    controls.target.copy(target);
    camera.position.set(0, 4.8, 0.01);
    controls.update();
    await sleep(150);
    renderer.render(api.scene, camera);
    const gl = renderer.getContext();
    const W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, w = Math.min(320, W), h = Math.min(320, H);
    const px = new Uint8Array(w * h * 4);
    gl.readPixels((W - w) >> 1, (H - h) >> 1, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
    let blue = 0;
    for (let i = 0; i < w * h; i++) {
      const [hh, ss, vv] = hsv(px[4 * i], px[4 * i + 1], px[4 * i + 2]);
      if (hh >= 160 && hh <= 270 && ss > 0.25 && vv > 0.25) blue++;
    }
    check("1b Morpho-like butterfly renders blue wings", blue / (w * h) > 0.02, `${(100 * blue / (w * h)).toFixed(1)}% blue-ish pixels in a ${w}×${h} centre crop`);

    // ---------------------------------------------------------------- 2. click → speaks
    S.lastSpeak = null;
    const v = b.mesh.group.position.clone().project(camera);
    const r = canvas.getBoundingClientRect();
    const hit = pickAt(r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height);
    const ls = S.lastSpeak;
    const pk = ls && ls.buf ? peak(ls.buf) : 0;
    const ftxt = $("bF").textContent.trim(), vtxt = $("bVowel").textContent.trim();
    check("2 raycast click on butterfly → speaks", hit === b && ls && ls.buf instanceof AudioBuffer && ls.buf.length > 10000 && pk > 0.1
      && ftxt && ftxt !== "—" && vtxt && vtxt !== "—",
      `hit ${hit ? hit.name : "none"}, buffer ${ls && ls.buf ? ls.buf.length : 0} samples @${ls && ls.buf ? ls.buf.sampleRate : "?"} Hz, peak ${pk.toFixed(2)}, θ ${ls ? ls.theta : "?"}°, formants "${ftxt.slice(0, 60)}", vowel "${vtxt.slice(0, 40)}"`);
    S.freezeFlap = null;
    camera.position.set(0, 3.0, 10.5);
    controls.target.set(0, 2, 0);
    controls.update();

    // ---------------------------------------------------------------- 3. atlas colour → metamers
    const sw = document.querySelector("#atlasSw button");
    if (!sw) throw new Error("no atlas swatches");
    sw.click();
    const ok3 = await waitFor(() => S.designer && S.designer.done && S.butterflies.some((x) => x.kind === "metamer"), 30000, 100);
    const metas = S.butterflies.filter((x) => x.kind === "metamer");
    const c = cfg();
    const tgt = S.designer ? S.designer.target : null;
    const dEs = metas.map((m) => P.deltaE00(P.filmColour(m.n, m.d, 0, c.ill, c.qty).Lab, tgt));
    let sep = Infinity;
    for (let i = 0; i < metas.length; i++) for (let j = i + 1; j < metas.length; j++) {
      sep = Math.min(sep, Math.hypot(metas[i].design.voice.F1 - metas[j].design.voice.F1, metas[i].design.voice.F2 - metas[j].design.voice.F2));
    }
    check("3 atlas colour → ≥3 metamer butterflies, ΔE00<2 (TMM re-check), distinct F1/F2",
      ok3 && metas.length >= 3 && Math.max(...dEs) < 2 && sep > 50 && $("metaList").children.length === metas.length,
      `${metas.length} metamers, ΔE00 ${dEs.map((x) => x.toFixed(2)).join("/")}, F1/F2 ${metas.map((m) => `${Math.round(m.design.voice.F1)}/${Math.round(m.design.voice.F2)}`).join(" ")}, min sep ${sep.toFixed(0)} Hz${S.designer && S.designer.retargeted ? " (retargeted)" : ""}`);

    // ---------------------------------------------------------------- 4. evolve one generation
    const e = S.butterflies.find((x) => x.kind === "random");
    select(e);
    const L0 = $("lineage").children.length, hex0 = e.hex0, nOld = Array.from(e.n);
    $("evolve").click();
    const L1 = $("lineage").children.length;
    const inb = Array.from(e.n).every((x, k) => (k === 0 ? x === 1 : x >= 1 - 1e-12 && x <= 2.5 + 1e-12));
    const changed = e.n.some((x, k) => x !== nOld[k]);
    check("4 evolve: lineage strip grows, n changed and in [1, 2.5]", L1 > L0 && inb && changed,
      `lineage ${L0} → ${L1}, colour ${hex0} → ${e.hex0}, N=${e.n.length - 2}`);

    // ---------------------------------------------------------------- 5. sing a word
    $("word").value = "heed hod who'd";
    $("sing").click();
    const s = S.singing;
    const spk = s && s.buf ? peak(s.buf) : 0;
    const seen = new Set(), mixes = new Set();
    const ended = await waitFor(() => {
      if (S.singing) { seen.add(lutHex(S.singing.b.mesh.lut2) + "|" + lutHex(S.singing.b.mesh.lut)); mixes.add(S.singing.b.mesh.material.uniforms.uMix.value.toFixed(2)); }
      return !S.singing;
    }, 6000, 40);
    const chips = $("seq").children.length;
    check("5 sing 'heed hod who'd': audio buffer + wing colour animates through the vowels",
      s && s.buf instanceof AudioBuffer && spk > 0.1 && chips === 3 && seen.size >= 2 && ended,
      `buffer ${s && s.buf ? s.buf.length : 0} samples, peak ${spk.toFixed(2)}, ${chips} vowels, LUT states seen ${seen.size} (${[...seen].map((x) => x.split("|")[0]).join(" ")}), mix values ${mixes.size}, finished ${ended}, audio ${S.ctx ? S.ctx.state : "none"}`);
  }

  const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error("timeout after 50 s")), 50000));
  try {
    await Promise.race([main(), timeout]);
    const bad = results.filter((x) => !x.ok).map((x) => x.name);
    console.log(bad.length ? `AUTOTEST FAIL garden ${bad.join("; ")}` : `AUTOTEST PASS garden ${results.length}/${results.length} checks`);
  } catch (e) {
    console.log(`AUTOTEST FAIL garden ${e && e.message ? e.message : e}`);
  }
}
