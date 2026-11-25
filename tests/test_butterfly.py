"""Realistic butterfly-scale model (core/butterfly.py): physics checks + published facts.
Fast (< 20 s) when results/cache_butterfly_tables.npz exists (written by `python -m core.butterfly`)."""
import json
from pathlib import Path

import numpy as np
import pytest

from core import butterfly as b, colour as col, film

WL = b.WL_GRID


def _Y(R):
    return col.spectrum_to_xyz(b._full(R))[1]


def _hue(R):
    L, a, bb = col.xyz_to_lab(col.spectrum_to_xyz(b._full(R)))
    return np.degrees(np.arctan2(bb, a)) % 360


def test_tmm_matches_core_film_lossless_and_lossy():
    e = b.effective_film("Morpho rhetenor")
    for th in (0.0, 40.0):
        Rf, Tf = film.film_rt(e["n"], e["d_nm"], WL, th)
        n = np.repeat(np.asarray(e["n"], complex)[:, None], WL.size, 1)
        R = 0.5 * sum(b.tmm(n, e["d_nm"], WL, [th], p)[0][0, 0] for p in "sp")
        assert np.abs(R - Rf).max() < 1e-12
    n, d = b.build_stack("Chrysochroa fulgidissima", WL)      # absorbing; core.film wants N = n - ik
    R, _, _ = b.tmm(n, d, WL, [50.0], "p")
    Rf = np.array([film._rt_pol(np.conj(n[:, i]), d, [w], 50.0, "p")[0][0] for i, w in enumerate(WL)])
    assert np.abs(R[0, 0] - Rf).max() < 1e-12


@pytest.mark.parametrize("name", ["Morpho rhetenor", "Chrysochroa fulgidissima"])
def test_energy_conservation(name):
    for lossless in (True, False):
        n, d = b.build_stack(name, WL, lossless=lossless)
        dd = d[None] * (1 + 0.1 * np.random.default_rng(1).standard_normal((4, d.size)))
        for pol in "sp":
            R, T, A = b.tmm(n, dd, WL, [0.0, 45.0, 75.0], pol)
            assert np.abs(R + T + A - 1).max() < 1e-10          # A computed independently
            if lossless:
                assert np.abs(A).max() < 1e-10
            else:
                assert A.min() > 0 and A.max() < 1
            assert R.min() >= 0 and R.max() <= 1


@pytest.mark.parametrize("name", ["Morpho rhetenor", "Morpho didius"])
def test_morpho_blue_and_broad(name):
    R = b.model_R(name, [0, 40])
    peak = WL[np.argmax(R[0])]
    assert 430 <= peak <= 480
    assert 230 <= _hue(R[1]) <= 300                                 # still bluish at 40°
    Ri = b.model_R(name, [0, 40], b.IDEAL_FLAGS)
    keep_real, keep_ideal = _Y(R[1]) / _Y(R[0]), _Y(Ri[1]) / _Y(Ri[0])
    assert keep_real > 0.8 and keep_real > keep_ideal                # broad angular reflection


def test_papilio_green():
    R = b.model_R("Papilio blumei", [0])[0]
    assert 520 <= WL[np.argmax(R)] <= 560
    assert 100 <= _hue(R) <= 170


def test_disorder_broadens_and_lowers():
    only = {k: False for k in b.DEFAULT_FLAGS}
    # width = equivalent width ∫R dλ / R_max (FWHM is not monotone for saturated flat-top stop bands:
    # Morpho didius FWHM 140 -> 136 nm while its equivalent width grows 151 -> 157 nm)
    for name in b.species():
        Ri = b.model_R(name, [0], only)[0]
        Rd = b.model_R(name, [0], {**only, "disorder": True})[0]
        assert Rd.max() < Ri.max()
        assert Rd.sum() / Rd.max() > Ri.sum() / Ri.max()
    Ri = b.model_R("Chrysiridia rhipheus", [0], only)[0]
    Rd = b.model_R("Chrysiridia rhipheus", [0], {**only, "disorder": True})[0]
    assert b._fwhm(Rd) > b._fwhm(Ri)


def test_compare_and_json():
    e = b.effective_film("Morpho rhetenor")
    c = b.compare_film_to_species(e["n"], e["d_nm"])
    assert set(c) == set(b.species())
    assert all(np.isfinite(v["dE00"]) and -1 <= v["spectral_corr"] <= 1 for v in c.values())
    assert max(c, key=lambda k: c[k]["spectral_corr"]).startswith("Morpho")
    p = Path(__file__).resolve().parent.parent / "results" / "butterfly_real.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert set(d["species"]) == set(b.species())
        assert all(s["citations"] for s in d["species"].values())
