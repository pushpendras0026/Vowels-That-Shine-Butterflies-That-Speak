"""Linear prediction (LPC) with the sign convention of docs/CONTRACT.md §3.

a = [1, a1..ap],  A(z) = sum a_i z^-i,  e[n] = sum a_i x[n-i],  H(z) = g/A(z).
Step-up:  a^(m)_i = a^(m-1)_i + k_m a^(m-1)_{m-i},  a^(m)_m = k_m.
Closed glottis tube:  k_m = -c_m  (c = tube/film reflection coefficient, glottis->lips order).
"""
from __future__ import annotations

import numpy as np

FS = 16000


def autocorr(x, p):
    x = np.asarray(x, float)
    n = len(x)
    return np.array([np.dot(x[: n - i], x[i:]) for i in range(p + 1)])


def levinson(r, p):
    r = np.asarray(r, float)
    a = np.zeros(p + 1)
    a[0] = 1.0
    k = np.zeros(p)
    err = r[0]
    if err <= 0:
        return a, k, 0.0
    for m in range(1, p + 1):
        acc = r[m] + np.dot(a[1:m], r[m - 1:0:-1])
        km = -acc / err
        prev = a.copy()
        a[1:m] = prev[1:m] + km * prev[m - 1:0:-1]
        a[m] = km
        k[m - 1] = km
        err *= (1.0 - km * km)
        if err <= 0:
            err = 0.0
            break
    return a, k, err


def lpc(x, p=16, preemph=0.97, window="hamming"):
    x = np.asarray(x, float)
    if preemph:
        x = np.append(x[0], x[1:] - preemph * x[:-1])
    if window == "hamming":
        x = x * np.hamming(len(x))
    r = autocorr(x, p)
    r[0] *= 1.0 + 1e-9  # tiny white-noise floor for numerical stability
    a, k, err = levinson(r, p)
    return a, k, float(np.sqrt(max(err, 0.0)))


def step_up(k):
    a = np.array([1.0])
    for km in np.asarray(k, float):
        ext = np.append(a, 0.0)
        a = ext + km * ext[::-1]
    return a


def step_down(a):
    a = np.asarray(a, float).copy()
    if abs(a[0] - 1) > 1e-12:
        a = a / a[0]
    p = len(a) - 1
    k = np.zeros(p)
    for m in range(p, 0, -1):
        km = a[m]
        if abs(km) >= 1:
            raise ValueError(f"unstable polynomial: |k_{m}| = {abs(km):.6f} >= 1")
        k[m - 1] = km
        a = (a[: m] - km * a[m:0:-1]) / (1 - km * km)
        a = a[:m]
    return k


def reflection_to_areas(k, A1=1.0):
    k = np.asarray(k, float)
    areas = [A1]
    for km in k:
        areas.append(areas[-1] * (1 + km) / (1 - km))
    return np.array(areas)


def areas_to_reflection(areas):
    A = np.asarray(areas, float)
    # k_m = -c_m,  c_m = (A_m - A_{m+1})/(A_m + A_{m+1})
    return (A[1:] - A[:-1]) / (A[1:] + A[:-1])


def poly_from_formants(F, B, fs=FS):
    a = np.array([1.0])
    for f, b in zip(F, B):
        r = np.exp(-np.pi * b / fs)
        th = 2 * np.pi * f / fs
        a = np.convolve(a, [1.0, -2 * r * np.cos(th), r * r])
    return a


def formants_from_poly(a, fs=FS, fmin=90.0, max_bw=600.0):
    roots = np.roots(a)
    roots = roots[np.imag(roots) > 1e-9]
    F = np.angle(roots) * fs / (2 * np.pi)
    B = -np.log(np.maximum(np.abs(roots), 1e-12)) * fs / np.pi
    keep = (F > fmin) & (F < fs / 2 - 50) & (B < max_bw)
    F, B = F[keep], B[keep]
    order = np.argsort(F)
    return F[order], B[order]


def envelope_db(a, gain=1.0, nfft=1024, fs=FS):
    A = np.fft.rfft(a, nfft)
    f = np.arange(len(A)) * fs / nfft
    return f, 20 * np.log10(gain / np.maximum(np.abs(A), 1e-12))
