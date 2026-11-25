"""(8) Choosing the mapping. The isomorphism is exact for ANY common optical thickness d_opt (period
dnu = c / (2 d_opt)); the brief fixes d_opt = 428.27 nm. Here: sweep d_opt for how well the DISPLAYED colours
separate the vowels, and compare the brief mapping with the full-band mapping (d_opt = 199.86 nm, f = 0 at
750 THz, visible = 0-7.47 kHz exactly once) on every Hillenbrand token (real speaker-to-speaker variation)."""
from __future__ import annotations

import itertools

import numpy as np

from core import mapping as mp, colour as col, film, vowels, lpc
from core.synth import glottal_source, synth_allpole
from research.common import plt, savefig, vowel_table, GROUPS, OI, RES, rnd

M_INV = np.linalg.inv(col.M_XYZ_TO_SRGB)
VIEWS = (("ideal", "T"), ("realizable", "R"), ("realizable", "T"))
D_SWEEP = np.round(np.concatenate([np.arange(150, 300, 5.0), np.arange(300, 801, 10.0)]), 2)
D_SWEEP = np.unique(np.concatenate([D_SWEEP, [round(mp.D_OPT_FULL_NM, 2), round(mp.D_OPT_NM, 2)]]))


def shown_lab(X):
    """Lab of what the page actually shows: display_rgb (Y -> 50, scaled into gamut, negatives clipped)."""
    rgb = col.display_rgb(X)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return col.xyz_to_lab(M_INV @ lin * 100)


def view_xyz(m, d_opt, mode, q):
    n = mp.film_from_media(m, mode)
    R, T = film.film_rt(n, mp.goupillaud_d(n[1:-1], d_opt), col.WL)
    return col.spectrum_to_xyz(T if q == "T" else R)


def group_median_de(media_by_group, d_opt, mode, q):
    out = []
    for g in GROUPS:
        labs = [shown_lab(view_xyz(m, d_opt, mode, q)) for m in media_by_group[g]]
        out.append(np.median([col.delta_e00(a, b) for a, b in itertools.combinations(labs, 2)]))
    return out


def token_media():
    toks = [t for t in vowels.load_tokens()
            if min(t["f0"], t["F1"], t["F2"], t["F3"]) > 0 and t["vowel"] in vowels.VOWELS]
    media = []
    for t in toks:
        a = lpc.poly_from_formants([t["F1"], t["F2"], t["F3"]], vowels.BANDWIDTHS, mp.FS)
        y = synth_allpole(a, glottal_source(t["f0"], mp.FS, 0.5), 1.0)
        mid = len(y) // 2
        media.append(mp.vowel_media(lpc.lpc(y[mid - 256: mid + 256], mp.ORDER)[0]))
    return toks, media


def group_of(s):
    return "men" if s == "m" else "women" if s == "w" else "children"


def token_scores(toks, labs):
    """12-way nearest-centroid accuracy (dE00 on displayed colour) + centroid separation, per group."""
    out = {}
    for g in GROUPS:
        idx = [i for i, t in enumerate(toks) if group_of(t["speaker"]) == g]
        vs = sorted({toks[i]["vowel"] for i in idx})
        cen = {v: np.mean([labs[i] for i in idx if toks[i]["vowel"] == v], 0) for v in vs}
        ok, within = 0, []
        for i in idx:
            dd = {v: col.delta_e00(labs[i], cen[v]) for v in vs}
            ok += min(dd, key=dd.get) == toks[i]["vowel"]
            within.append(dd[toks[i]["vowel"]])
        between = [col.delta_e00(cen[a], cen[b]) for a, b in itertools.combinations(vs, 2)]
        out[g] = dict(n_tokens=len(idx), accuracy=rnd(ok / len(idx), 3), between_median=rnd(np.median(between), 2),
                      between_min=rnd(np.min(between), 2), within_median=rnd(np.median(within), 2))
    return out


def run(fresh=False):
    S = dict(d_opt_brief_nm=rnd(mp.D_OPT_NM, 4), d_opt_full_nm=rnd(mp.D_OPT_FULL_NM, 4),
             dnu_brief_THz=rnd(mp.DNU / 1e12, 1), dnu_full_THz=rnd(mp.DNU_FULL / 1e12, 1))
    fold = lambda nu, dnu: np.minimum(mp.f_of_nu(nu, dnu), mp.FS - mp.f_of_nu(nu, dnu))
    S["full_visible_audio_range_Hz"] = [rnd(fold(mp.NU_MAX - 1e6, mp.DNU_FULL), 1), rnd(fold(mp.NU_MIN, mp.DNU_FULL), 1)]
    # where formant ranges land under each mapping (single image for full-band)
    wl_of = lambda f: mp.C_LIGHT / (mp.DNU_FULL * (1 - f / mp.FS)) * 1e9
    S["full_F1_300_900Hz_nm"] = [rnd(wl_of(300), 1), rnd(wl_of(900), 1)]
    S["full_F2_900_2800Hz_nm"] = [rnd(wl_of(900), 1), rnd(wl_of(2800), 1)]
    S["full_fricative_3_7kHz_nm"] = [rnd(wl_of(3000), 1), rnd(wl_of(7000), 1)]

    V = vowel_table()
    mg = {g: [v["m"] for v in V if v["group"] == g] for g in GROUPS}

    # ---- sweep (group means, displayed colour)
    cache = RES / "cache_r8.npz"
    if cache.exists() and not fresh and np.array_equal(np.load(cache)["d"], D_SWEEP):
        sweep = np.load(cache)["sweep"]
    else:
        sweep = np.array([[group_median_de(mg, d, mo, q) for (mo, q) in VIEWS] for d in D_SWEEP])  # (nd, 3 views, 3 groups)
        np.savez(cache, d=D_SWEEP, sweep=sweep)
    mean_over_groups = sweep.mean(axis=2)
    S["sweep"] = {}
    for j, (mo, q) in enumerate(VIEWS):
        y = mean_over_groups[:, j]
        k = int(np.argmax(y))
        S["sweep"][f"{mo}_{q}"] = dict(best_d_nm=float(D_SWEEP[k]), best_median_dE00=rnd(y[k], 1),
                                       at_brief=rnd(y[np.argmin(abs(D_SWEEP - mp.D_OPT_NM))], 1),
                                       at_full=rnd(y[np.argmin(abs(D_SWEEP - mp.D_OPT_FULL_NM))], 1))

    # ---- every Hillenbrand token, both mappings
    toks, tm = token_media()
    S["n_tokens"] = len(toks)
    S["tokens"] = {}
    for name, d in (("brief", mp.D_OPT_NM), ("full", mp.D_OPT_FULL_NM)):
        for mo, q in VIEWS[:2]:
            labs = [shown_lab(view_xyz(m, d, mo, q)) for m in tm]
            S["tokens"][f"{name}_{mo}_{q}"] = token_scores(toks, labs)
    lf = [np.log([t["F1"], t["F2"], t["F3"]]) for t in toks]
    ceil = {}
    for g in GROUPS:
        idx = [i for i, t in enumerate(toks) if group_of(t["speaker"]) == g]
        vs = sorted({toks[i]["vowel"] for i in idx})
        cen = {v: np.mean([lf[i] for i in idx if toks[i]["vowel"] == v], 0) for v in vs}
        ceil[g] = rnd(np.mean([min(vs, key=lambda v: np.sum((lf[i] - cen[v]) ** 2)) == toks[i]["vowel"]
                               for i in idx]), 3)
    S["formant_ceiling_accuracy"] = ceil

    # hue ranges of the 36 means under the full-band mapping
    for mo, q in VIEWS[:2]:
        hues = []
        for g in GROUPS:
            for m in mg[g]:
                L = shown_lab(view_xyz(m, mp.D_OPT_FULL_NM, mo, q))
                hues.append(np.degrees(np.arctan2(L[2], L[1])) % 360)
        S[f"full_hue_{mo}_{q}_deg"] = dict(min=rnd(min(hues), 0), max=rnd(max(hues), 0), median=rnd(np.median(hues), 0))

    # ---- sensitivity of the full-band colours to the two illustrative modelling choices
    base = {(mo, q): [shown_lab(view_xyz(v["m"], mp.D_OPT_FULL_NM, mo, q)) for v in V] for mo, q in VIEWS[:2]}
    sens = {}
    for label, bw, rg in (("bandwidth_x0.5", 0.5, mp.R_GLOTTIS), ("bandwidth_x2", 2.0, mp.R_GLOTTIS),
                          ("glottis_-0.8", 1.0, -0.8), ("glottis_-0.95", 1.0, -0.95)):
        ms = []
        for v in V:
            a = v["a"] if bw == 1.0 else vowels.vowel_lpc([v["F1"], v["F2"], v["F3"]], v["F0"],
                                                         bandwidths=tuple(b * bw for b in vowels.BANDWIDTHS))[0]
            ms.append(mp.vowel_media(a, rg))
        for mo, q in VIEWS[:2]:
            d = [col.delta_e00(shown_lab(view_xyz(m, mp.D_OPT_FULL_NM, mo, q)), b) for m, b in zip(ms, base[(mo, q)])]
            sens[f"{label}_{mo}_{q}"] = dict(median=rnd(np.median(d), 2), max=rnd(np.max(d), 2))
    S["sensitivity_full"] = sens

    # ---- figure
    fig = plt.figure(figsize=(13, 9.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.15], hspace=0.38, wspace=0.22)
    ax = fig.add_subplot(gs[0, 0])
    for j, ((mo, q), c) in enumerate(zip(VIEWS, (OI["blue"], OI["vermillion"], OI["green"]))):
        ax.plot(D_SWEEP, mean_over_groups[:, j], color=c, lw=1.6, label=f"{mo} film, {'reflected' if q == 'R' else 'transmitted'}")
    for d, lab in ((mp.D_OPT_NM, "brief 428.3 nm"), (mp.D_OPT_FULL_NM, "full-band 199.9 nm")):
        ax.axvline(d, color="0.4", ls="--", lw=1)
        ax.text(d, ax.get_ylim()[1] * 0.97, " " + lab, rotation=90, va="top", fontsize=8, color="0.3")
    ax.set_xlabel("optical thickness of every layer  n·d  [nm]")
    ax.set_ylabel("median ΔE00 between vowels (displayed colour)")
    ax.set_title("(a) Every thickness is exact; some are far more colourful")
    ax.legend(fontsize=8, frameon=False)

    ax = fig.add_subplot(gs[0, 1])
    wl = np.linspace(380, 780, 801)
    nu = mp.C_LIGHT / (wl * 1e-9)
    for dnu, c, lab in ((mp.DNU, OI["blue"], "brief (Δν = 350 THz)"), (mp.DNU_FULL, OI["vermillion"], "full-band (Δν = 750 THz)")):
        ax.plot(wl, fold(nu, dnu) / 1000, color=c, lw=1.8, label=lab)
    ax.axhspan(0.25, 3.0, color=OI["yellow"], alpha=0.25, lw=0)
    ax.text(770, 1.6, "formants", ha="right", fontsize=8)
    ax.set_xlabel("wavelength [nm]"); ax.set_ylabel("audio frequency |f| it shows [kHz]")
    ax.set_title("(b) Which sound frequency each colour of light 'sees'")
    ax.legend(fontsize=8, frameon=False, loc="upper right")

    ax = fig.add_subplot(gs[1, :])
    cols = [("brief", mp.D_OPT_NM, "ideal", "T"), ("brief", mp.D_OPT_NM, "realizable", "R"),
            ("full", mp.D_OPT_FULL_NM, "ideal", "T"), ("full", mp.D_OPT_FULL_NM, "realizable", "R")]
    order = [v for g in GROUPS for v in V if v["group"] == g]
    for j, (name, d, mo, q) in enumerate(cols):
        for i, v in enumerate(order):
            rgb = col.display_rgb(view_xyz(v["m"], d, mo, q))
            ax.add_patch(plt.Rectangle((i, -j), 0.94, 0.9, color=np.clip(rgb, 0, 1)))
        ax.text(-0.4, -j + 0.45, f"{name}: {mo}, {'reflected' if q == 'R' else 'transmitted'}", ha="right", va="center", fontsize=8.5)
    for i, v in enumerate(order):
        ax.text(i + 0.47, 1.05, v["ipa"], ha="center", fontsize=8)
    for k, g in enumerate(GROUPS):
        ax.text(12 * k + 6, 1.45, g, ha="center", fontsize=9, weight="bold")
    ax.set_xlim(-11, 36); ax.set_ylim(-3.2, 1.8); ax.axis("off")
    ax.set_title("(c) The 36 Hillenbrand vowels under both mappings (display-normalised)")
    savefig(fig, "r8_mapping")
    return S


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=float)[:3000])
