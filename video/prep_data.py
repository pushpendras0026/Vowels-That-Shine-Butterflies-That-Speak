"""Precompute every curve / colour / stack the explainer video draws, using core/ only.

Writes video/data/scene_data.json and extra audio clips into video/audio/ (16 kHz wav).
Run:  . .\\tools\\env.ps1; python -m video.prep_data
Nothing in this file is hand-tuned physics: all numbers come from core.* and web/data/*.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from core import colour as col
from core import film, lpc, synth, tube
from core import mapping as mp

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OUT = ROOT / "video" / "data"
AUD = ROOT / "video" / "audio"


def L(x, nd=6):
    return np.round(np.asarray(x, float), nd).tolist()


def hexcol(XYZ):
    return col.to_hex(col.display_rgb(XYZ))


def _voice_env(n):
    n = np.asarray(n, float)
    d = mp.goupillaud_d(n[1:-1])
    a, g = film.voice_of_film(n, d)
    fe, edb = lpc.envelope_db(a, g, nfft=512)
    return a, g, fe, edb - edb.max()


def atlas_metamers(n_pick=4, n_ref=150):
    z = np.load(ROOT / "results" / "atlas.npz")
    N, labR = z["n"], z["labR"]
    chroma = np.hypot(labR[:, 1], labR[:, 2])
    refs = np.argsort(-chroma)[:n_ref]           # saturated colours make a convincing demo
    best = None
    for r in refs:
        cand = np.where(np.linalg.norm(labR - labR[r], axis=1) < 6)[0]
        if len(cand) < n_pick:
            continue
        dE = np.array([col.delta_e00(labR[r], labR[j]) for j in cand])
        cand = cand[dE < 2.0]
        if len(cand) < n_pick:
            continue
        envs = {j: _voice_env(N[j])[3] for j in cand[:40]}
        keys = list(envs)
        # greedy max-min selection of envelope diversity (RMS dB distance)
        dist = lambda i, j: float(np.sqrt(np.mean((envs[i] - envs[j]) ** 2)))
        sel = [r] if r in envs else [keys[0]]
        while len(sel) < n_pick:
            rest = [k for k in keys if k not in sel
                    and all(col.delta_e00(labR[k], labR[s_]) < 2.0 for s_ in sel)]
            if not rest:
                break
            sel.append(max(rest, key=lambda k: min(dist(k, s) for s in sel)))
        if len(sel) < n_pick:
            continue
        score = min(dist(i, j) for i in sel for j in sel if i < j)
        if best is None or score > best[0]:
            best = (score, sel)
    score, sel = best
    labs = labR[sel]
    items = []
    for i, j in enumerate(sel):
        n = N[j]
        d = mp.goupillaud_d(n[1:-1])
        a, g, fe, edb = _voice_env(n)
        Rf, _ = film.film_rt(n, d, col.WL)
        XR = col.spectrum_to_xyz(Rf, "D65")
        F, _ = lpc.formants_from_poly(a)
        fn = f"metamer_{i}.wav"
        synth.write_wav(AUD / fn, synth.film_voice(n, d))
        items.append(dict(atlas_index=int(j), n=L(n, 3), d_nm=L(d, 1), LabR=L(labs[i], 2),
                          dE_to_first=float(col.delta_e00(labs[0], labs[i])), hex=hexcol(XR),
                          F=L(F[:3], 0), env_f=L(fe, 1), env_db=L(edb, 2), audio="video/audio/" + fn))
    pair = [float(col.delta_e00(labs[i], labs[k])) for i in range(len(sel)) for k in range(i + 1, len(sel))]
    return dict(source="results/atlas.npz (20k random realizable Goupillaud stacks), reflected colour, D65",
                max_pair_dE00=max(pair), min_env_rms_db=score, items=items)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    AUD.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cie = json.loads((WEB / "data" / "cie.json").read_text(encoding="utf-8"))
    vowels = json.loads((WEB / "data" / "vowels.json").read_text(encoding="utf-8"))["items"]
    bfl = json.loads((WEB / "data" / "butterflies.json").read_text(encoding="utf-8"))["items"]
    D = {}

    # ---------------- light: C = E * R (Morpho-like reflectance under D65) ----------------
    wl = np.arange(380.0, 781.0, 2.0)
    wl_cie = np.asarray(cie["wl"])
    def on(wlg, key, src=cie):
        return np.interp(wlg, wl_cie, np.asarray(src[key]))
    E = np.interp(wl, wl_cie, np.asarray(cie["illuminants"]["D65"]))
    morpho = next(b for b in bfl if b["name"].startswith("Morpho"))
    R, _ = film.film_rt(morpho["n"], morpho["d_nm"], wl)
    Rfull, _ = film.film_rt(morpho["n"], morpho["d_nm"], col.WL)
    XR = col.spectrum_to_xyz(Rfull, "D65")
    D["light"] = dict(wl=L(wl, 1), E=L(E / E.max(), 4), R=L(R, 4), C=L(E * R / (E * R).max(), 4),
                      xbar=L(on(wl, "xbar"), 4), ybar=L(on(wl, "ybar"), 4), zbar=L(on(wl, "zbar"), 4),
                      XYZ=L(XR, 3), hex=hexcol(XR), name=morpho["name"], label=morpho["label"])

    # ---------------- sound: source-filter for men /ah/ ----------------
    v_ah = next(v for v in vowels if v["group"] == "men" and v["vowel"] == "ah")
    a = np.asarray(v_ah["a"]); g = v_ah["gain"]
    f0 = 120.0
    src = synth.glottal_source(f0, dur=1.0)
    spec = np.abs(np.fft.rfft(src * np.hanning(len(src))))
    fr = np.fft.rfftfreq(len(src), 1 / mp.FS)
    f0 = mp.FS / round(mp.FS / f0)       # actual pitch of the integer-period source
    harm = np.arange(1, int(5000 // f0) + 1) * f0
    # peak magnitude within +-f0/4 of each harmonic (robust to window / bin offset)
    sdb = 20 * np.log10(np.array([spec[(fr > h - f0 / 4) & (fr < h + f0 / 4)].max() for h in harm]) + 1e-12)
    sdb -= sdb.max()
    fe, edb = lpc.envelope_db(a, g, nfft=1024)
    edb_h = np.interp(harm, fe, edb)
    edb_n = edb - edb.max()
    out_db = sdb + (edb_h - edb.max())
    Fv, Bv = lpc.formants_from_poly(a)
    D["sound"] = dict(f0=f0, harm=L(harm, 1), src_db=L(sdb, 2), env_f=L(fe[fe <= 5000], 1),
                      env_db=L(edb_n[fe <= 5000], 2), out_db=L(out_db, 2), formants=L(Fv[:3], 1),
                      vowel="ah", example=v_ah["example"], F0=v_ah["F0"])
    y = synth._fade(synth._norm(src[: int(0.9 * mp.FS)]), mp.FS)
    synth.write_wav(AUD / "glottal_buzz.wav", 0.5 * y)

    # ---------------- tube / film of the same vowel ----------------
    m = np.asarray(v_ah["m"]); n_id = np.asarray(v_ah["n_ideal"]); n_re = np.asarray(v_ah["n_real"])
    c = mp.reflection_from_media(m)
    D["tract"] = dict(m=L(m), areas=L(v_ah["areas"]), n_ideal=L(n_id), n_real=L(n_re),
                      d_ideal=L(mp.goupillaud_d(n_id[1:-1]), 3), d_real=L(mp.goupillaud_d(n_re[1:-1]), 3),
                      c=L(c), D_OPT_NM=mp.D_OPT_NM, hexT=v_ah["colours"]["D65"]["T"],
                      hexT_real=v_ah["colours_real"]["D65"]["T"])

    # ---------------- Levinson / layer peeling ----------------
    k = lpc.step_down(a)                 # k_m, m = 1..16
    areas_lev = lpc.reflection_to_areas(k, A1=1.0)
    # step-down sequence of polynomial orders (each row a^(m))
    polys = []
    am = a.copy()
    for mm in range(len(k), 0, -1):
        polys.append(L(am, 4))
        km = am[mm]
        am = (am[:mm] - km * am[mm:0:-1]) / (1 - km ** 2)
    D["levinson"] = dict(k=L(k), c=L(-k), areas=L(areas_lev),
                         check_max_err=float(np.max(np.abs(areas_lev - m[1:]))))

    # ---------------- frequency mapping + isomorphism ----------------
    nu = np.linspace(mp.NU_MIN, mp.NU_MAX, 1401)[:-1]
    fnu = mp.f_of_nu(nu)
    folded = np.minimum(fnu, mp.FS - fnu)
    d_id = mp.goupillaud_d(n_id[1:-1])
    _, Tfilm = film.film_rt_nu(n_id, d_id, nu)
    Ptube = tube.tube_power_transfer(m, folded)
    P_poly = mp.power_transfer(c, mp.omega_of_nu(nu))
    F12 = Fv[:2]
    imgs = [L(mp.nu_images(f) / 1e12, 3) for f in F12]
    # colour band (spectral colours of the visible frequencies, for the axis strip)
    band_nu = np.linspace(mp.NU_MIN, mp.NU_MAX, 141)
    band = []
    for nn in band_nu:
        lam = mp.C_LIGHT / nn * 1e9
        S = np.exp(-0.5 * ((col.WL - lam) / 4.0) ** 2)
        band.append(col.to_hex(col.display_rgb(col.spectrum_to_xyz(S, "D65"))))
    D["mapping"] = dict(nu_thz=L(nu / 1e12, 3), f=L(fnu, 1), folded=L(folded, 1), T_film=L(Tfilm, 6),
                        P_tube=L(Ptube, 6), max_abs_diff=float(np.max(np.abs(Tfilm - Ptube))),
                        max_abs_diff_poly=float(np.max(np.abs(Tfilm - P_poly))),
                        F12=L(F12, 1), F12_images_thz=imgs, band_thz=L(band_nu / 1e12, 2), band_hex=band,
                        f_at_400=float(mp.f_of_nu(400e12)))

    # ---------------- vowel colours (straight from vowels.json) ----------------
    vc = []
    for v in vowels:
        vc.append(dict(group=v["group"], vowel=v["vowel"], ipa=v["ipa"], example=v["example"],
                       F1=round(v["F1"]), F2=round(v["F2"]), T=v["colours"]["D65"]["T"],
                       T_real=v["colours_real"]["D65"]["T"], Y_T=v["colours"]["D65"]["Y_T"],
                       Y_T_real=v["colours_real"]["D65"]["Y_T"], audio=v["audio"]))
    D["vowels"] = vc

    # ---------------- butterflies ----------------
    bo = []
    for b in bfl:
        fe_b, edb_b = lpc.envelope_db(np.asarray(b["a"]), b["gain"], nfft=1024)
        Rb, _ = film.film_rt(b["n"], b["d_nm"], wl)
        bo.append(dict(name=b["name"], label=b["label"], source=b["source"], n=L(b["n"], 3), d_nm=L(b["d_nm"], 1),
                       lut_angles=b["lut"]["angles"], lut_rgb=b["lut"]["rgb"], env_f=L(fe_b, 1),
                       env_db=L(edb_b - edb_b.max(), 2), R=L(Rb, 4), F=b["F"], audio=b["audio"]))
    D["butterflies"] = bo

    # ---------------- metamers: same colour, different voices ----------------
    # Search the 20k-stack atlas (random realizable Goupillaud stacks, results/atlas.npz) for a cluster of
    # stacks whose REFLECTED colour (D65) agrees within dE00 < 2 but whose voices differ the most.
    t1 = time.time()
    D["metamers"] = atlas_metamers()
    print(f"atlas metamers in {time.time() - t1:.1f}s")
    mets = D["metamers"]["items"]

    # ---------------- outro: a film "sings" /a/ -> /i/ -> /u/ ----------------
    seq = [next(v for v in vowels if v["group"] == "women" and v["vowel"] == w) for w in ("ah", "iy", "uw")]
    y = synth.sing([np.asarray(v["a"]) for v in seq], [0.6, 0.6, 0.7], f0=210.0)
    synth.write_wav(AUD / "outro_sing.wav", synth._fade(synth._norm(y), mp.FS))
    D["outro"] = dict(seq=[v["vowel"] for v in seq], hex=[v["colours"]["D65"]["T"] for v in seq],
                      hex_real=[v["colours_real"]["D65"]["T"] for v in seq])

    D["constants"] = dict(FS=mp.FS, ORDER=mp.ORDER, DNU=mp.DNU, NU_MIN=mp.NU_MIN, NU_MAX=mp.NU_MAX,
                          D_OPT_NM=mp.D_OPT_NM, R_GLOTTIS=mp.R_GLOTTIS)
    (OUT / "scene_data.json").write_text(json.dumps(D), encoding="utf-8")
    print(f"wrote scene_data.json in {time.time() - t0:.1f}s; iso max|T-P| = {D['mapping']['max_abs_diff']:.2e},"
          f" poly {D['mapping']['max_abs_diff_poly']:.2e}; F12={D['mapping']['F12']} -> {imgs}")
    for i, mt in enumerate(mets):
        print(f"  metamer {i}: dE={mt['dE_to_first']:.2f} F={mt['F']} hex={mt['hex']}")


if __name__ == "__main__":
    main()
