"""Source-filter synthesis: Rosenberg (1971) glottal pulse -> all-pole filter. CONTRACT §5.

Consonant excitation (added 2026-11-23, PHONEMES track): `excitation(cls, voiced, ...)` builds the source for every
phoneme class so that a film / LPC polynomial can speak consonants, not only buzz:
  vowel, nasal, lateral, approximant, diphthong -> glottal pulse train (Rosenberg derivative)
  fricative (voiceless, incl. h)                -> white Gaussian noise (turbulence at the constriction)
  fricative (voiced: v z ʒ ð)                   -> glottal pulses + pitch-synchronously modulated noise
  plosive   -> closure (silence; voice bar if voiced) -> burst (noise, 3 ms decay) -> aspiration
               (voiceless: decaying noise, 40 ms) -> voiced onset
  affricate -> plosive closure + burst -> fricative noise (mixed if voiced)
`speak(a, cls, voiced, ...)` = excitation -> all-pole 1/A(z). All random sources are seeded (deterministic).
"""
from __future__ import annotations

import wave

import numpy as np
from scipy.signal import lfilter

from .mapping import FS
from . import lpc as _lpc


def rosenberg(f0, fs=FS, dur=1.0, oq=0.6, sq=2.0, jitter=0.0, seed=0):
    """Rosenberg type-B glottal flow. oq = open quotient, sq = speed quotient (opening/closing)."""
    rng = np.random.default_rng(seed)
    n = int(round(dur * fs))
    u = np.zeros(n)
    t = 0
    while t < n:
        T0 = fs / (f0 * (1 + jitter * rng.standard_normal()))
        To = oq * T0
        Tp = To * sq / (1 + sq)
        Tn = To - Tp
        L = int(round(T0))
        k = np.arange(L)
        seg = np.zeros(L)
        o = k < Tp
        seg[o] = 0.5 * (1 - np.cos(np.pi * k[o] / Tp))
        c = (k >= Tp) & (k < To)
        seg[c] = np.cos(np.pi * (k[c] - Tp) / (2 * Tn))
        m = min(L, n - t)
        u[t:t + m] = seg[:m]
        t += L
    return u


def glottal_source(f0, fs=FS, dur=1.0, **kw):
    """Derivative of Rosenberg flow (glottal flow + lip radiation 1 - z^-1)."""
    u = rosenberg(f0, fs, dur, **kw)
    return np.diff(u, prepend=0.0)


def synth_allpole(a, source, gain=1.0):
    return lfilter([gain], a, source)


def _norm(y, peak=0.9):
    m = np.max(np.abs(y))
    return y * (peak / m) if m > 0 else y


def film_voice(n, d_nm, f0=140.0, dur=1.2, theta=0.0, fs=FS):
    from .film import voice_of_film
    a, g = voice_of_film(n, d_nm, theta)
    y = synth_allpole(a, glottal_source(f0, fs, dur, jitter=0.01), g)
    return _fade(_norm(y), fs)


def _fade(y, fs, ms=20):
    k = min(len(y) // 2, int(fs * ms / 1000))
    w = np.ones(len(y))
    w[:k] = np.linspace(0, 1, k)
    w[-k:] = np.linspace(1, 0, k)
    return y * w


def sing(a_list, durations, f0=140.0, fs=FS, hop=80, domain="k"):
    """Sequence of all-pole filters; interpolates reflection coefficients (always stable).

    domain="k" (default) interpolates k linearly; domain="lar" interpolates log-area ratios 2·atanh(k)
    (|k| clipped to 0.995), i.e. the log cross-section areas of the tube / log index ratios of the film."""
    ks = [_lpc.step_down(a) for a in a_list]
    if domain == "lar":
        ks = [2 * np.arctanh(np.clip(k, -0.995, 0.995)) for k in ks]
    times = np.concatenate([[0], np.cumsum(durations)])
    total = times[-1]
    src = glottal_source(f0, fs, total, jitter=0.01)
    centres = (times[:-1] + times[1:]) / 2
    out = np.zeros(len(src))
    p = len(ks[0])
    state = np.zeros(p)
    for start in range(0, len(src), hop):
        tt = start / fs
        kk = np.array([np.interp(tt, centres, [k[i] for k in ks]) for i in range(p)])
        if domain == "lar":
            kk = np.tanh(kk / 2)
        a = _lpc.step_up(kk)
        seg = src[start:start + hop]
        y, state = lfilter([1.0], a, seg, zi=state)
        out[start:start + len(seg)] = y
    return _fade(_norm(out), fs)


# ----------------------------------------------------------------------------- consonant excitation
DEFAULT_DUR = {"plosive": 0.35, "affricate": 0.45, "fricative": 0.5}
CLOSURE_S, BURST_TAU_S, BURST_S, ASPIR_S = 0.08, 0.003, 0.012, 0.04


def _unit(x):
    r = np.sqrt(np.mean(x ** 2)) if len(x) else 0.0
    return x / r if r > 0 else x


def noise_source(dur, fs=FS, seed=0):
    """Unit-RMS white Gaussian noise (turbulence source), deterministic for a given seed."""
    return np.random.default_rng(seed).standard_normal(int(round(dur * fs)))


def _ramp(n, fs, att_ms=15.0, rel_ms=30.0):
    w = np.ones(n)
    a, r = min(n // 2, int(fs * att_ms / 1000)), min(n // 2, int(fs * rel_ms / 1000))
    if a:
        w[:a] = np.linspace(0, 1, a)
    if r:
        w[-r:] = np.linspace(1, 0, r)
    return w


def _mixed(f0, dur, fs, seed, noise_ratio=0.5):
    """Voiced frication: glottal pulses + noise amplitude-modulated by the glottal flow (pitch-synchronous)."""
    u = rosenberg(f0, fs, dur, jitter=0.01, seed=seed)
    g = _unit(np.diff(u, prepend=0.0))
    nz = _unit(noise_source(dur, fs, seed + 1) * (0.3 + u))
    return g + noise_ratio * nz


def _plosive_head(voiced, f0, fs, seed):
    """Closure + burst (+ aspiration if voiceless); returns (head, n_burst_start)."""
    nc, nb = int(CLOSURE_S * fs), int(BURST_S * fs)
    closure = np.zeros(nc)
    if voiced:                                   # voice bar: weak glottal buzz during the closure
        closure = 0.05 * _unit(glottal_source(f0, fs, CLOSURE_S, jitter=0.01, seed=seed + 2))
    t = np.arange(nb) / fs
    burst = 3.0 * noise_source(BURST_S, fs, seed + 3) * np.exp(-t / BURST_TAU_S)
    head = [closure, burst]
    if not voiced:
        na = int(ASPIR_S * fs)
        ta = np.arange(na) / fs
        head.append(0.5 * noise_source(ASPIR_S, fs, seed + 4) * np.exp(-ta / (ASPIR_S / 3)))
    return np.concatenate(head), nc


def excitation(cls, voiced, f0=120.0, dur=None, fs=FS, seed=0):
    """Source signal for phoneme class `cls` (CONTRACT §5). Length = round(dur·fs). Deterministic per seed.

    Sustained parts are unit-RMS; plosive bursts are ~3x louder than the following onset."""
    dur = float(dur if dur is not None else DEFAULT_DUR.get(cls, 0.6))
    n = int(round(dur * fs))
    if cls in ("vowel", "nasal", "lateral", "approximant", "diphthong"):
        return _unit(glottal_source(f0, fs, dur, jitter=0.01, seed=seed))
    if cls == "fricative":
        x = _mixed(f0, dur, fs, seed) if voiced else noise_source(dur, fs, seed)
        return x * _ramp(n, fs)
    if cls in ("plosive", "affricate"):
        head, _ = _plosive_head(voiced, f0, fs, seed)
        rest = max(0, n - len(head))
        rd = rest / fs
        if cls == "plosive":                      # release into the (voiced) vowel onset
            tail = _unit(glottal_source(f0, fs, rd, jitter=0.01, seed=seed + 5)) if rest else np.zeros(0)
            tail = tail * _ramp(rest, fs, att_ms=20.0, rel_ms=30.0) * 0.6
        else:                                     # release into frication (mixed if voiced)
            tail = (_mixed(f0, rd, fs, seed + 5) if voiced else noise_source(rd, fs, seed + 5)) if rest else np.zeros(0)
            tail = tail * _ramp(rest, fs, att_ms=5.0, rel_ms=30.0)
        x = np.concatenate([head, tail])
        return x[:n] if len(x) >= n else np.append(x, np.zeros(n - len(x)))
    raise ValueError(f"unknown phoneme class {cls!r}")


def speak(a, cls, voiced, f0=120.0, dur=None, fs=FS, gain=1.0, seed=0):
    """The polynomial's own voice with class-appropriate excitation: excitation -> 1/A(z), peak 0.9, 5 ms fades."""
    y = synth_allpole(np.asarray(a, float), excitation(cls, voiced, f0, dur, fs, seed), gain)
    return _fade(_norm(y), fs, ms=5)


def write_wav(path, y, fs=FS):
    y16 = np.int16(np.clip(y, -1, 1) * 32767)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(y16.tobytes())
