"""Manim CE explainer: "Vowels That Shine, Butterflies That Speak".

One Scene per section (S01..S11). Every plotted curve / colour comes from video/data/scene_data.json, which
video/prep_data.py computes with core/ (and web/data/*.json). Equations: video/eqs/*.svg (matplotlib mathtext,
NO LaTeX). Each scene logs its sound cues (time, wav) to video/media/cues/<res>/<Scene>.json; video/assemble.py
mixes the real audio at those timestamps after rendering.

Render everything:  .\\video\\render.ps1   (see that file)
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
from manim import *  # noqa: F401,F403

# --------------------------------------------------------------------------------------------------
# LaTeX is forbidden in this project (TinyTeX would write caches outside the folder). Fail loudly.
# --------------------------------------------------------------------------------------------------
import manim.utils.tex_file_writing as _tfw  # noqa: E402
import manim.mobject.text.tex_mobject as _tm  # noqa: E402


def _no_tex(*_a, **_k):
    raise RuntimeError("LaTeX is forbidden in this project: use eq(...) (mathtext SVG) or Text.")


_tfw.tex_to_svg_file = _no_tex
_tm.tex_to_svg_file = _no_tex
_tm.SingleStringMathTex.__init__ = _no_tex

ROOT = Path(__file__).resolve().parents[1]
VID = ROOT / "video"
EQ_DIR = VID / "eqs"
D = json.loads((VID / "data" / "scene_data.json").read_text(encoding="utf-8"))
K = D["constants"]

# ---------------------------------------- style ---------------------------------------------------
BG = "#0b0e14"
TXT = "#e9ecf1"
DIM = "#8a93a3"
SOUND = "#f4a259"      # warm = acoustics
LIGHT = "#6cc7ff"      # cool = optics
ACC = "#ffd166"
EXACT = "#7bd389"
APPROX = "#f6c85f"
ART = "#ff8fab"
FONT = "Segoe UI"
config.background_color = BG


def T(s, size=28, color=TXT, **kw):
    return Text(s, font=FONT, font_size=size, color=color, **kw)


def eq(name, scale=1.0, color=TXT):
    """Load a mathtext SVG with a consistent glyph size (size taken from the SVG's pt height)."""
    path = EQ_DIR / f"{name}.svg"
    head = path.read_text(encoding="utf-8")[:600]
    h_pt = float(head.split('height="')[1].split("pt")[0])
    m = SVGMobject(str(path))
    m.set_fill(color, 1).set_stroke(width=0)
    m.height = h_pt * 0.0105 * scale
    return m


def tag(s, kind="art", size=17):
    c = {"art": ART, "exact": EXACT, "approx": APPROX}[kind]
    head = {"art": "ARTISTIC LICENSE", "exact": "EXACT PHYSICS", "approx": "APPROXIMATE"}[kind]
    t = T(f"{head}: {s}", size, c)
    box = SurroundingRectangle(t, buff=0.09, color=c, stroke_width=1.4, corner_radius=0.06)
    return VGroup(box, t)


def n_colour(n, lo, hi):
    t = 0.0 if hi <= lo else float(np.clip((np.log(n) - np.log(lo)) / (np.log(hi) - np.log(lo)), 0, 1))
    return interpolate_color(ManimColor("#17325c"), ManimColor("#a8ecff"), t)


def make_axes(xr, yr, xl, yl, xticks=(), yticks=(), xlab="", ylab="", fs=17):
    ax = Axes(x_range=xr, y_range=yr, x_length=xl, y_length=yl, tips=False,
              axis_config=dict(color=DIM, stroke_width=2, include_ticks=False))
    g = VGroup()
    for v, s in xticks:
        p = ax.c2p(v, yr[0])
        g.add(Line(p, p + DOWN * 0.08, color=DIM, stroke_width=2))
        g.add(T(s, fs, DIM).next_to(p, DOWN, buff=0.13))
    for v, s in yticks:
        p = ax.c2p(xr[0], v)
        g.add(Line(p, p + LEFT * 0.08, color=DIM, stroke_width=2))
        g.add(T(s, fs, DIM).next_to(p, LEFT, buff=0.13))
    if xlab:
        g.add(T(xlab, fs + 1, DIM).next_to(ax, DOWN, buff=0.5))
    if ylab:
        g.add(T(ylab, fs + 1, DIM).rotate(PI / 2).next_to(ax.y_axis, LEFT, buff=0.55))
    return ax, g


def curve(ax, x, y, color, width=3):
    pts = [ax.c2p(a, b) for a, b in zip(x, y)]
    return VMobject(stroke_color=color, stroke_width=width).set_points_as_corners(pts)


def area_under(ax, x, y, color, opacity=0.35):
    pts = [ax.c2p(x[0], 0)] + [ax.c2p(a, b) for a, b in zip(x, y)] + [ax.c2p(x[-1], 0)]
    return Polygon(*pts, stroke_width=0, fill_color=color, fill_opacity=opacity)


def resolve(rel):
    """Audio paths come as 'web/audio/x.wav', 'video/audio/x.wav' or web-relative 'audio/x.wav'."""
    p = ROOT / rel
    if not p.exists():
        p = ROOT / "web" / rel
    if not p.exists():
        raise FileNotFoundError(rel)
    return p


def wav_read(rel):
    p = resolve(rel)
    with wave.open(str(p)) as w:
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float) / 32768
        return y, w.getframerate(), p


def waveform(rel, width=4.0, height=0.7, color=ACC, n=220):
    y, fs, _ = wav_read(rel)
    env = np.array([c.max() for c in np.array_split(np.abs(y), n)])
    env = env / (env.max() + 1e-9)
    xs = np.linspace(-width / 2, width / 2, n)
    top = [[x, height / 2 * e + 0.01, 0] for x, e in zip(xs, env)]
    bot = [[x, -height / 2 * e - 0.01, 0] for x, e in zip(xs, env)][::-1]
    mob = VMobject(stroke_width=1, stroke_color=color, fill_color=color, fill_opacity=0.55)
    mob.set_points_as_corners(top + bot + [top[0]])
    return mob, len(y) / fs


# ---------------------------------------- butterfly ------------------------------------------------
_UP = [(0.06, 0.10), (0.45, 0.75), (1.05, 1.22), (1.62, 1.18), (1.78, 0.80), (1.45, 0.35), (0.85, 0.08), (0.06, 0.02)]
_LO = [(0.06, -0.02), (0.75, -0.12), (1.22, -0.55), (1.12, -1.08), (0.62, -1.22), (0.22, -0.75), (0.06, -0.12)]


def _wing(pts):
    v = VMobject()
    v.set_points_smoothly([np.array([x, y, 0.0]) for x, y in pts] + [np.array([*pts[0], 0.0])])
    return v


def butterfly(hex_col, scale=1.0):
    right = VGroup(_wing(_UP), _wing(_LO))
    left = right.copy().flip(UP, about_point=ORIGIN)
    wings = VGroup(left, right)
    wings.set_fill(hex_col, 1).set_stroke("#0d0d0d", 2)
    body = Ellipse(width=0.16, height=1.5, fill_color="#1c1c22", fill_opacity=1, stroke_width=0)
    ant = VGroup(*[CubicBezier([0, 0.7, 0], [0.05 * s, 1.0, 0], [0.2 * s, 1.15, 0], [0.32 * s, 1.25, 0],
                               stroke_color="#cfcfcf", stroke_width=1.6) for s in (-1, 1)])
    g = VGroup(wings, body, ant).scale(scale)
    return g


def flapping(bfly, lut, speed=1.6, max_tilt=70.0):
    """Wing tilt theta(t) is ARTISTIC (flapping); the colour shown at each tilt is the computed
    reflectance colour at that viewing angle (exact thin-film TMM, D65, from the LUT)."""
    wings, body = bfly[0], bfly[1]
    base = wings.copy()
    bbase = body.copy()
    state = {"ph": 0.0}

    def upd(m, dt):
        state["ph"] += dt * speed
        th = max_tilt * abs(np.sin(state["ph"]))
        idx = int(round(min(th, 80) / 2))
        c = body.get_center()
        s = body.height / bbase.height
        new = base.copy().scale(s, about_point=bbase.get_center()).shift(c - bbase.get_center())
        new.stretch(max(np.cos(np.radians(th)), 0.08), 0, about_point=c)
        op = body.get_fill_opacity()
        new.set_fill(lut[idx], op).set_stroke(opacity=op)
        m.become(new)

    wings.add_updater(upd)
    return state


# ---------------------------------------- base scene ----------------------------------------------
class Base(Scene):
    def setup(self):
        self.cues = []

    def cue(self, rel, gain=0.7):
        """Mark that the wav `rel` starts NOW (assemble.py mixes it in after rendering)."""
        p = resolve(rel).relative_to(ROOT).as_posix()
        self.cues.append(dict(t=float(self.renderer.time), wav=p, gain=gain))

    def play_clip(self, rel, wf, gain=0.7, extra=None):
        mob, dur = wf
        ph = Line(UP * 0.45, DOWN * 0.45, color=TXT, stroke_width=2).move_to(mob.get_left())
        self.add(ph)
        self.cue(rel, gain)
        anims = [ph.animate(rate_func=linear).move_to(mob.get_right())]
        if extra:
            anims += extra
        self.play(*anims, run_time=dur)
        self.remove(ph)

    def tear_down(self):
        out = VID / "media" / "cues" / f"{config.pixel_height}p{int(config.frame_rate)}"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{type(self).__name__}.json").write_text(
            json.dumps(dict(scene=type(self).__name__, duration=float(self.renderer.time), cues=self.cues)),
            encoding="utf-8")

    def section(self, s):
        t = T(s, 22, DIM).to_corner(UL, buff=0.35)
        self.add(t)
        return t

    def clear_all(self, rt=0.8):
        for m in self.mobjects:
            m.clear_updaters()
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=rt)


# ==================================================================================================
class S01_Hook(Base):
    def construct(self):
        b = D["butterflies"][0]
        bf = butterfly(b["lut_rgb"][0], 1.25).shift(UP * 0.7)
        self.play(FadeIn(bf, scale=0.8), run_time=1.5)
        flapping(bf, b["lut_rgb"], speed=2.2, max_tilt=60)
        lic = tag("wing flapping; wing colour at each tilt is computed", "art").to_corner(DR, buff=0.3)
        self.play(FadeIn(lic), run_time=0.5)
        self.wait(0.8)
        wf = waveform(b["audio"], 4.5, 0.7, LIGHT)
        wf[0].shift(DOWN * 2.2)
        lab = T("listen: this is the wing's colour filter, played as a voice", 24, DIM).next_to(wf[0], DOWN, 0.3)
        self.play(FadeIn(wf[0]), FadeIn(lab), run_time=0.6)
        self.play_clip(b["audio"], wf, 0.75)
        self.wait(0.8)
        self.play_clip(b["audio"], wf, 0.75)
        self.wait(1.0)
        title = T("Vowels That Shine,", 54, TXT)
        title2 = T("Butterflies That Speak", 54, LIGHT)
        tt = VGroup(title, title2).arrange(DOWN, buff=0.2).to_edge(UP, buff=0.4)
        self.play(FadeOut(wf[0]), FadeOut(lab), bf.animate.scale(0.7).shift(DOWN * 0.9), run_time=1.0)
        self.play(Write(title), run_time=1.2)
        self.play(Write(title2), run_time=1.2)
        sub = T("one equation for tubes of air and stacks of thin films", 26, DIM).next_to(bf, DOWN, 0.4)
        self.play(FadeIn(sub, shift=UP * 0.2), run_time=0.8)
        self.wait(4.0)
        self.clear_all()


# ==================================================================================================
class S02_Light(Base):
    def construct(self):
        self.section("1 · Light")
        L = D["light"]
        wl = np.array(L["wl"])
        head = eq("C_ER", 1.2).to_edge(UP, buff=0.55)
        self.play(Write(head), run_time=1.2)
        ax, deco = make_axes([380, 780, 50], [0, 1.05, 0.5], 7.0, 3.2,
                             xticks=[(400, "400"), (500, "500"), (600, "600"), (700, "700")],
                             yticks=[(0, "0"), (1, "1")], xlab="wavelength λ (nm)", fs=17)
        VGroup(ax, deco).to_edge(LEFT, buff=0.9).shift(DOWN * 0.95)
        strip = VGroup(*[Rectangle(width=ax.x_length / 70, height=0.12, stroke_width=0,
                                   fill_color=h, fill_opacity=1).move_to(ax.c2p(nu, 0) + DOWN * 0.06)
                         for nu, h in zip(np.linspace(380, 780, 71)[:-1] + 400 / 140,
                                          self._spectral_hex(np.linspace(380, 780, 71)[:-1] + 400 / 140))])
        self.play(Create(ax), FadeIn(deco), FadeIn(strip), run_time=1.2)
        E = curve(ax, wl, L["E"], "#fff4d6", 3)
        leg = VGroup(T("E(λ): daylight D65", 20, "#fff4d6"), T("R(λ): Morpho-like film reflectance", 20, LIGHT),
                     T("C(λ) = E·R: what reaches your eye", 20, ACC)).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        leg.next_to(ax, UP, 0.25).align_to(ax, LEFT).shift(RIGHT * 0.3)
        lE, lR, lC = leg
        self.play(Create(E), FadeIn(lE), run_time=1.5)
        self.wait(1.5)
        R = curve(ax, wl, L["R"], LIGHT, 3)
        self.play(Create(R), FadeIn(lR), run_time=1.5)
        self.wait(1.5)
        C = curve(ax, wl, L["C"], ACC, 4)
        Cf = area_under(ax, wl, L["C"], ACC, 0.3)
        self.play(FadeOut(E, run_time=0.8), ReplacementTransform(R.copy(), C), FadeIn(Cf), FadeIn(lC), run_time=1.6)
        self.wait(1.5)
        # CMFs
        ax2, deco2 = make_axes([380, 780, 100], [0, 1.9, 1], 4.6, 1.9,
                               xticks=[(400, "400"), (550, "550"), (700, "700")], fs=15)
        VGroup(ax2, deco2).to_edge(RIGHT, buff=0.7).shift(UP * 1.05)
        cm = VGroup(curve(ax2, wl, L["xbar"], "#ff6b6b", 3), curve(ax2, wl, L["ybar"], "#7bd389", 3),
                    curve(ax2, wl, L["zbar"], "#5b8cff", 3))
        lcm = T("CIE 1931 colour-matching functions", 19, DIM).next_to(ax2, UP, 0.12)
        lcm2 = T("x̄  ȳ  z̄  (a linear mix of the three cone types)", 16, DIM).next_to(ax2, DOWN, 0.42)
        self.play(Create(ax2), FadeIn(deco2), FadeIn(lcm), run_time=0.8)
        self.play(LaggedStart(*[Create(c) for c in cm], lag_ratio=0.3), FadeIn(lcm2), run_time=1.8)
        xyz = eq("XYZ", 0.62).next_to(lcm2, DOWN, 0.3).to_edge(RIGHT, buff=0.35)
        self.play(FadeIn(xyz, shift=UP * 0.2), run_time=1.0)
        sw = RoundedRectangle(corner_radius=0.12, width=1.6, height=0.9, fill_color=L["hex"], fill_opacity=1,
                              stroke_width=0).next_to(xyz, DOWN, 0.3).shift(LEFT * 0.5)
        lsw = T(f"→ {L['hex']}", 20, TXT).next_to(sw, RIGHT, 0.2)
        self.play(TransformFromCopy(Cf, sw), FadeIn(lsw), run_time=1.5)
        t1 = tag("Morpho-like stack, parameters illustrative", "approx", 15).to_corner(DR, buff=0.25).shift(UP * 0.35)
        t2 = tag("swatch brightness normalised for display", "art", 15).next_to(t1, DOWN, 0.08).align_to(t1, RIGHT)
        self.play(FadeIn(t1), FadeIn(t2), run_time=0.6)
        self.wait(4.5)
        self.clear_all()

    @staticmethod
    def _spectral_hex(lams):
        bt = np.array(D["mapping"]["band_thz"]) * 1e12
        bh = D["mapping"]["band_hex"]
        out = []
        for lam in lams:
            nu = 299792458.0 / (lam * 1e-9)
            if nu < bt[0] or nu > bt[-1]:
                out.append("#2a1020" if nu < bt[0] else "#1a1030")
            else:
                out.append(bh[int(np.argmin(np.abs(bt - nu)))])
        return out


# ==================================================================================================
def tube_mob(areas, total_w=7.0, max_h=2.6, color=SOUND):
    r = np.sqrt(np.asarray(areas, float))
    r = r / r.max() * max_h
    w = total_w / len(r)
    secs = VGroup(*[Rectangle(width=w, height=h, stroke_color=color, stroke_width=2,
                              fill_color=color, fill_opacity=0.28) for h in r]).arrange(RIGHT, buff=0)
    secs.align_to(ORIGIN, ORIGIN)
    for s in secs:
        s.set_y(0)
    return secs


class S03_Sound(Base):
    def construct(self):
        self.section("2 · Sound")
        S = D["sound"]
        head = eq("source_filter", 1.1).to_edge(UP, buff=0.55)
        self.play(Write(head), run_time=1.2)
        ax, deco = make_axes([0, 5000, 1000], [0, 66, 20], 6.4, 3.0,
                             xticks=[(0, "0"), (1000, "1"), (2000, "2"), (3000, "3"), (4000, "4"), (5000, "5 kHz")],
                             yticks=[(0, "−60"), (60, "0 dB")], xlab="frequency", fs=16)
        VGroup(ax, deco).to_edge(LEFT, buff=0.9).shift(DOWN * 0.75)
        self.play(Create(ax), FadeIn(deco), run_time=1.0)
        harm = np.array(S["harm"])
        stems = lambda db, c: VGroup(*[Line(ax.c2p(f, 0), ax.c2p(f, max(v + 60, 0.3)), color=c, stroke_width=3)
                                       for f, v in zip(harm, db)])
        src = stems(S["src_db"], ACC)
        leg = VGroup(T(f"source: glottal buzz, harmonics of F0 = {S['f0']:.0f} Hz", 20, ACC),
                     T("filter: the tube's resonances (formants)", 20, SOUND),
                     T("product: the vowel", 20, TXT)).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        leg.next_to(ax, UP, 0.3).align_to(ax, LEFT)
        ls, le, lo = leg
        self.play(LaggedStart(*[GrowFromEdge(s, DOWN) for s in src], lag_ratio=0.03), FadeIn(ls), run_time=1.6)
        wfb = waveform("video/audio/glottal_buzz.wav", 3.2, 0.5, ACC)
        wfb[0].next_to(ax, DOWN, 0.95)
        self.play(FadeIn(wfb[0]), run_time=0.3)
        self.play_clip("video/audio/glottal_buzz.wav", wfb, 0.6)
        # tube on the right
        tube = tube_mob(D["tract"]["areas"], 5.0, 2.2).to_edge(RIGHT, buff=0.7).shift(DOWN * 0.3)
        lg = T("glottis", 18, DIM).next_to(tube, DOWN, 0.08).align_to(tube, LEFT)
        ll = T("lips", 18, DIM).next_to(tube, DOWN, 0.08).align_to(tube, RIGHT)
        lt = T("16 equal sections · 17.5 cm · radius ∝ √area", 18, SOUND).next_to(tube, DOWN, 0.55)
        self.play(LaggedStart(*[GrowFromCenter(s) for s in tube], lag_ratio=0.05), FadeIn(lg), FadeIn(ll),
                  FadeIn(lt), run_time=2.0)
        lv = T(f"/ɑ/ as in “{S['example']}”: Hillenbrand 1995 (men), LPC-16 areas", 16, DIM)
        lv.next_to(lt, DOWN, 0.12)
        self.play(FadeIn(lv), run_time=0.6)
        self.wait(1.2)
        env = curve(ax, S["env_f"], np.maximum(np.array(S["env_db"]) + 60, 0), SOUND, 4)
        self.play(Create(env), FadeIn(le), run_time=1.6)
        fl = VGroup(*[DashedLine(ax.c2p(f, 0), ax.c2p(f, 57), color=SOUND, stroke_width=1.5, dash_length=0.06)
                      for f in S["formants"]])
        fls = VGroup(*[T(f"F{i + 1}", 16, SOUND).next_to(l, UP, 0.05) for i, l in enumerate(fl)])
        self.play(FadeIn(fl), FadeIn(fls), run_time=0.8)
        self.wait(1.0)
        out = stems(S["out_db"], TXT)
        self.play(ReplacementTransform(src, out), FadeIn(lo), run_time=1.6)
        vpath = "web/audio/vowel_men_ah.wav"
        wfv = waveform(vpath, 3.2, 0.5, SOUND)
        wfv[0].move_to(wfb[0])
        self.play(FadeOut(wfb[0]), FadeIn(wfv[0]), run_time=0.3)
        self.play_clip(vpath, wfv, 0.75, extra=[Indicate(tube, color=SOUND, scale_factor=1.04)])
        self.wait(0.6)
        self.play_clip(vpath, wfv, 0.75)
        self.wait(4.0)
        self.clear_all()


# ==================================================================================================
class S04_Equation(Base):
    def construct(self):
        self.section("3 · One equation")
        # tube junction (left)
        a1 = Rectangle(width=2.0, height=1.8, color=SOUND, fill_color=SOUND, fill_opacity=0.25)
        a2 = Rectangle(width=2.0, height=0.8, color=SOUND, fill_color=SOUND, fill_opacity=0.25)
        tj = VGroup(a1, a2).arrange(RIGHT, buff=0)
        a2.set_y(a1.get_y())
        la = VGroup(T("Aᵢ", 24, SOUND).move_to(a1).shift(UP * 0.55), T("Aᵢ₊₁", 24, SOUND).move_to(a2))
        tube = VGroup(tj, la).move_to(LEFT * 3.6 + UP * 1.3)
        cap1 = T("pressure wave in a tube", 22, SOUND).next_to(tube, UP, 0.3)
        # film interface (right)
        l1 = Rectangle(width=3.2, height=0.9, stroke_width=1, fill_color=n_colour(1.4, 1, 2.5), fill_opacity=1)
        l2 = Rectangle(width=3.2, height=0.9, stroke_width=1, fill_color=n_colour(2.2, 1, 2.5), fill_opacity=1)
        fj = VGroup(l1, l2).arrange(DOWN, buff=0)
        ln = VGroup(T("nᵢ", 24, TXT).move_to(l1), T("nᵢ₊₁", 24, BG).move_to(l2))
        film = VGroup(fj, ln).move_to(RIGHT * 3.6 + UP * 1.3)
        cap2 = T("light at a film interface (normal incidence)", 22, LIGHT).next_to(film, UP, 0.3)
        cap2.align_to(cap1, DOWN)
        self.play(FadeIn(tube), FadeIn(cap1), run_time=1.0)
        wave_t = Arrow(a1.get_left() + RIGHT * 0.1, a1.get_right() + LEFT * 0.1, color=ACC, buff=0, stroke_width=4)
        back_t = Arrow(a1.get_right() + LEFT * 0.1 + DOWN * 0.35, a1.get_center() + DOWN * 0.35, color=ACC,
                       buff=0, stroke_width=3)
        self.play(GrowArrow(wave_t), run_time=0.7)
        self.play(GrowArrow(back_t), run_time=0.6)
        rt = eq("r_tube", 1.15).next_to(tube, DOWN, 0.55)
        self.play(Write(rt), run_time=1.2)
        self.wait(1.0)
        self.play(FadeIn(film), FadeIn(cap2), run_time=1.0)
        ray = Arrow(l1.get_top() + LEFT * 0.75, l1.get_bottom() + LEFT * 0.2, color=ACC, buff=0, stroke_width=4)
        ref = Arrow(l1.get_bottom() + RIGHT * 0.1, l1.get_top() + RIGHT * 0.65, color=ACC, buff=0, stroke_width=3)
        ln[0].shift(RIGHT * 1.0)
        self.play(GrowArrow(ray), run_time=0.6)
        self.play(GrowArrow(ref), run_time=0.6)
        rf = eq("r_film", 1.15).next_to(film, DOWN, 0.55)
        self.play(Write(rf), run_time=1.2)
        self.wait(1.5)
        rg = eq("r_general", 1.5).move_to(DOWN * 2.3)
        rfc = rf.copy()
        self.play(TransformFromCopy(rt, rg), rfc.animate.move_to(rg).set_opacity(0), run_time=1.6)
        self.remove(rfc)
        box = SurroundingRectangle(rg, color=ACC, buff=0.2, corner_radius=0.1)
        self.play(Create(box), run_time=0.8)
        same = T("same number, same sign convention", 22, ACC).next_to(box, RIGHT, 0.4)
        self.play(FadeIn(same), run_time=0.6)
        ex = tag("lossless, plane waves, normal incidence", "exact", 16).to_corner(DR, buff=0.3)
        self.play(FadeIn(ex), run_time=0.5)
        self.wait(3.0)
        # timing condition
        self.play(*[FadeOut(m) for m in (wave_t, back_t, ray, ref, same, ex)], run_time=0.6)
        td = eq("tube_delay", 0.95).move_to(rt).shift(DOWN * 0.05)
        gd = eq("goupillaud", 0.95).move_to(rf).shift(DOWN * 0.05)
        self.play(FadeOut(rt, shift=DOWN * 0.3), FadeIn(td, shift=DOWN * 0.3),
                  FadeOut(rf, shift=DOWN * 0.3), FadeIn(gd, shift=DOWN * 0.3),
                  VGroup(rg, box).animate.scale(0.75).move_to(DOWN * 2.95), run_time=1.2)
        c1 = T("every section: one sample of round-trip time", 19, SOUND).next_to(td, DOWN, 0.25)
        c2 = T("every layer: the same optical thickness", 19, LIGHT).next_to(gd, DOWN, 0.25)
        self.play(FadeIn(c1), FadeIn(c2), run_time=0.8)
        self.wait(5.0)
        self.clear_all()


# ==================================================================================================
class S05_Morph(Base):
    def construct(self):
        self.section("4 · Tube → film")
        tr = D["tract"]
        areas = np.array(tr["areas"])
        n_id = np.array(tr["n_ideal"])[1:-1]
        n_re = np.array(tr["n_real"])
        tube = tube_mob(areas, 8.0, 3.0).move_to(ORIGIN + UP * 0.2)
        lg = T("glottis", 20, DIM).next_to(tube, LEFT, 0.25)
        ll = T("lips", 20, DIM).next_to(tube, RIGHT, 0.25)
        cap = T("/ɑ/ vocal tract: 16 sections of equal length", 24, SOUND).to_edge(UP, buff=0.9)
        self.play(LaggedStart(*[GrowFromCenter(s) for s in tube], lag_ratio=0.04), FadeIn(lg), FadeIn(ll),
                  FadeIn(cap), run_time=2.0)
        self.wait(1.2)
        # 1) turn it on its side: glottis on top = incident side, lips at bottom = substrate side
        self.play(FadeOut(lg), FadeOut(ll), FadeOut(cap), tube.animate.scale(0.68).move_to(LEFT * 4.6 + DOWN * 0.2),
                  run_time=1.0)
        self.play(Rotate(tube, -PI / 2), run_time=1.4)
        # 2) area (width) -> refractive index (shade); every layer the same optical thickness
        H = tube.height / 16
        W = 3.0
        lo, hi = n_id.min(), n_id.max()
        # targets built as rotated rectangles so their point order matches the rotated tube sections
        layers = VGroup(*[Rectangle(width=H, height=W, stroke_color=BG, stroke_width=1,
                                    fill_color=n_colour(n, lo, hi), fill_opacity=1).rotate(-PI / 2) for n in n_id])
        layers.arrange(DOWN, buff=0).move_to(LEFT * 0.7 + DOWN * 0.2)
        inc = T("incident medium (glottis side)", 17, DIM).next_to(layers, UP, 0.15)
        sub = T("substrate (lips / radiation side)", 17, DIM).next_to(layers, DOWN, 0.15)
        arr = Arrow(tube.get_right(), layers.get_left(), buff=0.25, color=DIM, stroke_width=3)
        self.play(*[TransformFromCopy(s, l) for s, l in zip(tube, layers)], GrowArrow(arr), run_time=2.4)
        npa = eq("n_prop_A", 1.2).next_to(layers, RIGHT, 0.6).align_to(layers, UP).shift(DOWN * 0.2)
        self.play(FadeIn(inc), FadeIn(sub), Write(npa), run_time=1.0)
        lab = VGroup(*[T(f"{n:.1f}", 13, TXT if n < 0.5 * hi else BG).move_to(l) for n, l in zip(n_id, layers)])
        self.play(FadeIn(lab), run_time=0.6)
        eqh = T("each layer: n·d = 428.27 nm (optical)", 18, LIGHT).next_to(npa, DOWN, 0.35).align_to(npa, LEFT)
        self.play(FadeIn(eqh), run_time=0.6)
        ide = VGroup(T(f"ideal mode: n from {lo:.0f} to {hi:.0f}", 18, APPROX),
                     T("(no such materials exist)", 18, APPROX)).arrange(DOWN, buff=0.06, aligned_edge=LEFT)
        ide.next_to(eqh, DOWN, 0.25).align_to(npa, LEFT)
        self.play(FadeIn(ide), run_time=0.6)
        self.wait(2.0)
        # 3) realizable compression and physical thickness d = 428.27/n
        nr = n_re[1:-1]
        d = K["D_OPT_NM"] / nr
        scale = 5.0 / d.sum()
        real = VGroup(*[Rectangle(width=dd * scale, height=W, stroke_color=BG, stroke_width=1,
                                  fill_color=n_colour(n, 1.0, 2.5), fill_opacity=1).rotate(-PI / 2)
                        for n, dd in zip(nr, d)])
        real.arrange(DOWN, buff=0).move_to(layers)
        lab2 = VGroup(*[T(f"{n:.2f}", 12, TXT if n < 1.7 else BG).move_to(r) for n, r in zip(nr, real)])
        rr = VGroup(T("realizable mode: n = (A/A_min)^γ", 18, APPROX),
                    T("compressed into [1.0, 2.5]", 18, APPROX)).arrange(DOWN, buff=0.06, aligned_edge=LEFT)
        rr.move_to(ide).align_to(npa, LEFT)
        rr2 = VGroup(T("physical thickness d = 428.27 nm / n", 18, LIGHT),
                     T(f"= {d.min():.0f} to {d.max():.0f} nm per layer", 18, LIGHT)).arrange(DOWN, buff=0.06,
                                                                                         aligned_edge=LEFT)
        rr2.next_to(rr, DOWN, 0.25).align_to(npa, LEFT)
        self.play(FadeOut(lab), ReplacementTransform(layers, real), FadeOut(ide), FadeIn(rr), run_time=2.0)
        self.play(inc.animate.next_to(real, UP, 0.15), sub.animate.next_to(real, DOWN, 0.15), FadeIn(lab2),
                  FadeIn(rr2), run_time=1.0)
        sw = VGroup(RoundedRectangle(corner_radius=0.08, width=0.8, height=0.5, fill_color=tr["hexT_real"],
                                     fill_opacity=1, stroke_width=0),
                    T("its transmitted colour", 17, TXT)).arrange(RIGHT, buff=0.2)
        sw.next_to(rr2, DOWN, 0.4).align_to(npa, LEFT)
        self.play(FadeIn(sw), run_time=0.8)
        tg = tag("compression γ and finite glottis (r = −0.9)", "approx", 15).to_corner(DR, buff=0.3)
        self.play(FadeIn(tg), run_time=0.5)
        self.wait(5.0)
        self.clear_all()


# ==================================================================================================
class S06_Levinson(Base):
    def construct(self):
        self.section("5 · Levinson = layer peeling")
        lv = D["levinson"]
        c = np.array(lv["c"])            # c_m = -k_m, m = 1..16
        n_id = np.array(D["tract"]["n_ideal"])[1:-1]
        lo, hi = n_id.min(), n_id.max()
        H = 0.27
        layers = VGroup(*[Rectangle(width=2.6, height=H, stroke_color=BG, stroke_width=1,
                                    fill_color=n_colour(n, lo, hi), fill_opacity=1) for n in n_id])
        layers.arrange(DOWN, buff=0).to_edge(LEFT, buff=0.9).shift(DOWN * 0.3)
        subs = Rectangle(width=2.6, height=0.3, stroke_width=0, fill_color="#3a3f4a", fill_opacity=1)
        subs.next_to(layers, DOWN, 0)
        ls = T("substrate", 15, DIM).move_to(subs)
        ax, deco = make_axes([0, 17, 1], [-1, 1, 1], 7.2, 3.6,
                             xticks=[(1, "1"), (4, "4"), (8, "8"), (12, "12"), (16, "16")],
                             yticks=[(-1, "−1"), (0, "0"), (1, "1")], xlab="interface m (glottis → lips)", fs=16)
        VGroup(ax, deco).to_edge(RIGHT, buff=0.7).shift(DOWN * 0.35)
        yl = T("reflection coefficient rₘ", 18, DIM).next_to(ax, UP, 0.1).align_to(ax, LEFT)
        self.play(FadeIn(layers), FadeIn(subs), FadeIn(ls), Create(ax), FadeIn(deco), FadeIn(yl), run_time=1.4)
        sd = eq("stepdown", 0.85).to_edge(UP, buff=0.55).shift(RIGHT * 1.0)
        kc = eq("k_eq_c", 0.9).next_to(sd, RIGHT, 0.6)
        self.play(Write(sd), Write(kc), run_time=1.4)
        note = T("step-down peels the polynomial one order at a time, starting at the lips end", 17, DIM)
        note.next_to(VGroup(sd, kc), DOWN, 0.15)
        self.play(FadeIn(note), run_time=0.6)
        self.wait(1.0)
        cnt = T("order 16", 22, ACC).next_to(layers, UP, 0.25)
        self.play(FadeIn(cnt), run_time=0.4)
        stems = VGroup()
        for m in range(16, 0, -1):
            L = layers[m - 1]
            iface = Line(L.get_corner(DL), L.get_corner(DR), color=ACC, stroke_width=6)
            st = Line(ax.c2p(m, 0), ax.c2p(m, c[m - 1]), color=ACC, stroke_width=6)
            dot = Dot(ax.c2p(m, c[m - 1]), radius=0.06, color=ACC)
            rt = 0.95 if m > 13 else 0.62
            new_cnt = T(f"order {m - 1}", 22, ACC).move_to(cnt)
            self.play(Create(iface), run_time=rt * 0.35)
            self.play(TransformFromCopy(iface, st), FadeIn(dot), FadeOut(L, shift=RIGHT * 0.6),
                      FadeOut(iface), Transform(cnt, new_cnt),
                      subs.animate.move_to(L.get_bottom() + UP * (H - 0.15)),
                      ls.animate.move_to(L.get_bottom() + UP * (H - 0.15)), run_time=rt * 0.65)
            stems.add(st, dot)
        self.wait(0.6)
        msg = T("16 reflection coefficients, read straight off the polynomial", 21, ACC).next_to(ax, DOWN, 0.95)
        self.play(FadeIn(msg), FadeOut(subs), FadeOut(ls), FadeOut(cnt), run_time=0.7)
        self.wait(1.0)
        # forward: grow the tube back from the glottis
        ag = eq("area_grow", 0.9).move_to(sd).align_to(sd, LEFT)
        self.play(FadeOut(sd), FadeOut(note), FadeIn(ag), run_time=0.8)
        tube = tube_mob(lv["areas"][:-1], 3.2, 2.2).move_to(LEFT * 4.4 + DOWN * 0.3)
        lt = T("areas rebuilt, glottis → lips", 18, SOUND).next_to(tube, DOWN, 0.5)
        self.play(LaggedStart(*[GrowFromCenter(s) for s in tube], lag_ratio=0.15), FadeIn(lt), run_time=3.0)
        err = T(f"round trip error {lv['check_max_err']:.0e}", 16, EXACT).next_to(lt, DOWN, 0.15)
        self.play(FadeIn(err), run_time=0.5)
        fin = T("LPC (Levinson–Durbin) on speech  ≡  layer peeling of a film", 26, TXT).to_edge(DOWN, buff=0.35)
        self.play(FadeOut(msg), Write(fin), run_time=1.4)
        self.wait(4.0)
        self.clear_all()


# ==================================================================================================
class S07_Mapping(Base):
    def construct(self):
        self.section("6 · Sound frequency ↔ light frequency")
        M = D["mapping"]
        nu = np.array(M["nu_thz"]); f = np.array(M["f"]); fo = np.array(M["folded"])
        head = eq("mapping", 0.95).to_edge(UP, buff=0.5)
        self.play(Write(head), run_time=1.2)
        ax, deco = make_axes([400, 750, 50], [0, 16000, 4000], 9.6, 3.5,
                             xticks=[(v, str(v)) for v in (400, 450, 500, 550, 600, 650, 700, 750)],
                             yticks=[(0, "0"), (8000, "8 kHz"), (16000, "16 kHz")],
                             xlab="light frequency ν (THz)", fs=16)
        VGroup(ax, deco).move_to(DOWN * 0.75 + RIGHT * 0.3)
        bt = np.array(M["band_thz"])
        band = VGroup(*[Rectangle(width=ax.x_length / (len(bt) - 1) * 1.02, height=0.16, stroke_width=0,
                                  fill_color=h, fill_opacity=1).move_to(ax.c2p(v, 0) + DOWN * 0.1)
                        for v, h in zip(bt, M["band_hex"])])
        self.play(Create(ax), FadeIn(deco), FadeIn(band), run_time=1.2)
        a = nu < 700
        saw = VGroup(curve(ax, nu[a], f[a], TXT, 3), curve(ax, nu[~a], f[~a], TXT, 3))
        self.play(Create(saw), run_time=2.0)
        half = DashedLine(ax.c2p(400, 8000), ax.c2p(750, 8000), color=DIM, stroke_width=1.5)
        self.play(Create(half), run_time=0.6)
        pts = [(400, M["f_at_400"], f"400 THz → {M['f_at_400']:.0f} Hz", UR),
               (525, 8000, "525 THz → 8 kHz", UP), (700, 0, "700 THz → 0 Hz", UL)]
        marks = VGroup()
        for x, y, s, dirn in pts:
            d = Dot(ax.c2p(x, y), color=ACC, radius=0.07)
            marks.add(d, T(s, 17, ACC).next_to(d, dirn, 0.1))
        self.play(LaggedStart(*[FadeIn(m) for m in marks], lag_ratio=0.2), run_time=1.6)
        self.wait(1.5)
        fold = VGroup(curve(ax, nu[a], fo[a], SOUND, 4), curve(ax, nu[~a], fo[~a], SOUND, 4))
        lf = T("folded: speech frequency (0–8 kHz) appears twice, mirrored about 700 THz", 19, SOUND)
        lf.next_to(ax, UP, 0.55).align_to(ax, LEFT)
        self.play(Create(fold), FadeIn(lf), run_time=1.8)
        self.wait(1.5)
        F12 = M["F12"]; imgs = M["F12_images_thz"]
        fl = VGroup()
        for i, (F, im) in enumerate(zip(F12, imgs)):
            for v in im:
                fl.add(DashedLine(ax.c2p(v, 0), ax.c2p(v, 16000), color=LIGHT, stroke_width=2, dash_length=0.07))
        lab = T(f"/ɑ/: F1 = {F12[0]:.0f} Hz → {imgs[0][0]:.0f} & {imgs[0][1]:.0f} THz,  "
                f"F2 = {F12[1]:.0f} Hz → {imgs[1][0]:.0f} & {imgs[1][1]:.0f} THz", 18, LIGHT)
        lab.next_to(lf, DOWN, 0.08).align_to(lf, LEFT)
        self.play(Create(fl), FadeIn(lab), run_time=1.4)
        vio = T("formants land at 670–730 THz: the violet end", 22, ACC).to_edge(DOWN, buff=0.15)
        self.play(FadeIn(vio), run_time=0.7)
        self.wait(3.0)
        # isomorphism panel
        self.play(*[FadeOut(m) for m in (saw, half, marks, fold, lf, lab, fl, deco, ax, vio)], run_time=0.8)
        ax2, deco2 = make_axes([400, 750, 50], [0, 1.0, 0.5], 9.6, 3.5,
                               xticks=[(v, str(v)) for v in (400, 450, 500, 550, 600, 650, 700, 750)],
                               yticks=[(0, "0"), (0.5, "0.5"), (1.0, "1")],
                               xlab="light frequency ν (THz)", fs=16)
        VGroup(ax2, deco2).move_to(DOWN * 0.75 + RIGHT * 0.3)
        Tf = np.array(M["T_film"]); Pt = np.array(M["P_tube"])
        self.play(Create(ax2), FadeIn(deco2), run_time=0.8)
        ct = curve(ax2, nu, Tf, LIGHT, 4)
        lt = T("film transmittance T(ν), /ɑ/ film (ideal mode, 16 layers)", 19, LIGHT).next_to(ax2, UP, 0.55).align_to(ax2, LEFT)
        self.play(Create(ct), FadeIn(lt), run_time=2.0)
        idx = np.arange(0, len(nu), 9)
        dots = VGroup(*[Dot(ax2.c2p(nu[i], Pt[i]), radius=0.035, color=SOUND) for i in idx])
        lp = T("tube power transfer at f(ν) (acoustic chain, independent code)", 19, SOUND).next_to(lt, DOWN, 0.08).align_to(lt, LEFT)
        self.play(LaggedStart(*[FadeIn(d) for d in dots], lag_ratio=0.01), FadeIn(lp), run_time=2.2)
        dd = T(f"max |T_film − P_tube| = {M['max_abs_diff']:.1e}", 22, EXACT).to_edge(DOWN, buff=0.15)
        self.play(FadeIn(dd), run_time=0.6)
        tg = tag("isomorphism: same curve", "exact", 16).to_corner(UR, buff=0.3)
        self.play(FadeIn(tg), run_time=0.5)
        self.wait(4.0)
        self.clear_all()


# ==================================================================================================
class S08_VowelColours(Base):
    def construct(self):
        self.section("7 · The colours of vowels")
        V = D["vowels"]
        order = ["iy", "ih", "ei", "eh", "ae", "ah", "aw", "oa", "oo", "uw", "uh", "er"]
        groups = ["men", "women", "children"]
        get = {(v["group"], v["vowel"]): v for v in V}
        s = 0.78
        grid = VGroup()
        for g in groups:
            row = VGroup(*[RoundedRectangle(corner_radius=0.08, width=s, height=s, stroke_width=0,
                                            fill_color=get[(g, w)]["T"], fill_opacity=1) for w in order])
            row.arrange(RIGHT, buff=0.14)
            grid.add(row)
        grid.arrange(DOWN, buff=0.22).move_to(RIGHT * 0.7 + UP * 0.35)
        rl = VGroup(*[T(g, 20, DIM).next_to(r, LEFT, 0.3) for g, r in zip(groups, grid)])
        ipa = VGroup(*[T(get[("men", w)]["ipa"], 22, TXT).next_to(grid[0][i], UP, 0.15) for i, w in enumerate(order)])
        ex = VGroup(*[T(get[("men", w)]["example"], 13, DIM).next_to(grid[-1][i], DOWN, 0.12) for i, w in enumerate(order)])
        cap = T("each vowel → LPC → area function → 16-layer film → transmitted colour (D65)", 21, TXT).to_edge(UP, buff=0.75)
        self.play(FadeIn(cap), run_time=0.8)
        self.play(FadeIn(ipa), FadeIn(ex), FadeIn(rl), run_time=0.8)
        self.play(LaggedStart(*[FadeIn(sq, scale=0.6) for row in grid for sq in row], lag_ratio=0.02), run_time=2.2)
        # play a few vowels, highlighting their swatch
        for w in ("iy", "ae", "ah", "uw"):
            i = order.index(w)
            v = get[("men", w)]
            box = SurroundingRectangle(grid[0][i], color=ACC, buff=0.06, corner_radius=0.08)
            self.play(Create(box), run_time=0.3)
            y, fs, _ = wav_read(v["audio"])
            self.cue(v["audio"], 0.75)
            self.play(Indicate(grid[0][i], scale_factor=1.15, color=None), run_time=len(y) / fs)
            self.play(FadeOut(box), run_time=0.25)
        self.wait(0.5)
        honest = VGroup(
            T("Honest result: they are all violet / lavender.", 26, ACC),
            T("F1 and F2 map to 650–750 THz, so the vowels differ only slightly:", 20, TXT),
            T("median ΔE00 between vowels: men 4.3 · women 5.7 · children 7.7  (≈1–2 is just noticeable)", 20, TXT),
        ).arrange(DOWN, buff=0.12).to_edge(DOWN, buff=0.35)
        self.play(FadeIn(honest[0], shift=UP * 0.2), run_time=0.8)
        self.play(FadeIn(honest[1]), FadeIn(honest[2]), run_time=1.0)
        tg = tag("ideal films pass only Y≈0.1–0.4 %: brightness normalised", "art", 15).to_corner(UR, buff=0.3)
        self.play(FadeIn(tg), run_time=0.5)
        self.wait(4.5)
        # realizable films
        new = VGroup()
        for gi, g in enumerate(groups):
            for i, w in enumerate(order):
                new.add(grid[gi][i].copy().set_fill(get[(g, w)]["T_real"], 1))
        rlab = T("realizable films (n 1.0–2.5): paler lavender, median ΔE00 3.6 · 3.8 · 6.5", 20, APPROX)
        rlab.move_to(honest[1:]).align_to(honest, DOWN)
        self.play(*[Transform(grid[gi][i], new[gi * 12 + i]) for gi in range(3) for i in range(12)],
                  FadeOut(honest[1:]), FadeIn(rlab), FadeOut(tg), run_time=1.8)
        tg2 = tag("realizable compression (n ∈ [1, 2.5])", "approx", 15).to_corner(UR, buff=0.3)
        self.play(FadeIn(tg2), run_time=0.4)
        self.wait(4.5)
        self.clear_all()


# ==================================================================================================
class S09_ButterflyVoices(Base):
    def _panel(self, b, x, beetle=False):
        lut = b["lut_rgb"]
        if beetle:
            body = Ellipse(width=1.1, height=1.45, fill_color=lut[0], fill_opacity=1, stroke_color="#0d0d0d")
            seam = Line(body.get_top(), body.get_bottom(), color="#0d0d0d", stroke_width=2)
            head = Circle(radius=0.22, fill_color="#1c1c22", fill_opacity=1, stroke_width=0).next_to(body, UP, -0.05)
            ani = VGroup(VGroup(body), seam, head).move_to([x, 1.75, 0])
        else:
            ani = butterfly(lut[0], 0.62).move_to([x, 1.75, 0])
        name = T(b["name"], 22, TXT).move_to([x - 3.2, 2.45, 0], aligned_edge=LEFT)
        lab = VGroup()
        strip = VGroup(*[Rectangle(width=0.085, height=0.24, stroke_width=0, fill_color=h, fill_opacity=1)
                         for h in lut]).arrange(RIGHT, buff=0).move_to([x, 0.62, 0])
        sl = VGroup(T("0°", 13, DIM).next_to(strip, LEFT, 0.08), T("80°", 13, DIM).next_to(strip, RIGHT, 0.08))
        st = T("reflected colour vs viewing angle", 14, DIM).next_to(strip, DOWN, 0.06)
        ax, deco = make_axes([0, 8000, 2000], [0, 40, 20], 4.4, 1.3,
                             xticks=[(0, "0"), (4000, "4"), (8000, "8 kHz")], yticks=[(0, "−40"), (40, "0 dB")], fs=13)
        VGroup(ax, deco).move_to([x + 0.2, -0.95, 0])
        env = curve(ax, b["env_f"], np.maximum(np.array(b["env_db"]) + 40, 0), SOUND, 3)
        el = T("its voice: 16-pole envelope", 15, SOUND).next_to(ax, UP, 0.02)
        return ani, name, lab, strip, sl, st, ax, deco, env, el

    def construct(self):
        self.section("8 · The voices of butterflies")
        B = D["butterflies"]
        cap = T("film → reflection coefficients → all-pole filter → glottal buzz", 22, TXT).to_edge(UP, buff=0.75)
        self.play(FadeIn(cap), run_time=0.8)
        for b, x, beetle in ((B[0], -3.4, False), (B[1], 3.4, True)):
            ani, name, lab, strip, sl, st, ax, deco, env, el = self._panel(b, x, beetle)
            self.play(FadeIn(ani), FadeIn(name), run_time=0.8)
            if not beetle:
                flapping(ani, b["lut_rgb"], speed=2.0, max_tilt=55)
            self.play(FadeIn(strip), FadeIn(sl), FadeIn(st), run_time=0.8)
            self.play(Create(ax), FadeIn(deco), Create(env), FadeIn(el), run_time=1.2)
            wf = waveform(b["audio"], 3.0, 0.4, LIGHT)
            wf[0].move_to([x, -2.45, 0])
            self.play(FadeIn(wf[0]), run_time=0.3)
            self.play_clip(b["audio"], wf, 0.75)
            self.wait(0.5)
            self.play_clip(b["audio"], wf, 0.75)
            self.wait(1.2)
        nb = VGroup(T("No clear formants: these stacks hum and buzz rather than say a vowel.", 20, ACC),
                    T("Their layers are not equal optical thickness, so each voice is the best 16-pole fit.", 18, DIM))
        nb.arrange(DOWN, buff=0.08).to_edge(DOWN, buff=0.15)
        self.play(FadeIn(nb), run_time=0.8)
        t1 = tag("stack parameters illustrative; voice = all-pole fit", "approx", 14).to_corner(UR, buff=0.25)
        t2 = tag("flapping", "art", 14).next_to(t1, DOWN, 0.06).align_to(t1, RIGHT)
        self.play(FadeIn(t1), FadeIn(t2), run_time=0.5)
        self.wait(4.0)
        self.clear_all()


# ==================================================================================================
class S10_Metamers(Base):
    def construct(self):
        self.section("9 · Metamers: same colour, different voices")
        M = D["metamers"]
        cap = T("4 of 20 000 random 16-layer films: the eye can't tell them apart", 23, TXT).to_edge(UP, buff=0.75)
        self.play(FadeIn(cap), run_time=0.8)
        cols = VGroup()
        xs = [-5.1, -1.7, 1.7, 5.1]
        parts = []
        for i, (it, x) in enumerate(zip(M["items"], xs)):
            sw = RoundedRectangle(corner_radius=0.12, width=2.4, height=1.2, fill_color=it["hex"], fill_opacity=1,
                                  stroke_width=0).move_to([x, 1.3, 0])
            n = np.array(it["n"])[1:-1]
            bars = VGroup(*[Rectangle(width=0.13, height=0.25 + 0.75 * (v - 1.0) / 1.5, stroke_width=0,
                                      fill_color=n_colour(v, 1, 2.5), fill_opacity=1) for v in n])
            bars.arrange(RIGHT, buff=0.02, aligned_edge=DOWN).next_to(sw, DOWN, 0.35)
            bl = T("refractive index, layers 1–16", 12, DIM).next_to(bars, DOWN, 0.06)
            ax, deco = make_axes([0, 8000, 2000], [0, 40, 20], 2.8, 1.4,
                                 xticks=[(0, "0"), (8000, "8 kHz")], yticks=[], fs=12)
            VGroup(ax, deco).next_to(bl, DOWN, 0.3)
            env = curve(ax, it["env_f"], np.maximum(np.array(it["env_db"]) + 40, 0), SOUND, 3)
            dl = T("reference" if i == 0 else f"ΔE00 = {it['dE_to_first']:.2f}", 15, EXACT).next_to(sw, UP, 0.1)
            wf = waveform(it["audio"], 2.4, 0.38, SOUND)
            wf[0].next_to(ax, DOWN, 0.33)
            parts.append((sw, bars, bl, ax, deco, env, dl, wf))
        self.play(LaggedStart(*[FadeIn(p[0], scale=0.8) for p in parts], lag_ratio=0.2), run_time=1.6)
        self.play(*[FadeIn(p[6]) for p in parts], run_time=0.6)
        same = T(f"max pairwise ΔE00 = {M['max_pair_dE00']:.2f}  (reflected colour, D65)", 19, EXACT)
        same.next_to(cap, DOWN, 0.15)
        self.play(FadeIn(same), run_time=0.6)
        self.wait(1.2)
        self.play(*[FadeIn(p[1]) for p in parts], *[FadeIn(p[2]) for p in parts], run_time=1.0)
        self.play(*[Create(p[3]) for p in parts], *[FadeIn(p[4]) for p in parts],
                  *[Create(p[5]) for p in parts], run_time=1.4)
        for p, it in zip(parts, M["items"]):
            box = SurroundingRectangle(VGroup(p[0], p[3]), color=ACC, buff=0.12, corner_radius=0.1)
            self.play(Create(box), FadeIn(p[7][0]), run_time=0.35)
            self.play_clip(it["audio"], p[7], 0.75)
            self.wait(0.3)
            self.play(FadeOut(box), run_time=0.25)
        why = T("Colour keeps 3 numbers of a spectrum; a voice keeps ~16. Many voices share one colour.", 21, ACC)
        why.to_edge(DOWN, buff=0.12)
        self.play(FadeIn(why, shift=UP * 0.2), run_time=0.8)
        self.wait(4.5)
        self.clear_all()


# ==================================================================================================
class S11_Outro(Base):
    def construct(self):
        O = D["outro"]
        bf = butterfly(O["hex_real"][0], 1.0).shift(UP * 1.6)
        self.play(FadeIn(bf), run_time=0.8)
        lab = T("a film that sings “ah – ee – oo” (women's vowels; wing = realizable film colour)", 19, DIM)
        lab.next_to(bf, DOWN, 0.3)
        self.play(FadeIn(lab), run_time=0.5)
        rel = "video/audio/outro_sing.wav"
        y, fs, _ = wav_read(rel)
        dur = len(y) / fs
        self.cue(rel, 0.75)
        seg = dur / 3
        for h in O["hex_real"]:
            self.play(bf[0].animate.set_fill(h, 1), run_time=seg * 0.35)
            self.play(Indicate(bf[0], scale_factor=1.05, color=None), run_time=seg * 0.65)
        rows = VGroup(
            VGroup(T("EXACT", 20, EXACT), T("r = (a−b)/(a+b) · equal travel time ↔ 428.27 nm layers · "
                                             "Levinson ↔ layer peeling · 400–750 THz = one period", 17, TXT)),
            VGroup(T("APPROXIMATE", 20, APPROX), T("finite glottis r = −0.9 · realizable n ∈ [1, 2.5] · "
                                                    "butterfly stack parameters · best-fit voices", 17, TXT)),
            VGroup(T("ARTISTIC", 20, ART), T("brightness normalisation of swatches · wing flapping", 17, TXT)),
        )
        for r in rows:
            r.arrange(RIGHT, buff=0.3)
        rows.arrange(DOWN, buff=0.22, aligned_edge=LEFT).next_to(lab, DOWN, 0.5)
        self.play(LaggedStart(*[FadeIn(r, shift=RIGHT * 0.2) for r in rows], lag_ratio=0.35), run_time=2.0)
        self.wait(3.0)
        end = VGroup(T("Vowels That Shine, Butterflies That Speak", 40, TXT),
                     T("DA321 · all curves computed with the project's core/ physics", 20, DIM)).arrange(DOWN, buff=0.2)
        end.to_edge(DOWN, buff=0.4)
        self.play(FadeIn(end, shift=UP * 0.2), run_time=1.0)
        self.wait(3.0)
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=1.5)
        self.wait(0.5)


SCENES = ["S01_Hook", "S02_Light", "S03_Sound", "S04_Equation", "S05_Morph", "S06_Levinson", "S07_Mapping",
          "S08_VowelColours", "S09_ButterflyVoices", "S10_Metamers", "S11_Outro"]
