"""Section 10 (every phoneme, experimental): fast checks of the verdict proofs/certificates and the web schema.

- "few" classes must carry a proof object; any proof claiming holds=True is re-checked numerically.
- "many" classes carry a certificate: 3 colours pairwise > threshold in CIEDE2000; two such colours can never share a
  complete-linkage cluster cut at the threshold, so distinct_colours >= 3. Re-verified here on those 3 colours only.
- phonemes_experiment.json follows the FIXED schema of docs/PHONEMES.md and has no NaN/inf.
"""
import json
import re
from pathlib import Path

import numpy as np
import pytest

from core import colour as col, mapping as mp
from research import r10_phonemes as r10
from research.r9_sounds import hex_lab

WEB = Path(__file__).resolve().parent.parent / "web" / "data" / "phonemes_experiment.json"
HEX = re.compile(r"^#[0-9a-f]{6}$")


@pytest.fixture(scope="module")
def data():
    if not WEB.exists():
        pytest.skip("run python -m research.run_all 10 first")
    return json.loads(WEB.read_text(encoding="utf-8"))


def test_de00_vectorised_matches_core():
    L = np.random.default_rng(1).uniform([10, -90, -90], [95, 90, 90], (60, 3))
    for i in range(59):
        assert abs(float(r10.de00(L[i], L[i + 1])) - col.delta_e00(L[i], L[i + 1])) < 1e-9


def test_cluster_and_certificate_on_small_input():
    # two tight groups far apart -> exactly 2 complete-linkage clusters; certificate for k=3 must fail
    labs = np.array([[50, 40, 10], [50, 41, 11], [50, 39, 9], [60, -40, -30], [60, -41, -29]], float)
    assert len(np.unique(r10.cluster(labs, 10.0))) == 2
    hexes = ["#ff0000", "#00ff00", "#0000ff", "#ff0101"]
    cert = r10.many_certificate(hexes)
    assert cert is not None and min(cert["pairwise_dE00"]) > 10
    assert r10.many_certificate(["#ff0000", "#fe0000", "#00ff00"]) is None


def test_validity_check_realizable_vs_ideal():
    a = np.array(json.loads((WEB.parent / "sounds.json").read_text(encoding="utf-8"))["items"][0]["a"])
    m = mp.vowel_media(a)
    assert all(r10.validity(a, mp.film_from_media(m, "realizable"), "realizable"))
    assert not r10.validity(a, mp.film_from_media(m, "ideal"), "ideal")[1]  # indices beyond N_MAX


def test_schema(data):
    json.dumps(data, allow_nan=False)
    for k in ("generated_by", "date", "settings", "findings", "classes", "items", "butterflies", "figures"):
        assert k in data
    s = data["settings"]
    assert s["view"] == "full·realizable·R" and s["angles_deg"] == [0, 15, 30, 45, 60] and s["illuminant"] == "D65"
    assert isinstance(s["cluster_dE00"], (int, float)) and len(s["views"]) >= 1
    assert 4 <= len(data["findings"]) <= 8 and all(isinstance(f, str) for f in data["findings"])
    for c in data["classes"]:
        assert c["verdict"] in ("few", "many") and isinstance(c["distinct_colours"], int)
        g = c["gamut"]
        assert len(g["hexes"]) == len(g["ab"]) and all(HEX.match(h) for h in g["hexes"])
        assert all(len(p) == 2 for p in g["ab"] + g["hull_ab"])
        if c["verdict"] == "few":
            p = c["proof"]
            assert p and {"title", "claim", "steps", "numeric_check", "holds"} <= set(p) and isinstance(p["holds"], bool)
        else:
            assert c["distinct_colours"] >= 3
    for it in data["items"]:
        assert HEX.match(it["hex"]) and len(it["Lab"]) == 3 and len(it["angle_hexes"]) == 5
        assert isinstance(it["modelled"], bool)
        nb, tw = it["nearest_butterfly"], it["twin"]
        assert {"name", "dE00", "spectral_corr"} <= set(nb) and -1 <= nb["spectral_corr"] <= 1
        assert {"materials", "n_layers", "dE00", "hex"} <= set(tw)
        names = {b["name"] for b in data["butterflies"]}
        assert nb["name"] in names and set(it["voice_lsd_db"]) == names
    for f in data["figures"]:
        assert f["file"].startswith("results/fig_r10_") and f["caption"]
    assert len(data["figures"]) <= 6


def test_many_certificates_hold(data):
    """Re-run the numeric check of every 'many' verdict on its 3 certificate colours."""
    thr = data["settings"]["cluster_dE00"]
    for c in data["classes"]:
        if c["verdict"] != "many":
            continue
        cert = c["many_certificate"]
        assert cert is not None, c["class"]
        assert set(cert["hexes"]) <= set(c["gamut"]["hexes"])
        labs = [hex_lab(h) for h in cert["hexes"]]
        d = [col.delta_e00(labs[i], labs[j]) for i in range(3) for j in range(i + 1, 3)]
        assert min(d) > thr, (c["class"], d)


def test_few_proofs_hold_or_are_not_claimed(data):
    for c in data["classes"]:
        p = c["proof"]
        if p is None:
            continue
        assert c["verdict"] == "few"
        if p["holds"]:
            assert p["steps"] and p["numeric_check"]


# ------------------------------------------------------------------ optional additions: realistic butterflies + fluorescence
def test_real_butterfly_fields(data):
    rb = data["real_butterflies"]
    names = {b["name"] for b in rb}
    assert len(rb) >= 3
    for b in rb:
        assert HEX.match(b["hex"]) and len(b["angle_hexes"]) == len(data["settings"]["angles_deg"])
        assert all(HEX.match(h) for h in b["angle_hexes"]) and 380 <= b["peak_nm"] <= 780 and b["source"]
    for it in data["items"]:
        nr = it["nearest_real_butterfly"]
        assert nr["name"] in names and -1 <= nr["spectral_corr"] <= 1 and nr["dE00"] >= 0
        assert "nearest_butterfly" in it          # old (idealised 1-D stacks) comparison kept
    assert "idealised" in data["settings"]["butterfly_models"]["nearest_butterfly"]


def test_fluorescence_fields(data):
    fl = data["fluorescence"]
    ids = {it["id"] for it in data["items"]}
    assert {f["id"] for f in fl["items"]} == ids
    for f in fl["items"]:
        assert all(HEX.match(f[k]) for k in ("hex_D65", "hex_UV", "hex_violet"))
        assert 0 <= f["fluor_fraction_D65"] <= 1 and 450 <= f["peak_emission_nm"] <= 560


def test_peak_shift_lemma_synthetic():
    """|λ* − λ0| ≤ σ²·max|d ln w/dλ| for a Gaussian times a positive weight with bounded log-slope."""
    wl = np.arange(300.0, 800.0, 0.01)
    rng = np.random.default_rng(3)
    for _ in range(20):
        l0, sig = rng.uniform(450, 600), rng.uniform(15, 60)
        c = rng.uniform(-1, 1, 3)
        lnw = 0.3 * (c[0] * np.sin(wl / 37.0) + c[1] * np.cos(wl / 91.0) + c[2] * (wl - 500) / 200)
        S = np.exp(-0.5 * ((wl - l0) / sig) ** 2 + lnw)
        kap = np.max(np.abs(np.gradient(lnw, wl)))
        assert abs(wl[np.argmax(S)] - l0) <= sig ** 2 * kap + 0.02


def test_fluorescence_proof_rechecked(data):
    """Re-run the numeric check of the blacklight proof from the published colours."""
    p = data["fluorescence_proof"]
    assert {"title", "claim", "steps", "numeric_check", "holds"} <= set(p) and len(p["steps"]) >= 5
    labs = [hex_lab(f["hex_UV"]) for f in data["fluorescence"]["items"]]
    mx = max(col.delta_e00(labs[i], labs[j]) for i in range(len(labs)) for j in range(i + 1, len(labs)))
    assert abs(mx - data["fluorescence"]["stats"]["max_dE00_UV"]) < 0.02
    if p["holds"]:
        assert mx <= data["settings"]["cluster_dE00"]
        assert data["fluorescence"]["distinct_colours_UV"] == 1
        st = data["fluorescence"]["stats"]
        assert st["shift_max"] <= st["bound_max"]
