"""(2) Vowel palette: 12 vowels x men/women/children under D65, A, F11, LED; T and R; tube silhouettes;
pairwise dE00 per group; the 'speech lives where the eye barely sees' numbers."""
from __future__ import annotations

import itertools

import numpy as np
from matplotlib.patches import Rectangle

from core import mapping as mp, colour as col, film
from research.common import (plt, savefig, vowel_table, gd, lab_eq, film_xyz, GROUPS, GROUP_COLOURS, OI, rnd)

ILLS = ("D65", "A", "F11", "LED")


def _hue(lab):
    return float(np.degrees(np.arctan2(lab[2], lab[1])) % 360)


def pairwise(labs):
    return np.array([[col.delta_e00(a, b) for b in labs] for a in labs])


def run():
    S = {}
    V = vowel_table()
    sw = {}  # (group, vowel, mode, ill, q) -> hex
    labs = {}  # (mode, eq) -> list aligned with V (D65, T)
    for mode, key in (("ideal", "n_ideal"), ("realizable", "n_real")):
        for eq in (True, False):
            labs[(mode, eq)] = []
        for v in V:
            n = v[key]; d = gd(n)
            R, T = film.film_rt(n, d, col.WL)
            for ill in ILLS:
                for q, Sp in (("T", T), ("R", R)):
                    X = col.spectrum_to_xyz(Sp, ill)
                    sw[(v["group"], v["vowel"], mode, ill, q)] = col.display_rgb(X)
            X = col.spectrum_to_xyz(T, "D65")
            labs[(mode, True)].append(lab_eq(X))
            labs[(mode, False)].append(col.xyz_to_lab(X))
            v.setdefault("_Y", {})[mode] = float(X[1])
            v.setdefault("_xy", {})[mode] = X[:2] / X.sum()

    # ---- pairwise dE00 per group
    mats = {}
    S["dE00_pairs"] = {}
    for mode in ("ideal", "realizable"):
        for eq in (True, False):
            for g in GROUPS:
                idx = [i for i, v in enumerate(V) if v["group"] == g]
                M = pairwise([labs[(mode, eq)][i] for i in idx])
                mats[(mode, eq, g)] = M
                tri = M[np.triu_indices(len(idx), 1)]
                iu = np.triu_indices(len(idx), 1)
                kmin = int(np.argmin(tri))
                closest = (V[idx[iu[0][kmin]]]["ipa"], V[idx[iu[1][kmin]]]["ipa"])
                S["dE00_pairs"][f"{mode}_{'eqY' if eq else 'raw'}_{g}"] = dict(
                    median=rnd(np.median(tri), 2), min=rnd(tri.min(), 2), max=rnd(tri.max(), 2),
                    frac_below_2=rnd(np.mean(tri < 2), 3), closest_pair="/" + "/–/".join(closest) + "/")

    # ---- violet numbers
    hues = np.array([_hue(l) for l in labs[("ideal", True)]])
    hues_r = np.array([_hue(l) for l in labs[("realizable", True)]])
    S["hue_ideal_deg"] = dict(min=rnd(hues.min(), 1), max=rnd(hues.max(), 1), median=rnd(np.median(hues), 1))
    S["hue_realizable_deg"] = dict(min=rnd(hues_r.min(), 1), max=rnd(hues_r.max(), 1), median=rnd(np.median(hues_r), 1))
    C_id = np.array([np.hypot(l[1], l[2]) for l in labs[("ideal", False)]])
    S["chroma_ideal_raw"] = dict(min=rnd(C_id.min(), 2), max=rnd(C_id.max(), 2))
    Y_id = np.array([v["_Y"]["ideal"] for v in V]); Y_re = np.array([v["_Y"]["realizable"] for v in V])
    S["Y_T_ideal"] = dict(min=rnd(Y_id.min(), 3), max=rnd(Y_id.max(), 3), median=rnd(np.median(Y_id), 3))
    S["Y_T_realizable"] = dict(min=rnd(Y_re.min(), 2), max=rnd(Y_re.max(), 2), median=rnd(np.median(Y_re), 2))
    S["L_raw_ideal"] = dict(min=rnd(min(l[0] for l in labs[("ideal", False)]), 2),
                            max=rnd(max(l[0] for l in labs[("ideal", False)]), 2))
    xy = np.array([v["_xy"]["ideal"] for v in V])
    S["xy_ideal"] = dict(x_min=rnd(xy[:, 0].min()), x_max=rnd(xy[:, 0].max()), y_min=rnd(xy[:, 1].min()),
                         y_max=rnd(xy[:, 1].max()))

    def ybar_at_images(f):
        nus = mp.nu_images(f)
        lam = 299792458.0 / nus * 1e9
        return lam, np.interp(lam, col.WL, col.CMF[:, 1])

    yb1, yb2, lam1 = [], [], []
    for v in V:
        l1, y1 = ybar_at_images(v["F1"]); _, y2 = ybar_at_images(v["F2"])
        yb1.append(y1.max()); yb2.append(y2.max()); lam1.extend(l1)
    S["F1_image_wavelength_nm"] = dict(min=rnd(min(lam1), 1), max=rnd(max(lam1), 1))
    S["ybar_at_F1_images"] = dict(median=rnd(np.median(yb1), 4), max=rnd(np.max(yb1), 4))
    S["ybar_at_F2_images"] = dict(median=rnd(np.median(yb2), 4), max=rnd(np.max(yb2), 4))
    # share of D65 luminance (Y) carried by the part of the visible band that maps to 0-4 kHz
    nu_wl = 299792458.0 / (col.WL * 1e-9)
    f = mp.f_of_nu(nu_wl)
    band = (np.minimum(f, mp.FS - f) <= 4000) & (nu_wl >= mp.NU_MIN) & (nu_wl < mp.NU_MAX)
    w = col.ILLUMINANTS["D65"] * col.CMF[:, 1]
    S["speech_0_4kHz_share_of_band_THz"] = 175.0
    S["speech_0_4kHz_share_of_D65_luminance"] = rnd(w[band].sum() / w.sum(), 4)
    band2 = (np.minimum(f, mp.FS - f) <= 1000) & (nu_wl >= mp.NU_MIN) & (nu_wl < mp.NU_MAX)
    S["speech_0_1kHz_share_of_D65_luminance"] = rnd(w[band2].sum() / w.sum(), 5)
    S["cross_check_contract_7b"] = "CONTRACT 7b (equal-luminance median dE00): ideal 4.3/5.7/7.7, realizable 3.6/3.8/6.5"

    # ---- figure 2a/b/c: palettes with tube silhouettes
    cols = [("ideal", ill, q) for ill in ILLS for q in ("T", "R")] + [("realizable", "D65", "T"), ("realizable", "D65", "R")]
    for g in GROUPS:
        vs = [v for v in V if v["group"] == g]
        amax = max(v["m"][1:-1].max() for v in vs)
        fig, ax = plt.subplots(figsize=(8.6, 6.6))
        ax.set_xlim(-1.6, 3.1 + len(cols) * 0.62 + 0.4)
        ax.set_ylim(len(vs) + 0.1, -0.9)
        ax.axis("off")
        for i, v in enumerate(vs):
            ax.text(-1.55, i + 0.45, f"/{v['ipa']}/  {v['example']}", fontsize=8, va="center")
            A = v["m"][1:-1]
            rad = 0.42 * np.sqrt(A / amax)
            xs = np.linspace(0, 2.6, len(A) + 1)
            xx = np.repeat(xs, 2)[1:-1]
            rr = np.repeat(rad, 2)
            ax.fill_between(xx, i + 0.45 - rr, i + 0.45 + rr, color=OI["blue"], alpha=0.75, lw=0)
            for j, (mode, ill, q) in enumerate(cols):
                x0 = 3.0 + j * 0.62 + (0.25 if mode == "realizable" else 0)
                ax.add_patch(Rectangle((x0, i + 0.05), 0.56, 0.8, color=sw[(g, v["vowel"], mode, ill, q)]))
        for j, (mode, ill, q) in enumerate(cols):
            x0 = 3.0 + j * 0.62 + (0.25 if mode == "realizable" else 0)
            ax.text(x0 + 0.28, -0.12, f"{ill}\n{q}", ha="center", va="bottom", fontsize=7)
        ax.text(3.0 + 4 * 0.62, -0.75, "ideal mode", ha="center", fontsize=8, weight="bold")
        ax.text(3.25 + 9 * 0.62, -0.75, "realizable", ha="center", fontsize=8, weight="bold")
        ax.text(1.3, -0.3, "tube: glottis → lips\n(radius ∝ √area)", ha="center", fontsize=7)
        ax.set_title(f"Vowel palette — {g} (Hillenbrand 1995 means); swatches use the labelled exposure "
                     "normalisation (Y→50)", fontsize=9)
        savefig(fig, f"2_palette_{g}")

    # ---- figure 2d: dE00 matrices (ideal, equal luminance, D65 T)
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.9))
    vmax = max(mats[("ideal", True, g)].max() for g in GROUPS)
    for ax, g in zip(axs, GROUPS):
        M = mats[("ideal", True, g)]
        im = ax.imshow(M, cmap="viridis", vmin=0, vmax=vmax)
        ipas = [v["ipa"] for v in V if v["group"] == g]
        ax.set_xticks(range(12)); ax.set_xticklabels(ipas, fontsize=7)
        ax.set_yticks(range(12)); ax.set_yticklabels(ipas, fontsize=7)
        ax.grid(False)
        for a_ in range(12):
            for b_ in range(12):
                if a_ != b_:
                    ax.text(b_, a_, f"{M[a_, b_]:.0f}", ha="center", va="center", fontsize=5,
                            color="white" if M[a_, b_] < 0.55 * vmax else "black")
        med = S["dE00_pairs"][f"ideal_eqY_{g}"]["median"]
        ax.set_title(f"{g}: median ΔE00 = {med}")
    fig.colorbar(im, ax=axs, shrink=0.8, label="ΔE00 (D65, transmittance, equal luminance)")
    savefig(fig, "2_dE00_matrices")

    # ---- figure 2e: chromaticity diagram
    fig, ax = plt.subplots(figsize=(5.6, 5.4))
    cmf = col.CMF[(col.WL >= 380) & (col.WL <= 700)]
    wl = col.WL[(col.WL >= 380) & (col.WL <= 700)]
    lx = cmf[:, 0] / cmf.sum(1); ly = cmf[:, 1] / cmf.sum(1)
    ax.plot(np.append(lx, lx[0]), np.append(ly, ly[0]), color="0.3", lw=1)
    for L_ in (420, 450, 470, 490, 510, 540, 580, 620):
        k = np.argmin(np.abs(wl - L_))
        ax.annotate(f"{L_}", (lx[k], ly[k]), fontsize=6, color="0.35", xytext=(-14 if L_ < 500 else 3, 0),
                    textcoords="offset points")
    Wd = col.white_xyz("D65"); ax.plot(*(Wd[:2] / Wd.sum()), "k+", ms=9, label="D65 white")
    for g in GROUPS:
        sel = [v for v in V if v["group"] == g]
        p = np.array([v["_xy"]["ideal"] for v in sel]); q = np.array([v["_xy"]["realizable"] for v in sel])
        ax.scatter(p[:, 0], p[:, 1], s=18, color=GROUP_COLOURS[g], label=f"{g} — ideal", zorder=3)
        ax.scatter(q[:, 0], q[:, 1], s=18, facecolor="none", edgecolor=GROUP_COLOURS[g], label=f"{g} — realizable", zorder=3)
    ax.set_xlabel("CIE x"); ax.set_ylabel("CIE y")
    ax.set_title("All 36 vowel films (D65, transmittance) sit on the violet side")
    ax.legend(fontsize=7, loc="upper right")
    ax.set_xlim(0, 0.75); ax.set_ylim(0, 0.85)
    savefig(fig, "2_chromaticity")
    return S
