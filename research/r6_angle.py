"""(6) Angle sweep 0-80 deg: colour strip vs angle and the F1/F2 trajectory of voice_of_film(theta)
('iridescence = diphthong'); audio of the glide via core.synth.sing over the angle sequence of polynomials."""
from __future__ import annotations

import numpy as np

from core import mapping as mp, film, colour as col, stacks, synth
from research.common import (plt, savefig, write_audio, vowel, gd, env_formants, film_xyz, lab_eq,
                             vowel_chart_axes, nearest_vowel, OI, rnd)

ANG = np.arange(0, 81, 2)


def films():
    mo = stacks.morpho_like()
    v = vowel("men", "ah")
    A = np.load(__import__("research.common", fromlist=["RES"]).RES / "atlas.npz")
    n_at = A["n"][6973]          # the /ɛ/-like realizable atlas stack used as exact-family source in r5
    return [dict(key="morpho", name="Morpho-like (R, illustrative)", n=mo["n"], d=mo["d_nm"], q="R", colour=OI["blue"]),
            dict(key="vowel_ah_ideal", name="men /ɑ/ ideal Goupillaud film (T)", n=v["n_ideal"], d=gd(v["n_ideal"]), q="T",
                 colour=OI["vermillion"]),
            dict(key="atlas_eh_like", name="realizable /ɛ/-like atlas stack #6973 (T)", n=n_at, d=gd(n_at), q="T",
                 colour=OI["green"])]


def run():
    S = {"angles_deg": [int(ANG[0]), int(ANG[-1]), int(ANG[1] - ANG[0])], "films": {}}
    rec = []
    for f in films():
        rgb, Y, labs, F12, alist = [], [], [], [], []
        for th in ANG:
            X = film_xyz(f["n"], f["d"], quantity=f["q"], theta=float(th))
            rgb.append(col.display_rgb(X)); Y.append(X[1]); labs.append(lab_eq(X))
            a, g = film.voice_of_film(f["n"], f["d"], theta_deg=float(th))
            alist.append(a)
            Fe, Pe = env_formants(a, g, min_prom=0.3)
            F12.append(Fe[:2] if len(Fe) >= 2 else [np.nan, np.nan])
        F12 = np.array(F12, float)
        ok = np.isfinite(F12).all(1)
        def disp(k):
            return rnd(np.hypot(*(np.log(F12[k]) - np.log(F12[0]))), 3) if ok[0] and ok[k] else None
        at = {int(th): (f"/{nearest_vowel(*F12[k])[0]['ipa']}/" if ok[k] else "none")
              for k, th in enumerate(ANG) if th % 20 == 0}
        nmin = f["n"][1:].min()
        crit = float(np.degrees(np.arcsin(nmin / f["n"][0]))) if f["n"][0] > nmin else None
        S["films"][f["key"]] = dict(
            name=f["name"], incident_index=rnd(f["n"][0], 3), min_layer_index=rnd(f["n"][1:].min(), 3),
            Y_range=[rnd(min(Y), 2), rnd(max(Y), 2)], Y_0=rnd(Y[0], 2), Y_80=rnd(Y[-1], 2),
            dE00_eqY_0_vs_40=rnd(col.delta_e00(labs[0], labs[len(ANG) // 2]), 2),
            dE00_eqY_0_vs_80=rnd(col.delta_e00(labs[0], labs[-1]), 2),
            hex_0_40_80=[col.to_hex(rgb[0]), col.to_hex(rgb[len(ANG) // 2]), col.to_hex(rgb[-1])],
            F1F2_0=rnd(F12[0], 0), F1F2_40=rnd(F12[len(ANG) // 2], 0), F1F2_80=rnd(F12[-1], 0),
            n_angles_with_F1F2=int(ok.sum()), F1_range_Hz=[rnd(np.nanmin(F12[:, 0]), 0), rnd(np.nanmax(F12[:, 0]), 0)],
            F2_range_Hz=[rnd(np.nanmin(F12[:, 1]), 0), rnd(np.nanmax(F12[:, 1]), 0)],
            displacement_ln_0_to_20=disp(10), displacement_ln_0_to_40=disp(20), displacement_ln_0_to_80=disp(40),
            nearest_vowel_at=at, critical_angle_deg=rnd(crit, 1) if crit else None,
            n_peak_set_changes=int(np.sum(np.abs(np.diff(np.log(F12[ok][:, 0]))) > np.log(1.25))))
        seq_a = alist + alist[-2::-1]
        y = synth.sing(seq_a, [0.04] * len(seq_a), f0=140.0)
        S["films"][f["key"]]["audio"] = write_audio(f"glide_{f['key']}.wav", y)
        rec.append((f, np.array(rgb), np.array(Y), F12))

    # ---- figure
    fig = plt.figure(figsize=(13.5, 6.0))
    gs = fig.add_gridspec(4, 3, width_ratios=[1.15, 0.8, 1.0], height_ratios=[1, 1, 1, 1.5], hspace=0.7, wspace=0.3)
    for i, (f, rgb, Y, F12) in enumerate(rec):
        ax = fig.add_subplot(gs[i, 0])
        ax.imshow(rgb[None, :, :], aspect="auto", extent=(ANG[0] - 1, ANG[-1] + 1, 0, 1))
        ax.set_yticks([]); ax.grid(False)
        ax.set_title(f["name"] + " — displayed colour vs angle", fontsize=8.5, loc="left")
        ax.set_xticks(np.arange(0, 81, 10)); ax.tick_params(labelsize=7)
    ax = fig.add_subplot(gs[3, 0])
    for f, rgb, Y, F12 in rec:
        ax.plot(ANG, Y, color=f["colour"], lw=1.4, label=f["name"])
    ax.set_yscale("log"); ax.set_xlabel("angle of incidence θ (deg, in the incident medium)")
    ax.set_ylabel("luminance Y (D65)"); ax.legend(fontsize=6)
    mk = ("o", "s", "^")
    for row, (k, lab) in enumerate(((0, "F1"), (1, "F2"))):
        ax = fig.add_subplot(gs[2 * row:2 * row + 2, 1])
        for (f, rgb, Y, F12), m_ in zip(rec, mk):
            ax.scatter(ANG, F12[:, k], s=12, marker=m_, color=f["colour"], label=f["name"].split(" (")[0])
        ax.set_yscale("log"); ax.set_ylabel(f"{lab} of voice_of_film(θ) (Hz)")
        if row == 1:
            ax.set_xlabel("angle θ (deg)")
        else:
            ax.legend(fontsize=6, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    ax = fig.add_subplot(gs[:, 2])
    vowel_chart_axes(ax, alpha=0.45, fs=6)
    for (f, rgb, Y, F12), m_ in zip(rec, mk):
        ok = np.isfinite(F12).all(1)
        sc = ax.scatter(F12[ok, 1], F12[ok, 0], c=ANG[ok], cmap="viridis", vmin=0, vmax=80, s=22, marker=m_,
                        zorder=5, edgecolor=f["colour"], linewidth=0.9)
        for th in (0, 40, 80):
            k = int(th // 2)
            if ok[k]:
                ax.annotate(f"{th}°", (F12[k, 1], F12[k, 0]), fontsize=6.5, color=f["colour"], xytext=(4, -8),
                            textcoords="offset points")
    fig.colorbar(sc, ax=ax, label="angle θ (deg)", shrink=0.7)
    ax.set_title("Iridescence = diphthong: (F2, F1) of voice_of_film(θ)\n"
                 "(○ Morpho-like, □ /ɑ/ ideal film, △ /ɛ/-like stack)", fontsize=9)
    savefig(fig, "6_angle_sweep")
    return S
