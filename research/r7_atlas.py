"""(7) Atlas of 20 000 random realizable Goupillaud stacks (results/atlas.npz, built by tools/build_all.py):
colour space coloured by voice, voice space coloured by colour; Hillenbrand means marked."""
from __future__ import annotations

import numpy as np
from matplotlib.colors import LogNorm, to_rgb
from scipy.stats import spearmanr

from core import colour as col, mapping as mp
from research.common import (plt, savefig, RES, vowel_table, gd, film_xyz, vowel_chart_axes, hill_points,
                             median_neighbour_vowel_distance, OI, rnd)


def run():
    S = {}
    A = np.load(RES / "atlas.npz")
    arm, L, F = A["arm"], A["labT"], A["F12"]
    ok = np.isfinite(F).all(1)
    hue = np.degrees(np.arctan2(L[:, 2], L[:, 1])) % 360
    C = np.hypot(L[:, 1], L[:, 2])
    S["n_stacks"] = int(len(arm))
    S["arms"] = {"0": "log-uniform n in [1, 2.5]", "1": "bimodal: each layer low (1.0-1.25) or high (2.1-2.5)"}
    S["frac_ge2_formants"] = {str(k): rnd(ok[arm == k].mean(), 4) for k in (0, 1)}
    S["frac_ge2_formants_all"] = rnd(ok.mean(), 4)
    S["contract_7b_claim"] = "39% (log-uniform) / 74% (bimodal)"
    S["frac_hue_270_330"] = {str(k): rnd(np.mean((hue[arm == k] >= 270) & (hue[arm == k] < 330)), 4) for k in (0, 1)}
    S["frac_hue_270_330_all"] = rnd(np.mean((hue >= 270) & (hue < 330)), 4)
    S["chroma_median"] = {str(k): rnd(np.median(C[arm == k]), 1) for k in (0, 1)}
    S["L_median"] = {str(k): rnd(np.median(L[arm == k, 0]), 1) for k in (0, 1)}
    S["F1_median_Hz"] = {str(k): rnd(np.nanmedian(F[arm == k, 0]), 0) for k in (0, 1)}
    S["F2_median_Hz"] = {str(k): rnd(np.nanmedian(F[arm == k, 1]), 0) for k in (0, 1)}
    P36, V = hill_points()
    lnF = np.log(F[ok])
    dmin = np.min(np.hypot(lnF[:, :1] - P36[None, :, 0], lnF[:, 1:2] - P36[None, :, 1]), axis=1)
    nnd = median_neighbour_vowel_distance()
    S["frac_within_neighbour_distance_of_a_vowel_mean"] = rnd(np.mean(dmin < nnd), 4)
    S["n_within_neighbour_distance_of_a_vowel_mean"] = int(np.sum(dmin < nnd))
    rho = {}
    for name, x in (("L*", L[ok, 0]), ("a*", L[ok, 1]), ("b*", L[ok, 2]), ("C*", C[ok])):
        rho[name] = dict(F1=rnd(spearmanr(x, F[ok, 0])[0], 3), F2=rnd(spearmanr(x, F[ok, 1])[0], 3))
    S["spearman_colour_vs_formant"] = rho
    S["spearman_abs_max"] = rnd(max(abs(v) for d_ in rho.values() for v in d_.values()), 3)
    # why purple: T at omega=0 (700 THz, 428 nm, all layers 'absentee') vs omega=pi (525 THz, 571 nm)
    T0, Tpi = [], []
    for n in A["n"]:
        c = mp.reflection_from_media(n)
        P = mp.power_transfer(c, np.array([0.0, np.pi]))
        T0.append(P[0]); Tpi.append(P[1])
    T0, Tpi = np.array(T0), np.array(Tpi)
    S["T_at_700THz_median"] = rnd(np.median(T0), 3)
    S["T_at_525THz_median"] = rnd(np.median(Tpi), 3)
    S["frac_T700_gt_T525"] = rnd(np.mean(T0 > Tpi), 4)

    # realizable vowel films for reference in colour space
    VL = np.array([col.xyz_to_lab(film_xyz(v["n_real"], gd(v["n_real"]))) for v in vowel_table()])

    fig, axs = plt.subplots(1, 3, figsize=(13.5, 4.4), gridspec_kw=dict(width_ratios=[1.1, 1.1, 0.8]))
    ax = axs[0]
    ax.scatter(L[~ok, 1], L[~ok, 2], s=1.5, color="0.8", rasterized=True, label="< 2 formants (bw < 600 Hz)")
    sc = ax.scatter(L[ok, 1], L[ok, 2], s=1.5, c=F[ok, 0], cmap="viridis", norm=LogNorm(300, 7000), rasterized=True)
    ax.scatter(VL[:, 1], VL[:, 2], s=22, marker="x", color=OI["vermillion"], label="36 realizable vowel films", zorder=5)
    fig.colorbar(sc, ax=ax, label="F1 of the stack's voice (Hz)", shrink=0.85)
    ax.set_xlabel("a* (D65, transmittance)"); ax.set_ylabel("b*")
    ax.set_title("Colour space, coloured by voice (F1)"); ax.legend(fontsize=6, loc="lower left", markerscale=3)
    ax = axs[1]
    rgb = np.array([to_rgb(h) for h in A["rgbT"][ok]])
    ax.scatter(F[ok, 1], F[ok, 0], s=1.5, c=rgb, rasterized=True)
    vowel_chart_axes(ax, alpha=1.0, fs=6)
    ax.set_xlim(8000, 600); ax.set_ylim(8000, 200)
    ax.set_title("Voice space (first two formants), coloured by display colour")
    ax = axs[2]
    bins = np.arange(0, 361, 10)
    for k, colr, lab in ((0, OI["blue"], "log-uniform arm"), (1, OI["orange"], "bimodal arm")):
        ax.hist(hue[arm == k], bins, histtype="step", lw=1.5, color=colr, label=lab)
    ax.set_yscale("log"); ax.set_xlabel("CIELAB hue angle h_ab (deg)"); ax.set_ylabel("stacks")
    ax.set_title("Hue distribution (10 000 per arm)"); ax.legend(fontsize=7)
    fig.tight_layout()
    savefig(fig, "7_atlas")
    return S
