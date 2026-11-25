import numpy as np

from core import lpc, mapping as mp, film, vowels, stacks, inverse, synth, colour as col


def test_hillenbrand_loaded():
    rows = vowels.load_tokens()
    assert len(rows) > 1600
    gm = vowels.group_means()
    assert len(gm) == 36
    iy_men = [g for g in gm if g["vowel"] == "iy" and g["group"] == "men"][0]
    assert 250 < iy_men["F1"] < 400 and 2100 < iy_men["F2"] < 2500  # /i/ men (H95 Table V ≈ 342/2322)


def test_vowel_lpc_recovers_formants():
    a, g = vowels.vowel_lpc([730, 1090, 2440], 130)
    F, B = lpc.formants_from_poly(a)
    for target in (730, 1090, 2440):
        assert np.min(np.abs(F - target)) / target < 0.08


def test_realizable_bounds_and_materials():
    a, _ = vowels.vowel_lpc([300, 2300, 3000], 130)
    m = mp.vowel_media(a)
    n = mp.film_from_media(m, "realizable")
    assert n.min() >= mp.N_MIN - 1e-12 and n.max() <= mp.N_MAX + 1e-9
    nm = mp.film_from_media(m, "materials")
    assert set(np.round(nm, 2)).issubset(set(np.round(list(mp.MATERIALS.values()), 2)))


def test_stacks_lossless():
    for s in (stacks.morpho_like(), stacks.beetle_like(),
              stacks.random_goupillaud(np.random.default_rng(1))):
        R, T = film.film_rt(s["n"], s["d_nm"], col.WL)
        assert np.max(np.abs(R + T - 1)) < 1e-12
    R, _ = film.film_rt(stacks.morpho_like()["n"], stacks.morpho_like()["d_nm"], col.WL)
    assert 420 < col.WL[np.argmax(R)] < 520  # blue Morpho-like peak


def test_exact_films_same_voice_different_profile():
    a = lpc.poly_from_formants([700, 1200, 2600], [80, 100, 150])
    m1 = inverse.exact_films_for_polynomial(a, 0.5)
    m2 = inverse.exact_films_for_polynomial(a, 0.2)
    assert m1 is not None and m2 is not None
    for m in (m1, m2):
        D = mp.poly_from_reflection(mp.reflection_from_media(m))
        assert np.allclose(D / D[0], a, atol=1e-8)
    assert not np.allclose(m1, m2, rtol=1e-3)


def test_design_stacks_hits_target():
    rng = np.random.default_rng(3)
    ref = stacks.random_goupillaud(rng)
    _, lab = inverse.stack_colour(ref["n"])
    sols = inverse.design_stacks(lab, n_solutions=3, restarts=12, seed=1)
    assert len(sols) >= 1 and all(s["dE"] < 2 for s in sols)


def test_synth_and_sing():
    s = stacks.random_goupillaud(np.random.default_rng(2))
    y = synth.film_voice(s["n"], s["d_nm"], dur=0.3)
    assert np.isfinite(y).all() and 0.5 < np.max(np.abs(y)) <= 0.9 + 1e-9
    a1 = lpc.poly_from_formants([300, 2300], [80, 100])
    a2 = lpc.poly_from_formants([750, 1100], [80, 100])
    y2 = synth.sing([a1, a2], [0.2, 0.2])
    assert np.isfinite(y2).all()
