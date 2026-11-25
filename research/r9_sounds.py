"""(9) Every sound has a colour: real IPA recordings (Wikimedia Commons, data/ipa/ATTRIBUTION.md) -> LPC -> film.

Input: web/data/sounds.json written by `python -m tools.build_sounds` (CONTRACT §7c; rebuilt here if missing).
Figure results/fig_r9_sounds.png: per sound, the displayed colour for full-band vs brief mapping, reflected
(realizable film) and transmitted (ideal film) — the two quantities measured in CONTRACT §4b — plus the per-frame
colour strip of each recording. Numbers (results/r9_sounds.json): pairwise CIEDE2000 between sounds, computed on the
DISPLAYED sRGB colours (hex -> Lab D65), the same convention as CONTRACT §4b.
"""
from __future__ import annotations

import itertools
import json

import numpy as np

from core import colour as col
from research.common import ROOT, RES, plt, savefig, rnd

SOUNDS = ROOT / "web" / "data" / "sounds.json"
VIEWS = [("full", "realizable", "R", "full-band · realizable · R"), ("full", "ideal", "T", "full-band · ideal · T"),
         ("brief", "realizable", "R", "brief · realizable · R"), ("brief", "ideal", "T", "brief · ideal · T")]


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def hex_lab(h):
    """Displayed sRGB hex -> CIE Lab (D65, sRGB primaries)."""
    u = hex_rgb(h)
    lin = np.where(u <= 0.04045, u / 12.92, ((u + 0.055) / 1.055) ** 2.4)
    XYZ = np.linalg.solve(col.M_XYZ_TO_SRGB, lin) * 100.0
    return col.xyz_to_lab(XYZ, "D65")


def load():
    if not SOUNDS.exists():
        from tools import build_sounds
        build_sounds.main()
    if not SOUNDS.exists():
        return []
    return json.loads(SOUNDS.read_text(encoding="utf-8")).get("items", [])


def pair_stats(labs, idx_a, idx_b=None):
    if idx_b is None:
        pairs = list(itertools.combinations(idx_a, 2))
    else:
        pairs = [(i, j) for i in idx_a for j in idx_b]
    if not pairs:
        return dict(n_pairs=0, median=None, min=None, frac_below_2=None)
    d = np.array([col.delta_e00(labs[i], labs[j]) for i, j in pairs])
    return dict(n_pairs=len(pairs), median=rnd(np.median(d), 2), min=rnd(d.min(), 2),
                frac_below_2=rnd(np.mean(d < 2.0), 3))


def run():
    items = load()
    S = dict(source="web/data/sounds.json (tools/build_sounds.py, Wikimedia Commons IPA recordings)",
             dE_convention="CIEDE2000 on displayed sRGB (exposure-normalised hex -> Lab D65), as CONTRACT §4b",
             n_sounds=len(items), n_vowels=sum(i["kind"] == "vowel" for i in items),
             n_consonants=sum(i["kind"] != "vowel" for i in items), views={})
    if not items:
        S["note"] = "no sounds.json / no sounds"
        (RES / "r9_sounds.json").write_text(json.dumps(S, indent=1, ensure_ascii=False), encoding="utf-8")
        return S
    order = {"vowel": 0, "plosive": 1, "nasal": 2, "fricative": 3, "lateral": 4, "approximant": 5}
    items = sorted(items, key=lambda i: order.get(i["class"], 9))
    V = [k for k, i in enumerate(items) if i["kind"] == "vowel"]
    C = [k for k, i in enumerate(items) if i["kind"] != "vowel"]
    grid = []
    for mp_, mode, q, label in VIEWS:
        hexes = [i["colours"][mp_][mode][q]["hex"] for i in items]
        labs = [hex_lab(h) for h in hexes]
        grid.append([hex_rgb(h) for h in hexes])
        nn = []
        for c in C:
            nn.append(min(col.delta_e00(labs[c], labs[v]) for v in V) if V else np.nan)
        S["views"][f"{mp_}_{mode}_{q}"] = dict(
            label=label, all=pair_stats(labs, list(range(len(items)))), vowels=pair_stats(labs, V),
            consonants=pair_stats(labs, C), vowel_vs_consonant=pair_stats(labs, V, C),
            consonant_to_nearest_vowel_median=rnd(np.nanmedian(nn), 2) if nn else None,
            n_distinct_hex=len(set(hexes)))
    S["frames_used_median"] = rnd(np.median([i["frames_used"] for i in items if "frames_used" in i]), 1)
    S["fallback_items"] = [i["id"] for i in items if i.get("rule") == "fallback"]
    S["headline"] = dict(full_realR_median_dE_all=S["views"]["full_realizable_R"]["all"]["median"],
                         brief_realR_median_dE_all=S["views"]["brief_realizable_R"]["all"]["median"],
                         full_idealT_median_dE_all=S["views"]["full_ideal_T"]["all"]["median"],
                         brief_idealT_median_dE_all=S["views"]["brief_ideal_T"]["all"]["median"])

    # ---- figure: swatch grid (4 views x sounds) + per-frame strips
    n = len(items)
    fig = plt.figure(figsize=(max(9.0, 0.36 * n + 2.0), 7.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.7], hspace=0.25)
    ax = fig.add_subplot(gs[0])
    ax.imshow(np.array(grid), aspect="auto", interpolation="nearest")
    ax.set_yticks(range(len(VIEWS)), [v[3] for v in VIEWS], fontsize=7.5)
    ax.set_xticks(range(n), [f"[{i['ipa']}]" for i in items], fontsize=8)
    ax.grid(False)
    for x in (len(V) - 0.5,):
        ax.axvline(x, color="white", lw=2.5)
    ax.set_title(f"Real IPA recordings → LPC → thin film: displayed colour ({len(V)} vowels | {len(C)} consonants; "
                 "D65, exposure-normalised)", fontsize=9.5, loc="left")
    ax = fig.add_subplot(gs[1])
    L = max(len(i["strip"]) for i in items) or 1
    img = np.ones((n, L, 3)) * 0.92
    for r, it in enumerate(items):
        st = it["strip"]
        if st:
            xs = np.linspace(0, len(st) - 1, L).round().astype(int)
            img[r] = [hex_rgb(st[k]) for k in xs]
    ax.imshow(img, aspect="auto", interpolation="nearest")
    ax.set_yticks(range(n), [f"[{i['ipa']}] {i['class']}" for i in items], fontsize=6.5)
    ax.set_xticks([])
    ax.grid(False)
    ax.set_xlabel("time → (energetic frames of the recording, resampled to equal length)")
    ax.set_title("Colour of every 32 ms frame (full-band, realizable film, reflected): the target sound vs its context",
                 fontsize=9.5, loc="left")
    S["figure"] = savefig(fig, "r9_sounds")
    (RES / "r9_sounds.json").write_text(json.dumps(S, indent=1, ensure_ascii=False), encoding="utf-8")
    return S


if __name__ == "__main__":
    out = run()
    print(json.dumps(out["headline"] if "headline" in out else out, ensure_ascii=False))
