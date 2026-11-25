/**
 * lab_autotest.js — in-browser self-test of the REAL Live Voice Lab path. It is loaded only by lab.html?autotest.
 * Play demo (AudioContext → AudioBufferSource → lab_worklet.js → resampler → gate → LPC → physics), then check
 * the colour, F1/F2 against Hillenbrand, the film-vs-tube isomorphism, the 3D tube update and the paint-strip PNG.
 * It logs one line per check, then exactly one final "AUTOTEST PASS lab …" or "AUTOTEST FAIL lab <reason>".
 */
export async function runAutotest(api) {
  const T0 = performance.now();
  let finished = false, firstFail = null, nOk = 0;
  const finish = (msg) => { if (finished) return; finished = true; console.log(msg); document.title = msg.slice(0, 60); };
  const log = (ok, name, info = "") => {
    console.log(`AUTOTEST ${ok ? "ok  " : "FAIL"} ${name}${info ? " | " + info : ""}`);
    if (ok) nOk++; else if (!firstFail) firstFail = `${name} (${info})`;
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const waitFor = async (cond, ms, what) => {
    const end = performance.now() + ms;
    while (!cond()) { if (performance.now() > end) throw new Error(`timeout waiting for ${what}`); await sleep(40); }
  };
  const median = (xs) => { const s = xs.filter((x) => x != null && Number.isFinite(x)).sort((a, b) => a - b); return s.length ? s[s.length >> 1] : NaN; };
  const watchdog = setTimeout(() => finish(`AUTOTEST FAIL lab watchdog: no result after 20 s (${nOk} checks ok so far)`), 20000);

  async function runVowel(group, id, minFrames = 20) {
    const frames = [];
    const fn = (h) => { if (h.updated) frames.push(h); };
    api.hopListeners.push(fn);
    try {
      api.selectDemo(group, id);
      await api.playDemo();
      const ctx = api.getCtx();
      log(api.getSrcKind() === "demo" && ctx && ctx.state === "running", `${group}/${id}: demo playing through AudioContext`,
        `state ${ctx && ctx.state}, ${ctx && ctx.sampleRate} Hz, capture ${api.getCapKind()}`);
      await waitFor(() => frames.length >= minFrames, 8000, `${minFrames} voiced frames of ${id}`);
      await waitFor(() => api.getSrcKind() === null, 6000, `end of demo ${id}`);
    } finally {
      api.hopListeners.splice(api.hopListeners.indexOf(fn), 1);
    }
    return frames;
  }

  function checkVowel(group, id, frames) {
    const ref = api.VOWELS.find((v) => v.group === group && v.vowel === id);
    log(frames.length >= 20, `${group}/${id}: voiced frames passed the gate`, `${frames.length}`);
    const F1 = median(frames.map((h) => h.F1)), F2 = median(frames.map((h) => h.F2));
    const e1 = F1 / ref.F1 - 1, e2 = F2 / ref.F2 - 1;
    log(Math.abs(e1) < 0.25 && Math.abs(e2) < 0.25, `${group}/${id}: F1/F2 within ±25% of Hillenbrand`,
      `F1 ${F1.toFixed(0)} vs ${ref.F1.toFixed(0)} (${(100 * e1).toFixed(1)}%), F2 ${F2.toFixed(0)} vs ${ref.F2.toFixed(0)} (${(100 * e2).toFixed(1)}%)`);
    const last = frames[frames.length - 1];
    const [Lv, a, b] = last.colour.Lab, C = Math.hypot(a, b);
    log(C > 15 && /^#[0-9a-f]{6}$/.test(last.colour.hex), `${group}/${id}: non-grey film colour`, `${last.colour.hex}, Lab ${Lv.toFixed(1)}/${a.toFixed(1)}/${b.toFixed(1)}, chroma ${C.toFixed(1)}`);
    const md = Math.max(...frames.map((h) => (h.iso ? h.iso.maxDiff : Infinity)));
    log(md < 1e-6, `${group}/${id}: max |T_film - P_tube| < 1e-6 over all frames`, md.toExponential(2));
    return last;
  }

  try {
    log(api.S.mode === "ideal" && api.VOWELS.length > 0, "page booted (physics data + vowels.json loaded)", `${api.VOWELS.length} vowels`);
    // (1) men /ɑ/ through the real audio path
    const v0 = api.hero.gOuter.attributes.position.version;
    const fa = await runVowel("men", "ah");
    const lastA = checkVowel("men", "ah", fa);
    // (2) 3D tube follows the voice (wait a few animation frames)
    await sleep(400);
    const la = api.hero.logA || [];
    const spread = la.length ? Math.max(...la) - Math.min(...la) : 0;
    const tgt = lastA.areas.map((x) => Math.log(x));
    const err = la.length ? Math.max(...la.map((v, i) => Math.abs(v - tgt[i]))) : Infinity;
    log(api.hero.gOuter.attributes.position.version > v0 + 10 && spread > 0.3, "3D neon tube geometry updated with the /ɑ/ area function",
      `position updates ${api.hero.gOuter.attributes.position.version - v0}, log-area spread ${spread.toFixed(2)}, |display - target| ${err.toExponential(1)}`);
    // (3) paint your sentence: record over men /i/
    api.rec.length = 0;
    api.toggleRec();
    log(api.isRecording(), "recording started");
    const fi = await runVowel("men", "iy");
    checkVowel("men", "iy", fi);
    api.toggleRec();
    api.redrawStrip();
    const nv = api.rec.filter((q) => q.voiced).length;
    log(!api.isRecording() && api.rec.length > 40 && nv >= 20 && nv < api.rec.length, "recorded strip has voiced frames and silence gaps",
      `${api.rec.length} hops, ${nv} voiced`);
    const sg = api.$("strip").getContext("2d").getImageData(0, 0, api.$("strip").width, api.$("strip").height).data;
    let lit = 0;
    for (let i = 0; i < sg.length; i += 4) if (sg[i + 2] > 120 && sg[i + 2] > sg[i + 1] + 40) lit++;
    log(lit > 100, "strip canvas painted with violet frames", `${lit} violet pixels`);
    const url = api.renderPNGCanvas().toDataURL("image/png");
    const sig = atob(url.slice(22, 34)).slice(1, 4);
    log(url.startsWith("data:image/png;base64,") && url.length > 2000 && sig === "PNG", "PNG export (dataURL, no download)", `${url.length} chars, signature ${sig}`);
    api.$("btn-png").disabled = api.rec.length === 0;
    log(!api.$("btn-png").disabled, "Download PNG button enabled");
  } catch (e) {
    log(false, "exception", (e && e.message) || String(e));
  }
  clearTimeout(watchdog);
  const secs = ((performance.now() - T0) / 1000).toFixed(1);
  finish(firstFail ? `AUTOTEST FAIL lab ${firstFail}` : `AUTOTEST PASS lab ${nOk} checks in ${secs} s`);
}
