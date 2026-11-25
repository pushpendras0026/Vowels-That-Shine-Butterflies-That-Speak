"""Render every equation of the explainer with matplotlib mathtext -> SVG (NO LaTeX).

Run:  . .\\tools\\env.ps1; python -m video.make_eqs      -> video/eqs/<name>.svg
Scenes load them with SVGMobject (see scenes.py: eq()).
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

matplotlib.rcParams["svg.fonttype"] = "path"     # glyphs as paths: no font dependency in manim
matplotlib.rcParams["mathtext.fontset"] = "cm"
matplotlib.rcParams["svg.hashsalt"] = "da321"      # deterministic ids -> reproducible files

OUT = Path(__file__).resolve().parent / "eqs"

EQS = {
    "C_ER": r"$C(\lambda) = E(\lambda)\,R(\lambda)$",
    "XYZ": r"$X = \int C(\lambda)\,\bar{x}(\lambda)\,d\lambda,\quad Y = \int C\,\bar{y}\,d\lambda,\quad Z = \int C\,\bar{z}\,d\lambda$",
    "source_filter": r"$\mathrm{Speech}(f) = \mathrm{Source}(f)\,\times\,|H(f)|^2$",
    "r_general": r"$r = \dfrac{a - b}{a + b}$",
    "r_tube": r"$r_i = \dfrac{A_i - A_{i+1}}{A_i + A_{i+1}}$",
    "r_film": r"$r_i = \dfrac{n_i - n_{i+1}}{n_i + n_{i+1}}$",
    "n_prop_A": r"$n_i \;\propto\; A_i$",
    "tube_delay": r"$\dfrac{2\ell}{c_{\mathrm{sound}}} = \dfrac{1}{f_s} = \dfrac{1}{16\,\mathrm{kHz}}$",
    "goupillaud": r"$n_i\, d_i = \dfrac{c}{2\,\Delta\nu} = 428.27\ \mathrm{nm}$",
    "power": r"$P(\omega) = \dfrac{\prod_i\,(1 - r_i^{\,2})}{|D(e^{j\omega})|^2}$",
    "stepdown": r"$a^{(m-1)}_i = \dfrac{a^{(m)}_i - k_m\, a^{(m)}_{m-i}}{1 - k_m^{\,2}}$",
    "k_eq_c": r"$k_m = -\,r_m$",
    "area_grow": r"$A_{m+1} = A_m\,\dfrac{1 + k_m}{1 - k_m}$",
    "mapping": r"$f(\nu) = f_s \cdot \mathrm{frac}\!\left(\dfrac{\nu}{\Delta\nu}\right),\quad \Delta\nu = 350\ \mathrm{THz}$",
    "omega": r"$\omega_{\mathrm{tube}} = \dfrac{2\pi f}{f_s} \;=\; 2\delta_{\mathrm{film}} = \dfrac{4\pi\, n d\, \nu}{c}$",
    "deltaE": r"$\Delta E_{00} < 2$",
}


def render(name, tex, fontsize=40):
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.patch.set_visible(False)
    fig.text(0, 0, tex, fontsize=fontsize, color="white")
    fig.savefig(OUT / f"{name}.svg", transparent=True, bbox_inches="tight", pad_inches=0.02, metadata={"Date": None})
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for k, v in EQS.items():
        render(k, v)
    print(f"wrote {len(EQS)} equations to {OUT}")


if __name__ == "__main__":
    main()
