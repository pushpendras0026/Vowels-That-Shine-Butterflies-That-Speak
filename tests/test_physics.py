"""Gate tests: sign convention, round trips, uniform tube, lossless film, and the ISOMORPHISM."""
import numpy as np
import pytest
from scipy.signal import lfilter

from core import lpc, mapping as mp, tube, film, colour as col

RNG = np.random.default_rng(42)


def random_media(N=16, lo=0.3, hi=6.0, rng=RNG):
    return np.exp(rng.uniform(np.log(lo), np.log(hi), N + 2))


# ---------- LPC / areas round trips ----------
def test_step_up_down_roundtrip():
    k = RNG.uniform(-0.95, 0.95, 16)
    assert np.max(np.abs(lpc.step_down(lpc.step_up(k)) - k)) < 1e-12


def test_area_reflection_lpc_area_roundtrip():
    areas = np.exp(RNG.uniform(-1.5, 1.5, 17))  # 16 sections + radiation
    areas /= areas[0]
    k = lpc.areas_to_reflection(areas)
    a = lpc.step_up(k)
    k2 = lpc.step_down(a)
    areas2 = lpc.reflection_to_areas(k2, A1=areas[0])
    assert np.max(np.abs(areas2 - areas) / areas) < 1e-9


def test_levinson_recovers_ar_model():
    a_true = lpc.poly_from_formants([700, 1200, 2600], [80, 90, 150])
    imp = np.zeros(4096); imp[0] = 1
    h = lfilter([1], a_true, imp)
    r = lpc.autocorr(h, len(a_true) - 1)
    a, _, _ = lpc.levinson(r, len(a_true) - 1)
    assert np.max(np.abs(a - a_true)) < 1e-6


def test_closed_glottis_polynomial_is_lpc_stepup():
    """CONTRACT §3: c_0 = -1  =>  D(z) = step_up(k) with k_m = -c_m."""
    c = np.concatenate([[-1.0], RNG.uniform(-0.9, 0.9, 16)])
    assert np.allclose(mp.poly_from_reflection(c), lpc.step_up(-c[1:]), atol=1e-13)


def test_direction_not_mirrored():
    """Asymmetric area function (wide back, narrow lips) -> KL tube (closed glottis) -> D(z) ->
    step-down -> areas must equal the input, NOT its mirror image."""
    areas = np.array([6.0, 6.5, 7.0, 6.0, 5.0, 4.0, 3.2, 2.6, 2.0, 1.6, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 2.0])
    c = np.concatenate([[-1.0], mp.reflection_from_media(areas)])  # closed glottis + radiation
    h = tube.kl_impulse_response(c, 64, source="inject")  # = prod_{i>=1}(1+c)/D(z)
    # recover D from the impulse response: D = deconvolution of prod(1+c)*delta by h
    g = h[0]
    D = np.zeros(17); D[0] = 1.0
    for n in range(1, 17):                         # h * D = g*delta
        D[n] = -np.dot(D[:n], h[n:0:-1]) / g
    k = lpc.step_down(D)
    rec = lpc.reflection_to_areas(k, A1=areas[0])
    assert np.max(np.abs(rec - areas) / areas) < 1e-9
    assert not np.allclose(rec, areas[::-1], rtol=1e-2)


# ---------- tube ----------
def test_uniform_tube_formants():
    L, c = 0.175, 350.0
    f = np.arange(50, 4000, 0.5)
    H = tube.tube_volume_velocity_transfer(np.ones(16), f, L, c)
    peaks = f[1:-1][(H[1:-1] > H[:-2]) & (H[1:-1] > H[2:])][:3]
    assert np.allclose(peaks, [500, 1500, 2500], atol=1.0)
    assert np.allclose(tube.uniform_tube_resonances(L, c), [500, 1500, 2500])
    # same from the polynomial: closed glottis c0=-1, open lips cN=-1
    cc = np.zeros(17); cc[0] = -1; cc[-1] = -1
    D = mp.poly_from_reflection(cc)
    F = np.sort(np.angle(np.roots(D)) * mp.FS / (2 * np.pi))
    F = F[F > 0][:3]
    assert np.allclose(F, [500, 1500, 2500], atol=1e-6)


def test_kl_time_domain_matches_polynomial():
    m = random_media()
    c = mp.reflection_from_media(m)
    h = tube.kl_impulse_response(c, 400)
    imp = np.zeros(400); imp[0] = 1
    ref = lfilter([np.prod(1 + c)], mp.poly_from_reflection(c), imp)
    assert np.max(np.abs(h - ref)) < 1e-12


def test_tube_abcd_equals_polynomial_power_transfer():
    m = random_media()
    f = np.linspace(0, mp.FS, 3001)
    P_tube = tube.tube_power_transfer(m, f)
    P_poly = mp.power_transfer(mp.reflection_from_media(m), 2 * np.pi * f / mp.FS)
    assert np.max(np.abs(P_tube - P_poly)) < 1e-10


# ---------- film ----------
def test_film_lossless_R_plus_T_is_one():
    n = 1 + 1.5 * RNG.random(18)
    d = RNG.uniform(50, 300, 16)
    wl = np.linspace(380, 780, 801)
    for th in (0, 30, 60):
        for pol in ("s", "p", "u"):
            R, T = film.film_rt(n, d, wl, th, pol)
            assert np.max(np.abs(R + T - 1)) < 1e-12


def test_film_single_interface_fresnel():
    R, T = film.film_rt([1.0, 1.5], [], [550.0])
    assert np.isclose(R[0], ((1 - 1.5) / 2.5) ** 2)


def test_quarter_wave_mirror():
    nH, nL = 2.4, 1.38
    n = [1.0] + [nH, nL] * 5 + [1.52]
    d = [550 / 4 / x for x in n[1:-1]]
    R, _ = film.film_rt(n, d, [550.0])
    assert R[0] > 0.98


# ---------- THE ISOMORPHISM ----------
@pytest.mark.parametrize("seed", range(5))
def test_isomorphism_film_T_equals_tube_power_transfer(seed):
    rng = np.random.default_rng(seed)
    m = random_media(rng=rng)                      # arbitrary tube (ideal mode)
    n = mp.film_from_media(m, "ideal")             # n ∝ A
    d = mp.goupillaud_d(n[1:-1])
    nu = np.linspace(mp.NU_MIN, mp.NU_MAX, 4001)
    _, T = film.film_rt_nu(n, d, nu)               # Abelès, physical units
    P = tube.tube_power_transfer(m, mp.f_of_nu(nu))  # acoustic ABCD, physical units
    assert np.max(np.abs(T - P)) < 1e-10           # absolute, not just shape
    Tn, Pn = T / T.max(), P / P.max()
    assert np.max(np.abs(Tn - Pn)) < 1e-10


def test_isomorphism_with_lpc_vowel():
    a = lpc.poly_from_formants([730, 1090, 2440], [60, 90, 120])
    a16 = np.concatenate([a, np.zeros(16 - (len(a) - 1))])
    m = mp.vowel_media(a16)
    n = mp.film_from_media(m)
    nu = np.linspace(mp.NU_MIN, mp.NU_MAX, 2001)
    _, T = film.film_rt_nu(n, mp.goupillaud_d(n[1:-1]), nu)
    P = mp.power_transfer(mp.reflection_from_media(m), 2 * np.pi * mp.f_of_nu(nu) / mp.FS)
    assert np.max(np.abs(T - P)) < 1e-10


def test_voice_of_film_exact_for_goupillaud():
    m = random_media(lo=0.6, hi=3.0)
    n = mp.film_from_media(m)
    a, g = film.voice_of_film(n, mp.goupillaud_d(n[1:-1]), n_freq=8192)
    D = mp.poly_from_reflection(mp.reflection_from_media(m))
    assert np.max(np.abs(a - D)) < 1e-6


@pytest.mark.parametrize("d_opt", [mp.D_OPT_FULL_NM, 300.0, mp.D_OPT_NM, 777.7])
def test_isomorphism_any_layer_thickness(d_opt):
    """The isomorphism does not depend on WHICH equal optical thickness is used: only the mapping
    f(nu) = FS*frac(nu/dnu), dnu = c/(2 d_opt), changes. This is what makes the full-band mapping exact."""
    rng = np.random.default_rng(7)
    m = random_media(rng=rng)
    for mode in ("ideal", "realizable"):
        n = mp.film_from_media(m, mode)
        nu = np.linspace(mp.NU_MIN, mp.NU_MAX, 3001)
        R, T = film.film_rt_nu(n, mp.goupillaud_d(n[1:-1], d_opt), nu)
        P = tube.tube_power_transfer(mp.media_from_reflection(mp.reflection_from_media(n), n[0]),
                                     mp.f_of_nu(nu, mp.dnu_of(d_opt)))
        assert np.max(np.abs(T - P)) < 1e-10
        assert np.max(np.abs(R + T - 1)) < 1e-12


def test_full_band_mapping():
    assert np.isclose(mp.D_OPT_FULL_NM, 199.8617, atol=1e-3)
    assert np.isclose(mp.dnu_of(mp.D_OPT_FULL_NM), 750e12)
    f = mp.f_of_nu(np.linspace(mp.NU_MIN, mp.NU_MAX - 1e9, 2001), mp.DNU_FULL)
    fold = np.minimum(f, mp.FS - f)                  # |f| on the speech circle
    assert np.all(np.diff(fold) <= 1e-6)             # monotone: every audio frequency appears at most once
    assert np.isclose(fold[0], mp.FS * (1 - 400 / 750), atol=1e-3) and fold[-1] < 1.0
    m = random_media(lo=0.6, hi=3.0)
    n = mp.film_from_media(m)
    a, _ = film.voice_of_film(n, mp.goupillaud_d(n[1:-1], mp.D_OPT_FULL_NM), n_freq=8192, dnu=mp.DNU_FULL)
    assert np.max(np.abs(a - mp.poly_from_reflection(mp.reflection_from_media(m)))) < 1e-6


def test_frequency_mapping():
    assert np.isclose(mp.f_of_nu(700e12), 0.0, atol=1e-6) or np.isclose(mp.f_of_nu(700e12), mp.FS)
    assert np.isclose(mp.f_of_nu(400e12), mp.FS / 7)
    assert np.isclose(mp.D_OPT_NM, 428.2749, atol=1e-3)
    for f in (500.0, 1500.0, 2500.0):
        for nu in mp.nu_images(f):
            ff = mp.f_of_nu(nu)
            assert min(abs(ff - f), abs(mp.FS - ff - f)) < 1e-3


# ---------- colour ----------
def test_white_and_black():
    for ill in col.ILLUMINANTS:
        W = col.white_xyz(ill)
        assert np.isclose(W[1], 100.0)
        assert np.allclose(col.xyz_to_lab(W, ill), [100, 0, 0], atol=1e-9)
    assert np.allclose(col.xyz_to_srgb(col.white_xyz("D65")), 1.0, atol=2e-3)


def test_delta_e00_matches_colour_science():
    import colour
    for _ in range(50):
        l1 = RNG.uniform([0, -80, -80], [100, 80, 80])
        l2 = RNG.uniform([0, -80, -80], [100, 80, 80])
        assert np.isclose(col.delta_e00(l1, l2), colour.delta_E(l1, l2, method="CIE 2000"), atol=1e-9)


def test_lab_matches_colour_science():
    import colour
    XYZ = np.array([30.0, 40.0, 20.0])
    W = col.white_xyz("D65")
    ref = colour.XYZ_to_Lab(XYZ / 100, colour.XYZ_to_xy(W / 100))
    assert np.allclose(col.xyz_to_lab(XYZ, "D65"), ref, atol=1e-9)
