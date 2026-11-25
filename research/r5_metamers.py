"""(5) METAMERS both ways.
 (a) same colour (dE00 < 2, D65 transmittance), different voices: atlas pairs + core.inverse.design_stacks.
 (b) same voice, different colour: atlas pairs with |dF1|,|dF2| < 5 %, and exact_films_for_polynomial families
     (identical polynomial => identical voice) compared at normal and oblique incidence.
Bulk dE00 screening uses colour-science's vectorised CIEDE2000 (validated against core.colour.delta_e00);
quoted example pairs are recomputed with core.colour.delta_e00."""
from __future__ import annotations

import json

import numpy as np
from matplotlib.patches import Rectangle
from scipy.spatial import cKDTree
import colour as cs

from core import lpc, mapping as mp, film, colour as col, inverse, synth
from research.common import (plt, savefig, write_audio, silence, RES, OI, SERIES, rnd, vowel, gd, lab_eq,
                             film_xyz, env_formants, nearest_vowel, vowel_extent, vowel_chart_axes,
                             median_neighbour_vowel_distance)

CACHE_PAIRS = RES / "cache_atlas_pairs.npz"
CACHE_DESIGN = RES / "cache_design_stacks.json"
R_SCREEN = (16.0, 20.0)


def de00_vec(L1, L2):
    return np.asarray(cs.difference.delta_E_CIE2000(L1, L2), float)


def ln_dist(Fa, Fb):
    return np.hypot(*(np.log(Fa) - np.log(Fb)).T)


def pct(x, q):
    return rnd(np.percentile(x, q), 3)


def dist_stats(x, nd=3):
    x = np.asarray(x, float)
    return dict(n=int(len(x)), p10=rnd(np.percentile(x, 10), nd), median=rnd(np.median(x), nd),
                p90=rnd(np.percentile(x, 90), nd), max=rnd(np.max(x), nd))


BOX = dict(F1=(250.0, 1100.0), F2=(700.0, 3500.0))   # roughly the Hillenbrand F1/F2 ranges


def in_box(FF):
    FF = np.atleast_2d(FF)
    return ((FF[:, 0] >= BOX["F1"][0]) & (FF[:, 0] <= BOX["F1"][1]) & (FF[:, 1] >= BOX["F2"][0])
            & (FF[:, 1] <= BOX["F2"][1]))


def low(FF):
    """'Low-formant' voices: F1 <= 1.5 kHz and F2 <= 4 kHz (looser than the vowel box; see report)."""
    FF = np.atleast_2d(FF)
    return (FF[:, 0] <= 1500.0) & (FF[:, 1] <= 4000.0)


def voice(n):
    return synth.film_voice(n, gd(n), dur=0.8)


def run(fresh=False):
    S = {}
    ext = vowel_extent(); nnd = median_neighbour_vowel_distance()
    S["vowel_extent_ln"] = rnd(ext, 3); S["median_neighbour_vowel_distance_ln"] = rnd(nnd, 3)
    A = np.load(RES / "atlas.npz")
    ok = np.isfinite(A["F12"]).all(1)
    idx = np.flatnonzero(ok)
    L, F = A["labT"][ok], A["F12"][ok]
    S["atlas_stacks_with_F1F2"] = int(ok.sum())
    S["atlas_stacks_in_vowel_box"] = int(in_box(F).sum())
    S["atlas_stacks_low_formant"] = int(low(F).sum())
    S["atlas_F1_percentiles_Hz"] = dict(p5=rnd(np.percentile(F[:, 0], 5), 0), median=rnd(np.median(F[:, 0]), 0),
                                        p95=rnd(np.percentile(F[:, 0], 95), 0))

    # ------------------------------------------------ (a) atlas: same colour, different voices
    if CACHE_PAIRS.exists() and not fresh:
        z = np.load(CACHE_PAIRS)
        P, dE, counts, P_v, dE_v, val_err = z["P"], z["dE"], z["counts"], z["P_v"], z["dE_v"], float(z["val_err"])
    else:
        tree = cKDTree(L)
        counts = []
        for rad in R_SCREEN:
            cand = tree.query_pairs(rad, output_type="ndarray")
            d_ = de00_vec(L[cand[:, 0]], L[cand[:, 1]])
            counts.append(int((d_ < 2).sum()))
        P, dE = cand[d_ < 2], d_[d_ < 2]
        rng = np.random.default_rng(5)
        pick = cand[rng.choice(len(cand), 300, replace=False)]
        val_err = max(abs(col.delta_e00(L[i], L[j]) - de00_vec(L[i], L[j])) for i, j in pick)
        # same voice: |dF1|,|dF2| < 5 % (relative to the smaller value)
        cand = cKDTree(np.log(F)).query_pairs(np.sqrt(2) * np.log(1.05) + 1e-9, output_type="ndarray")
        rel = np.abs(F[cand[:, 0]] - F[cand[:, 1]]) / np.minimum(F[cand[:, 0]], F[cand[:, 1]])
        P_v = cand[(rel < 0.05).all(1)]
        dE_v = de00_vec(L[P_v[:, 0]], L[P_v[:, 1]])
        np.savez_compressed(CACHE_PAIRS, P=P, dE=dE, counts=np.array(counts), P_v=P_v, dE_v=dE_v, val_err=val_err)
    S["colour_science_vs_core_dE00_max_abs_diff_300_pairs"] = float(val_err)
    import time as _t
    _t0 = _t.perf_counter()
    for q in range(100):
        col.delta_e00(L[q], L[q + 1])
    _timing_ms = rnd(  # not stored: timings would make tracked results non-reproducible
(_t.perf_counter() - _t0) * 10, 2)
    S["screen_radius_dE76"] = list(R_SCREEN)
    S["metamer_pair_counts_at_radii"] = [int(c) for c in counts]
    dl = ln_dist(F[P[:, 0]], F[P[:, 1]])
    Cm = 0.5 * (np.hypot(*L[P[:, 0], 1:].T) + np.hypot(*L[P[:, 1], 1:].T))
    dF = np.abs(F[P[:, 0]] - F[P[:, 1]])
    S["atlas_metamers"] = dict(
        n_pairs=int(len(P)), frac_pairs_chroma_ge_20=rnd(np.mean(Cm >= 20), 3),
        dF1_Hz=dist_stats(dF[:, 0], 0), dF2_Hz=dist_stats(dF[:, 1], 0), dist_ln=dist_stats(dl),
        frac_dist_gt_neighbour_vowel=rnd(np.mean(dl > nnd), 3),
        chroma_lt_20=dict(n=int((Cm < 20).sum()), dist_ln=dist_stats(dl[Cm < 20]),
                          frac_dist_gt_neighbour_vowel=rnd(np.mean(dl[Cm < 20] > nnd), 3)),
        chroma_ge_20=dict(n=int((Cm >= 20).sum()), dist_ln=dist_stats(dl[Cm >= 20]),
                          dF1_Hz=dist_stats(dF[Cm >= 20, 0], 0), dF2_Hz=dist_stats(dF[Cm >= 20, 1], 0),
                          frac_dist_gt_neighbour_vowel=rnd(np.mean(dl[Cm >= 20] > nnd), 3)))
    vb = low(F[P[:, 0]]) & low(F[P[:, 1]])
    S["atlas_metamers"]["both_low_formant"] = dict(
        n=int(vb.sum()), dist_ln=dist_stats(dl[vb]), dF1_Hz=dist_stats(dF[vb, 0], 0),
        dF2_Hz=dist_stats(dF[vb, 1], 0), frac_dist_gt_neighbour_vowel=rnd(np.mean(dl[vb] > nnd), 3))
    # example: chromatic metamer pair, both voices low-formant, with the most different voices
    ch = np.flatnonzero((Cm >= 20) & vb)
    k = ch[np.argmax(dl[ch])]
    i, j = P[k]
    ni, nj = A["n"][idx[i]], A["n"][idx[j]]
    ex_a = dict(atlas_index=[int(idx[i]), int(idx[j])], dE00_core=rnd(col.delta_e00(L[i], L[j]), 3),
                Lab=[rnd(L[i], 2), rnd(L[j], 2)], F1F2=[rnd(F[i], 0), rnd(F[j], 0)], dist_ln=rnd(dl[k], 3),
                hex=[str(A["rgbT"][idx[i]]), str(A["rgbT"][idx[j]])],
                nearest_vowels=[f"/{nearest_vowel(*F[i])[0]['ipa']}/", f"/{nearest_vowel(*F[j])[0]['ipa']}/"])
    ex_a["audio"] = write_audio("metamer_pair_atlas.wav", np.concatenate([voice(ni), silence(0.3), voice(nj)]))
    S["atlas_metamer_example"] = ex_a

    # ------------------------------------------------ (a) inverse design for 3 target colours
    tgt = {}
    va = vowel("men", "ah")
    tgt["A: realizable men /ɑ/ film"] = col.xyz_to_lab(film_xyz(va["n_real"], gd(va["n_real"])))
    Lall = A["labT"]
    hue = np.degrees(np.arctan2(Lall[:, 2], Lall[:, 1])) % 360
    C = np.hypot(Lall[:, 1], Lall[:, 2])
    # atlas transmittance colours are ~all violet/purple or near-neutral (see r7), so targets come from there
    for name, (h0, h1), q in (("B: atlas saturated purple", (300, 330), 75), ("C: atlas pale warm white", (30, 90), 75)):
        sel = np.flatnonzero((hue >= h0) & (hue < h1) & (A["arm"] == 0))
        cq = np.percentile(C[sel], q)
        tgt[name] = Lall[sel[np.argmin(np.abs(C[sel] - cq))]]
    design = json.loads(CACHE_DESIGN.read_text(encoding="utf-8")) if CACHE_DESIGN.exists() and not fresh else {}
    if sorted(design) != sorted(tgt) or any(not np.allclose(design[k]["target"], tgt[k]) for k in tgt):
        design = {}
        for t, (name, lab) in enumerate(tgt.items()):
            sols = inverse.design_stacks(lab, n_solutions=8, restarts=40, seed=100 + t)
            design[name] = dict(target=list(map(float, lab)),
                                sols=[dict(n=list(map(float, s["n"])), dE=float(s["dE"])) for s in sols])
        CACHE_DESIGN.write_text(json.dumps(design), encoding="utf-8")
    S["design"] = {}
    design_pts = {}
    for t, (name, D) in enumerate(design.items()):
        rows = []
        for s in D["sols"]:
            n = np.array(s["n"])
            Fp, _ = inverse.stack_formants(n)
            a = mp.poly_from_reflection(mp.reflection_from_media(n))
            rule = "poles"
            if len(Fp) < 2:
                Fp, _ = env_formants(a, fmax=5500.0, min_prom=0.3); rule = "envelope"
            X = film_xyz(n, gd(n))
            rows.append(dict(n=n, F=Fp[:2] if len(Fp) >= 2 else None, rule=rule,
                             dE=col.delta_e00(col.xyz_to_lab(X), np.array(D["target"])), hex=col.to_hex(col.display_rgb(X))))
        good = [r_ for r_ in rows if r_["F"] is not None]
        FF = np.array([r_["F"] for r_ in good])
        FP = np.array([r_["F"] for r_ in good if r_["rule"] == "poles"])
        pair = [ln_dist(FF[a_], FF[b_]) for a_ in range(len(FF)) for b_ in range(a_ + 1, len(FF))]
        S["design"][name] = dict(
            target_Lab=rnd(D["target"], 2), n_solutions=len(rows), n_with_F1F2=len(good),
            n_envelope_rule=int(sum(r_["rule"] == "envelope" for r_ in rows)),
            dE00_to_target_max=float(max(r_["dE"] for r_ in rows)),
            n_flat_voice=int(sum(r_["F"] is None for r_ in rows)),
            F1_range_Hz=[rnd(FF[:, 0].min(), 0), rnd(FF[:, 0].max(), 0)],
            F2_range_Hz=[rnd(FF[:, 1].min(), 0), rnd(FF[:, 1].max(), 0)],
            max_pair_dist_ln=rnd(max(pair), 3), median_pair_dist_ln=rnd(np.median(pair), 3),
            max_pair_dist_frac_extent=rnd(max(pair) / ext, 3),
            nearest_vowels=sorted({f"/{nearest_vowel(*f)[0]['ipa']}/" for f in FF}),
            n_vowel_like=int(in_box(FF).sum()),
            poles_only_F1_range_Hz=[rnd(FP[:, 0].min(), 0), rnd(FP[:, 0].max(), 0)] if len(FP) >= 2 else None,
            poles_only_F2_range_Hz=[rnd(FP[:, 1].min(), 0), rnd(FP[:, 1].max(), 0)] if len(FP) >= 2 else None)
        design_pts[name] = (rows, FF)
        tag = "ABC"[t]
        S["design"][name]["audio"] = write_audio(
            f"metamer_set_{tag}.wav",
            np.concatenate(sum([[voice(r_["n"]), silence(0.25)] for r_ in rows], [])))
    # individual voices for set A (for the web page)
    for q, r_ in enumerate(design_pts[list(design)[0]][0]):
        write_audio(f"metamer_A_{q + 1}.wav", voice(r_["n"]))

    # ------------------------------------------------ (b) atlas: same voice, different colour
    dlv = ln_dist(F[P_v[:, 0]], F[P_v[:, 1]])
    S["atlas_same_voice"] = dict(n_pairs=int(len(P_v)), dE00=dist_stats(dE_v, 2),
                                 frac_dE00_gt_10=rnd(np.mean(dE_v > 10), 3), frac_dE00_lt_2=rnd(np.mean(dE_v < 2), 4),
                                 note="F1 and F2 within 5 % only (F3.. and bandwidths free): weaker than identical polynomials")
    vbv = low(F[P_v[:, 0]]) & low(F[P_v[:, 1]])
    S["atlas_same_voice"]["both_low_formant"] = dict(n=int(vbv.sum()), dE00=dist_stats(dE_v[vbv], 2),
                                                    frac_dE00_gt_10=rnd(np.mean(dE_v[vbv] > 10), 3))
    cand_k = np.flatnonzero(vbv)
    k = int(cand_k[np.argmax(dE_v[cand_k])])
    i, j = P_v[k]
    ex_b = dict(atlas_index=[int(idx[i]), int(idx[j])], dE00_core=rnd(col.delta_e00(L[i], L[j]), 2),
                Lab=[rnd(L[i], 2), rnd(L[j], 2)], F1F2=[rnd(F[i], 0), rnd(F[j], 0)],
                hex=[str(A["rgbT"][idx[i]]), str(A["rgbT"][idx[j]])])
    ex_b["audio"] = write_audio("same_voice_pair_atlas.wav",
                                np.concatenate([voice(A["n"][idx[i]]), silence(0.3), voice(A["n"][idx[j]])]))
    S["atlas_same_voice_example"] = ex_b

    # ------------------------------------------------ (b) exact families: identical polynomial
    # source polynomial: a bimodal-arm atlas stack with >=3 sharp formants, closest to a Hillenbrand mean
    P36 = np.array([[np.log(v_["F1"]), np.log(v_["F2"])] for v_ in __import__("research.common", fromlist=["vowel_table"]).vowel_table()])
    dmin = np.min(np.hypot(np.log(F[:, :1]) - P36[None, :, 0], np.log(F[:, 1:2]) - P36[None, :, 1]), axis=1)
    src = None
    for q in np.argsort(dmin):
        if A["arm"][idx[q]] != 1:
            continue
        n0 = A["n"][idx[q]]
        if len(inverse.stack_formants(n0)[0]) >= 3:
            src = int(q); break
    n0 = A["n"][idx[src]]
    a0 = mp.poly_from_reflection(mp.reflection_from_media(n0))
    fam = [dict(name="original atlas stack", n=n0, K=None, flips=None)]
    tried = 0
    for K in (0.9, 0.5, 0.2):
        kept = 0
        for fl in [None] + [[q, q + 1] for q in range(len(a0) - 2)]:
            if kept >= 3:
                break
            tried += 1
            m = inverse.exact_films_for_polynomial(a0, K, flips=fl)
            if m is None:
                continue
            D = mp.poly_from_reflection(mp.reflection_from_media(m))
            if np.abs(D - a0).max() > 1e-8:      # non-conjugate flips do not preserve |G| -> rejected
                continue
            nrev = m[::-1] / m[-1]     # reversed (reciprocity) so that the incident medium is air (n=1)
            if any(np.allclose(nrev, f_["n"], rtol=1e-3) for f_ in fam):
                continue
            fam.append(dict(name=f"K={K}" + (f", zero-flip {fl}" if fl else ""), n=nrev, m=m, K=K, flips=fl))
            kept += 1
    # checks
    nu = np.linspace(mp.NU_MIN, mp.NU_MAX, 1401)
    rev_err, coef_err, shape_err = 0.0, 0.0, 0.0
    T0 = film.film_rt_nu(n0, gd(n0), nu)[1]
    for f_ in fam[1:]:
        Tm = film.film_rt_nu(f_["m"], gd(f_["m"]), nu)[1]
        Tr = film.film_rt_nu(f_["n"], gd(f_["n"]), nu)[1]
        rev_err = max(rev_err, np.abs(Tm - Tr).max())
        ratio = Tr / T0
        shape_err = max(shape_err, (ratio.max() - ratio.min()) / ratio.mean())
        av, _ = film.voice_of_film(f_["n"], gd(f_["n"]), n_freq=4096)
        coef_err = max(coef_err, np.abs(av - a0).max())
    ANG = (0, 30, 45, 60)
    for f_ in fam:
        f_["X"] = {th: film_xyz(f_["n"], gd(f_["n"]), theta=th) for th in ANG}
        f_["hex"] = {th: col.to_hex(col.display_rgb(f_["X"][th])) for th in ANG}
        f_["F_obl"] = {}
        for th in ANG:
            av, gv = film.voice_of_film(f_["n"], gd(f_["n"]), theta_deg=th)
            Fe, _ = env_formants(av, gv, min_prom=0.3)
            f_["F_obl"][th] = Fe[:2] if len(Fe) >= 2 else np.array([np.nan, np.nan])
    fam_stats = {}
    for th in ANG:
        labs_eq = [lab_eq(f_["X"][th]) for f_ in fam]
        labs_raw = [col.xyz_to_lab(f_["X"][th]) for f_ in fam]
        pe = [col.delta_e00(labs_eq[p], labs_eq[q]) for p in range(len(fam)) for q in range(p + 1, len(fam))]
        pr = [col.delta_e00(labs_raw[p], labs_raw[q]) for p in range(len(fam)) for q in range(p + 1, len(fam))]
        xy = np.array([f_["X"][th][:2] / f_["X"][th].sum() for f_ in fam])
        FF = np.array([f_["F_obl"][th] for f_ in fam])
        fam_stats[str(th)] = dict(dE00_eqY_median=rnd(np.median(pe), 3), dE00_eqY_max=rnd(np.max(pe), 3),
                                  dE00_raw_median=rnd(np.median(pr), 2), dE00_raw_max=rnd(np.max(pr), 2),
                                  xy_spread=rnd(np.max(np.ptp(xy, 0)), 5),
                                  Y_range=[rnd(min(f_["X"][th][1] for f_ in fam), 2), rnd(max(f_["X"][th][1] for f_ in fam), 2)],
                                  F1_range_Hz=[rnd(np.nanmin(FF[:, 0]), 0), rnd(np.nanmax(FF[:, 0]), 0)],
                                  F2_range_Hz=[rnd(np.nanmin(FF[:, 1]), 0), rnd(np.nanmax(FF[:, 1]), 0)])
    Fsrc, Bsrc = inverse.stack_formants(n0)
    S["exact_family"] = dict(
        source_atlas_index=int(idx[src]), source_formants_Hz=rnd(Fsrc[:4], 0), source_bandwidths_Hz=rnd(Bsrc[:4], 0),
        source_nearest_vowel=f"/{nearest_vowel(Fsrc[0], Fsrc[1])[0]['ipa']}/ ({nearest_vowel(Fsrc[0], Fsrc[1])[0]['group']})",
        n_members=len(fam), members=[f_["name"] for f_ in fam], exact_calls_tried=tried,
        index_range=[rnd(min(f_["n"].min() for f_ in fam), 3), rnd(max(f_["n"].max() for f_ in fam), 3)],
        reversal_T_max_abs_diff=float(rev_err), T_shape_max_rel_ratio_spread=float(shape_err),
        voice_coef_max_abs_diff=float(coef_err), by_angle_deg=fam_stats,
        orientation="exact films reversed (reciprocity) and scaled so the incident medium is air (n=1)")
    S["exact_family"]["audio"] = write_audio(
        "same_voice_family.wav", np.concatenate(sum([[voice(f_["n"]), silence(0.25)] for f_ in fam[:4]], [])))

    # ------------------------------------------------ figures
    fig, axs = plt.subplots(1, 3, figsize=(12.5, 4.0))
    ax = axs[0]
    bins = np.linspace(0, max(dl.max(), 1.5), 50)
    ax.hist(dl[Cm >= 20], bins, color=OI["blue"], alpha=0.6, label=f"C* ≥ 20 ({(Cm >= 20).sum():,} pairs)")
    ax.hist(dl[Cm < 20], bins, color=OI["orange"], histtype="step", lw=1.6, label=f"C* < 20 ({(Cm < 20).sum():,} pairs)")
    ax.axvline(nnd, color=OI["vermillion"], ls="--", lw=1.2, label="median distance to nearest\nneighbouring vowel")
    ax.set_yscale("log"); ax.set_xlabel("voice distance in (ln F1, ln F2)"); ax.set_ylabel("metamer pairs (ΔE00 < 2)")
    ax.set_title("Atlas: same colour, how different the voices?"); ax.legend(fontsize=7)
    ax = axs[1]
    vowel_chart_axes(ax, groups=("men",), alpha=0.5)
    marks = ["o", "s", "D"]
    for (name, (rows, FF)), mk, ec in zip(design_pts.items(), marks, (OI["black"], OI["vermillion"], OI["blue"])):
        tl = np.array(design[name]["target"])
        ax.scatter(FF[:, 1], FF[:, 0], s=55, marker=mk, color=[r_["hex"] for r_ in rows if r_["F"] is not None],
                   edgecolor=ec, linewidth=1.2, zorder=6, label=name)
    ax.set_xlim(9000, 600); ax.set_ylim(7000, 200)
    ax.set_title("Designed metamers: 3 target colours × 8 stacks")
    ax.legend(fontsize=6, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1)
    ax = axs[2]
    bins = np.linspace(0, dE_v.max(), 50)
    ax.hist(dE_v, bins, color=OI["green"], alpha=0.85)
    ax.axvline(2, color=OI["vermillion"], ls="--", lw=1.2, label="ΔE00 = 2")
    ax.set_yscale("log"); ax.set_xlabel("ΔE00 (D65, transmittance)"); ax.set_ylabel("pairs with |ΔF1|,|ΔF2| < 5 %")
    ax.set_title("Atlas: same voice, how different the colours?"); ax.legend(fontsize=7)
    fig.tight_layout()
    savefig(fig, "5_metamers_spread")

    # exact family figure
    fig = plt.figure(figsize=(12.5, 5.2))
    gs = fig.add_gridspec(2, 3, width_ratios=[1.0, 1.0, 1.1])
    ax = fig.add_subplot(gs[:, 0])
    show = fam[:7]
    for f_, colr in zip(show, SERIES):
        ax.step(np.arange(len(f_["n"])), f_["n"], where="mid", color=colr, lw=1.2, label=f_["name"])
    ax.set_yscale("log"); ax.set_xlabel("medium index (0 = incident air … 17 = substrate)"); ax.set_ylabel("refractive index n")
    ax.set_title("Same polynomial D(z), different films"); ax.legend(fontsize=6)
    ax = fig.add_subplot(gs[:, 1])
    ax.axis("off"); ax.set_xlim(0, 6.0); ax.set_ylim(len(show) + 0.2, -1.0)
    for q, f_ in enumerate(show):
        ax.text(0.0, q + 0.45, f_["name"].replace(", zero-flip", "\nzero-flip"), fontsize=6.5, va="center")
        for t_, th in enumerate(ANG):
            ax.add_patch(Rectangle((2.5 + t_ * 0.9 - 0.4, q + 0.08), 0.8, 0.75, color=f_["hex"][th]))
            ax.text(2.5 + t_ * 0.9, q + 0.47, f"Y={f_['X'][th][1]:.0f}", fontsize=5.5, ha="center", va="center", color="black")
    for t_, th in enumerate(ANG):
        ax.text(2.5 + t_ * 0.9, -0.2, f"{th}°", ha="center", fontsize=8)
    ax.set_title("Displayed colour (exposure-normalised) vs angle", fontsize=9)
    wl = col.WL
    for row, th in enumerate((0, 60)):
        ax = fig.add_subplot(gs[row, 2])
        for f_, colr in zip(show, SERIES):
            _, T = film.film_rt(f_["n"], gd(f_["n"]), wl, th)
            ax.plot(wl, T / T.max(), color=colr, lw=1.0)
        ax.set_xlim(380, 780); ax.set_ylabel("T / max T")
        ax.set_title(f"normalised transmittance, {th}°" + (" (all curves coincide)" if th == 0 else ""), fontsize=9)
        if row == 1:
            ax.set_xlabel("wavelength (nm)")
    fig.tight_layout()
    savefig(fig, "5_exact_family")
    return S
