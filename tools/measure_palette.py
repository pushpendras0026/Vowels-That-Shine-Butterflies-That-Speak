"""Pairwise ΔE00 between the 12 vowels of each group: canonical vs pi-shifted mapping, raw vs Y-equalised."""
import itertools
import numpy as np
from core import mapping as mp, film, colour as col, vowels


def lab_of(n, eq):
    _, T = film.film_rt(n, mp.goupillaud_d(n[1:-1]), col.WL)
    X = col.spectrum_to_xyz(T)
    if eq and X[1] > 0:
        X = X * 50 / X[1]
    return col.xyz_to_lab(X)


def shifted(m):
    c = mp.reflection_from_media(m) * (-1.0) ** np.arange(len(m) - 1)
    return mp.media_from_reflection(c, m[0])


rows = vowels.group_means()
for g in ("men", "women", "children"):
    vs = [r for r in rows if r["group"] == g]
    media = [mp.vowel_media(vowels.vowel_lpc([r["F1"], r["F2"], r["F3"]], r["F0"])[0]) for r in vs]
    for mapname, tf in (("canonical", lambda m: m), ("shifted", shifted)):
        for mode in ("ideal", "realizable"):
            for eq in (False, True):
                labs = [lab_of(mp.film_from_media(tf(m), mode), eq) for m in media]
                d = [col.delta_e00(a, b) for a, b in itertools.combinations(labs, 2)]
                print(f"{g:8s} {mapname:9s} {mode:10s} eq={int(eq)}  dE00 median {np.median(d):5.1f}  "
                      f"min {np.min(d):4.1f}  max {np.max(d):5.1f}  L* {np.mean([l[0] for l in labs]):5.1f}")
