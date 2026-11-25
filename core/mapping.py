"""The shared object (media vector), reflection coefficients, the characteristic polynomial and the
tube-frequency <-> light-frequency mapping. See docs/CONTRACT.md §1, §2, §4."""
from __future__ import annotations

import numpy as np

from . import lpc as _lpc

FS = 16000
ORDER = 16
C_SOUND = 350.0
L_TRACT = ORDER * C_SOUND / (2 * FS)  # 0.175 m
C_LIGHT = 299_792_458.0
NU_MIN, NU_MAX = 400e12, 750e12
DNU = NU_MAX - NU_MIN  # 350 THz = one 2*pi period
D_OPT_NM = C_LIGHT / (2 * DNU) * 1e9  # 428.2749 nm optical thickness of every layer
# Second exact mapping ("full-band", CONTRACT §4b): period 750 THz, every layer half-wave at 400 nm, so the
# visible band 400-750 THz covers the audio band 0-7.47 kHz exactly ONCE (f = 0 at 750 THz, no mirror image).
DNU_FULL = 750e12
D_OPT_FULL_NM = C_LIGHT / (2 * DNU_FULL) * 1e9  # 199.8617 nm
MAPPINGS = {"brief": dict(dnu=DNU, d_opt=D_OPT_NM), "full": dict(dnu=DNU_FULL, d_opt=D_OPT_FULL_NM)}
R_GLOTTIS = -0.9  # illustrative finite glottal termination
N_MIN, N_MAX = 1.0, 2.5
MATERIALS = {"air": 1.00, "MgF2": 1.38, "SiO2": 1.46, "chitin": 1.56,
             "Al2O3": 1.77, "ZnS": 2.35, "TiO2": 2.40}


def reflection_from_media(m):
    m = np.asarray(m, float)
    return (m[:-1] - m[1:]) / (m[:-1] + m[1:])


def media_from_reflection(c, m0=1.0):
    m = [m0]
    for ci in np.asarray(c, float):
        m.append(m[-1] * (1 - ci) / (1 + ci))
    return np.array(m)


def poly_from_reflection(c):
    """Row recursion [F,G]=[1,c0]; [F,G] <- [F + c z^-1 G, c F + z^-1 G]. Returns D (degree N)."""
    c = np.asarray(c, float)
    F = np.array([1.0])
    G = np.array([c[0]])
    for ci in c[1:]:
        Gs = np.append(0.0, G)          # z^-1 G
        Fe = np.append(F, 0.0)
        F, G = Fe + ci * Gs, ci * Fe + Gs
    return F


def power_transfer(c, omega):
    c = np.asarray(c, float)
    D = poly_from_reflection(c)
    z = np.exp(-1j * np.outer(np.atleast_1d(omega), np.arange(len(D))))
    return np.prod(1 - c ** 2) / np.abs(z @ D) ** 2


def omega_of_nu(nu, d_opt=D_OPT_NM):
    return 4 * np.pi * d_opt * 1e-9 * np.asarray(nu, float) / C_LIGHT  # = 2*delta


def dnu_of(d_opt):
    """Period in nu of a Goupillaud stack whose layers all have optical thickness d_opt (nm)."""
    return C_LIGHT / (2 * d_opt * 1e-9)


def f_of_nu(nu, dnu=DNU):
    x = np.asarray(nu, float) / dnu
    return FS * (x - np.floor(x))


def nu_images(f, dnu=DNU):
    """All nu in [NU_MIN, NU_MAX) with f_of_nu(nu) = +-f (mod FS)."""
    out = []
    for ff in (f, FS - f):
        base = (ff / FS) * dnu
        kmin = int(np.ceil((NU_MIN - base) / dnu))
        for k in range(kmin, kmin + 3):
            nu = base + k * dnu
            if NU_MIN <= nu < NU_MAX:
                out.append(nu)
    return np.unique(np.round(np.array(out), 3))


def vowel_media(a, r_glottis=R_GLOTTIS):
    k = _lpc.step_down(a)
    areas = _lpc.reflection_to_areas(k, A1=1.0)  # p sections + radiation
    m0 = areas[0] * (1 + r_glottis) / (1 - r_glottis)
    return np.concatenate([[m0], areas])


def film_from_media(m, mode="ideal"):
    m = np.asarray(m, float)
    ratio = m / m.min()
    if mode == "ideal":
        return ratio * N_MIN
    span = np.log(ratio.max())
    gamma = 1.0 if span <= 0 else min(1.0, np.log(N_MAX / N_MIN) / span)
    n = N_MIN * ratio ** gamma
    if mode == "realizable":
        return n
    if mode == "materials":
        vals = np.array(sorted(MATERIALS.values()))
        idx = np.argmin(np.abs(np.log(n)[:, None] - np.log(vals)[None, :]), axis=1)
        return vals[idx]
    raise ValueError(mode)


def goupillaud_d(n_layers, d_opt=D_OPT_NM):
    return d_opt / np.asarray(n_layers, float)
