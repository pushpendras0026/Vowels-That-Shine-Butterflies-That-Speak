"""Generate all shared data: web/data/*.json, web/audio/*.wav, results/atlas.npz.
Run:  . .\\tools\\env.ps1; python -m tools.build_all  [--quick]"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from core import lpc, mapping as mp, film, colour as col, synth, stacks, vowels, inverse

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "data"
AUDIO = ROOT / "web" / "audio"
RES = ROOT / "results"
for d in (WEB, AUDIO, RES):
    d.mkdir(parents=True, exist_ok=True)
QUICK = "--quick" in sys.argv


def L(x, nd=10):
    """JSON-friendly rounded list."""
    a = np.asarray(x, float)
    return [float(np.round(v, nd)) for v in a.ravel()] if a.ndim else float(np.round(a, nd))


def dump(name, obj):
    (WEB / name).write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    print(f"  wrote {name} ({(WEB / name).stat().st_size / 1024:.0f} KB)")


def build_cie():
    consts = {k: getattr(mp, k) for k in ("FS", "ORDER", "C_SOUND", "L_TRACT", "C_LIGHT", "NU_MIN", "NU_MAX",
                                          "DNU", "D_OPT_NM", "R_GLOTTIS", "N_MIN", "N_MAX")}
    dump("cie.json", dict(wl=L(col.WL, 3), xbar=L(col.CMF[:, 0], 9), ybar=L(col.CMF[:, 1], 9),
                          zbar=L(col.CMF[:, 2], 9),
                          illuminants={k: L(v, 6) for k, v in col.ILLUMINANTS.items()},
                          materials=mp.MATERIALS, constants=consts,
                          srgb_matrix=col.M_XYZ_TO_SRGB.tolist(),
                          source="CIE 1931 2° CMFs + illuminants from colour-science 0.4.7, linearly "
                                 "interpolated to 0.5 nm; LED = CIE LED-B3"))


def colours_for(n, d):
    out = {}
    for ill in col.ILLUMINANTS:
        R, T = film.film_rt(n, d, col.WL)
        XT, XR = col.spectrum_to_xyz(T, ill), col.spectrum_to_xyz(R, ill)
        out[ill] = dict(T=col.to_hex(col.display_rgb(XT)), R=col.to_hex(col.display_rgb(XR)),
                        Lab=L(col.xyz_to_lab(XT, ill), 4), LabR=L(col.xyz_to_lab(XR, ill), 4),
                        Y_T=float(np.round(XT[1], 4)))
    return out


def build_vowels():
    items = []
    for g in vowels.group_means():
        a, gain = vowels.vowel_lpc([g["F1"], g["F2"], g["F3"]], g["F0"])
        m = mp.vowel_media(a)
        n_id = mp.film_from_media(m, "ideal")
        n_re = mp.film_from_media(m, "realizable")
        n_ma = mp.film_from_media(m, "materials")
        F, B = lpc.formants_from_poly(a)
        it = dict(g, a=L(a), gain=float(gain), areas=L(m[1:-1]), m=L(m), n_ideal=L(n_id), n_real=L(n_re),
                  n_materials=L(n_ma), lpc_formants=L(F[:4], 2),
                  colours=colours_for(n_id, mp.goupillaud_d(n_id[1:-1])),
                  colours_real=colours_for(n_re, mp.goupillaud_d(n_re[1:-1])),
                  # full-band mapping (CONTRACT §4b): same films, layers 199.86 nm optical thickness
                  colours_full=colours_for(n_id, mp.goupillaud_d(n_id[1:-1], mp.D_OPT_FULL_NM)),
                  colours_full_real=colours_for(n_re, mp.goupillaud_d(n_re[1:-1], mp.D_OPT_FULL_NM)),
                  audio=f"audio/vowel_{g['group']}_{g['vowel']}.wav")
        items.append(it)
        y = synth.synth_allpole(a, synth.glottal_source(g["F0"], dur=0.7, jitter=0.01), gain)
        synth.write_wav(AUDIO / f"vowel_{g['group']}_{g['vowel']}.wav", synth._fade(synth._norm(y), mp.FS))
    dump("vowels.json", dict(source="Hillenbrand et al. 1995 (JASA 97:3099) group means of steady-state F0/F1-F3; "
                                    "bandwidths illustrative (80/100/150 Hz); LPC-16 of Rosenberg-excited synthesis",
                             items=items))
    return items


def lut(n, d, quantity="R", illuminant="D65", angles=np.arange(0, 81, 2)):
    hexes = []
    for th in angles:
        R, T = film.film_rt(n, d, col.WL, float(th))
        X = col.spectrum_to_xyz(R if quantity == "R" else T, illuminant)
        hexes.append(col.to_hex(col.display_rgb(X)))
    return dict(angles=L(angles), rgb=hexes, quantity=quantity, illuminant=illuminant)


def build_butterflies():
    rng = np.random.default_rng(2026)
    items = [stacks.morpho_like(), stacks.beetle_like()]
    for i in range(4):
        s = stacks.random_goupillaud(rng)
        s["name"] = f"Goupillaud speaker #{i + 1}"
        items.append(s)
    out = []
    for s in items:
        a, g = film.voice_of_film(s["n"], s["d_nm"])
        F, _ = lpc.formants_from_poly(a)
        fn = "bfly_" + s["name"].split()[0].lower().replace("-like", "") + (s["name"][-1] if "#" in s["name"] else "") + ".wav"
        synth.write_wav(AUDIO / fn, synth.film_voice(s["n"], s["d_nm"]))
        out.append(dict(name=s["name"], label=s["label"], source=s["source"], n=L(s["n"]), d_nm=L(s["d_nm"]),
                        lut=lut(s["n"], s["d_nm"]), a=L(a), gain=g, F=L(F[:4], 2), audio="audio/" + fn))
    dump("butterflies.json", dict(items=out))


def build_atlas(N=20000):
    rng = np.random.default_rng(7)
    t0 = time.time()
    ns = np.zeros((N, mp.ORDER + 2))
    labT = np.zeros((N, 3)); labR = np.zeros((N, 3)); rgbT = []; rgbR = []
    F12 = np.full((N, 2), np.nan)
    for i in range(N):
        s = stacks.random_goupillaud(rng, mode="realizable" if i % 2 == 0 else "bimodal")
        n = s["n"]; ns[i] = n
        R, T = film.film_rt(n, s["d_nm"], col.WL)
        XT, XR = col.spectrum_to_xyz(T), col.spectrum_to_xyz(R)
        labT[i] = col.xyz_to_lab(XT); labR[i] = col.xyz_to_lab(XR)
        rgbT.append(col.to_hex(col.display_rgb(XT))); rgbR.append(col.to_hex(col.display_rgb(XR)))
        F, _ = inverse.stack_formants(n)
        if len(F) >= 2:
            F12[i] = F[:2]
    np.savez_compressed(RES / "atlas.npz", arm=np.arange(N) % 2, n=ns, labT=labT, labR=labR, rgbT=np.array(rgbT), rgbR=np.array(rgbR),
                        F12=F12)
    print(f"  atlas {N} stacks in {time.time() - t0:.0f}s; with >=2 formants: {np.isfinite(F12[:, 0]).mean():.2%}")
    idx = rng.choice(N, min(3000, N), replace=False)
    dump("atlas_sample.json", dict(n=int(len(idx)), total=N, mode="realizable Goupillaud, n in [1,2.5]; even index = log-uniform arm, odd = bimodal arm; "
                                   "incident air, D65, transmittance",
                                   items=[dict(arm=int(i % 2), n=L(ns[i], 4), rgb=rgbT[i], rgbR=rgbR[i], Lab=L(labT[i], 3),
                                               LabR=L(labR[i], 3), F1=None if np.isnan(F12[i, 0]) else float(round(F12[i, 0], 1)),
                                               F2=None if np.isnan(F12[i, 1]) else float(round(F12[i, 1], 1)))
                                          for i in idx]))


def build_vectors():
    # Full float precision (repr round-trips): rounding inputs to 1e-10 made stepDown/synthAllpole
    # expectations inconsistent with the stored args (ill-conditioned; Python itself failed them).
    def L(x, nd=None):
        a = np.asarray(x, float)
        return [float(v) for v in a.ravel()] if a.ndim else float(a)

    rng = np.random.default_rng(11)
    cases = []

    def add(name, fn, args, expect, tol=1e-9):
        cases.append(dict(name=name, fn=fn, args=args, expect=expect, tol=tol))

    x = synth.synth_allpole(lpc.poly_from_formants([600, 1400, 2500], [80, 100, 150]),
                            synth.glottal_source(120, dur=0.04), 1.0)[:512]
    r = lpc.autocorr(x, 16)
    a, k, e = lpc.levinson(r, 16)
    add("levinson", "levinson", [L(r), 16], dict(a=L(a), k=L(k), err=float(e)), 1e-7)
    a2, k2, g2 = lpc.lpc(x, 16, 0.97)
    add("lpc frame", "lpc", [L(x), 16, 0.97], dict(a=L(a2), k=L(k2), gain=float(g2)), 1e-6)
    kk = rng.uniform(-0.9, 0.9, 16)
    add("stepUp", "stepUp", [L(kk)], L(lpc.step_up(kk)))
    add("stepDown", "stepDown", [L(lpc.step_up(kk))], L(kk), 1e-8)
    add("reflectionToAreas", "reflectionToAreas", [L(kk), 1.0], L(lpc.reflection_to_areas(kk)), 1e-8)
    areas = np.exp(rng.uniform(-1, 1, 17))
    add("areasToReflection", "areasToReflection", [L(areas)], L(lpc.areas_to_reflection(areas)))
    pf = lpc.poly_from_formants([500, 1500, 2500], [60, 90, 120])
    add("polyFromFormants", "polyFromFormants", [[500, 1500, 2500], [60, 90, 120], 16000], L(pf))
    F, B = lpc.formants_from_poly(pf)
    add("formantsFromPoly", "formantsFromPoly", [L(pf), 16000], dict(F=L(F), B=L(B)), 1e-6)
    m = np.exp(rng.uniform(-1, 1.5, 18))
    c = mp.reflection_from_media(m)
    add("reflectionFromMedia", "reflectionFromMedia", [L(m)], L(c))
    add("polyFromReflection", "polyFromReflection", [L(c)], L(mp.poly_from_reflection(c)))
    om = np.linspace(0, 2 * np.pi, 33)
    add("powerTransfer", "powerTransfer", [L(c), L(om)], L(mp.power_transfer(c, om)), 1e-8)
    nus = np.linspace(mp.NU_MIN, mp.NU_MAX, 9)
    add("fOfNu", "fOfNu", [L(nus)], L(mp.f_of_nu(nus)), 1e-6)
    add("fOfNu full-band", "fOfNu", [L(nus), mp.DNU_FULL], L(mp.f_of_nu(nus, mp.DNU_FULL)), 1e-6)
    va, _ = vowels.vowel_lpc([730, 1090, 2440], 130)
    vm = mp.vowel_media(va)
    add("vowelMedia", "vowelMedia", [L(va), mp.R_GLOTTIS], L(vm), 1e-7)
    for mode in ("ideal", "realizable", "materials"):
        add(f"filmFromMedia {mode}", "filmFromMedia", [L(vm), mode], L(mp.film_from_media(vm, mode)), 1e-7)
    n = mp.film_from_media(vm, "realizable")
    d = mp.goupillaud_d(n[1:-1])
    add("goupillaudD", "goupillaudD", [L(n[1:-1])], L(d))
    dF = mp.goupillaud_d(n[1:-1], mp.D_OPT_FULL_NM)
    add("goupillaudD full-band", "goupillaudD", [L(n[1:-1]), mp.D_OPT_FULL_NM], L(dF))
    avF, gvF = film.voice_of_film(n, dF, 0.0, 16, 2048, mp.DNU_FULL)
    add("voiceOfFilm full-band", "voiceOfFilm", [L(n), L(dF), 0.0, 16, 2048, mp.DNU_FULL], dict(a=L(avF), gain=gvF), 1e-6)
    fcF = col.film_colour(n, dF, 0.0, "D65", "R")
    add("filmColour full-band R", "filmColour", [L(n), L(dF), 0.0, "D65", "R"],
        dict(XYZ=L(fcF["XYZ"]), Lab=L(fcF["Lab"]), rgb=L(fcF["rgb"]), hex=fcF["hex"]), 1e-7)
    wl = np.linspace(380, 780, 41)
    for th, pol in ((0, "u"), (35, "s"), (35, "p"), (60, "u")):
        Rr, Tt = film.film_rt(n, d, wl, th, pol)
        add(f"filmRT th={th} {pol}", "filmRT", [L(n), L(d), L(wl), th, pol], dict(R=L(Rr), T=L(Tt)), 1e-9)
    mo = stacks.morpho_like()
    Rr, Tt = film.film_rt(mo["n"], mo["d_nm"], wl, 20, "u")
    add("filmRT morpho 20deg", "filmRT", [L(mo["n"]), L(mo["d_nm"]), L(wl), 20, "u"], dict(R=L(Rr), T=L(Tt)))
    av, gv = film.voice_of_film(n, d, 0.0, 16, 2048)
    add("voiceOfFilm goupillaud", "voiceOfFilm", [L(n), L(d), 0.0, 16, 2048], dict(a=L(av), gain=gv), 1e-6)
    av, gv = film.voice_of_film(mo["n"], mo["d_nm"], 30.0, 16, 2048)
    add("voiceOfFilm morpho 30deg", "voiceOfFilm", [L(mo["n"]), L(mo["d_nm"]), 30.0, 16, 2048],
        dict(a=L(av), gain=gv), 1e-5)
    _, T = film.film_rt(n, d, col.WL)
    for ill in col.ILLUMINANTS:
        X = col.spectrum_to_xyz(T, ill)
        add(f"spectrumToXYZ {ill}", "spectrumToXYZ", [L(T), ill], L(X), 1e-7)
        add(f"xyzToLab {ill}", "xyzToLab", [L(X), ill], L(col.xyz_to_lab(X, ill)), 1e-7)
    X = np.array([41.2, 21.3, 1.9])
    add("xyzToSRGB", "xyzToSRGB", [L(X)], L(col.xyz_to_srgb(X)))
    add("displayRGB", "displayRGB", [L(X)], L(col.display_rgb(X)))
    for i in range(6):
        l1, l2 = rng.uniform([0, -80, -80], [100, 80, 80]), rng.uniform([0, -80, -80], [100, 80, 80])
        add(f"deltaE00 {i}", "deltaE00", [L(l1), L(l2)], col.delta_e00(l1, l2))
    fc = col.film_colour(mo["n"], mo["d_nm"], 25.0, "D65", "R")
    add("filmColour morpho R 25deg", "filmColour", [L(mo["n"]), L(mo["d_nm"]), 25.0, "D65", "R"],
        dict(XYZ=L(fc["XYZ"]), Lab=L(fc["Lab"]), rgb=L(fc["rgb"]), hex=fc["hex"]), 1e-7)
    src = synth.glottal_source(150.0, 16000, 0.02, oq=0.6, sq=2.0)
    add("glottalSource", "glottalSource", [150.0, 16000, 0.02, 0.6, 2.0], L(src))
    add("synthAllpole", "synthAllpole", [L(pf), L(src), 1.0], L(synth.synth_allpole(pf, src, 1.0)), 1e-7)
    dump("test_vectors.json", dict(version=1, generated_by="tools/build_all.py", cases=cases))


if __name__ == "__main__":
    print("cie"); build_cie()
    print("vectors"); build_vectors()
    print("vowels"); build_vowels()
    print("butterflies"); build_butterflies()
    print("atlas"); build_atlas(2000 if QUICK else 20000)
