"""(3) Ideal vs realizable vs materials, and the effect of the illustrative R_GLOTTIS.

Chain of stages, each compared with the vowel's LPC polynomial a (reference 1/|A|^2):
  ideal film   = Goupillaud film with n ∝ m = vowel_media(a)  (only change: finite glottis R_GLOTTIS)
  realizable   = n compressed into [1, 2.5]                    (film_from_media 'realizable')
  materials    = realizable snapped to the MATERIALS list
Formant matching = nearest pole of the stage polynomial (any bandwidth) to each reference formant."""
from __future__ import annotations

import numpy as np

from core import lpc, mapping as mp, film, colour as col
from research.common import (plt, savefig, vowel_table, vowel, gd, poles, nearest_pole, env_formants,
                             poly_power, lsd, db, F_GRID, lab_eq, film_xyz, OI, rnd)

STAGES = (("ideal", "n_ideal"), ("realizable", "n_real"), ("materials", "n_mat"))
RG = (-0.7, -0.8, -0.9, -0.95, -0.98, -0.99)


def stage_poly(n):
    c = mp.reflection_from_media(n)
    return mp.poly_from_reflection(c), c


def run():
    S = {}
    V = vowel_table()
    rows = {s: dict(npk=[], dF=[], dFpct=[], B=[], lsd_ref=[], lsd_ideal=[], dE_eq=[], dE_raw=[], dHill=[], dHillpct=[])
            for s, _ in STAGES}
    rows["lpc"] = dict(dF=[], dFpct=[], B=[])
    voice_err = 0.0
    nref = []
    for v in V:
        a = v["a"]
        nref.append(len(lpc.formants_from_poly(a)[0]))
        hill = np.array([v["F1"], v["F2"], v["F3"]])
        FBr = np.array([nearest_pole(a, f) for f in hill])   # LPC pole nearest to each Hillenbrand formant
        Fr, Br = FBr[:, 0], FBr[:, 1]
        rows["lpc"]["dF"].append(np.abs(Fr - hill)); rows["lpc"]["dFpct"].append(100 * np.abs(Fr - hill) / hill)
        rows["lpc"]["B"].append(Br)
        P_ref = poly_power(a)
        X_id = film_xyz(v["n_ideal"], gd(v["n_ideal"]))
        P_id = None
        for s, key in STAGES:
            n = v[key]
            D, c = stage_poly(n)
            if s == "realizable":
                av, _ = film.voice_of_film(n, gd(n), n_freq=4096)
                voice_err = max(voice_err, np.abs(av - D).max())
            FB = np.array([nearest_pole(D, f) for f in Fr])
            rows[s]["dF"].append(np.abs(FB[:, 0] - Fr)); rows[s]["dFpct"].append(100 * np.abs(FB[:, 0] - Fr) / Fr)
            rows[s]["dHill"].append(np.abs(FB[:, 0] - hill)); rows[s]["dHillpct"].append(100 * np.abs(FB[:, 0] - hill) / hill)
            rows[s]["B"].append(FB[:, 1])
            Fe, Pe = env_formants(D, fmax=4000.0, min_prom=1.0)
            rows[s]["npk"].append(len(Fe))
            P = poly_power(D, c)
            if s == "ideal":
                P_id = P
            rows[s]["lsd_ref"].append(lsd(P, P_ref)); rows[s]["lsd_ideal"].append(lsd(P, P_id))
            X = film_xyz(n, gd(n))
            rows[s]["dE_eq"].append(col.delta_e00(lab_eq(X), lab_eq(X_id)))
            rows[s]["dE_raw"].append(col.delta_e00(col.xyz_to_lab(X), col.xyz_to_lab(X_id)))
    S["reference_poles_bw_lt_600_count"] = dict(min=int(min(nref)), max=int(max(nref)), n_vowels_lt_3=int(np.sum(np.array(nref) < 3)))
    S["voice_of_film_vs_D_realizable_max_abs_coef"] = float(voice_err)
    S["lpc_vs_hillenbrand"] = dict(
        mean_abs_Hz=rnd(np.mean(rows["lpc"]["dF"], 0), 1), mean_abs_pct=rnd(np.mean(rows["lpc"]["dFpct"], 0), 2),
        mean_B_Hz=rnd(np.mean(rows["lpc"]["B"], 0), 1))
    for s, _ in STAGES:
        R = rows[s]
        S[s] = dict(
            dF_vs_lpc_mean_Hz=rnd(np.mean(R["dF"], 0), 1), dF_vs_lpc_mean_pct=rnd(np.mean(R["dFpct"], 0), 2),
            dF_vs_lpc_max_pct=rnd(np.max(R["dFpct"], 0), 1),
            dF_vs_hill_mean_pct=rnd(np.mean(R["dHillpct"], 0), 2),
            B_mean_Hz=rnd(np.mean(R["B"], 0), 1),
            env_peaks_below_4kHz_prom_ge_1dB=dict(median=rnd(np.median(R["npk"]), 1), min=int(np.min(R["npk"])),
                                                  max=int(np.max(R["npk"]))), B_median_Hz=rnd(np.median(R["B"], 0), 1),
            lsd_vs_lpc_dB=dict(median=rnd(np.median(R["lsd_ref"]), 2), max=rnd(np.max(R["lsd_ref"]), 2)),
            lsd_vs_ideal_dB=dict(median=rnd(np.median(R["lsd_ideal"]), 2), max=rnd(np.max(R["lsd_ideal"]), 2)),
            dE00_vs_ideal_eqY=dict(median=rnd(np.median(R["dE_eq"]), 2), max=rnd(np.max(R["dE_eq"]), 2)),
            dE00_vs_ideal_raw=dict(median=rnd(np.median(R["dE_raw"]), 2), max=rnd(np.max(R["dE_raw"]), 2)))
    # index ranges
    span = np.array([v["n_ideal"].max() for v in V])
    gam = np.log(mp.N_MAX / mp.N_MIN) / np.log(span)
    S["ideal_index_max"] = dict(min=rnd(span.min(), 1), median=rnd(np.median(span), 1), max=rnd(span.max(), 1))
    S["realizable_gamma"] = dict(min=rnd(gam.min(), 3), median=rnd(np.median(gam), 3), max=rnd(gam.max(), 3))
    S["coef_shrink_factor_median"] = rnd(1 / np.median(gam), 1)
    S["materials_distinct_used"] = int(len(np.unique(np.concatenate([v["n_mat"] for v in V]))))

    # ---- figure 3a
    ex = vowel("men", "iy")
    fig, axs = plt.subplots(2, 3, figsize=(11.5, 6.4))
    ax = axs[0, 0]
    Pref = poly_power(ex["a"])
    ax.plot(F_GRID, db(Pref) - db(Pref).mean(), color=OI["black"], lw=2.2, label="LPC 1/|A|² (reference)")
    for (s, key), colr, ls in zip(STAGES, (OI["blue"], OI["orange"], OI["green"]), ("-", "--", "-.")):
        D, c = stage_poly(ex[key])
        P = poly_power(D, c)
        ax.plot(F_GRID, db(P) - db(P).mean(), color=colr, lw=1.3, ls=ls, label=f"{s} film T")
    ax.set_xlabel("speech frequency (Hz)"); ax.set_ylabel("power (dB, mean removed)")
    ax.set_title("men /i/: spectrum through the chain"); ax.legend(fontsize=7)
    labels = ["F1", "F2", "F3"]
    x = np.arange(3); w = 0.26
    ax = axs[0, 1]
    for j, ((s, _), colr) in enumerate(zip(STAGES, (OI["blue"], OI["orange"], OI["green"]))):
        ax.bar(x + (j - 1) * w, np.mean(rows[s]["dFpct"], 0), w, color=colr, label=s)
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_yscale("log")
    ax.set_ylabel("mean |ΔF| vs LPC formant (%)"); ax.set_title("Formant frequency error (36 vowels)"); ax.legend(fontsize=7)
    ax = axs[0, 2]
    ax.bar(x - 1.5 * w, np.mean(rows["lpc"]["B"], 0), w, color=OI["black"], label="LPC reference")
    for j, ((s, _), colr) in enumerate(zip(STAGES, (OI["blue"], OI["orange"], OI["green"]))):
        ax.bar(x + (j - 0.5) * w, np.mean(rows[s]["B"], 0), w, color=colr, label=s)
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_yscale("log")
    ax.set_ylabel("mean bandwidth of matched pole (Hz)"); ax.set_title("Bandwidth (formant sharpness)")
    ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=4)
    ax = axs[1, 0]
    data = [rows[s]["lsd_ref"] for s, _ in STAGES]
    ax.boxplot(data, tick_labels=[s for s, _ in STAGES], widths=0.5)
    ax.set_ylabel("log-spectral distance to 1/|A|² (dB)"); ax.set_title("Spectral shape error")
    ax = axs[1, 1]
    data = [rows[s]["dE_eq"] for s, _ in STAGES[1:]]
    ax.boxplot(data, tick_labels=[s for s, _ in STAGES[1:]], widths=0.5)
    ax.set_ylabel("ΔE00 vs ideal film (equal luminance)"); ax.set_title("Colour change (D65, T)")
    ax = axs[1, 2]
    data = [rows[s]["dE_raw"] for s, _ in STAGES[1:]]
    ax.boxplot(data, tick_labels=[s for s, _ in STAGES[1:]], widths=0.5)
    ax.set_ylabel("ΔE00 vs ideal film (raw, incl. lightness)"); ax.set_title("Colour change incl. brightness")
    fig.tight_layout()
    savefig(fig, "3_fidelity")

    # ---- R_GLOTTIS sweep
    a_chk = ex["a"]
    D_lim = mp.poly_from_reflection(mp.reflection_from_media(mp.vowel_media(a_chk, -0.99999)))
    S["glottis_limit_check_max_abs_D_minus_a_at_rg_-0.99999"] = float(np.abs(D_lim - a_chk).max())
    assert np.abs(D_lim - a_chk).max() < 1e-3
    sw = {rg: dict(dF=[], dB=[], lsd=[]) for rg in RG}
    for v in V:
        a = v["a"]
        FBr = np.array([nearest_pole(a, f) for f in (v["F1"], v["F2"], v["F3"])])
        Fr, Br = FBr[:, 0], FBr[:, 1]
        Pref = poly_power(a)
        for rg in RG:
            m = mp.vowel_media(a, rg)
            c = mp.reflection_from_media(m)
            D = mp.poly_from_reflection(c)
            FB = np.array([nearest_pole(D, f) for f in Fr])
            sw[rg]["dF"].append(FB[:, 0] - Fr); sw[rg]["dB"].append(FB[:, 1] - Br)
            sw[rg]["lsd"].append(lsd(poly_power(D, c), Pref))
    S["glottis_sweep"] = {str(rg): dict(mean_abs_dF_Hz=rnd(np.mean(np.abs(sw[rg]["dF"]), 0), 1),
                                        mean_dF_Hz=rnd(np.mean(sw[rg]["dF"], 0), 1),
                                        mean_dB_Hz=rnd(np.mean(sw[rg]["dB"], 0), 1),
                                        lsd_median_dB=rnd(np.median(sw[rg]["lsd"]), 2)) for rg in RG}
    fig, axs = plt.subplots(1, 3, figsize=(11.5, 3.6))
    ax = axs[0]
    Pref = poly_power(ex["a"])
    ax.plot(F_GRID, db(Pref) - db(Pref).max(), color=OI["black"], lw=2.2, label="1/|A|² (closed glottis)")
    cmap = plt.get_cmap("viridis")
    for i, rg in enumerate(RG):
        c = mp.reflection_from_media(mp.vowel_media(ex["a"], rg)); P = poly_power(mp.poly_from_reflection(c), c)
        ax.plot(F_GRID, db(P) - db(P).max(), color=cmap(i / (len(RG) - 1)), lw=1, label=f"R_g = {rg}")
    ax.set_xlim(0, 4000); ax.set_ylim(-45, 3)
    ax.set_xlabel("speech frequency (Hz)"); ax.set_ylabel("power (dB re peak)"); ax.set_title("men /i/"); ax.legend(fontsize=6)
    xg = 1 + np.array(RG)
    for ax, key, ttl, yl in ((axs[1], "dF", "Formant shift", "mean |ΔF| (Hz)"), (axs[2], "dB", "Bandwidth increase", "mean ΔB (Hz)")):
        for k, (lab, colr) in enumerate(zip(labels, (OI["blue"], OI["orange"], OI["green"]))):
            vals = [np.mean(np.abs(np.array(sw[rg][key])[:, k])) if key == "dF" else np.mean(np.array(sw[rg][key])[:, k]) for rg in RG]
            ax.plot(xg, vals, "o-", color=colr, label=lab)
        ax.axvline(1 + mp.R_GLOTTIS, color=OI["grey"], ls=":", lw=1)
        ax.set_xscale("log"); ax.set_xlabel("1 + R_GLOTTIS (log; dotted = default −0.9)"); ax.set_ylabel(yl)
        ax.set_title(ttl + " vs 1/|A|² (36 vowels)"); ax.legend(fontsize=7)
    fig.tight_layout()
    savefig(fig, "3_glottis_sweep")
    return S
