"""Inverse design: target colour -> many Goupillaud film stacks (metamers with different voices).
Also: exact films for a given all-pole polynomial via spectral factorisation + layer peeling."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from . import colour as col
from . import lpc as _lpc
from .film import film_rt
from .mapping import (N_MIN, N_MAX, ORDER, goupillaud_d, poly_from_reflection, reflection_from_media,
                      media_from_reflection)


def stack_colour(n, illuminant="D65", quantity="T"):
    R, T = film_rt(n, goupillaud_d(n[1:-1]), col.WL)
    XYZ = col.spectrum_to_xyz(T if quantity == "T" else R, illuminant)
    return XYZ, col.xyz_to_lab(XYZ, illuminant)


def stack_formants(n):
    D = poly_from_reflection(reflection_from_media(n))
    return _lpc.formants_from_poly(D)


def design_stacks(target_lab, n_layers=ORDER, n_solutions=8, mode="realizable", illuminant="D65",
                  quantity="T", seed=0, restarts=60, tol=2.0):
    rng = np.random.default_rng(seed)
    lo, hi = (N_MIN, N_MAX) if mode != "ideal" else (0.2, 20.0)
    target = np.asarray(target_lab, float)

    def unpack(x):
        return np.concatenate([[1.0], np.exp(x)])

    def cost(x):
        _, lab = stack_colour(unpack(x), illuminant, quantity)
        return col.delta_e00(lab, target)

    found = []
    bounds = [(np.log(lo), np.log(hi))] * (n_layers + 1)
    for _ in range(restarts):
        x0 = rng.uniform(np.log(lo), np.log(hi), n_layers + 1)
        res = minimize(cost, x0, method="L-BFGS-B", bounds=bounds, options=dict(maxiter=200))
        if res.fun < tol:
            n = unpack(res.x)
            F, B = stack_formants(n)
            XYZ, lab = stack_colour(n, illuminant, quantity)
            found.append(dict(n=n, d_nm=goupillaud_d(n[1:-1]), Lab=lab, dE=float(res.fun),
                              a=poly_from_reflection(reflection_from_media(n)), F=F))
        if len(found) >= 3 * n_solutions:
            break
    return _diverse(found, n_solutions)


def _diverse(found, k):
    """Greedy farthest-point selection in (F1, F2) so metamers sound as different as possible."""
    if len(found) <= k:
        return found
    def key(s):
        F = list(s["F"]) + [0, 0]
        return np.array([F[0], F[1]], float)
    pts = np.array([key(s) for s in found])
    chosen = [int(np.argmin([s["dE"] for s in found]))]
    while len(chosen) < k:
        d = np.min(np.linalg.norm(pts[:, None] - pts[chosen][None], axis=2), axis=1)
        chosen.append(int(np.argmax(d)))
    return [found[i] for i in chosen]


def exact_films_for_polynomial(a, K_frac=0.5, flips=None, n_fft=4096):
    """All-pole target |1/A|^2 realised by a film with FINITE end media (no closed glottis):
    choose K = K_frac * min|A|^2, spectrally factor |G|^2 = |A|^2 - K (G of degree p), peel layers from
    (A, G). Different K and zero-flip choices give different index profiles with the SAME transmittance
    shape (same voice). Returns media vector m (len p+2, m_0=1) or None if peeling fails."""
    a = np.asarray(a, float)
    p = len(a) - 1
    w = np.exp(-1j * 2 * np.pi * np.arange(n_fft) / n_fft)
    A = np.polyval(a[::-1], w)
    K = K_frac * np.min(np.abs(A) ** 2)
    # minimum-phase spectral factor of |G|^2 = |A|^2 - K via the cepstrum (Kolmogorov); accurate
    # because the target is smooth and bounded away from 0.
    big = 1 << 16
    wb = np.exp(-1j * 2 * np.pi * np.arange(big) / big)
    S = np.abs(np.polyval(a[::-1], wb)) ** 2 - K
    cep = np.real(np.fft.ifft(0.5 * np.log(S)))  # log|G| = 0.5 log|G|^2
    fold = np.zeros(big)
    fold[0] = cep[0]
    fold[1:big // 2] = 2 * cep[1:big // 2]
    fold[big // 2] = cep[big // 2]
    g = np.real(np.fft.ifft(np.exp(np.fft.fft(fold))))[: p + 1]  # min-phase, degree p
    # optional zero flips r -> 1/conj(r) keep |G| (all-pass), giving other films with the same voice
    if flips:
        z = np.roots(g)
        for i in flips:
            if i < len(z):
                z[i] = 1 / np.conj(z[i])
        g2 = np.real(np.poly(z))
        G1 = np.polyval(g[::-1], w)
        G2 = np.polyval(g2[::-1], w)
        g = g2 * np.sqrt(np.mean(np.abs(G1) ** 2) / np.mean(np.abs(G2) ** 2))    # layer peeling of [F, G] with F = A:  reverse the row recursion
    F, G = a.copy(), g.copy()
    cs = []
    for _ in range(p):
        # leading (z^-m) coefficients: F[-1] = c * G'[-1], G[-1] = G'[-1]
        ci = F[-1] / G[-1] if abs(G[-1]) > 1e-14 else 0.0
        # [F,G] = [F' + c z^-1 G', c F' + z^-1 G']  ->  F' = (F - c G)/(1-c^2), z^-1 G' = (G - c F)/(1-c^2)
        Fp = (F - ci * G) / (1 - ci * ci)
        Gp = (G - ci * F) / (1 - ci * ci)
        cs.append(ci)
        F, G = Fp[:-1], Gp[1:]
    c0 = G[0] / F[0]
    c = np.array([c0] + cs[::-1])
    if np.any(np.abs(c) >= 1):
        return None
    return media_from_reflection(c, 1.0)
