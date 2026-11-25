"""Validation of core/fluorescence.py (approximate fluorescence-in-a-film model). Runs in a few seconds."""
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from core import fluorescence as F

ROOT = Path(__file__).resolve().parents[1]
I505 = int(np.argmin(np.abs(F.WL - 505)))


@pytest.fixture(scope="module")
def papilio():
    return {ill: F.papilio_appearance(ill) for ill in F.ILLUMINANTS}


def test_fluorophore_shape():
    f = F.PAPILIOCHROME
    assert F.WL[np.argmax(f.emission())] == pytest.approx(505, abs=1)
    assert F.WL[np.argmax(f.excitation())] == pytest.approx(420, abs=1)
    assert np.sum(f.emission()) == pytest.approx(1.0)
    assert f.stokes_shift()["nm"] == pytest.approx(85)


def test_papilio_emission_peak(papilio):
    for ill in ("UV365", "violet405", "D65"):
        assert 490 <= papilio[ill]["peak_emission_nm"] <= 520


def test_qy_zero_gives_no_fluorescence():
    p = F.papilio_nireus_scale()
    a = F.appearance(p["n"], p["d_nm"], "violet405", fluor=replace(F.PAPILIOCHROME, qy=0.0), dye_layers=[1])
    assert a["absorbed_photons"] > 0
    assert np.all(a["fluo"] == 0) and a["fluor_fraction"] == 0 and a["emitted_photons"] == 0


def test_energy_conservation(papilio):
    p = F.papilio_nireus_scale()
    for ill in F.ILLUMINANTS:
        a = F.appearance(p["n"], p["d_nm"], ill, dye_layers=[1])
        assert np.all((a["A"] >= 0) & (a["A"] <= 1))
        assert np.all((a["eta"] >= 0) & (a["eta"] <= 1 + 1e-12))
        assert a["emitted_photons"] <= F.PAPILIOCHROME.qy * a["absorbed_photons"] * (1 + 1e-9)
        assert a["emitted_photons"] <= a["absorbed_photons"]
    # no dye absorption -> nothing absorbed
    a = F.appearance(p["n"], p["d_nm"], "D65", fluor=replace(F.PAPILIOCHROME, k_max=0.0))
    assert np.all(a["A"] == 0) and a["absorbed_photons"] == 0


def test_uv_colour_is_set_by_emission(papilio):
    a = papilio["UV365"]
    Xr, Xf = F.xyz_of(a["refl"]), F.xyz_of(a["fluo"])
    assert np.linalg.norm(Xr) < 0.05 * np.linalg.norm(Xf) and Xr[1] < 1e-3 * Xf[1]  # LED tail leaks a little violet
    assert a["fluor_fraction"] > 0.99
    xy = lambda X: X[:2] / X.sum()
    assert np.allclose(xy(a["XYZ"]), xy(Xf), atol=0.01)


def test_uniform_medium_escape_is_half():
    eta = F.escape_factor([1.5, 1.5, 1.5, 1.5], [100.0, 200.0], F.WL, 0.0)
    assert np.allclose(eta, 0.5)
    eta30 = F.escape_factor([1.0, 1.0, 1.0], [300.0], F.WL, 30.0)
    assert np.allclose(eta30, 0.5)


def test_dbr_extraction_monotonic():
    """Quarter-wave chitin/air DBR (505 nm) under a dye slab: more pairs -> more light out of the top
    (gap-averaged, i.e. incoherent with the slab, as in papilio_appearance)."""
    nc, lam = 1.56, 505.0
    vals = []
    for pairs in range(0, 5):
        etas = []
        for gap in np.linspace(1000, 1600, 9):
            n = [1.0, nc, 1.0] + [nc, 1.0] * pairs + [1.0]
            d = [300.0, gap] + [lam / 4 / nc, lam / 4] * pairs
            etas.append(F.escape_factor(n, d, np.array([lam]), 0.0, emitter_layers=[1])[0])
        vals.append(np.mean(etas))
    assert vals[0] == pytest.approx(0.5, abs=1e-9)
    assert np.all(np.diff(vals) > 0) and vals[-1] > 0.85
    # the real P. nireus DBR (75/35/75 nm) also pushes emission out of the top at 505 nm
    with_dbr = F.papilio_appearance("UV365", dbr=True)["eta"][I505]
    without = F.papilio_appearance("UV365", dbr=False)["eta"][I505]
    assert with_dbr > without


def test_phoneme_pipeline_consistency():
    items = json.loads((ROOT / "web/data/sounds.json").read_text())["items"]
    it = next(x for x in items if x["id"] == "i")
    r = F.phoneme_fluorescence(it["a"])
    a0 = F.appearance(r["n"], r["d_nm"], "D65", fluor=None)
    assert a0["hex"] == it["colours"]["full"]["realizable"]["R"]["hex"]
    for ill, a in r["by_illuminant"].items():
        assert a["emitted_photons"] <= a["absorbed_photons"]
    assert r["by_illuminant"]["UV365"]["fluor_fraction"] > 0.99
