"""Thin-film multilayer optics: Abelès characteristic-matrix method (Macleod's formulation).
n = [n_incident, n_1..n_N, n_substrate]; d_nm for the N layers. Oblique incidence, s/p/unpolarised.
Independent of the polynomial code in mapping.py."""
from __future__ import annotations

import numpy as np

from .mapping import (C_LIGHT, DNU, NU_MIN, ORDER, FS, f_of_nu)
from . import lpc as _lpc


def _rt_pol(n, d_nm, wl_nm, theta_deg, pol):
    n = np.asarray(n, complex)
    wl = np.atleast_1d(np.asarray(wl_nm, float))
    s0 = n[0] * np.sin(np.deg2rad(theta_deg))
    cos_t = np.sqrt(1 - (s0 / n) ** 2 + 0j)
    eta = n * cos_t if pol == "s" else n / cos_t
    B = np.ones(len(wl), complex)
    C = np.full(len(wl), eta[-1], complex)
    # multiply from the substrate side backwards: [B;C] = M1 M2 .. MN [1; eta_s]
    for j in range(len(n) - 2, 0, -1):
        delta = 2 * np.pi * n[j] * d_nm[j - 1] * cos_t[j] / wl
        cs, sn = np.cos(delta), np.sin(delta)
        B, C = cs * B + 1j * sn / eta[j] * C, 1j * eta[j] * sn * B + cs * C
    den = eta[0] * B + C
    r = (eta[0] * B - C) / den
    R = np.abs(r) ** 2
    T = 4 * np.real(eta[0]) * np.real(eta[-1]) / np.abs(den) ** 2
    return R, T


def film_rt(n, d_nm, wl_nm, theta_deg=0.0, pol="u"):
    d_nm = np.asarray(d_nm, float)
    if pol == "u" and theta_deg == 0:
        return _rt_pol(n, d_nm, wl_nm, 0.0, "s")  # s == p at normal incidence
    if pol == "u":
        Rs, Ts = _rt_pol(n, d_nm, wl_nm, theta_deg, "s")
        Rp, Tp = _rt_pol(n, d_nm, wl_nm, theta_deg, "p")
        return 0.5 * (Rs + Rp), 0.5 * (Ts + Tp)
    return _rt_pol(n, d_nm, wl_nm, theta_deg, pol)


def film_rt_nu(n, d_nm, nu_hz, theta_deg=0.0, pol="u"):
    return film_rt(n, d_nm, C_LIGHT / np.asarray(nu_hz, float) * 1e9, theta_deg, pol)


def voice_of_film(n, d_nm, theta_deg=0.0, p=ORDER, n_freq=2048, dnu=None):
    """All-pole 'voice' of a film: T over exactly one period of nu (the visible band), mapped to the
    speech circle omega = 2*pi*f/FS, used as a power spectrum -> autocorrelation -> Levinson.
    Exact for Goupillaud stacks with N <= p (a = D(z)); best all-pole fit otherwise.
    Returns (a, gain) with |gain/A|^2 ~ T."""
    # uniform grid in f over [0, FS): pick nu so that f_of_nu covers it once (one period starting at NU_MIN).
    # dnu = period of the mapping (default: the brief's 350 THz; DNU_FULL for the full-band mapping).
    dnu = DNU if dnu is None else dnu
    f = np.arange(n_freq) * FS / n_freq
    nu = NU_MIN + ((f / FS - (NU_MIN / dnu) % 1.0) % 1.0) * dnu
    _, T = film_rt_nu(n, d_nm, nu, theta_deg)
    assert np.allclose(f_of_nu(nu, dnu), f, atol=1e-6 * FS)
    r = np.real(np.fft.ifft(T))[: p + 1]
    a, _, err = _lpc.levinson(r, p)
    return a, float(np.sqrt(max(err, 0.0)))
