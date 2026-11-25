"""Real IPA recordings (Wikimedia Commons) -> LPC -> vocal-tract media -> thin film -> colour.  (CONTRACT §7c)

    . .\\tools\\env.ps1; python -m tools.fetch_ipa      # once: downloads data/ipa/raw/*.ogg + ATTRIBUTION
    python -m tools.build_sounds                        # writes web/audio/ipa/<id>.wav and web/data/sounds.json

Pipeline per recording (never crashes: a bad/silent file is skipped with a logged reason):
  decode (soundfile) -> mono -> resample to 16 kHz (scipy.signal.resample_poly) -> peak-normalise 0.9
  -> 512-sample frames, hop 256 -> features per frame:
       E   = RMS level in dB relative to the loudest frame
       zcr = zero-crossing rate, per = max normalised autocorrelation for lags 2.5-20 ms (50-400 Hz)
       hf  = fraction of frame energy above 2.5 kHz, lf = fraction below 500 Hz
  -> SEGMENTATION RULE of the target sound (by class, see RULES below)
  -> core.lpc.lpc(frame, 16, 0.97) on each selected frame -> k; average in the log-area-ratio domain
     LAR = 2·atanh(k) (as web/js/lab_core.js LarSmoother; |k| clipped to 0.995) -> k -> a = step_up(k)
  -> mapping.vowel_media(a) -> film_from_media(mode) -> Goupillaud stack (d_opt per mapping) -> CIE colour.
"""
from __future__ import annotations

import json
import sys
import zlib
from fractions import Fraction
from pathlib import Path

import numpy as np

from core import lpc, mapping as mp, film, colour as col, synth

ROOT = Path(__file__).resolve().parent.parent
IPA = ROOT / "data" / "ipa"
WEB = ROOT / "web"
OUT_AUDIO = WEB / "audio" / "ipa"
OUT_JSON = WEB / "data" / "sounds.json"
AUDIO_REL = "audio/ipa"   # --source user switches these three (see main)
USER_VOICE = ROOT / "data" / "user_voice"

FRAME, HOP, ORDER, PRE = 512, 256, mp.ORDER, 0.97
K_MAX = 0.995
STRIP_MAX = 60
TRAJ_N = 30          # diphthong trajectory steps
SYNTH_F0 = 120.0     # f0 of the film's own voice (audio_synth)
DIPH_DUR = 0.5       # s, diphthong audio
# diphthongs: id, IPA, name, example, start vowel id, end vowel id (ids of recorded vowels in this file).
# Choice: offglides end on the LAX vowels ɪ / ʊ (as in RP/GA "price", "mouth", "goat"), not on tense i / u.
DIPHTHONGS = [
    ("ei", "eɪ", "closing front diphthong", "face", "e", "ih"),
    ("ai", "aɪ", "wide closing front diphthong", "price", "a", "ih"),
    ("oi", "ɔɪ", "closing back-to-front diphthong", "choice", "aw", "ih"),
    ("au", "aʊ", "wide closing back diphthong", "mouth", "a", "uu"),
    ("ou", "oʊ", "closing back diphthong", "goat", "o", "uu"),
]
E_LOOSE = -40.0      # dB re loudest frame: "energetic" for the colour strip / fricatives / plosive context
E_VOWEL = -20.0      # dB re loudest frame: steady part of a vowel / sonorant
PER_VOICED = 0.45    # periodicity threshold for "voiced"

RULES = {
    "vowel": "voiced frames (periodicity > 0.45, ZCR < 0.25) within 20 dB of the loudest frame.",
    "nasal": "voiced frames within 30 dB of the loudest frame; if the file also contains a context vowel "
             "(spread of the <500 Hz energy fraction over voiced frames > 0.15) keep only frames whose low-frequency "
             "fraction is in the upper half of that range (nasal murmur has F1 < 400 Hz, the vowel [a] does not).",
    "lateral": "as nasal (voiced, low-F1 frames: [l] has F1 ≈ 300-400 Hz, lower than the context vowel).",
    "approximant": "as nasal (voiced, low-F1 frames: [ɹ w j] have F1 ≈ 250-400 Hz, lower than the context vowel).",
    "fricative": "voiceless: aperiodic (periodicity < 0.4) frames within 40 dB of the loudest frame whose "
                 ">2.5 kHz energy fraction or ZCR marks frication (hf > 0.3 or ZCR > 0.2); [h] has no high-"
                 "frequency requirement (aperiodic frames only). Voiced: frames within 40 dB whose >2.5 kHz energy "
                 "fraction is at least 60 % of the file's maximum (frication rides on voicing).",
    "plosive": "release bursts: hop positions where the level jumps by ≥ 15 dB within 2 hops from a quiet frame "
               "(≤ −30 dB re max); the onset is refined to 1 ms and ONE 512-sample frame starting 8 ms before the "
               "onset is analysed per burst (burst + aspiration/transition; for voiced plosives the following vowel "
               "onset contributes).",
    "affricate": "closure -> burst -> frication: release bursts are found as for plosives (≥ 15 dB jump within 2 hops "
                 "from a frame ≤ −30 dB re max); per burst the 512-sample frame starting 8 ms before the onset is "
                 "analysed PLUS the following hop frames while they stay fricated (within 40 dB of the loudest frame and "
                 "hf > 0.3 or ZCR > 0.2; voiceless additionally aperiodic, periodicity < 0.4; voiced: hf ≥ 50 % of the "
                 "max hf after the burst), at most 25 frames (400 ms) per burst. If no burst is found, the fricative "
                 "rule of the same voicing is used (noted).",
    "diphthong": "not a recording: time-varying film. The start and end vowel polynomials (items of this file) are "
                 "interpolated linearly in the log-area-ratio domain LAR = 2·atanh(k), t = 0..1 (30 steps) -> k(t) -> "
                 "a(t) -> film -> colour (trajectory). a/k/colours of the item are the midpoint t = 0.5. Audio: "
                 "core.synth.sing([a_start, a_end], [d/2, d/2], domain='lar') = hold, glide, hold.",
    "fallback": "if a rule selects no frame, all frames within 40 dB of the loudest are used (noted in the item).",
}


# ----------------------------------------------------------------------------- audio
def load_16k(path):
    import soundfile as sf
    from scipy.signal import resample_poly
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    x = x.mean(1)
    if sr != mp.FS:
        fr = Fraction(mp.FS, int(sr)).limit_denominator(1000)
        x = resample_poly(x, fr.numerator, fr.denominator)
    x = x - np.mean(x)
    pk = np.max(np.abs(x)) if len(x) else 0.0
    if not np.isfinite(pk) or pk < 1e-6:
        raise ValueError("silent or invalid audio")
    return x * (0.9 / pk), int(sr)


def frames_of(x):
    if len(x) < FRAME:
        x = np.append(x, np.zeros(FRAME - len(x)))
    n = 1 + (len(x) - FRAME) // HOP
    return np.stack([x[i * HOP:i * HOP + FRAME] for i in range(n)]), x


def features(F):
    rms = np.sqrt(np.mean(F ** 2, 1))
    E = 20 * np.log10(rms + 1e-12)
    E = E - E.max()
    zcr = np.mean(np.abs(np.diff(np.signbit(F).astype(int), axis=1)), 1)
    w = np.hanning(FRAME)
    S = np.abs(np.fft.rfft(F * w, axis=1)) ** 2
    f = np.fft.rfftfreq(FRAME, 1 / mp.FS)
    tot = S.sum(1) + 1e-20
    hf = S[:, f > 2500].sum(1) / tot
    lf = S[:, f < 500].sum(1) / tot
    per = np.zeros(len(F))
    lo, hi = int(mp.FS / 400), int(mp.FS / 50)
    for i, fr in enumerate(F):
        fr = fr - fr.mean()
        r = np.correlate(fr, fr, "full")[FRAME - 1:]
        if r[0] > 0:
            per[i] = float(np.max(r[lo:hi]) / r[0])
    return dict(E=E, zcr=zcr, hf=hf, lf=lf, per=per)


def bursts(x, ft):
    """Plosive release onsets (sample indices)."""
    E = ft["E"]
    on = []
    for i in range(2, len(E)):
        quiet = min(E[i - 1], E[i - 2])
        if quiet <= -30.0 and E[i] - quiet >= 15.0 and E[i] > -25.0:
            if on and i * HOP - on[-1] < 4 * HOP:
                continue
            # refine: 1 ms envelope inside [ (i-2)·hop, i·hop + frame )
            s0 = max(0, (i - 2) * HOP)
            seg = np.abs(x[s0:i * HOP + FRAME])
            env = np.array([seg[j:j + 16].max() for j in range(0, len(seg) - 16, 16)])
            if not len(env):
                continue
            thr = 0.1 * env.max()
            j = int(np.argmax(env > thr))
            on.append(s0 + 16 * j)
    return on


def select(cls, voiced, F, x, ft, glottal=False):
    """Indices of selected frames (or explicit frames for plosives) and a note."""
    E, zcr, hf, lf, per = ft["E"], ft["zcr"], ft["hf"], ft["lf"], ft["per"]
    loose = E >= E_LOOSE
    if cls == "plosive":
        on = bursts(x, ft)
        fr, n_ap = [], 0
        for s in on:
            s0 = max(0, s - 128)
            seg = x[s0:s0 + FRAME]
            if len(seg) < FRAME:
                continue
            # keep releases whose first 10 ms are noise-like (burst), not a periodic vowel onset
            b = seg[128:128 + 160]
            zc = np.mean(np.abs(np.diff(np.signbit(b).astype(int))))
            Sb = np.abs(np.fft.rfft(b * np.hanning(len(b)))) ** 2
            fb = np.fft.rfftfreq(len(b), 1 / mp.FS)
            hfb = Sb[fb > 2500].sum() / (Sb.sum() + 1e-20)
            if zc > 0.15 or hfb > 0.2:
                fr.append(seg); n_ap += 1
        return fr, f"{n_ap} of {len(on)} onset(s) burst-like"
    if cls == "affricate":
        on = bursts(x, ft)
        fr, nb = [], 0
        for s in on:
            s0 = max(0, s - 128)
            seg = x[s0:s0 + FRAME]
            if len(seg) < FRAME:
                continue
            j0 = s0 // HOP + 1                       # first hop frame after the burst frame
            win = np.arange(j0, min(len(F), j0 + 25))
            if not len(win):
                continue
            hmax = hf[win].max()
            fric = []
            for j in win:
                ok = (E[j] >= E_LOOSE) and (hf[j] > 0.3 or zcr[j] > 0.2)
                ok = ok and (per[j] < 0.4 if not voiced else hf[j] >= 0.5 * hmax)
                if not ok:
                    break
                fric.append(F[j])
            fr += [seg] + fric; nb += 1
        if fr:
            return fr, f"{nb} burst(s) + {len(fr) - nb} frication frame(s)"
        fr, note = select("fricative", voiced, F, x, ft)
        return fr, f"no burst found; fricative rule: {note}"
    if cls == "vowel":
        sel = (E >= E_VOWEL) & (per > PER_VOICED) & (zcr < 0.25)
    elif cls in ("nasal", "lateral", "approximant"):
        v = (E >= -30.0) & (per > PER_VOICED) & (zcr < 0.25)
        sel = v.copy()
        if v.sum() >= 4:
            q10, q90 = np.percentile(lf[v], [10, 90])
            if q90 - q10 > 0.15:
                sel = v & (lf >= 0.5 * (q10 + q90))
    elif cls == "fricative":
        if not voiced:
            sel = loose & (per < 0.4)
            hfsel = sel & ((hf > 0.3) | (zcr > 0.2))
            if hfsel.any() and not glottal:
                sel = hfsel
        else:
            m = hf[loose].max() if loose.any() else 0.0
            sel = loose & (hf >= 0.6 * m) & (m > 0.05)
    else:
        sel = loose
    return [F[i] for i in np.flatnonzero(sel)], f"{int(sel.sum())} frame(s)"


def analyse(frames):
    """LAR-domain average of per-frame LPC reflection coefficients -> (a, k, gain)."""
    lars, lg = [], []
    for fr in frames:
        if np.sqrt(np.mean(fr ** 2)) < 1e-5:
            continue
        try:
            _, k, g = lpc.lpc(fr, ORDER, PRE)
        except Exception:  # noqa: BLE001
            continue
        if not np.all(np.isfinite(k)):
            continue
        k = np.clip(k, -K_MAX, K_MAX)
        lars.append(2 * np.arctanh(k))
        lg.append(np.log(max(g, 1e-12)))
    if not lars:
        return None
    k = np.tanh(np.mean(lars, 0) / 2)
    return lpc.step_up(k), k, float(np.exp(np.mean(lg))), len(lars)


def colour_set(a):
    """{full|brief: {ideal|realizable: {T|R: {hex, Lab}}}} (D65, display hex = exposure-normalised)."""
    m = mp.vowel_media(a)
    out, ns = {}, {}
    for mode in ("ideal", "realizable"):
        ns[mode] = mp.film_from_media(m, mode)
    for mapping, d_opt in (("full", mp.D_OPT_FULL_NM), ("brief", mp.D_OPT_NM)):
        out[mapping] = {}
        for mode, n in ns.items():
            R, T = film.film_rt(n, mp.goupillaud_d(n[1:-1], d_opt), col.WL)
            q = {}
            for name, S in (("T", T), ("R", R)):
                X = col.spectrum_to_xyz(S, "D65")
                if not np.all(np.isfinite(X)):
                    q[name] = dict(hex="#000000", Lab=None)
                    continue
                q[name] = dict(hex=col.to_hex(col.display_rgb(X)),
                               Lab=[round(float(v), 3) for v in col.xyz_to_lab(X, "D65")], Y=round(float(X[1]), 4))
            out[mapping][mode] = q
    return out, ns


def strip_hex(a):
    n = mp.film_from_media(mp.vowel_media(a), "realizable")
    R, _ = film.film_rt(n, mp.goupillaud_d(n[1:-1], mp.D_OPT_FULL_NM), col.WL)
    X = col.spectrum_to_xyz(R, "D65")
    return col.to_hex(col.display_rgb(X)) if np.all(np.isfinite(X)) else "#000000"


def build_one(it):
    sid, cls = it["id"], it["cls"]
    x, sr = load_16k(ROOT / it["file"])
    OUT_AUDIO.mkdir(parents=True, exist_ok=True)
    synth.write_wav(OUT_AUDIO / f"{sid}.wav", synth._fade(x, mp.FS, ms=5))
    F, xp = frames_of(x)
    ft = features(F)
    fr, note = select(cls, it["voiced"], F, xp, ft, glottal=(it["ipa"] == "h"))
    used_rule = cls
    res = analyse(fr) if fr else None
    if res is None:
        fr = [F[i] for i in np.flatnonzero(ft["E"] >= E_LOOSE)]
        res = analyse(fr)
        used_rule = "fallback"
        note = f"rule '{cls}' selected nothing; fallback {len(fr)} frame(s)"
    if res is None:
        raise ValueError("no analysable frame")
    a, k, gain, n_used = res
    cols, ns = colour_set(a)
    # colour strip: every energetic frame (time order), sub-sampled to <= STRIP_MAX
    idx = np.flatnonzero(ft["E"] >= E_LOOSE)
    if len(idx) > STRIP_MAX:
        idx = idx[np.round(np.linspace(0, len(idx) - 1, STRIP_MAX)).astype(int)]
    strip = []
    for i in idx:
        r = analyse([F[i]])
        strip.append(strip_hex(r[0]) if r else "#000000")
    seed = zlib.crc32(sid.encode()) & 0x7FFFFFFF
    synth.write_wav(OUT_AUDIO / f"{sid}_synth.wav", synth.speak(a, cls, it["voiced"], f0=SYNTH_F0, seed=seed))
    try:
        Fm, _ = lpc.formants_from_poly(a)
        Fm = [round(float(v), 1) for v in Fm[:4]]
    except Exception:  # noqa: BLE001
        Fm = []
    return dict(
        id=sid, ipa=it["ipa"], name=it["name"], example=it["example"], kind=it["kind"], **{"class": cls},
        voiced=bool(it["voiced"]), audio=f"{AUDIO_REL}/{sid}.wav", audio_synth=f"{AUDIO_REL}/{sid}_synth.wav",
        source_rate=sr,
        duration_s=round(len(x) / mp.FS, 3), frames_total=int(len(F)), frames_used=int(n_used),
        rule=used_rule, segment_note=note,
        a=[round(float(v), 6) for v in a], k=[round(float(v), 6) for v in k], gain=round(gain, 6),
        lpc_formants=Fm, n_ideal_max=round(float(np.max(ns["ideal"])), 2),
        colours=cols, strip=strip,
        attribution=dict(title=it["title"], page=it["page"], url=it["url"], author=it["author"],
                         license=it["license"], license_url=it["license_url"]))


# ---- modelled items (recordings unavailable: Wikimedia 429 during the 2026-11-23 fetch). Flag modelled:true.
HILLENBRAND = [("e", "e", "close-mid front unrounded vowel", "face (start)", "ei"),
               ("eh", "ɛ", "open-mid front unrounded vowel", "dress", "eh"),
               ("o", "o", "close-mid back rounded vowel", "goat (start)", "oa")]
# id, ipa, name, example, class, voiced, burst source id (or None), frication source id, note
RELATIVES = [
    ("zh", "ʒ", "voiced postalveolar fricative", "vision", "fricative", True, None, "sh",
     "modelled: ʒ ← ʃ LPC polynomial (same envelope) + voiced (mixed) excitation"),
    ("ch", "tʃ", "voiceless postalveolar affricate", "chin", "affricate", False, "t", "sh",
     "modelled: tʃ ← t burst + ʃ frication (LAR mean, weights 0.25 burst / 0.75 frication)"),
    ("jh", "dʒ", "voiced postalveolar affricate", "jam", "affricate", True, "d", "sh",
     "modelled: dʒ ← d burst + ʒ (= ʃ LPC) frication (LAR mean, weights 0.25 / 0.75), voiced excitation"),
]
W_BURST = 0.25


def _item_from_poly(sid, ipa, name, ex, kind, cls, voiced, a, gain, strip, note, extra):
    k = lpc.step_down(a)
    cols, ns = colour_set(a)
    seed = zlib.crc32(sid.encode()) & 0x7FFFFFFF
    synth.write_wav(OUT_AUDIO / f"{sid}_synth.wav", synth.speak(a, cls, voiced, f0=SYNTH_F0, seed=seed))
    try:
        Fm, _ = lpc.formants_from_poly(a)
        Fm = [round(float(v), 1) for v in Fm[:4]]
    except Exception:  # noqa: BLE001
        Fm = []
    return dict(id=sid, ipa=ipa, name=name, example=ex, kind=kind, **{"class": cls}, voiced=bool(voiced),
                modelled=True, audio=f"audio/ipa/{sid}_synth.wav", audio_synth=f"audio/ipa/{sid}_synth.wav",
                rule="modelled", segment_note=note, a=[round(float(v), 6) for v in a],
                k=[round(float(v), 6) for v in k], gain=round(float(gain), 6), lpc_formants=Fm,
                n_ideal_max=round(float(np.max(ns["ideal"])), 2), colours=cols, strip=strip, **extra)


def build_modelled(have):
    """Items for phonemes whose recording is missing. `have`: id -> built recorded item."""
    out, skipped = [], []
    vj = json.loads((WEB / "data" / "vowels.json").read_text(encoding="utf-8"))
    hb = {v["vowel"]: v for v in vj["items"] if v["group"] == "men"}
    for sid, ipa, name, ex, hid in HILLENBRAND:
        if sid in have:
            continue
        if hid not in hb:
            skipped.append(dict(id=sid, reason=f"no recording and no Hillenbrand vowel {hid}")); continue
        v = hb[hid]
        a = np.array(v["a"], float)
        out.append(_item_from_poly(sid, ipa, name, ex, "vowel", "vowel", True, a, v["gain"], [strip_hex(a)],
                                   f"modelled: Hillenbrand 1995 men mean /{hid}/ (F1-F3 "
                                   f"{', '.join(str(round(f)) for f in v['lpc_formants'])} Hz) LPC-16 polynomial "
                                   "from web/data/vowels.json; no recording",
                                   dict(source="hillenbrand-model",
                                        attribution=dict(derived_from="Hillenbrand et al. 1995, JASA 97:3099 "
                                                                      "(group means; web/data/vowels.json)"))))
    for sid, ipa, name, ex, cls, voiced, bid, fid, note in RELATIVES:
        if sid in have:
            continue
        need = [i for i in (bid, fid) if i]
        if any(i not in have for i in need):
            skipped.append(dict(id=sid, reason=f"no recording; relative(s) {need} missing too")); continue
        Lf = 2 * np.arctanh(np.clip(np.array(have[fid]["k"]), -K_MAX, K_MAX))
        if bid:
            Lb = 2 * np.arctanh(np.clip(np.array(have[bid]["k"]), -K_MAX, K_MAX))
            L = W_BURST * Lb + (1 - W_BURST) * Lf
            gain = np.exp(W_BURST * np.log(have[bid]["gain"]) + (1 - W_BURST) * np.log(have[fid]["gain"]))
            strip = (have[bid]["strip"][:5] + have[fid]["strip"])[:STRIP_MAX]
        else:
            L, gain, strip = Lf, have[fid]["gain"], list(have[fid]["strip"])
        a = lpc.step_up(np.tanh(L / 2))
        out.append(_item_from_poly(sid, ipa, name, ex, "consonant", cls, voiced, a, gain, strip, note,
                                   dict(source="relatives-model", modelled_from=need,
                                        attribution=dict(derived_from=[have[i]["attribution"] for i in need]))))
    return out, skipped


def build_diphthong(d, by_id):
    sid, ipa, name, ex, s_id, e_id = d
    if s_id not in by_id or e_id not in by_id:
        raise ValueError(f"endpoint vowel missing: {s_id if s_id not in by_id else e_id}")
    vs, ve = by_id[s_id], by_id[e_id]
    a_s, a_e = np.array(vs["a"]), np.array(ve["a"])
    L_s = 2 * np.arctanh(np.clip(lpc.step_down(a_s), -K_MAX, K_MAX))
    L_e = 2 * np.arctanh(np.clip(lpc.step_down(a_e), -K_MAX, K_MAX))
    ts = np.linspace(0, 1, TRAJ_N)
    traj = [strip_hex(lpc.step_up(np.tanh(((1 - t) * L_s + t * L_e) / 2))) for t in ts]
    k_mid = np.tanh(0.5 * (L_s + L_e) / 2)
    a_mid = lpc.step_up(k_mid)
    cols, ns = colour_set(a_mid)
    y = synth.sing([a_s, a_e], [DIPH_DUR / 2, DIPH_DUR / 2], f0=SYNTH_F0, domain="lar")
    synth.write_wav(OUT_AUDIO / f"{sid}_synth.wav", y)
    try:
        Fm, _ = lpc.formants_from_poly(a_mid)
        Fm = [round(float(v), 1) for v in Fm[:4]]
    except Exception:  # noqa: BLE001
        Fm = []
    ends = dict(start=dict(id=s_id, ipa=vs["ipa"], hex=traj[0]), mid=dict(hex=strip_hex(a_mid)),
                end=dict(id=e_id, ipa=ve["ipa"], hex=traj[-1]))
    return dict(
        id=sid, ipa=ipa, name=name, example=ex, kind="diphthong", **{"class": "diphthong"}, voiced=True,
        recorded=False, audio=f"audio/ipa/{sid}_synth.wav", audio_synth=f"audio/ipa/{sid}_synth.wav",
        duration_s=DIPH_DUR, rule="diphthong",
        segment_note=f"LAR interpolation /{vs['ipa']}/ -> /{ve['ipa']}/ ({TRAJ_N} steps); a, k, colours = midpoint",
        **{"from": s_id, "to": e_id}, endpoints=ends,
        a=[round(float(v), 6) for v in a_mid], k=[round(float(v), 6) for v in k_mid],
        gain=round(float(np.sqrt(vs["gain"] * ve["gain"])), 6), lpc_formants=Fm,
        n_ideal_max=round(float(np.max(ns["ideal"])), 2), colours=cols, trajectory=traj, strip=traj,
        attribution=dict(derived_from=[vs["attribution"], ve["attribution"]]))


def user_source():
    """Items for the user's own recordings (web/record.html -> data/user_voice/<id>.wav)."""
    from tools.fetch_ipa import SOUNDS
    att = dict(title="your recording (web/record.html)", page="", url="", author="the project author (own voice)",
               license="own recording", license_url="")
    items = [dict(id=sid, ipa=ipa, name=name, example=ex, kind=kind, cls=cls, voiced=v,
                  file=str(USER_VOICE / f"{sid}.wav"), **att)
             for sid, ipa, name, ex, kind, cls, v, _ in SOUNDS if (USER_VOICE / f"{sid}.wav").exists()]
    for sid, ipa, name, ex, *_ in DIPHTHONGS:
        if (USER_VOICE / f"{sid}.wav").exists():
            items.append(dict(id=sid, ipa=ipa, name=name, example=ex, kind="diphthong", cls="vowel", voiced=True,
                              file=str(USER_VOICE / f"{sid}.wav"), recorded_diphthong=True, **att))
    return dict(items=items, skipped=[])


def build_sentence(path):
    """A read sentence -> colour ribbon: one film colour per energetic frame (<= 240, time order)."""
    x, _ = load_16k(path)
    F, _ = frames_of(x)
    ft = features(F)
    idx = np.flatnonzero(ft["E"] >= E_LOOSE)
    if len(idx) > 240:
        idx = idx[np.round(np.linspace(0, len(idx) - 1, 240)).astype(int)]
    rib = []
    for i in idx:
        r = analyse([F[i]])
        rib.append(strip_hex(r[0]) if r else "#000000")
    OUT_AUDIO.mkdir(parents=True, exist_ok=True)
    synth.write_wav(OUT_AUDIO / f"{path.stem}.wav", synth._fade(x, mp.FS, ms=5))
    return dict(id=path.stem, audio=f"{AUDIO_REL}/{path.stem}.wav", duration_s=round(len(x) / mp.FS, 3),
                t_s=[round(float(i * HOP / mp.FS), 3) for i in idx], ribbon=rib)


def main(argv=()):
    global OUT_AUDIO, OUT_JSON, AUDIO_REL
    user = "--source" in argv and argv[list(argv).index("--source") + 1] == "user"
    att_path = IPA / "ATTRIBUTION.json"
    if user:
        OUT_AUDIO, OUT_JSON, AUDIO_REL = WEB / "audio" / "user", WEB / "data" / "sounds_user.json", "audio/user"
        OUT_AUDIO.mkdir(parents=True, exist_ok=True)
        src = user_source()
        print(f"user voice: {len(src['items'])} recordings in data/user_voice/")
    elif not att_path.exists():
        print("no data/ipa/ATTRIBUTION.json — run python -m tools.fetch_ipa first; writing empty sounds.json")
        src = dict(items=[], skipped=[])
    else:
        src = json.loads(att_path.read_text(encoding="utf-8"))
    items, skipped = [], list(src.get("skipped", []))
    for it in src.get("items", []):
        try:
            if not (ROOT / it["file"]).exists():
                raise FileNotFoundError(it["file"])
            r = build_one(it)
            if it.get("recorded_diphthong"):   # real glide: the colour trajectory is the per-frame strip
                r.update(kind="diphthong", trajectory=r["strip"], rule="diphthong-recorded",
                         segment_note="recorded glide; a = LAR mean of voiced frames, trajectory = per-frame colours")
                r["class"] = "diphthong"
            json.dumps(r, allow_nan=False)          # raises on NaN/inf -> item skipped, file stays valid JSON
            items.append(r)
            c = r["colours"]["full"]["realizable"]
            print(f"  {r['id']:6s} /{r['ipa']}/ {r['class']:11s} {r['frames_used']:3d}/{r['frames_total']:3d} fr "
                  f"[{r['segment_note']}]  full-real R {c['R']['hex']} T {c['T']['hex']}")
        except Exception as e:  # noqa: BLE001
            skipped.append(dict(id=it.get("id"), reason=f"{type(e).__name__}: {e}"))
            print(f"  skip {it.get('id')}: {type(e).__name__}: {e}")
    mod, msk = build_modelled({i["id"]: i for i in items})
    for r in mod:
        json.dumps(r, allow_nan=False)
        items.append(r)
        print(f"  {r['id']:6s} /{r['ipa']}/ {r['class']:11s} MODELLED  full-real R "
              f"{r['colours']['full']['realizable']['R']['hex']}  [{r['segment_note'][:60]}]")
    have_ids = {i["id"] for i in items}
    skipped = [s_ for s_ in skipped if s_.get("id") not in have_ids] + msk
    by_id = {i["id"]: i for i in items if i["kind"] == "vowel"}
    for d in DIPHTHONGS:
        if d[0] in {i["id"] for i in items}:
            continue
        try:
            r = build_diphthong(d, by_id)
            json.dumps(r, allow_nan=False)
            items.append(r)
            print(f"  {r['id']:6s} /{r['ipa']}/ diphthong   {' '.join(r['trajectory'][::7])}")
        except Exception as e:  # noqa: BLE001
            skipped.append(dict(id=d[0], reason=f"{type(e).__name__}: {e}"))
            print(f"  skip {d[0]}: {type(e).__name__}: {e}")
    out = dict(
        source="Wikimedia Commons IPA-chart recordings (see data/ipa/ATTRIBUTION.md); analysis by tools/build_sounds.py",
        generated_by="python -m tools.build_sounds",
        analysis=dict(fs=mp.FS, frame=FRAME, hop=HOP, order=ORDER, preemph=PRE, window="hamming",
                      average="log-area-ratio mean (LAR = 2·atanh k), |k| ≤ 0.995", illuminant="D65",
                      strip="per energetic frame (≤ 40 dB below max), full-band realizable R, ≤ 60 frames",
                      d_opt_nm=dict(full=round(mp.D_OPT_FULL_NM, 4), brief=round(mp.D_OPT_NM, 4)),
                      trajectory=f"diphthongs: {TRAJ_N} LAR-interpolation steps start->end, full-band realizable R",
                      audio_synth=f"core.synth.speak(a, class, voiced, f0={SYNTH_F0:g}) = the film's own voice with "
                                  "class excitation (noise / mixed / closure-burst-aspiration / burst+frication / "
                                  "glottal); diphthongs: core.synth.sing(domain='lar')"),
        rules=RULES, items=items, skipped=skipped)
    if user:
        out["source"] = "the author's own voice, recorded on web/record.html (data/user_voice/); analysis by tools/build_sounds.py"
        out["generated_by"] = "python -m tools.build_sounds --source user"
        out["sentences"] = [build_sentence(p) for p in sorted(USER_VOICE.glob("sent_*.wav"))]
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    from collections import Counter
    nv = sum(1 for i in items if i["kind"] == "vowel")
    print("per class:", dict(Counter(i["class"] for i in items)),
          "fallback:", [i["id"] for i in items if i["rule"] == "fallback"])
    print(f"{len(items)} sounds ({nv} vowels, {len(items) - nv} other), {len(skipped)} skipped -> "
          f"{OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
