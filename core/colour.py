"""Colour science (CIE 1931 2°, illuminants from the `colour-science` package). CONTRACT §5.
Implemented with explicit formulas (sRGB IEC 61966-2-1, CIELAB, CIEDE2000) so the JS port can match;
tests cross-check against `colour-science`."""
from __future__ import annotations

import numpy as np
import colour as _cs

from .film import film_rt

WL = np.arange(360.0, 830.0 + 1e-9, 0.5)
_ILL_KEYS = {"D65": "D65", "A": "A", "F11": "FL11", "LED": "LED-B3"}


def _interp(sd):
    return np.interp(WL, sd.wavelengths, sd.values, left=0.0, right=0.0)


_cmf = _cs.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
CMF = np.stack([np.interp(WL, _cmf.wavelengths, _cmf.values[:, i], left=0, right=0) for i in range(3)], 1)
ILLUMINANTS = {k: _interp(_cs.SDS_ILLUMINANTS[v]) for k, v in _ILL_KEYS.items()}

M_XYZ_TO_SRGB = np.array([[3.2404542, -1.5371385, -0.4985314],
                          [-0.9692660, 1.8760108, 0.0415560],
                          [0.0556434, -0.2040259, 1.0572252]])


def spectrum_to_xyz(S, illuminant="D65"):
    E = ILLUMINANTS[illuminant]
    k = 100.0 / np.sum(E * CMF[:, 1])
    return k * (np.asarray(S, float) * E) @ CMF


def white_xyz(illuminant="D65"):
    return spectrum_to_xyz(np.ones_like(WL), illuminant)


def xyz_to_lab(XYZ, illuminant="D65"):
    Wn = white_xyz(illuminant)
    t = np.asarray(XYZ, float) / Wn
    d = 6 / 29
    f = np.where(t > d ** 3, np.cbrt(t), t / (3 * d * d) + 4 / 29)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def _gamma(u):
    u = np.clip(u, 0, 1)
    return np.where(u <= 0.0031308, 12.92 * u, 1.055 * u ** (1 / 2.4) - 0.055)


def xyz_to_srgb(XYZ):
    """XYZ (Y in 0..100, no chromatic adaptation) -> gamma-encoded sRGB in [0,1] (clipped)."""
    return _gamma(M_XYZ_TO_SRGB @ (np.asarray(XYZ, float) / 100.0))


def display_rgb(XYZ, target_Y=50.0):
    """ARTISTIC exposure normalisation for display: scale so Y = target_Y, then sRGB."""
    XYZ = np.asarray(XYZ, float)
    if XYZ[1] <= 1e-12:
        return np.zeros(3)
    lin = M_XYZ_TO_SRGB @ (XYZ * (target_Y / XYZ[1]) / 100.0)
    m = lin.max()
    if m > 1:
        lin = lin / m
    return _gamma(lin)


def to_hex(rgb):
    v = np.round(np.clip(rgb, 0, 1) * 255).astype(int)
    return "#%02x%02x%02x" % tuple(v)


def delta_e00(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    if C1p * C2p == 0:
        dh = 0.0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return float(np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                         + Rt * (dCp / Sc) * (dHp / Sh)))


def film_colour(n, d_nm, theta_deg=0.0, illuminant="D65", quantity="T"):
    R, T = film_rt(n, d_nm, WL, theta_deg)
    S = T if quantity == "T" else R
    XYZ = spectrum_to_xyz(S, illuminant)
    rgb = display_rgb(XYZ)
    return {"XYZ": XYZ, "Lab": xyz_to_lab(XYZ, illuminant), "rgb": rgb, "hex": to_hex(rgb),
            "rgb_abs": xyz_to_srgb(XYZ)}
