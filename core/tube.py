"""Acoustic tube models (independent of the polynomial code in mapping.py).

Two independent implementations:
  * tube_power_transfer: frequency-domain acoustic ABCD chain in physical units (L, c, f).
  * kl_impulse_response: time-domain Kelly-Lochbaum scattering lattice (pressure waves).
Convention (CONTRACT §2): media m_0 (glottis side) .. m_{N+1} (radiation), sections glottis->lips,
c_i = (m_i - m_{i+1})/(m_i + m_{i+1}); acoustic admittance of a tube ∝ its area (rho*c = 1).
"""
from __future__ import annotations

import numpy as np

from .mapping import C_SOUND, L_TRACT


def _chain(areas, f_hz, L, c):
    """ABCD matrix (p,U)_in = M (p,U)_out for sections `areas` (glottis->lips), per frequency."""
    f = np.atleast_1d(np.asarray(f_hz, float))
    ell = L / len(areas)
    kl = 2 * np.pi * f * ell / c
    M = np.zeros((len(f), 2, 2), complex)
    M[:, 0, 0] = M[:, 1, 1] = 1.0
    for A in areas:
        Z = 1.0 / A
        S = np.empty_like(M)
        S[:, 0, 0] = np.cos(kl)
        S[:, 0, 1] = 1j * Z * np.sin(kl)
        S[:, 1, 0] = 1j * np.sin(kl) / Z
        S[:, 1, 1] = np.cos(kl)
        M = M @ S
    return M


def tube_power_transfer(m, f_hz, L=L_TRACT, c=C_SOUND):
    """Power transmission from a semi-infinite tube of area m_0 into one of area m_{N+1}."""
    m = np.asarray(m, float)
    M = _chain(m[1:-1], f_hz, L, c)
    Z0, ZL = 1.0 / m[0], 1.0 / m[-1]
    # output: only an outgoing wave, p_out = ZL * U_out ; take U_out = 1
    p_in = M[:, 0, 0] * ZL + M[:, 0, 1]
    U_in = M[:, 1, 0] * ZL + M[:, 1, 1]
    p_plus = 0.5 * (p_in + Z0 * U_in)
    return (np.abs(ZL) ** 2 / ZL) / (np.abs(p_plus) ** 2 / Z0)


def tube_volume_velocity_transfer(areas, f_hz, L=L_TRACT, c=C_SOUND):
    """|U_lips / U_glottis| for a closed-glottis (volume-velocity source), ideal open lips (p=0)."""
    M = _chain(np.asarray(areas, float), f_hz, L, c)
    return 1.0 / np.abs(M[:, 1, 1])


def uniform_tube_resonances(L=L_TRACT, c=C_SOUND, n=3):
    return np.array([(2 * k - 1) * c / (4 * L) for k in range(1, n + 1)])


def kl_impulse_response(c, n_samples, source="incident"):
    """Kelly-Lochbaum lattice. c = [c_0..c_N]. Simulated at 2*FS (one-way delay = 1 sample per
    section), then the response is sampled at FS (one sample per section round trip), aligned so
    that out[0] is the first arrival. source="incident": unit pressure wave incident from medium 0
    (response = prod(1+c)/D(z)); source="inject": ideal source injecting directly into section 1 (needed
    for a closed glottis c_0=-1; response = prod_{i>=1}(1+c_i)/D(z)). Returns pressure transmitted into the radiation medium for a
    unit pressure impulse incident from the glottis medium; equals prod(1+c) / D(z) (CONTRACT §2)."""
    c = np.asarray(c, float)
    N = len(c) - 1
    total = N + 2 * n_samples + 2
    fwd = np.zeros(N)   # forward wave arriving at the right end of section i (after its delay)
    bwd = np.zeros(N)   # backward wave arriving at the left end of section i
    y = np.zeros(total)
    for t in range(total):
        x = 1.0 if t == 0 else 0.0
        new_fwd_in = np.zeros(N)   # wave entering section i at its left end
        new_bwd_in = np.zeros(N)   # wave entering section i at its right end
        # glottis junction (between medium 0 and section 1)
        gain_in = (1 + c[0]) if source == "incident" else 1.0
        new_fwd_in[0] = gain_in * x - c[0] * bwd[0]
        # internal junctions i | i+1  (c index i+1)
        for i in range(N - 1):
            ci = c[i + 1]
            new_fwd_in[i + 1] = (1 + ci) * fwd[i] - ci * bwd[i + 1]
            new_bwd_in[i] = ci * fwd[i] + (1 - ci) * bwd[i + 1]
        # lips junction
        y[t] = (1 + c[N]) * fwd[N - 1]
        new_bwd_in[N - 1] = c[N] * fwd[N - 1]
        # one-sample propagation through each section
        fwd, bwd = new_fwd_in, new_bwd_in
    # first arrival appears at t = N
    return y[N::2][:n_samples]
