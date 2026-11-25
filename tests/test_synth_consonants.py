"""Consonant excitation (core.synth.excitation / speak): shape, finiteness, spectral band, determinism."""
import numpy as np
import pytest

from core import lpc, synth
from core.mapping import FS


def _hf_fraction(x, f_cut=2500.0):
    S = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / FS)
    return S[f > f_cut].sum() / S.sum()


CASES = [("vowel", True), ("nasal", True), ("lateral", True), ("approximant", True), ("diphthong", True),
         ("fricative", False), ("fricative", True), ("plosive", False), ("plosive", True),
         ("affricate", False), ("affricate", True)]


@pytest.mark.parametrize("cls,voiced", CASES)
def test_excitation_shape_finite_deterministic(cls, voiced):
    x = synth.excitation(cls, voiced, f0=120, dur=0.3, seed=3)
    assert x.shape == (int(0.3 * FS),) and np.isfinite(x).all() and np.abs(x).max() > 0
    assert np.array_equal(x, synth.excitation(cls, voiced, f0=120, dur=0.3, seed=3))
    if cls in ("fricative", "plosive", "affricate"):
        assert not np.array_equal(x, synth.excitation(cls, voiced, f0=120, dur=0.3, seed=4))


def test_excitation_bands():
    voiced = synth.excitation("vowel", True, dur=0.3)
    noise = synth.excitation("fricative", False, dur=0.3)
    assert _hf_fraction(voiced) < 0.15          # glottal spectrum falls ~12 dB/oct
    assert 0.6 < _hf_fraction(noise) < 0.8      # white: 5.5/8 kHz above 2.5 kHz ≈ 0.69
    mixed = synth.excitation("fricative", True, dur=0.3)
    assert _hf_fraction(voiced) < _hf_fraction(mixed) < _hf_fraction(noise)


def test_plosive_closure_burst_order():
    x = synth.excitation("plosive", False, dur=0.3)
    nc = int(synth.CLOSURE_S * FS)
    assert np.all(x[:nc] == 0)                  # voiceless closure is silent
    burst = x[nc:nc + int(0.005 * FS)]
    later = x[nc + int(0.15 * FS):]
    assert np.sqrt(np.mean(burst ** 2)) > 1.5 * np.sqrt(np.mean(later ** 2))
    xb = synth.excitation("plosive", True, dur=0.3)
    assert 0 < np.abs(xb[:nc]).max() < 0.5      # voice bar: weak but present


def test_affricate_frication_after_burst():
    x = synth.excitation("affricate", False, dur=0.4)
    nc = int(synth.CLOSURE_S * FS)
    tail = x[nc + int(0.1 * FS):nc + int(0.25 * FS)]
    assert np.sqrt(np.mean(tail ** 2)) > 0.5 and _hf_fraction(tail) > 0.5


def test_speak_fricative_energy_band():
    a_s = lpc.poly_from_formants([5000, 6500], [400, 500])      # [s]-like high resonances
    y = synth.speak(a_s, "fricative", False, dur=0.3, seed=1)
    assert np.isfinite(y).all() and abs(np.abs(y).max() - 0.9) < 1e-9
    assert _hf_fraction(y, 4000) > 0.7
    a_v = lpc.poly_from_formants([700, 1200], [80, 100])
    yv = synth.speak(a_v, "vowel", True, dur=0.3)
    assert _hf_fraction(yv, 2500) < 0.05
    with pytest.raises(ValueError):
        synth.excitation("click", False)


def test_sing_lar_domain():
    a1 = lpc.poly_from_formants([750, 1200], [80, 100])
    a2 = lpc.poly_from_formants([300, 2300], [80, 100])
    y = synth.sing([a1, a2], [0.15, 0.15], domain="lar")
    assert np.isfinite(y).all() and len(y) == int(0.3 * FS)
