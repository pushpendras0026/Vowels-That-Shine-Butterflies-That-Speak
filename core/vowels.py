"""Vowel formant targets from Hillenbrand et al. (1995), J. Acoust. Soc. Am. 97(5), 3099-3111.
File: data/hillenbrand/bigdata.dat (retrieved via web.archive.org snapshot of
homepages.wmich.edu/~hillenbr/voweldata/bigdata.dat). Steady-state F0, F1-F3; zeros = unmeasurable.
Group means: men, women, children (boys + girls).

Vowel -> LPC pipeline (same as the live lab): synthesise 0.5 s with the Rosenberg source at the group-mean
F0 through the formant filter (F1-F3 from data; bandwidths BANDWIDTHS are ILLUSTRATIVE typical values, not
from the dataset), then LPC order 16, pre-emphasis 0.97, Hamming window."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import lpc as _lpc
from .mapping import FS, ORDER
from .synth import glottal_source, synth_allpole

DATA = Path(__file__).resolve().parent.parent / "data" / "hillenbrand" / "bigdata.dat"
BANDWIDTHS = (80.0, 100.0, 150.0)  # ILLUSTRATIVE
VOWELS = {  # code: (IPA, example word)
    "iy": ("i", "heed"), "ih": ("ɪ", "hid"), "ei": ("e", "haid"), "eh": ("ɛ", "head"),  # 'haid': header says "ey", rows use "ei"
    "ae": ("æ", "had"), "ah": ("ɑ", "hod"), "aw": ("ɔ", "hawed"), "oa": ("o", "boat"),
    "oo": ("ʊ", "hood"), "uw": ("u", "who'd"), "uh": ("ʌ", "hud"), "er": ("ɝ", "heard"),
}
GROUPS = {"men": "m", "women": "w", "children": "bg"}


def load_tokens(path=DATA):
    rows = []
    for line in Path(path).read_text(errors="ignore").splitlines():
        parts = line.split()
        if len(parts) < 6 or len(parts[0]) != 5 or not parts[1].isdigit():
            continue
        name = parts[0]
        rows.append(dict(speaker=name[0], vowel=name[3:5], f0=float(parts[2]),
                         F1=float(parts[3]), F2=float(parts[4]), F3=float(parts[5])))
    return rows


def group_means(path=DATA):
    rows = load_tokens(path)
    out = []
    for g, letters in GROUPS.items():
        for v, (ipa, ex) in VOWELS.items():
            sel = [r for r in rows if r["speaker"] in letters and r["vowel"] == v]
            vals = {}
            for key in ("f0", "F1", "F2", "F3"):
                x = np.array([r[key] for r in sel if r[key] > 0])
                vals[key] = float(np.mean(x))
            out.append(dict(vowel=v, ipa=ipa, example=ex, group=g, n_tokens=len(sel),
                            F0=vals["f0"], F1=vals["F1"], F2=vals["F2"], F3=vals["F3"]))
    return out


def vowel_lpc(F, f0, p=ORDER, fs=FS, dur=0.5, bandwidths=BANDWIDTHS):
    a_true = _lpc.poly_from_formants(F, bandwidths[: len(F)], fs)
    y = synth_allpole(a_true, glottal_source(f0, fs, dur), 1.0)
    mid = len(y) // 2
    frame = y[mid - 256: mid + 256]
    a, k, g = _lpc.lpc(frame, p)
    return a, g
