"""Fluorescence experiment: Papilio nireus validation + every phoneme film as the photonic structure
around a papiliochrome-type fluorophore. -> results/fluorescence.json, results/fig_fluorescence.png.
Run: python research/fluorescence_run.py   (~10 s on the phone)."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import fluorescence as F  # noqa: E402

BAND = (F.WL >= 450) & (F.WL <= 650)
ILL_KEYS = {"D65": "D65", "UV": "UV365", "violet": "violet405"}


def r(x, k=4):
    return round(float(x), k)


def main():
    items_in = json.loads((ROOT / "web/data/sounds.json").read_text())["items"]
    items = []
    for it in items_in:
        res = F.phoneme_fluorescence(it["a"])
        b = res["by_illuminant"]
        ideal = F.phoneme_fluorescence(it["a"], mode="ideal")
        items.append(dict(
            id=it["id"], ipa=it["ipa"], **{"class": it["class"]},
            hex_D65=b["D65"]["hex"], hex_UV=b["UV365"]["hex"], hex_violet=b["violet405"]["hex"],
            hex_D65_no_dye=F.appearance(res["n"], res["d_nm"], "D65", fluor=None)["hex"],
            fluor_fraction_D65=r(b["D65"]["fluor_fraction"]),
            fluor_fraction_violet=r(b["violet405"]["fluor_fraction"]),
            peak_emission_nm=r(res["peak_emission_nm"], 1),
            eta_450_650=[r(res["eta"][BAND].min()), r(res["eta"][BAND].max())],
            photon_yield_UV=r(b["UV365"]["emitted_photons"] / b["UV365"]["absorbed_photons"]),
            ideal_unphysical=dict(hex_UV=ideal["by_illuminant"]["UV365"]["hex"],
                                  eta_450_650=[r(ideal["eta"][BAND].min()), r(ideal["eta"][BAND].max())])))

    pap = {}
    for dbr in (True, False):
        key = "with_DBR" if dbr else "no_DBR"
        pap[key] = {}
        for short, ill in ILL_KEYS.items():
            a = F.papilio_appearance(ill, dbr=dbr)
            pap[key][short] = dict(hex=a["hex"], Lab=[r(v, 2) for v in a["Lab"]],
                                   fluor_fraction=r(a["fluor_fraction"]), peak_emission_nm=a["peak_emission_nm"],
                                   photon_yield=r(a["emitted_photons"] / a["absorbed_photons"]))
        pap[key]["eta_505"] = r(a["eta"][np.argmin(np.abs(F.WL - 505))])
    f = F.PAPILIOCHROME
    sc = f.stokes_shift()
    out = dict(
        generated_by="research/fluorescence_run.py (core/fluorescence.py)", date=str(date.today()),
        label="approximate",
        settings=dict(film="full mapping, realizable indices (same as sounds.json colours.full.realizable)",
                      dye="in every layer of the phoneme film", theta_deg=0,
                      illuminants=dict(D65="CIE D65", UV="365 nm LED, Gaussian FWHM 10 nm (illustrative)",
                                       violet="405 nm LED, Gaussian FWHM 15 nm (illustrative)"),
                      hex="exposure-normalised display colour (artistic), Lab vs D65 white"),
        fluorophore=dict(name=f.name, exc_peak_nm=f.exc_peak_nm, em_peak_nm=f.em_peak_nm,
                         stokes_shift_nm=r(sc["nm"], 1), stokes_shift_cm1=r(sc["cm1"], 0), qy=f.qy, k_max=f.k_max,
                         label=f.label),
        papilio=dict(structure="air | 2-D PC slab as effective medium n=%.3f, 1300 nm, dye | air gap 1200-1800 nm "
                               "(averaged) | DBR cuticle 75 / air 35 / cuticle 75 nm | air" % F.N_PC, **pap),
        items=items,
        findings=[
            "P. nireus preset: extracted emission peaks at %s nm (cited ~505 nm); under UV-A the scale glows %s." % (
                pap["with_DBR"]["UV"]["peak_emission_nm"], pap["with_DBR"]["UV"]["hex"]),
            "The 3-layer DBR raises the top escape factor at 505 nm from %.3f to %.3f (model)." % (
                pap["no_DBR"]["eta_505"], pap["with_DBR"]["eta_505"]),
            "Realizable phoneme films (n 1-2.5) only reshape extraction mildly: escape factor over 450-650 nm "
            "ranges %.2f-%.2f across all %d items, so under blacklight every phoneme glows nearly the same green; "
            "in daylight the dye adds %d-%d%% of Y on top of the film's own reflection." % (
                min(i["eta_450_650"][0] for i in items), max(i["eta_450_650"][1] for i in items), len(items),
                round(100 * min(i["fluor_fraction_D65"] for i in items)),
                round(100 * max(i["fluor_fraction_D65"] for i in items))),
            "With the unphysical 'ideal' indices (up to n~200) the films do filter the emission strongly "
            "(escape factor down to ~0.1) and blacklight colours diverge - reported only as ideal_unphysical."],
        citations=F.CITATIONS,
        caveats=[
            "Spectral shapes are Gaussian fits to cited peaks and band edges, not digitised spectra.",
            "Quantum yield 0.3 and dye extinction k_max 0.02 are ILLUSTRATIVE (no literature value found).",
            "Extraction is Purcell-free: eta = P_top/(P_top+P_bottom) for in-plane dipole sheets, s/p averaged; "
            "vertical dipoles, re-absorption of emission and the 2-D PC's in-plane band gap are ignored.",
            "Reflection is specular, fluorescence is spread over angles; fluor_fraction is indicative only.",
            "Display hexes are exposure-normalised, so a dim blacklight scene shows its hue at display brightness.",
            "Phoneme films use the project pipeline's media (incident medium = film n[0], not necessarily air).",
        ])
    (ROOT / "results/fluorescence.json").write_text(json.dumps(out, indent=1, allow_nan=False))
    figure(out, items)
    print("items", len(items), "papilio UV", pap["with_DBR"]["UV"])


def figure(out, items):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig = plt.figure(figsize=(13, 8.5), dpi=110)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.15, 1], height_ratios=[1, 1.25], hspace=0.35, wspace=0.18)
    ax = fig.add_subplot(gs[0, 0])
    f = F.PAPILIOCHROME
    a = F.papilio_appearance("UV365", dbr=True)
    a0 = F.papilio_appearance("UV365", dbr=False)
    ink, mute = "#333333", "#888888"
    ax.plot(F.WL, f.excitation(), color="#6a3d9a", lw=2)
    ax.text(392, 1.03, "excitation (peak 420 nm)", color=ink, fontsize=9, ha="center")
    em = f.emission() / f.emission().max()
    ax.plot(F.WL, em, color=mute, lw=2, ls="--")
    ax.text(560, 0.75, "intrinsic emission", color=ink, fontsize=9)
    ext = a["fluo"] / a["fluo"].max()
    ax.plot(F.WL, ext, color="#1b9e77", lw=2)
    ax.text(572, 0.3, "extracted (x η), with DBR", color=ink, fontsize=9)
    ax.plot(F.WL, a["eta"], color="#d95f02", lw=1.5)
    ax.text(700, a["eta"][400] + 0.04, "escape factor η (DBR)", color=ink, fontsize=9)
    ax.set_xlim(330, 750), ax.set_ylim(0, 1.12)
    ax.set_xlabel("wavelength (nm)"), ax.set_ylabel("normalised")
    ax.set_title("Papilio nireus scale (1-D approx.): peak %s nm (cited ~505)" % a["peak_emission_nm"], fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    ax = fig.add_subplot(gs[0, 1])
    ax.set_title("P. nireus model colour under three lights", fontsize=10)
    for j, key in enumerate(("with_DBR", "no_DBR")):
        for i, ill in enumerate(("D65", "violet", "UV")):
            c = out["papilio"][key][ill]
            ax.add_patch(Rectangle((i, 1 - j), 0.9, 0.85, color=c["hex"]))
            ax.text(i + 0.45, 1 - j - 0.12, "%s · %.0f%%" % (c["hex"], 100 * c["fluor_fraction"]),
                    ha="center", fontsize=8, color=ink)
        ax.text(-0.05, 1.42 - j, key.replace("_", " "), ha="right", va="center", fontsize=9)
    ax.text(1.45, -0.3, "% = share of luminance from fluorescence", ha="center", fontsize=8, color=mute)
    for i, ill in enumerate(("daylight D65", "violet 405 nm", "UV-A 365 nm")):
        ax.text(i + 0.45, 1.95, ill, ha="center", fontsize=9)
    ax.set_xlim(-0.8, 3), ax.set_ylim(-0.25, 2.1), ax.axis("off")

    ax = fig.add_subplot(gs[1, :])
    ax.set_title("Every phoneme film as the photonic structure around the dye: top = daylight, "
                 "bottom = blacklight (UV-A 365 nm)  [approximate]", fontsize=10)
    ncol = 22
    for k, it in enumerate(items):
        row, colm = divmod(k, ncol)
        y = -row * 3.0
        ax.add_patch(Rectangle((colm, y), 0.9, 0.9, color=it["hex_D65"]))
        ax.add_patch(Rectangle((colm, y - 1.0), 0.9, 0.9, color=it["hex_UV"]))
        ax.text(colm + 0.45, y + 1.0, it["ipa"], ha="center", fontsize=10, color=ink)
        ax.text(colm + 0.45, y - 1.35, "%d%%" % round(100 * it["fluor_fraction_D65"]), ha="center",
                fontsize=7, color=mute)
    ax.text(0, -5.6, "grey %% = share of daylight luminance Y coming from fluorescence. Blacklight colours are "
            "near-identical because realizable films (n 1-2.5) change the escape factor only within %.2f-%.2f."
            % (min(i["eta_450_650"][0] for i in items), max(i["eta_450_650"][1] for i in items)),
            fontsize=8, color=mute)
    ax.set_xlim(-0.2, ncol), ax.set_ylim(-5.9, 1.5), ax.axis("off")
    fig.savefig(ROOT / "results/fig_fluorescence.png", facecolor="white")


if __name__ == "__main__":
    main()
