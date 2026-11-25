"""(1) Isomorphism verification + frequency mapping figure."""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

from core import mapping as mp, film, tube, colour as col
from research.common import (plt, savefig, vowel, vowel_table, gd, db, OI, rnd)


def run():
    S = {}
    v = vowel("men", "ah")
    m, n = v["m"], v["n_ideal"]
    d = gd(n)
    nu = np.linspace(mp.NU_MIN, mp.NU_MAX, 3501)[:-1]
    _, T_film = film.film_rt_nu(n, d, nu)                       # Abelès, optics units
    P_tube = tube.tube_power_transfer(m, mp.f_of_nu(nu))        # acoustic ABCD, physical units
    c = mp.reflection_from_media(m)
    P_poly = mp.power_transfer(c, 2 * np.pi * mp.f_of_nu(nu) / mp.FS)  # polynomial prod(1-c^2)/|D|^2
    e_fp = np.abs(T_film - P_poly)
    e_tp = np.abs(P_tube - P_poly)
    S["example"] = "men /ɑ/ (hod), ideal mode, finite glottis R_GLOTTIS=-0.9"
    S["example_max_abs_film_minus_poly"] = float(e_fp.max())
    S["example_max_abs_tube_minus_poly"] = float(e_tp.max())
    S["example_max_rel_film_minus_poly"] = float((e_fp / P_poly).max())
    S["example_T_peak"] = rnd(T_film.max(), 4)

    # all 36 vowels (ideal films) and 200 random media
    worst_f, worst_t, worst_rel = 0.0, 0.0, 0.0
    for w in vowel_table():
        nn = w["n_ideal"]
        _, T = film.film_rt_nu(nn, gd(nn), nu[::5])
        P = mp.power_transfer(mp.reflection_from_media(w["m"]), 2 * np.pi * mp.f_of_nu(nu[::5]) / mp.FS)
        Pt = tube.tube_power_transfer(w["m"], mp.f_of_nu(nu[::5]))
        worst_f = max(worst_f, np.abs(T - P).max())
        worst_t = max(worst_t, np.abs(Pt - P).max())
        worst_rel = max(worst_rel, (np.abs(T - P) / P).max())
    rng = np.random.default_rng(101)
    worst_rand = 0.0
    for _ in range(200):
        mm = np.exp(rng.uniform(-1.5, 1.5, mp.ORDER + 2))
        nn = mp.film_from_media(mm, "ideal")
        _, T = film.film_rt_nu(nn, gd(nn), nu[::7])
        P = mp.power_transfer(mp.reflection_from_media(mm), 2 * np.pi * mp.f_of_nu(nu[::7]) / mp.FS)
        Pt = tube.tube_power_transfer(mm, mp.f_of_nu(nu[::7]))
        worst_rand = max(worst_rand, np.abs(T - P).max(), np.abs(Pt - P).max())
    S["all36_max_abs_film_minus_poly"] = float(worst_f)
    S["all36_max_abs_tube_minus_poly"] = float(worst_t)
    S["all36_max_rel_film_minus_poly"] = float(worst_rel)
    S["random200_max_abs"] = float(worst_rand)
    # 4th independent route: time-domain Kelly-Lochbaum lattice vs prod(1+c)/D(z) impulse response
    h_kl = tube.kl_impulse_response(c, 256)
    imp = np.zeros(256); imp[0] = 1.0
    h_poly = lfilter([np.prod(1 + c)], mp.poly_from_reflection(c), imp)
    S["kl_lattice_max_abs_vs_poly"] = float(np.abs(h_kl - h_poly).max())

    # ---- figure 1a: overlay + residual
    THz = nu / 1e12
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 5.6), sharex=True, gridspec_kw=dict(height_ratios=[2, 1.2]))
    a1.plot(THz, db(T_film), color=OI["blue"], lw=2.6, label="film $T(\\nu)$, Abelès matrices (optics)")
    a1.plot(THz, db(P_tube), color=OI["orange"], lw=1.4, ls="--", label="tube power transfer, acoustic ABCD chain")
    a1.plot(THz, db(P_poly), color=OI["black"], lw=0.8, ls=":", label="polynomial $\\prod(1-c_i^2)/|D(e^{j\\omega})|^2$")
    a1.set_ylabel("transmitted power (dB)")
    a1.set_title("Isomorphism check: men /ɑ/ as an ideal 16-layer Goupillaud film (finite glottis)")
    a1.legend(loc="lower left")
    for x in (525, 700):
        a1.axvline(x, color=OI["grey"], lw=0.8, ls="-.")
    sec = a1.secondary_xaxis("top", functions=(lambda t: 299792.458 / np.maximum(t, 1), lambda l: 299792.458 / np.maximum(l, 1)))
    sec.set_xlabel("wavelength (nm)")
    a2.semilogy(THz, np.maximum(e_fp, 1e-18), color=OI["blue"], lw=0.9, label="|film − polynomial|")
    a2.semilogy(THz, np.maximum(e_tp, 1e-18), color=OI["orange"], lw=0.9, label="|tube − polynomial|")
    a2.set_ylim(1e-19, 1e-10)
    a2.set_xlabel("optical frequency ν (THz)")
    a2.set_ylabel("absolute residual")
    a2.legend(loc="upper right", ncol=2)
    savefig(fig, "1_isomorphism")

    # ---- figure 1b: frequency mapping
    nu2 = np.linspace(mp.NU_MIN, mp.NU_MAX, 7001)[:-1]
    f = mp.f_of_nu(nu2)
    fold = np.minimum(f, mp.FS - f)
    lam = 299792458.0 / nu2 * 1e9
    ybar = np.interp(lam, col.WL, col.CMF[:, 1])
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(nu2 / 1e12, f / 1e3, color=OI["blue"], lw=1.6, label="$f(\\nu)=F_s\\,\\mathrm{frac}(\\nu/\\Delta\\nu)$")
    ax.plot(nu2 / 1e12, fold / 1e3, color=OI["vermillion"], lw=1.2, ls="--",
            label="effective speech frequency min(f, Fs−f)")
    F1 = np.array([w["F1"] for w in vowel_table()]); F2 = np.array([w["F2"] for w in vowel_table()])
    for (lo, hi), lab, colr in (((F1.min(), F1.max()), "where Hillenbrand F1 lands", OI["green"]),
                                ((F2.min(), F2.max()), "where Hillenbrand F2 lands", OI["orange"])):
        ax.fill_between(nu2 / 1e12, 0, 16.5, where=(fold >= lo) & (fold <= hi), color=colr, alpha=0.3,
                        lw=0, label=lab)
    for x, t in ((525, "mirror (8 kHz)"), (700, "mirror (0 Hz)")):
        ax.axvline(x, color=OI["grey"], lw=0.8, ls="-.")
        ax.text(x - 3, 16.6, t, fontsize=7, color="0.3", ha="right", va="bottom")
    ax.set_xlabel("optical frequency ν (THz)")
    ax.set_ylabel("tube (speech) frequency (kHz)")
    ax.set_ylim(0, 16.5)
    ax2 = ax.twinx()
    ax2.plot(nu2 / 1e12, ybar, color=OI["black"], lw=1.0, label="eye sensitivity $\\bar y(\\lambda)$")
    ax2.set_ylabel("CIE 1931 $\\bar y$ (relative)")
    ax2.set_ylim(0, 1.05)
    ax2.grid(False)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, -0.17), fontsize=7, ncol=3)
    ax.set_title("Frequency mapping: one 2π period of the tube response spans 400–750 THz", pad=14)
    savefig(fig, "1_frequency_mapping")
    S["nu_of_0Hz_THz"] = 700.0
    S["nu_of_8kHz_THz"] = 525.0
    S["f_at_400THz_Hz"] = rnd(mp.f_of_nu(400e12), 1)
    S["D_OPT_nm"] = rnd(mp.D_OPT_NM, 4)
    return S
