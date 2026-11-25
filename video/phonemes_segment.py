"""Extra explainer segment "Every phoneme: an experiment" (S12), matplotlib (Agg) frames piped to ffmpeg.

    python -m video.phonemes_segment --quality l      -> video/final/phonemes_segment_480p30.mp4 (quick test)
    python -m video.phonemes_segment --quality h      -> video/final/phonemes_segment_1080p.mp4
    python -m video.phonemes_segment --concat         -> web/video/explainer.mp4 = original explainer + segment
    python -m video.phonemes_segment --snap 12.5 40   -> PNG snapshots (l quality) in video/final/snaps/

This segment is drawn with matplotlib + ffmpeg (no manim needed). It copies the explainer's look (dark background,
same palette). Every number and colour comes from web/data/phonemes_experiment.json (research section 10) and
web/data/sounds.json (tools/build_sounds.py); spectra / angle sweeps are recomputed with core/ from the stored LPC
polynomials (same functions as build_sounds / r10). Audio: a short excerpt of each IPA recording (web/audio/ipa/*.wav,
film voice *_synth.wav where no recording exists) + the explainer's quiet pad bed, mono 48 kHz like the original.
No voice-over: on-screen captions carry the narration (also written to video/final/timeline_phonemes_<res>.json).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon, Rectangle  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

from core import colour as col  # noqa: E402
from core import film  # noqa: E402
from core import mapping as mp  # noqa: E402
from core import stacks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VID = ROOT / "video"
FINAL = VID / "final"
WEB = ROOT / "web"
PE = json.loads((WEB / "data" / "phonemes_experiment.json").read_text(encoding="utf-8"))
SD = json.loads((WEB / "data" / "sounds.json").read_text(encoding="utf-8"))
ITEMS = {it["id"]: it for it in PE["items"]}
SOUNDS = {it["id"]: it for it in SD["items"]}
CLASSES = PE["classes"]

FPS, SR = 30, 48000
QUAL = {"l": (854, 480, "480p30"), "m": (1280, 720, "720p30"), "h": (1920, 1080, "1080p")}

# palette = video/scenes.py
BG, TXT, DIM = "#0b0e14", "#e9ecf1", "#8a93a3"
SOUND, LIGHT, ACC = "#f4a259", "#6cc7ff", "#ffd166"
EXACT, APPROX, ART = "#7bd389", "#f6c85f", "#ff8fab"
TILE_OFF, TILE_EDGE = "#161b26", "#2a3140"
FONT = ["DejaVu Sans"]
plt.rcParams.update({"font.family": FONT, "axes.facecolor": BG, "figure.facecolor": BG, "text.color": TXT,
                     "axes.edgecolor": DIM, "axes.labelcolor": TXT, "xtick.color": DIM, "ytick.color": DIM,
                     "axes.grid": False, "savefig.facecolor": BG})
FADE = 0.35


# ----------------------------------------------------------------------------------------------- helpers
def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


def hex_lab(h):
    c = hex_rgb(h)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    X = M @ lin / np.array([0.95047, 1.0, 1.08883])
    f = np.where(X > (6 / 29) ** 3, np.cbrt(X), X / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def ink(h):
    """Black or white text on a swatch."""
    r, g, b = hex_rgb(h)
    return "#0b0e14" if 0.299 * r + 0.587 * g + 0.114 * b > 0.55 else "#ffffff"


def ease(x):
    x = float(np.clip(x, 0, 1))
    return x * x * (3 - 2 * x)


def film_of(a):
    n = mp.film_from_media(mp.vowel_media(np.asarray(a, float)), "realizable")
    return n, mp.goupillaud_d(n[1:-1], mp.D_OPT_FULL_NM)


def disp_hex(R):
    X = col.spectrum_to_xyz(R, "D65")
    return col.to_hex(col.display_rgb(X))


def morpho_scaled(sc):
    s = stacks.morpho_like(d_chitin=stacks.MORPHO_D_CHITIN * sc, d_air=stacks.MORPHO_D_AIR * sc)
    return s["n"], s["d_nm"]


def bfly_named(name):
    """Film of a butterfly named as in phonemes_experiment.json (as research/r10_phonemes.butterflies)."""
    if "×" in name:
        base, sc = name.split(" ×")
        sc = float(sc)
        if base == "Morpho-like":
            return morpho_scaled(sc)
        s = stacks.beetle_like(d1=95.0 * sc, d2=75.0 * sc)
        return s["n"], s["d_nm"]
    b = next(b for b in json.loads((WEB / "data" / "butterflies.json").read_text(encoding="utf-8"))["items"]
             if b["name"] == name)
    return np.array(b["n"], float), np.array(b["d_nm"], float)


def tag_text(fig, x, y, kind, s, size=15, ha="left", va="center"):
    c = {"art": ART, "exact": EXACT, "approx": APPROX}[kind]
    head = {"art": "ARTISTIC LICENSE", "exact": "EXACT PHYSICS", "approx": "APPROXIMATE"}[kind]
    return fig.text(x, y, f"{head}: {s}", color=c, fontsize=size, ha=ha, va=va,
                    bbox=dict(boxstyle="round,pad=0.35", fc=BG, ec=c, lw=1.4))


_UP = [(0.06, 0.10), (0.45, 0.75), (1.05, 1.22), (1.62, 1.18), (1.78, 0.80), (1.45, 0.35), (0.85, 0.08), (0.06, 0.02)]
_LO = [(0.06, -0.02), (0.75, -0.12), (1.22, -0.55), (1.12, -1.08), (0.62, -1.22), (0.22, -0.75), (0.06, -0.12)]


def draw_butterfly(ax, cx, cy, s, colour):
    arts = []
    for pts in (_UP, _LO):
        for sx in (1, -1):
            p = Polygon([(cx + sx * x * s, cy + y * s) for x, y in pts], closed=True, fc=colour, ec="#ffffff",
                        lw=1.0, alpha=0.95)
            ax.add_patch(p)
            arts.append(p)
    body = Ellipse((cx, cy), 0.12 * s, 1.5 * s, fc="#2b2f38", ec="#cfd5df", lw=0.8)
    ax.add_patch(body)
    return arts + [body]


# ----------------------------------------------------------------------------------------------- scenes
class Scene:
    dur = 5.0
    title = ""

    def __init__(self):
        self.captions = []   # (t0, t1, text)
        self.cues = []       # (t, wav_rel, excerpt_s or None)

    def caption_at(self, t):
        for t0, t1, s in self.captions:
            if t0 <= t < t1:
                return s
        return ""

    def build(self, fig):
        pass

    def update(self, t):
        return 0


class Title(Scene):
    dur = 5.0

    def __init__(self):
        super().__init__()
        n = len(PE["items"])
        self.captions = [(0.3, 5.0, f"So far, vowels. Here we push the same film recipe to all {n} phonemes "
                                    f"in {len(CLASSES)} classes, and report what came out.")]

    def build(self, fig):
        self.a = fig.text(0.5, 0.58, "We experimented beyond vowels", fontsize=58, ha="center", color=TXT,
                          weight="bold")
        self.b = fig.text(0.5, 0.48, "Every phoneme: an experiment", fontsize=34, ha="center", color=ACC)
        labels = " · ".join(c["label"].lower() for c in CLASSES)
        self.c = fig.text(0.5, 0.40, labels, fontsize=20, ha="center", color=DIM)
        self.d = fig.text(0.5, 0.30, "sound  →  LPC polynomial  →  thin film  →  colour  →  butterfly?",
                          fontsize=22, ha="center", color=LIGHT)
        self.t = tag_text(fig, 0.5, 0.20, "approx", "experimental track; results reported as they came out",
                          size=16, ha="center")

    def update(self, t):
        k = 0
        for i, (art, t0) in enumerate(((self.a, 0.0), (self.b, 0.8), (self.c, 1.6), (self.d, 2.4), (self.t, 3.2))):
            on = t >= t0
            art.set_visible(on)
            k += on << i
        return k


class Chart(Scene):
    STEP, CLS_GAP, INTRO, HOLD = 0.40, 0.35, 1.6, 2.4

    def __init__(self):
        super().__init__()
        self.rows = [(c, [it for it in PE["items"] if it["class"] == c["class"]]) for c in CLASSES]
        self.sched = []   # (t_on, row, col)
        t = self.INTRO
        for r, (c, its) in enumerate(self.rows):
            t += self.CLS_GAP
            for j, it in enumerate(its):
                self.sched.append((t, r, j))
                snd = SOUNDS[it["id"]]
                self.cues.append((t, "web/" + snd["audio"], self.STEP - 0.02))
                t += self.STEP
        self.t_end = t
        self.dur = t + self.HOLD
        n_rec = sum(1 for it in PE["items"] if not SOUNDS[it["id"]]["audio"].endswith("_synth.wav"))
        mid = self.INTRO + (self.t_end - self.INTRO) / 2
        self.captions = [
            (0.2, mid, f"The IPA chart, class by class. Each tile lights up in its film's colour while its "
                       f"recording plays ({n_rec} real recordings)."),
            (mid, self.t_end, "Recording → averaged LPC polynomial → realizable film (n 1–2.5) → reflected "
                              "colour under daylight (D65)."),
            (self.t_end, self.dur + 1, "* modelled (no clean recording: you hear the film's own voice)   "
                                       "† fallback plosive (context vowel averaged in)   ~ trajectory model"),
        ]

    def build(self, fig):
        nmax = max(len(its) for _, its in self.rows)
        x0, x1, y_top, y_bot = 0.205, 0.975, 0.865, 0.135
        rh = (y_top - y_bot) / len(self.rows)
        tw = (x1 - x0) / nmax
        self.tiles, self.lbls = [], []
        for r, (c, its) in enumerate(self.rows):
            yc = y_top - (r + 0.5) * rh
            lab = fig.text(0.03, yc + 0.012, c["label"], fontsize=22, color=DIM, va="center")
            cnt = fig.text(0.03, yc - 0.022, f"{len(its)} phoneme{'s' if len(its) > 1 else ''}", fontsize=13,
                           color=DIM, va="center")
            self.lbls.append((lab, cnt))
            row = []
            for j, it in enumerate(its):
                xl = x0 + j * tw
                p = FancyBboxPatch((xl + 0.004, yc - rh * 0.40), tw - 0.008, rh * 0.80,
                                   boxstyle="round,pad=0,rounding_size=0.008", transform=fig.transFigure,
                                   fc=TILE_OFF, ec=TILE_EDGE, lw=1.2)
                fig.add_artist(p)
                sym = fig.text(xl + tw / 2, yc + 0.006, it["ipa"], fontsize=25, ha="center", va="center", color=DIM)
                ex = fig.text(xl + tw / 2, yc - rh * 0.27, it["example"], fontsize=10, ha="center", va="center",
                              color=DIM)
                mark = {"modelled": "*", "fallback": "†", "trajectory-model": "~"}.get(it["flag"] or "", "")
                mk = fig.text(xl + tw - 0.009, yc + rh * 0.27, mark, fontsize=14, ha="right", va="center",
                              color=DIM)
                row.append((p, sym, ex, mk, it["hex"]))
            self.tiles.append(row)

    def update(self, t):
        cur = None
        lit = set()
        for t_on, r, j in self.sched:
            if t >= t_on:
                lit.add((r, j))
                if t < t_on + self.STEP:
                    cur = (r, j)
        cur_row = None
        if self.sched and self.INTRO <= t < self.t_end:
            cur_row = max((r for t_on, r, j in self.sched if t >= t_on - self.CLS_GAP), default=None)
        for r, row in enumerate(self.tiles):
            lab, cnt = self.lbls[r]
            lab.set_color(ACC if r == cur_row else (TXT if any((r, j) in lit for j in range(len(row))) else DIM))
            for j, (p, sym, ex, mk, h) in enumerate(row):
                on = (r, j) in lit
                p.set_facecolor(h if on else TILE_OFF)
                p.set_edgecolor(ACC if (r, j) == cur else (h if on else TILE_EDGE))
                p.set_linewidth(4.0 if (r, j) == cur else 1.2)
                c = ink(h) if on else DIM
                for a in (sym, ex, mk):
                    a.set_color(c)
        return (len(lit), cur, cur_row)


class Fricative(Scene):
    dur = 17.5
    # cue times (s): envelope, film, colour, synth voice, butterflies, spectra, caveat
    TE, TF, TC, TV, TB, TS, TK = 0.4, 4.2, 8.0, 9.0, 11.0, 11.8, 14.0
    SID = "s"

    def __init__(self):
        super().__init__()
        it, snd = ITEMS[self.SID], SOUNDS[self.SID]
        self.it, self.snd = it, snd
        ni = it["nearest_insect"]
        best = max(PE["items"], key=lambda x: x["nearest_insect"]["spectral_corr"])
        self.best = best
        self.cues = [(0.6, "web/" + snd["audio"], 1.2), (self.TV, "web/" + snd["audio_synth"], 1.0)]
        self.captions = [
            (0.2, self.TF, f"One fricative: /{it['ipa']}/ as in '{it['example']}'. Its LPC envelope is the hiss "
                       f"shaped by the mouth: most energy high up."),
            (self.TF, self.TC, "Layer peeling turns the 16 reflection coefficients into 16 film layers: "
                       "bars of refractive index, each of equal optical thickness."),
            (self.TC, self.TB, f"That film reflects daylight as {it['hex']}. Played back, the film has a voice too."),
            (self.TB, self.TK, f"Its nearest butterfly: the {ni['name']} film, spectral shape correlation "
                         f"ρ = {ni['spectral_corr']:.2f}, ΔE00 = {ni['dE00']:.1f}."),
            (self.TK, self.dur + 1, f"Caveat: same shape, not the same strength: peak R {it['R_peak']:.2f} for "
                         f"/{it['ipa']}/ vs {it['R_peak_nearest']:.2f}. "
                         f"(Best match overall: [{best['ipa']}], ρ = {best['nearest_insect']['spectral_corr']:.2f}.)"),
        ]
        a = np.array(snd["a"], float)
        self.f = np.linspace(0, mp.FS / 2, 400)
        z = np.exp(-1j * np.outer(2 * np.pi * self.f / mp.FS, np.arange(len(a))))
        env = 20 * np.log10(snd["gain"] / np.abs(z @ a))
        self.env = env - env.max()
        self.n, self.d = film_of(a)
        self.R, _ = film.film_rt(self.n, self.d, col.WL)
        bn, bd = bfly_named(ni["name"])
        self.Rb, _ = film.film_rt(bn, bd, col.WL)
        self.bhex = next(b["hex"] for b in PE["butterflies"] if b["name"] == ni["name"])
        self.check = dict(R_peak=float(self.R.max()), R_peak_nearest=float(self.Rb.max()),
                          hex_recomputed=disp_hex(self.R), hex_json=it["hex"],
                          rho_recomputed=float(np.corrcoef(self.R, self.Rb)[0, 1]))

    def build(self, fig):
        it = self.it
        fig.text(0.5, 0.905, f"/{it['ipa']}/  '{it['example']}'  —  sound → film → colour → butterfly",
                 fontsize=26, ha="center", color=TXT)
        # (a) envelope
        self.ax1 = ax = fig.add_axes([0.05, 0.53, 0.26, 0.30])
        ax.set_xlim(0, 8)
        ax.set_ylim(min(-60, self.env.min() - 3), 5)
        ax.set_xlabel("frequency (kHz)", fontsize=13)
        ax.set_ylabel("LPC envelope (dB)", fontsize=13)
        ax.tick_params(labelsize=11)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        self.l_env, = ax.plot([], [], color=SOUND, lw=3)
        ax.set_title("1  sound: all-pole envelope", fontsize=15, color=SOUND, loc="left")
        # (b) film bars
        self.ax2 = ax = fig.add_axes([0.38, 0.53, 0.28, 0.30])
        n = self.n
        ax.set_xlim(-0.7, len(n) - 0.3)
        ax.set_ylim(0, 2.75)
        ax.set_ylabel("refractive index n", fontsize=13)
        ax.set_xticks([0, len(n) - 1], ["incident", "exit"], fontsize=11)
        ax.tick_params(labelsize=11)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        lo, hi = np.log(n.min()), np.log(n.max())
        self.bars = []
        for i, v in enumerate(n):
            t = 0 if hi <= lo else (np.log(v) - lo) / (hi - lo)
            c = np.array(hex_rgb("#17325c")) * (1 - t) + np.array(hex_rgb("#a8ecff")) * t
            if i in (0, len(n) - 1):
                c = hex_rgb("#3a4252")
            self.bars.append(ax.add_patch(Rectangle((i - 0.4, 0), 0.8, 0.0, fc=c, ec="none")))
        ax.set_title(f"2  film: {len(n) - 2} Goupillaud layers, n·d = {mp.D_OPT_FULL_NM:.1f} nm",
                     fontsize=15, color=LIGHT, loc="left")
        self.n_note = ax.text(0.02, 0.97, f"n = {n.min():.2f} … {n.max():.2f}", transform=ax.transAxes,
                              ha="left", va="top", fontsize=12, color=DIM)
        # (c) swatch
        self.sw = FancyBboxPatch((0.73, 0.545), 0.22, 0.27, boxstyle="round,pad=0,rounding_size=0.015",
                                 transform=fig.transFigure, fc=it["hex"], ec="#ffffff", lw=1.2)
        fig.add_artist(self.sw)
        self.sw_t = fig.text(0.84, 0.68, f"/{it['ipa']}/\n{it['hex']}", fontsize=26, ha="center", va="center",
                             color=ink(it["hex"]))
        self.sw_h = fig.text(0.73, 0.84, "3  colour: reflected, D65, 0°", fontsize=15, color=ACC)
        self.arrows = [fig.text(0.335, 0.68, "→", fontsize=40, ha="center", va="center", color=DIM),
                       fig.text(0.695, 0.68, "→", fontsize=40, ha="center", va="center", color=DIM)]
        # bottom: butterflies + spectra
        self.ax3 = ax = fig.add_axes([0.03, 0.12, 0.40, 0.33])
        ax.set_xlim(-4.4, 4.4)
        ax.set_ylim(-1.75, 1.6)
        ax.set_aspect("equal")
        ax.axis("off")
        ni = it["nearest_insect"]
        self.bf = draw_butterfly(ax, -2.1, 0.05, 1.05, it["hex"]) + draw_butterfly(ax, 2.1, 0.05, 1.05, self.bhex)
        self.bf += [ax.text(-2.1, -1.55, f"/{it['ipa']}/ film", ha="center", fontsize=15, color=TXT),
                    ax.text(2.1, -1.55, ni["name"], ha="center", fontsize=15, color=TXT),
                    ax.text(0, 0.05, f"ρ = {ni['spectral_corr']:.2f}\nΔE00 {ni['dE00']:.1f}", ha="center",
                            va="center", fontsize=15, color=ACC)]
        self.ax4 = ax = fig.add_axes([0.48, 0.15, 0.22, 0.25])
        wl = col.WL
        ax.plot(wl, self.R / self.R.max(), color=it["hex"], lw=2.5, label=f"/{it['ipa']}/")
        ax.plot(wl, self.Rb / self.Rb.max(), color=self.bhex, lw=2.5, ls="--", label=ni["name"])
        ax.set_xlim(380, 780)
        ax.set_ylim(0, 1.08)
        ax.set_title("shape (each ÷ its own peak)", fontsize=14, color=TXT, loc="left")
        ax.set_xlabel("wavelength (nm)", fontsize=12)
        ax.legend(fontsize=11, frameon=False, labelcolor=TXT, loc="upper right")
        self.ax5 = ax2 = fig.add_axes([0.76, 0.15, 0.21, 0.25])
        ax2.plot(wl, self.R, color=it["hex"], lw=2.5)
        ax2.plot(wl, self.Rb, color=self.bhex, lw=2.5, ls="--")
        ax2.set_xlim(380, 780)
        ax2.set_ylim(0, 1.0)
        ax2.set_title("absolute reflectance R", fontsize=14, color=TXT, loc="left")
        ax2.set_xlabel("wavelength (nm)", fontsize=12)
        ax2.text(0.03, 0.93, f"peak {it['R_peak']:.2f} vs {it['R_peak_nearest']:.2f}", transform=ax2.transAxes,
                 fontsize=13, color=APPROX, va="top")
        for a in (ax, ax2):
            a.tick_params(labelsize=10)
            for s in ("top", "right"):
                a.spines[s].set_visible(False)
        self.cav = tag_text(fig, 0.5, 0.468, "approx",
                            f"same hue & shape, but /{it['ipa']}/ reflects ~{it['R_peak'] / it['R_peak_nearest']:.0%}"
                            f" as strongly (swatches are exposure-normalised)", size=15, ha="center")

    def update(self, t):
        TE, TF, TC, TB, TS, TK = self.TE, self.TF, self.TC, self.TB, self.TS, self.TK
        u1 = ease((t - TE - 0.4) / 3.0)
        m = max(2, int(u1 * len(self.f)))
        self.l_env.set_data(self.f[:m] / 1000, self.env[:m])
        self.ax1.set_visible(t >= TE)
        self.ax2.set_visible(t >= TF)
        nb = len(self.bars)
        for i, b in enumerate(self.bars):
            u = ease((t - TF - 0.3 - i * 0.18) / 0.5)
            b.set_height(self.n[i] * u)
        self.arrows[0].set_visible(t >= TF - 0.2)
        self.arrows[1].set_visible(t >= TC - 0.2)
        for a in (self.sw, self.sw_t, self.sw_h):
            a.set_visible(t >= TC)
        self.ax3.set_visible(t >= TB)
        for a in (self.ax4, self.ax5):
            a.set_visible(t >= TS)
        self.cav.set_visible(t >= TK)
        bar_state = tuple(round(min(1, max(0, (t - TF - 0.3 - i * 0.18) / 0.5)), 2) for i in range(nb))
        return (m, bar_state) + tuple(t >= x for x in (TE, TF - 0.2, TF, TC - 0.2, TC, TB, TS, TK))


class Gamut(Scene):
    STEP, T0 = 1.0, 1.0

    def __init__(self):
        super().__init__()
        self.dur = self.T0 + self.STEP * len(CLASSES) + 4.5
        self.t_all = self.T0 + self.STEP * len(CLASSES)
        tot = sum(c["views"][PE["settings"]["view"]]["n_colours"] for c in CLASSES)
        lo = min(c["distinct_colours"] for c in CLASSES)
        hi = max(c["distinct_colours"] for c in CLASSES)
        self.allvalid = all(c["views"][PE["settings"]["view"]]["all_valid"] for c in CLASSES)
        self.tot, self.lo, self.hi = tot, lo, hi
        self.captions = [
            (0.2, self.t_all, f"Every valid colour of each class in the a*b* plane: all frames of every recording, "
                              f"viewed at {', '.join(str(a) for a in PE['settings']['angles_deg'])}°."),
            (self.t_all, self.dur + 1,
             f"No class is limited to one or two colours: {lo}–{hi} distinct colours per class, and in every class "
             f"3 colours lie more than ΔE00 = {PE['settings']['cluster_dE00']:g} apart. So we show them all."),
        ]

    def build(self, fig):
        fig.text(0.5, 0.905, "The colour gamut of each phoneme class", fontsize=28, ha="center", color=TXT)
        self.ax = ax = fig.add_axes([0.04, 0.13, 0.42, 0.72])
        ax.set_xlim(-105, 105)
        ax.set_ylim(-105, 105)
        ax.set_aspect("equal")
        ax.axhline(0, color="#2a3140", lw=1)
        ax.axvline(0, color="#2a3140", lw=1)
        ax.set_xlabel("a*  (green ← → red)", fontsize=13)
        ax.set_ylabel("b*  (blue ← → yellow)", fontsize=13)
        ax.tick_params(labelsize=11)
        self.sc, self.hull = [], []
        for c in CLASSES:
            ab = np.array(c["gamut"]["ab"], float)
            s = ax.scatter(ab[:, 0], ab[:, 1], c=c["gamut"]["hexes"], s=9, lw=0, alpha=0.9)
            s.set_visible(False)
            self.sc.append(s)
            h = np.array(c["gamut"]["hull_ab"] + c["gamut"]["hull_ab"][:1], float)
            ln, = ax.plot(h[:, 0], h[:, 1], color=TXT, lw=1.6)
            ln.set_visible(False)
            self.hull.append(ln)
        # right: class table
        fig.text(0.52, 0.83, "class", fontsize=15, color=DIM)
        fig.text(0.68, 0.83, "distinct", fontsize=15, color=DIM)
        fig.text(0.77, 0.83, "3 colours, pairwise ΔE00", fontsize=15, color=DIM)
        self.rows = []
        for i, c in enumerate(CLASSES):
            y = 0.78 - i * 0.068
            arts = [fig.text(0.52, y, c["label"], fontsize=19, color=TXT, va="center"),
                    fig.text(0.70, y, str(c["distinct_colours"]), fontsize=19, color=ACC, va="center", ha="center")]
            mc = c["many_certificate"]
            for k, h in enumerate(mc["hexes"]):
                p = FancyBboxPatch((0.77 + k * 0.036, y - 0.022), 0.03, 0.044,
                                   boxstyle="round,pad=0,rounding_size=0.005", transform=fig.transFigure, fc=h,
                                   ec="none")
                fig.add_artist(p)
                arts.append(p)
            arts.append(fig.text(0.885, y, "  ".join(f"{v:.0f}" for v in mc["pairwise_dE00"]), fontsize=15,
                                 color=TXT, va="center"))
            for a in arts:
                a.set_visible(False)
            self.rows.append(arts)
        self.msg = tag_text(fig, 0.52, 0.175, "exact",
                            f"{self.tot} colours plotted, {'all' if self.allvalid else 'NOT all'} from realizable films",
                            size=15)

    def update(self, t):
        k = int(np.floor((t - self.T0) / self.STEP)) + 1 if t >= self.T0 else 0
        k = min(k, len(CLASSES))
        final = t >= self.t_all
        for i in range(len(CLASSES)):
            on = i < k
            self.sc[i].set_visible(on)
            self.sc[i].set_alpha(0.9 if (final or i == k - 1) else 0.22)
            self.hull[i].set_visible(on and i == k - 1 and not final)
            for a in self.rows[i]:
                a.set_visible(on)
        self.msg.set_visible(t >= self.t_all + 1.0)
        return (k, final, t >= self.t_all + 1.0)


class Angle(Scene):
    dur = 9.0
    IDS = ["i", "a", "m", "s", "l", "w"]
    T0, T1 = 1.0, 6.4

    def __init__(self):
        super().__init__()
        self.ids = [i for i in self.IDS if i in ITEMS]
        self.th = np.round(np.arange(0, 60.0 + 1e-9, 0.5), 1)
        self.hexes = {}
        self.max_mismatch = 0.0
        for sid in self.ids:
            n, d = film_of(SOUNDS[sid]["a"])
            hs = [disp_hex(film.film_rt(n, d, col.WL, float(a))[0]) for a in self.th]
            self.hexes[sid] = hs
            for a, hj in zip(PE["settings"]["angles_deg"], ITEMS[sid]["angle_hexes"]):
                hc = hs[int(round(a / 0.5))]
                self.max_mismatch = max(self.max_mismatch, float(np.abs(hex_rgb(hc) - hex_rgb(hj)).max() * 255))
        lv = [c["levels"]["item_angles"]["distinct"] for c in CLASSES]
        self.captions = [
            (0.2, 4.5, "Iridescence: tilt each film from 0° to 60° and its reflected colour drifts, "
                       "like a wing turning in the light."),
            (4.5, self.dur + 1, f"Tilting alone multiplies the colours: one film per phoneme × 5 angles already "
                                f"gives {min(lv)}–{max(lv)} distinct colours per class."),
        ]

    def build(self, fig):
        fig.text(0.5, 0.905, "Iridescence: the same films, tilted", fontsize=28, ha="center", color=TXT)
        self.ax = ax = fig.add_axes([0.05, 0.16, 0.20, 0.62])
        ax.set_xlim(-1.2, 1.2)
        ax.set_ylim(-1.2, 1.6)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.add_patch(Rectangle((-1.0, -0.12), 2.0, 0.12, fc="#3a4252", ec="none"))
        ax.plot([0, 0], [0, 1.3], color=DIM, lw=1, ls=":")
        self.ray, = ax.plot([], [], color=ACC, lw=3)
        self.ray2, = ax.plot([], [], color=LIGHT, lw=3)
        self.ang_t = ax.text(0, -0.55, "", ha="center", fontsize=26, color=ACC)
        ax.text(0, -0.85, "angle of incidence", ha="center", fontsize=13, color=DIM)
        self.rows = []
        nr = len(self.ids)
        x0, x1 = 0.39, 0.95
        self.x0, self.x1 = x0, x1
        for r, sid in enumerate(self.ids):
            it = ITEMS[sid]
            y = 0.80 - r * (0.62 / max(1, nr - 1))
            fig.text(0.27, y, f"/{it['ipa']}/", fontsize=24, color=TXT, va="center")
            fig.text(0.27, y - 0.035, it["class"], fontsize=11, color=DIM, va="center")
            sw = FancyBboxPatch((0.34, y - 0.035), 0.035, 0.07, boxstyle="round,pad=0,rounding_size=0.006",
                                transform=fig.transFigure, fc=it["hex"], ec="#ffffff", lw=1)
            fig.add_artist(sw)
            img = fig.add_axes([x0, y - 0.03, x1 - x0, 0.06])
            img.axis("off")
            rgb = np.array([[hex_rgb(h) for h in self.hexes[sid]]])
            im = img.imshow(rgb, aspect="auto", interpolation="nearest", extent=(0, 60, 0, 1))
            img.set_xlim(0, 60)
            self.rows.append((sw, im, img, sid))
        axl = fig.add_axes([x0, 0.12, x1 - x0, 0.01])
        axl.set_xlim(0, 60)
        axl.set_yticks([])
        axl.set_xticks(PE["settings"]["angles_deg"], [f"{a}°" for a in PE["settings"]["angles_deg"]])
        axl.tick_params(labelsize=13)
        for s in ("top", "right", "left"):
            axl.spines[s].set_visible(False)

    def theta(self, t):
        return float(np.round(60 * ease((t - self.T0) / (self.T1 - self.T0)) * 2) / 2)

    def update(self, t):
        th = self.theta(t)
        i = int(round(th / 0.5))
        r = np.radians(th)
        self.ray.set_data([-1.3 * np.sin(r), 0], [1.3 * np.cos(r), 0])
        self.ray2.set_data([0, 1.3 * np.sin(r)], [0, 1.3 * np.cos(r)])
        self.ang_t.set_text(f"θ = {th:.0f}°")
        for sw, im, img, sid in self.rows:
            sw.set_facecolor(self.hexes[sid][i])
            img.set_xlim(0, max(th, 0.25))
            img.set_position([self.x0, img.get_position().y0, (self.x1 - self.x0) * max(th, 0.25) / 60,
                              img.get_position().height])
        return th


class Diphthong(Scene):
    dur = 7.5
    SID = "ai"
    PLAYS = (0.9, 2.4, 3.9, 5.4)
    PLAY_DUR = 0.5

    def __init__(self):
        super().__init__()
        snd = SOUNDS[self.SID]
        self.snd = snd
        self.traj = snd["trajectory"]
        self.PLAY_DUR = float(snd["duration_s"])
        self.cues = [(t, "web/" + snd["audio_synth"], None) for t in self.PLAYS]
        e = snd["endpoints"]
        self.captions = [
            (0.2, 3.9, f"A diphthong is a moving film. /{snd['ipa']}/ as in '{snd['example']}' glides from "
                       f"/{e['start']['ipa']}/ to /{e['end']['ipa']}/, and its colour glides with it."),
            (3.9, self.dur + 1, f"{len(self.traj)} interpolation steps between the two vowel polynomials "
                                f"(log-area ratios); the sound is the film's own synthesised voice."),
        ]

    def build(self, fig):
        snd = self.snd
        e = snd["endpoints"]
        fig.text(0.5, 0.905, f"/{snd['ipa']}/  '{snd['example']}': a colour trajectory", fontsize=28, ha="center",
                 color=TXT)
        self.sw = FancyBboxPatch((0.06, 0.40), 0.24, 0.38, boxstyle="round,pad=0,rounding_size=0.02",
                                 transform=fig.transFigure, fc=self.traj[0], ec="#ffffff", lw=1.2)
        fig.add_artist(self.sw)
        self.sw_t = fig.text(0.18, 0.59, "", fontsize=30, ha="center", va="center")
        # strip
        axs = fig.add_axes([0.06, 0.25, 0.42, 0.08])
        axs.imshow(np.array([[hex_rgb(h) for h in self.traj]]), aspect="auto", interpolation="nearest",
                   extent=(0, 1, 0, 1))
        axs.set_xlim(0, 1)
        axs.set_ylim(0, 1)
        axs.axis("off")
        self.cur, = axs.plot([0, 0], [-0.1, 1.1], color=TXT, lw=4, clip_on=False)
        fig.text(0.06, 0.21, f"/{e['start']['ipa']}/", fontsize=22, color=TXT, va="top")
        fig.text(0.48, 0.21, f"/{e['end']['ipa']}/", fontsize=22, color=TXT, va="top", ha="right")
        # a*b* path
        self.ax = ax = fig.add_axes([0.56, 0.20, 0.38, 0.62])
        lab = np.array([hex_lab(h) for h in self.traj])
        self.ab = lab[:, 1:]
        ax.plot(self.ab[:, 0], self.ab[:, 1], color=DIM, lw=1.5)
        ax.scatter(self.ab[:, 0], self.ab[:, 1], c=self.traj, s=70, lw=0, zorder=3)
        pad = 12
        ax.set_xlim(self.ab[:, 0].min() - pad, self.ab[:, 0].max() + pad)
        ax.set_ylim(self.ab[:, 1].min() - pad, self.ab[:, 1].max() + pad)
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlabel("a*", fontsize=13)
        ax.set_ylabel("b*", fontsize=13)
        ax.tick_params(labelsize=11)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.set_title("path in a*b* (display colours)", fontsize=14, color=DIM, loc="left")
        self.dot, = ax.plot([], [], "o", ms=20, mfc="none", mec=TXT, mew=3, zorder=4)
        tag_text(fig, 0.06, 0.12, "approx", "trajectory model (no recording); LAR interpolation /a/ → /ɪ/",
                 size=14)

    def update(self, t):
        u = 0.0
        for t0 in self.PLAYS:
            if t >= t0:
                u = min(1.0, (t - t0) / self.PLAY_DUR)
        i = int(round(u * (len(self.traj) - 1)))
        h = self.traj[i]
        self.sw.set_facecolor(h)
        self.sw_t.set_text(h)
        self.sw_t.set_color(ink(h))
        self.cur.set_xdata([i / (len(self.traj) - 1) * 0.985 + 0.0075] * 2)
        self.dot.set_data([self.ab[i, 0]], [self.ab[i, 1]])
        return i


class Caveats(Scene):
    dur = 8.5

    def __init__(self):
        super().__init__()
        self.captions = [(0.2, self.dur + 1, "What to keep in mind: these are experiments, labelled as such.")]

    def build(self, fig):
        mod = [it["ipa"] for it in PE["items"] if it["modelled"]]
        fb = [it["ipa"] for it in PE["items"] if it["flag"] == "fallback"]
        tr = [it["ipa"] for it in PE["items"] if it["flag"] == "trajectory-model"]
        tot = sum(c["views"][PE["settings"]["view"]]["n_colours"] for c in CLASSES)
        fig.text(0.5, 0.86, "Caveats", fontsize=40, ha="center", color=TXT, weight="bold")
        lines = [
            ("approx", f"Modelled phonemes (no clean recording): {' '.join(mod)}; diphthongs {' '.join(tr)} "
                       f"are interpolated trajectories."),
            ("approx", "All-pole LPC is an envelope model: nasals have zeros, fricatives and plosives have their\n"
                       "source inside the tract. The film is exact for the polynomial; the tube reading is not."),
            ("approx", f"Fallback plosives {' '.join(fb)}: the burst is too short, so the context vowel is "
                       f"averaged in."),
            ("art", "Swatches are exposure-normalised; most phoneme films reflect far less than a Morpho wing."),
            ("exact", f"All {tot} colours shown come from realizable films (n 1–2.5, |k| < 1, R + T = 1 checked)."),
        ]
        self.arts = []
        for i, (k, s) in enumerate(lines):
            self.arts.append(tag_text(fig, 0.06, 0.73 - i * 0.12, k, s, size=18))

    def update(self, t):
        k = 0
        for i, a in enumerate(self.arts):
            on = t >= 0.4 + i * 0.7
            a.set_visible(on)
            k += on
        return k


class End(Scene):
    dur = 5.0

    def __init__(self):
        super().__init__()
        self.captions = [(0.3, 6, "Every phoneme has a film, and every film has colours. "
                                  "Explore them all on the Experiments page.")]

    def build(self, fig):
        fig.text(0.5, 0.60, "Every phoneme has a film.", fontsize=46, ha="center", color=TXT, weight="bold")
        fig.text(0.5, 0.50, "Every film has colours.", fontsize=46, ha="center", color=ACC, weight="bold")
        fig.text(0.5, 0.36, "Experiments page  ·  web/data/phonemes_experiment.json  ·  report section 10",
                 fontsize=20, ha="center", color=DIM)
        cols = [it["hex"] for it in PE["items"]]
        w = 0.8 / len(cols)
        for i, h in enumerate(cols):
            fig.add_artist(Rectangle((0.1 + i * w, 0.25), w * 0.92, 0.03, transform=fig.transFigure, fc=h,
                                     ec="none"))

    def update(self, t):
        return 0


SCENES = [Title, Chart, Fricative, Gamut, Angle, Diphthong, Caveats, End]


# ----------------------------------------------------------------------------------------------- audio
def pad_bed(n):
    """Same soft pad as video/assemble.py (~ -32 dBFS), so the join is seamless."""
    t = np.arange(n) / SR
    freqs = [110.0, 164.81, 220.0, 261.63, 329.63, 493.88]
    amps = [1.0, 0.7, 0.6, 0.45, 0.35, 0.18]
    y = np.zeros(n)
    for i, (f, a) in enumerate(zip(freqs, amps)):
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.03 + 0.011 * i) * t + i)
        y += a * lfo * np.sin(2 * np.pi * f * t + 0.7 * i) * (1 + 0.002 * np.sin(2 * np.pi * 0.2 * t))
    y /= np.sqrt(np.mean(y ** 2))
    y *= 10 ** (-32 / 20)
    fade = int(3 * SR)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return y * env


def clip(rel, excerpt):
    y, fs = sf.read(str(ROOT / rel), dtype="float64", always_2d=True)
    y = y.mean(1)
    if fs != SR:
        from math import gcd
        g = gcd(SR, fs)
        y = resample_poly(y, SR // g, fs // g)
    if excerpt and len(y) > excerpt * SR:          # loudest window of `excerpt` s
        L = int(excerpt * SR)
        e = np.convolve(y ** 2, np.ones(L // 8), "same")
        c = int(np.argmax(e))
        i0 = int(np.clip(c - L // 2, 0, len(y) - L))
        y = y[i0:i0 + L].copy()
    f = min(len(y) // 4, int(0.015 * SR))
    if f > 0:
        y[:f] *= np.linspace(0, 1, f)
        y[-f:] *= np.linspace(1, 0, f)
    rms = np.sqrt(np.mean(y ** 2)) + 1e-12
    y *= min(10 ** (-20 / 20) / rms, 0.7 / (np.abs(y).max() + 1e-12))   # ~ -20 dBFS RMS, peak <= 0.7
    return y


# ----------------------------------------------------------------------------------------------- render
def render(q="h", snaps=None):
    W, H, res = QUAL[q]
    dpi = W / 19.2
    scenes = [S() for S in SCENES]
    total_frames = sum(int(round(s.dur * FPS)) for s in scenes)
    total = total_frames / FPS
    # audio
    n = int(round(total * SR))
    mix = pad_bed(n)
    t0, cues, caps = 0.0, [], []
    for s in scenes:
        for t, rel, ex in s.cues:
            y = clip(rel, ex)
            i0 = int(round((t0 + t) * SR))
            mix[i0:i0 + len(y)] += y[: max(0, n - i0)]
            cues.append(dict(t=round(t0 + t, 3), wav=rel, scene=type(s).__name__))
        for a, b, txt in s.captions:
            caps.append(dict(t0=round(t0 + a, 2), t1=round(t0 + min(b, s.dur), 2), scene=type(s).__name__,
                             text=txt))
        t0 += int(round(s.dur * FPS)) / FPS
    mix *= min(1.0, 0.97 / np.abs(mix).max())
    FINAL.mkdir(exist_ok=True)
    wav = FINAL / f"_phonemes_audio_{res}.wav"
    sf.write(str(wav), mix.astype(np.float32), SR, subtype="PCM_16")
    checks = {type(s).__name__: s.check for s in scenes if hasattr(s, "check")}
    checks["Angle_max_rgb_mismatch_vs_json_0_15_30_45_60"] = next(s for s in scenes if isinstance(s, Angle)).max_mismatch
    (FINAL / f"timeline_phonemes_{res}.json").write_text(json.dumps(dict(
        duration=total, frames=total_frames, fps=FPS, scenes=[dict(scene=type(s).__name__, dur=s.dur) for s in scenes],
        captions=caps, cues=cues, checks=checks), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[seg] {res}: {total:.2f} s, {total_frames} frames, {len(cues)} audio cues; checks {checks}", flush=True)

    out = FINAL / ("phonemes_segment_1080p.mp4" if q == "h" else f"phonemes_segment_{res}.mp4")
    proc = None
    if snaps is None:
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium",
               "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p", "-video_track_timescale", "15360",
               "-c:a", "aac", "-b:a", "96k", "-ar", str(SR), "-ac", "1", "-movflags", "+faststart", str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    bg = (hex_rgb(BG) * 255).astype(np.float32)
    t_glob, drawn = 0.0, 0
    import time
    tic = time.time()
    snap_dir = FINAL / "snaps"
    for s in scenes:
        fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi, facecolor=BG)
        fig.text(0.015, 0.975, "S12 · Every phoneme: an experiment", fontsize=16, color=DIM, va="top")
        cap = fig.text(0.5, 0.045, "", fontsize=19, color=TXT, ha="center", va="center", wrap=False,
                       bbox=dict(boxstyle="round,pad=0.45", fc="#141a24", ec="none", alpha=0.92))
        s.build(fig)
        nf = int(round(s.dur * FPS))
        last_key, buf = None, None
        for i in range(nf):
            t = i / FPS
            tg = t_glob + t
            if snaps is not None and not any(abs(tg - x) < 0.5 / FPS for x in snaps):
                continue
            key = s.update(t)
            c = s.caption_at(t)
            cap.set_text(textwrap.fill(c, 124))
            cap.set_visible(bool(c))
            key = (key, c)
            if key != last_key:
                fig.canvas.draw()
                buf = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
                last_key = key
                drawn += 1
            a = min(1.0, t / FADE, (s.dur - t) / FADE)
            frame = buf if a >= 1 else (buf.astype(np.float32) * a + bg * (1 - a)).astype(np.uint8)
            if snaps is not None:
                snap_dir.mkdir(exist_ok=True)
                plt.imsave(snap_dir / f"snap_{tg:06.2f}.png", frame)
            else:
                proc.stdin.write(frame.tobytes())
        plt.close(fig)
        t_glob += nf / FPS
        print(f"[seg] {type(s).__name__} done at {t_glob:.1f} s ({time.time() - tic:.0f} s wall, {drawn} draws)",
              flush=True)
    if proc:
        proc.stdin.close()
        if proc.wait() != 0:
            sys.exit("ffmpeg failed")
        print(f"[seg] wrote {out.relative_to(ROOT)}", flush=True)
    return caps, total


# ----------------------------------------------------------------------------------------------- concat
def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_name,codec_type,width,height,r_frame_rate,pix_fmt,sample_rate,channels,profile,"
                        "time_base,duration", "-of", "json", str(p)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"]


def concat():
    web = WEB / "video" / "explainer.mp4"
    orig = FINAL / "explainer_original_1080p.mp4"
    seg = FINAL / "phonemes_segment_1080p.mp4"
    if not orig.exists():
        shutil.copy2(web, orig)
        print(f"[concat] backed up original -> {orig.relative_to(ROOT)}")
    keys = ("codec_name", "width", "height", "r_frame_rate", "pix_fmt", "sample_rate", "channels", "profile",
            "time_base")
    a = [{k: s.get(k) for k in keys} for s in probe(orig)]
    b = [{k: s.get(k) for k in keys} for s in probe(seg)]
    print("[concat] original:", a, "\n[concat] segment: ", b)
    tmp = FINAL / "_explainer_concat.mp4"
    if a == b:
        lst = FINAL / "_concat.txt"
        lst.write_text(f"file '{orig.resolve()}'\nfile '{seg.resolve()}'\n", encoding="utf-8")
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
               "-movflags", "+faststart", str(tmp)]
    else:
        print("[concat] stream parameters differ -> re-encoding")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(orig), "-i", str(seg), "-filter_complex",
               "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
               "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ar",
               str(SR), "-ac", "1", "-movflags", "+faststart", str(tmp)]
    subprocess.run(cmd, check=True)
    shutil.move(str(tmp), str(web))
    print("[concat] ->", web.relative_to(ROOT), probe(web))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quality", default="h", choices=list(QUAL))
    ap.add_argument("--concat", action="store_true")
    ap.add_argument("--snap", nargs="*", type=float)
    a = ap.parse_args(argv)
    if a.concat:
        return concat()
    if a.snap:
        return render("l" if a.quality == "h" else a.quality, snaps=a.snap)
    render(a.quality)


if __name__ == "__main__":
    main()
