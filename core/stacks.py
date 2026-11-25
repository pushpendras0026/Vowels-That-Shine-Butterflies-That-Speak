"""Parametric butterfly-/beetle-like multilayers. ALL parameters are APPROXIMATE / ILLUSTRATIVE.

Morpho-like: alternating cuticle / air lamellae as in the ridge structure of Morpho scales (structure:
  Vukusic, Sambles, Lawrence & Wootton 1999, Proc. R. Soc. B 266:1403; Kinoshita et al. 2002, Proc. R. Soc. B
  269:1417). Dimensions from Kinoshita, Yoshioka, Fujii & Okamoto 2002, "Photophysics of Structural Color in the
  Morpho Butterflies", Forma 17(2):103: ridges carry 6-8 cuticle/air layers, TEM thickness cuticle ~55 nm /
  air ~150 nm; their multilayer model uses an *averaged* dielectric layer 60 nm / air 145 nm (cuticle n 1.6,
  dielectric constant averaged over the ridge spacing). We use 60 / 145 nm, 7 pairs, and a laterally averaged
  lamella index n_eff = sqrt(f*n_chitin^2 + (1-f)) with fill fraction f = 0.5 (ILLUSTRATIVE, not measured).
  Why the fill matters: with solid chitin (f = 1) the 1.56/1.0 stop band spans ~410-570 nm at R ~ 1 and the
  colour reads cyan (hue ~185 deg); with f = 0.5 the band narrows to ~405-505 nm, peak ~450 nm, hue ~216 deg.
  Real Morpho colour also involves diffraction and disorder, which this 1-D model ignores.
Beetle-like: chitin (1.56) / higher-index melanin-rich layers (n≈1.70 ILLUSTRATIVE) multilayer as in
  jewel beetles (e.g. Stavenga et al. 2011, J. Exp. Biol. 214:2724 discuss such reflectors); 12 pairs,
  ILLUSTRATIVE thicknesses giving a green peak.
Goupillaud: random equal-optical-thickness stacks (the ones that 'speak' exactly)."""
from __future__ import annotations

import numpy as np

from .mapping import N_MIN, N_MAX, ORDER, goupillaud_d, MATERIALS

N_CHITIN = MATERIALS["chitin"]


# Morpho-like defaults (see module docstring; research/r4_butterflies.py scales these)
MORPHO_PAIRS = 7
MORPHO_D_CHITIN = 60.0   # nm, Kinoshita et al. 2002 (Forma) averaged-model lamella
MORPHO_D_AIR = 145.0     # nm, idem
MORPHO_FILL = 0.5        # lateral fill fraction of the lamellae (ILLUSTRATIVE)


def morpho_like(pairs=MORPHO_PAIRS, d_chitin=MORPHO_D_CHITIN, d_air=MORPHO_D_AIR, n_chitin=N_CHITIN, fill=MORPHO_FILL):
    """Air | (lamella, air) x pairs | solid chitin. Lamella index = spatially averaged dielectric constant."""
    n_lam = float(np.sqrt(fill * n_chitin ** 2 + (1.0 - fill)))
    n = [1.0] + [n_lam, 1.0] * pairs + [n_chitin]
    d = [d_chitin, d_air] * pairs
    return dict(name="Morpho-like", label="approximate/illustrative",
                source="Kinoshita et al. 2002, Forma 17:103 (lamella 60 nm / air 145 nm, 6-8 layers); "
                       "lamella fill 0.5 illustrative",
                n=np.array(n), d_nm=np.array(d, float))


def beetle_like(pairs=12, d1=95.0, d2=75.0, n1=N_CHITIN, n2=1.70):
    n = [1.0] + [n1, n2] * pairs + [n1]
    d = [d1, d2] * pairs
    return dict(name="Beetle-like", label="illustrative",
                source="jewel-beetle multilayer type (e.g. Stavenga et al. 2011); values illustrative",
                n=np.array(n), d_nm=np.array(d, float))


def random_goupillaud(rng, N=ORDER, mode="realizable", lo=N_MIN, hi=N_MAX, incident=1.0):
    if mode == "bimodal":  # high-contrast arm: each layer low (1.0-1.25) or high (2.1-2.5)
        hi_mask = rng.random(N + 1) < 0.5
        layers = np.where(hi_mask, rng.uniform(2.1, hi, N + 1), rng.uniform(lo, 1.25, N + 1))
    elif mode == "materials":
        vals = np.array(sorted(MATERIALS.values()))
        layers = rng.choice(vals, N + 1)
    else:
        layers = np.exp(rng.uniform(np.log(lo), np.log(hi), N + 1))
    n = np.concatenate([[incident], layers])
    return dict(name="Goupillaud", label="exact speaker", source="random", n=n, d_nm=goupillaud_d(n[1:-1]))
