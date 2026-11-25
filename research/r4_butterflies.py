"""(4) Butterfly-like stacks (core.stacks; APPROXIMATE / ILLUSTRATIVE parameters) -> reflectance colour,
voice_of_film formants (secondary rule: LPC-envelope peaks), nearest Hillenbrand vowel in (ln F1, ln F2), audio."""
from __future__ import annotations

import numpy as np
from matplotlib.patches import Rectangle

from core import lpc, mapping as mp, film, colour as col, stacks, synth
from research.common import (plt, savefig, write_audio, env_formants, poles, nearest_vowel, vowel_extent,
                             median_neighbour_vowel_distance, vowel_chart_axes, film_T_on_f, lsd, F_GRID,
                             OI, SERIES, rnd)


def butterfly_set():
    out = []
    for scale, tag in ((1.0, ""), (0.9, " (lamellae ×0.9)"), (1.1, " (lamellae ×1.1)")):
        s = stacks.morpho_like(d_chitin=stacks.MORPHO_D_CHITIN * scale, d_air=stacks.MORPHO_D_AIR * scale)
        s["name"] = "Morpho-like" + tag; s["key"] = "morpho" + ("" if scale == 1 else f"_x{scale:.1f}".replace(".", "p"))
        out.append(s)
    for scale, tag in ((1.0, ""), (0.9, " (layers ×0.9)"), (1.1, " (layers ×1.1)")):
        s = stacks.beetle_like(d1=95.0 * scale, d2=75.0 * scale)
        s["name"] = "Beetle-like" + tag; s["key"] = "beetle" + ("" if scale == 1 else f"_x{scale:.1f}".replace(".", "p"))
        out.append(s)
    return out


def run():
    S = {"label": "all stack parameters approximate/illustrative (core/stacks.py); 1-D lossless, non-dispersive",
         "items": []}
    ext = vowel_extent(); nn = median_neighbour_vowel_distance()
    S["morpho_layer_optical_thickness_nm"] = rnd(sorted({float(x) for x in np.round(stacks.morpho_like()["n"][1:-1] * stacks.morpho_like()["d_nm"], 1)}), 1)
    S["D_OPT_nm"] = rnd(mp.D_OPT_NM, 1)
    S["vowel_extent_ln"] = rnd(ext, 3); S["median_neighbour_vowel_distance_ln"] = rnd(nn, 3)
    B = butterfly_set()
    rec = []
    for s in B:
        n, d = s["n"], s["d_nm"]
        R, T = film.film_rt(n, d, col.WL)
        XR, XT = col.spectrum_to_xyz(R), col.spectrum_to_xyz(T)
        a, g = film.voice_of_film(n, d)
        F, P = env_formants(a, g)
        Fp, Bp = poles(a)
        fit = lsd(film_T_on_f(n, d), (g ** 2) * np.abs(1 / np.fft.rfft(a, 1024))[:513] ** 2)
        item = dict(name=s["name"], label=s["label"], layers=int(len(d)), R_peak_nm=rnd(col.WL[np.argmax(R)], 1),
                    R_peak=rnd(R.max(), 3), hex_R=col.to_hex(col.display_rgb(XR)), Y_R=rnd(XR[1], 2),
                    Lab_R=rnd(col.xyz_to_lab(XR), 2), hex_T=col.to_hex(col.display_rgb(XT)),
                    env_peaks_Hz=rnd(F[:4], 0), env_prominence_dB=rnd(P[:4], 2),
                    min_pole_bandwidth_Hz=rnd(Bp.min() if len(Bp) else np.nan, 0),
                    allpole_fit_lsd_dB=rnd(fit, 2))
        if len(F) >= 2:
            v, dist = nearest_vowel(F[0], F[1])
            item.update(F1=rnd(F[0], 0), F2=rnd(F[1], 0), nearest_vowel=f"/{v['ipa']}/ ({v['example']}, {v['group']})",
                        nearest_vowel_F1F2=[rnd(v["F1"], 0), rnd(v["F2"], 0)], dist_ln=rnd(dist, 3),
                        dist_frac_extent=rnd(dist / ext, 3), weak_peaks=bool(np.min(P[:2]) < 3.0))
        y = synth.film_voice(n, d)
        item["audio"] = write_audio(f"bfly_{s['key']}.wav", y)
        S["items"].append(item)
        rec.append((s, R, a, g, F, P, XR))

    lsds = [it["allpole_fit_lsd_dB"] for it in S["items"]]
    S["allpole_fit_lsd_min"], S["allpole_fit_lsd_max"] = min(lsds), max(lsds)
    f_pk = mp.f_of_nu(299792458.0 / (S["items"][0]["R_peak_nm"] * 1e-9))
    S["morpho_R_peak_speech_freq_Hz"] = rnd(min(f_pk, mp.FS - f_pk), 0)

    # ---- figure
    fig = plt.figure(figsize=(12, 4.4))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.1, 1.1, 1.0])
    ax = fig.add_subplot(gs[0])
    for q, ((s, R, *_), colr, ls) in enumerate(zip(rec, SERIES, ["-", "--", ":", "-", "--", ":"])):
        ax.plot(col.WL, R, color=colr, lw=1.2, ls=ls, label=f"{q + 1}  {s['name']}")
    ax.set_xlim(380, 780); ax.set_xlabel("wavelength (nm)"); ax.set_ylabel("reflectance R (normal incidence)")
    ax.set_title("Butterfly-/beetle-like stacks (illustrative)"); ax.legend(fontsize=6, loc="upper right")
    for i, (s, R, a, g, F, P, XR) in enumerate(rec):
        ax.add_patch(Rectangle((385 + i * 22, 1.02), 20, 0.07, color=col.display_rgb(XR), clip_on=False,
                               transform=ax.transData))
        ax.text(395 + i * 22, 1.055, str(i + 1), ha="center", va="center", fontsize=6)
    ax.set_ylim(0, 1.1)
    ax = fig.add_subplot(gs[1])
    for (s, R, a, g, F, P, XR), colr in zip(rec, SERIES):
        f, e = lpc.envelope_db(a, g, nfft=2048)
        ax.plot(f, e, color=colr, lw=1.1, label=s["name"])
        if len(F):
            ax.plot(F[:4], np.interp(F[:4], f, e), "v", color=colr, ms=4)
    ax.set_xlim(0, 6000); ax.set_xlabel("speech frequency (Hz)"); ax.set_ylabel("voice envelope 20log10(g/|A|) (dB)")
    ax.set_title("Their voices (voice_of_film, order 16); ▼ = envelope peaks")
    ax = fig.add_subplot(gs[2])
    vowel_chart_axes(ax, alpha=0.6)
    for (s, R, a, g, F, P, XR), colr, it in zip(rec, SERIES, S["items"]):
        if "F1" in it:
            ax.scatter(it["F2"], it["F1"], s=70, marker="*", color=col.display_rgb(XR), edgecolor=colr, linewidth=1.4, zorder=5)
            ax.plot([it["F2"], it["nearest_vowel_F1F2"][1]], [it["F1"], it["nearest_vowel_F1F2"][0]], color=colr, lw=0.8, ls=":")
    ax.set_title("Where they sit on the vowel chart (★ fill = R colour)")
    fig.tight_layout()
    savefig(fig, "4_butterflies")
    return S
