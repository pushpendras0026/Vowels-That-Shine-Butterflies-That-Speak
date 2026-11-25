"""Shared helpers for the research figures (paths, plot style, formant policy, vowel table).

Formant policy (stated in docs/REPORT.md):
  * primary   = poles of the all-pole polynomial (core.lpc.formants_from_poly, bandwidth < 600 Hz);
  * secondary = peaks of the LPC envelope 20 log10(g/|A|) with their prominence in dB
                (scipy.signal.find_peaks), used wherever a voice is too weak/broad for the primary rule
                (butterfly-like stacks, angle sweeps).
Vowel-chart unit: natural-log Hz, d = sqrt((ln F1a - ln F1b)^2 + (ln F2a - ln F2b)^2); spreads are also
expressed as a fraction of the Hillenbrand 12-vowel extent in that unit.
"""
from __future__ import annotations

import functools
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.signal import find_peaks  # noqa: E402

from core import lpc, mapping as mp, film, colour as col, synth, vowels  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
AUD = RES / "audio"
for _d in (RES, AUD):
    _d.mkdir(parents=True, exist_ok=True)

# Okabe & Ito colour-blind-safe palette
OI = dict(black="#000000", orange="#E69F00", sky="#56B4E9", green="#009E73", yellow="#F0E442",
          blue="#0072B2", vermillion="#D55E00", purple="#CC79A7", grey="#999999")
SERIES = [OI["blue"], OI["orange"], OI["green"], OI["vermillion"], OI["purple"], OI["sky"], OI["black"]]
GROUP_COLOURS = {"men": OI["blue"], "women": OI["vermillion"], "children": OI["green"]}
GROUPS = ("men", "women", "children")

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 150, "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
    "legend.fontsize": 8, "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "axes.prop_cycle": matplotlib.cycler(color=SERIES),
})

FIGS: list[str] = []
AUDIO: list[str] = []


def savefig(fig, name):
    path = RES / f"fig_{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    FIGS.append(path.name)
    return path.name


def write_audio(name, y):
    path = AUD / name
    synth.write_wav(path, y)
    AUDIO.append(path.name)
    return path.name


def silence(sec=0.25):
    return np.zeros(int(sec * mp.FS))


# ---------------------------------------------------------------- vowel table (same pipeline as build_all)
@functools.lru_cache(maxsize=None)
def vowel_table():
    out = []
    for g in vowels.group_means():
        a, gain = vowels.vowel_lpc([g["F1"], g["F2"], g["F3"]], g["F0"])
        m = mp.vowel_media(a)
        out.append(dict(g, a=a, gain=gain, m=m, n_ideal=mp.film_from_media(m, "ideal"),
                        n_real=mp.film_from_media(m, "realizable"), n_mat=mp.film_from_media(m, "materials")))
    return tuple(out)


def vowel(group, code):
    return next(v for v in vowel_table() if v["group"] == group and v["vowel"] == code)


def gd(n):
    """Goupillaud thicknesses for a full index vector n (incident, layers, substrate)."""
    return mp.goupillaud_d(np.asarray(n)[1:-1])


# ---------------------------------------------------------------- spectra on the speech axis
F_GRID = np.linspace(0, mp.FS / 2, 513)


def nu_for_f(f):
    """Exact CONTRACT §6 mapping used by voice_of_film: the nu in [NU_MIN, NU_MAX) with f_of_nu(nu) = f."""
    f = np.asarray(f, float)
    return mp.NU_MIN + ((f / mp.FS - (mp.NU_MIN / mp.DNU) % 1.0) % 1.0) * mp.DNU


def film_T_on_f(n, d, f=F_GRID, theta=0.0):
    _, T = film.film_rt_nu(n, d, nu_for_f(f), theta)
    return T


def poly_power(D, c=None, f=F_GRID):
    """prod(1-c^2)/|D|^2 (or 1/|D|^2 if c is None) on the speech axis."""
    z = np.exp(-1j * np.outer(2 * np.pi * np.asarray(f) / mp.FS, np.arange(len(D))))
    P = 1.0 / np.abs(z @ D) ** 2
    return P * (np.prod(1 - np.asarray(c) ** 2) if c is not None else 1.0)


def db(P):
    return 10 * np.log10(np.maximum(P, 1e-300))


def lsd(P1, P2):
    """Log-spectral distance (dB RMS) after removing the mean dB level (shape only)."""
    d1, d2 = db(P1), db(P2)
    d1, d2 = d1 - d1.mean(), d2 - d2.mean()
    return float(np.sqrt(np.mean((d1 - d2) ** 2)))


# ---------------------------------------------------------------- formants
def poles(a):
    """All complex poles in (0, FS/2): frequencies and bandwidths, no bandwidth filter."""
    return lpc.formants_from_poly(a, fmin=1.0, max_bw=1e9)


def nearest_pole(a, f_ref):
    F, B = poles(a)
    if len(F) == 0:
        return np.nan, np.nan
    i = int(np.argmin(np.abs(F - f_ref)))
    return float(F[i]), float(B[i])


def env_formants(a, gain=1.0, fmax=5500.0, min_prom=0.3, nfft=8192):
    """Secondary formant rule: LPC-envelope peaks (parabolic interpolation) with prominence (dB)."""
    f, e = lpc.envelope_db(a, gain, nfft=nfft)
    pk, props = find_peaks(e, prominence=min_prom)
    F, P = [], []
    df = f[1] - f[0]
    for i, pr in zip(pk, props["prominences"]):
        y0, y1, y2 = e[i - 1], e[i], e[i + 1]
        den = y0 - 2 * y1 + y2
        off = 0.5 * (y0 - y2) / den if den != 0 else 0.0
        fi = f[i] + off * df
        if 90 < fi < fmax:
            F.append(fi)
            P.append(pr)
    return np.array(F), np.array(P)


# ---------------------------------------------------------------- vowel chart (ln Hz)
def hill_points():
    V = vowel_table()
    return np.array([[np.log(v["F1"]), np.log(v["F2"])] for v in V]), V


def vowel_extent():
    """Diagonal of the bounding box of all 36 Hillenbrand means in (ln F1, ln F2)."""
    P, _ = hill_points()
    return float(np.hypot(*(P.max(0) - P.min(0))))


def nearest_vowel(F1, F2):
    P, V = hill_points()
    d = np.hypot(P[:, 0] - np.log(F1), P[:, 1] - np.log(F2))
    i = int(np.argmin(d))
    return V[i], float(d[i])


def median_neighbour_vowel_distance():
    """Median over the 36 means of the ln-distance to the nearest OTHER vowel of the same group."""
    P, V = hill_points()
    out = []
    for i, v in enumerate(V):
        same = [j for j, w in enumerate(V) if w["group"] == v["group"] and j != i]
        out.append(np.min(np.hypot(*(P[same] - P[i]).T)))
    return float(np.median(out))


def vowel_chart_axes(ax, groups=GROUPS, label=True, alpha=0.9, fs=7):
    """Classic orientation: F2 on x (reversed), F1 on y (reversed), log axes; Hillenbrand means."""
    for v in vowel_table():
        if v["group"] not in groups:
            continue
        ax.scatter(v["F2"], v["F1"], s=14, color=GROUP_COLOURS[v["group"]], alpha=alpha, zorder=3,
                   edgecolor="white", linewidth=0.4)
        if label:
            ax.annotate(v["ipa"], (v["F2"], v["F1"]), fontsize=fs, color=GROUP_COLOURS[v["group"]],
                        xytext=(3, 2), textcoords="offset points")
    from matplotlib.ticker import FixedLocator, NullFormatter, FuncFormatter
    ax.set_xscale("log")
    ax.set_yscale("log")
    if not ax.xaxis_inverted():
        ax.invert_xaxis()
    if not ax.yaxis_inverted():
        ax.invert_yaxis()
    fmt = FuncFormatter(lambda v, _: f"{v / 1000:g}k" if v >= 1000 else f"{v:g}")
    ax.xaxis.set_major_locator(FixedLocator([500, 700, 1000, 1500, 2000, 3000, 5000, 8000]))
    ax.yaxis.set_major_locator(FixedLocator([200, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 8000]))
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_formatter(fmt)
        axis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("F2 (Hz, log scale)")
    ax.set_ylabel("F1 (Hz, log scale)")


def lab_eq(XYZ, ill="D65", Y=50.0):
    """Lab after scaling Y to 50 (equal luminance; same convention as tools/measure_palette.py)."""
    XYZ = np.asarray(XYZ, float)
    return col.xyz_to_lab(XYZ * (Y / XYZ[1]) if XYZ[1] > 0 else XYZ, ill)


def film_xyz(n, d, ill="D65", quantity="T", theta=0.0):
    R, T = film.film_rt(n, d, col.WL, theta)
    return col.spectrum_to_xyz(T if quantity == "T" else R, ill)


def rnd(x, nd=3):
    """Round for JSON."""
    if isinstance(x, (list, tuple, np.ndarray)):
        return [rnd(v, nd) for v in x]
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    if isinstance(x, (int, np.integer)):
        return int(x)
    return float(round(float(x), nd))
