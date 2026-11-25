"""Realistic butterfly-/beetle-scale optics. Replaces the idealised 1-D 'Morpho-like' film of
core/stacks.py for comparisons phoneme-film <-> real wing.  Everything is vectorised over wavelength, angle and
an ensemble of disordered stacks.  Labels on every parameter: MEASURED (number taken from a paper), APPROXIMATE
(literature range, value picked inside it) or ILLUSTRATIVE (chosen by us to reproduce a published colour).

Model (per species), in order of application
--------------------------------------------
1. Materials
   * chitin: Cauchy n(λ) = 1.517 + 8.80e3/λ² (λ in nm), MEASURED on Graphium sarpedon wing scales by
     Leertouwer, Wilts & Stavenga 2011, Opt. Express 19:24061 (n = 1.572/1.552/1.541 at 400/500/600 nm).
     That paper gives the REAL part only; the imaginary part is ours (below).
   * melanin-rich cuticle: n ≈ 1.567 + 3.563e4/λ²  (≈1.79 at 400 nm → 1.64 at 700 nm, APPROXIMATE, the range
     reported for melanised damselfly-wing layers in Stavenga et al. 2012, PLoS ONE 7:e49743), absorption
     k_mel(λ) = 0.56·exp(-λ/270 nm) (APPROXIMATE exponential melanin form used by the Stavenga group;
     k ≈ 0.13 at 400 nm, 0.04 at 700 nm).
   * pigmented scale chitin: k = p·k_mel(λ) with a species melanin fraction p (APPROXIMATE/ILLUSTRATIVE), giving
     k ≈ 0.01-0.06 in the blue for Morpho lamellae.
   * lamella fill: Morpho ridge lamellae are laterally finite; following Kinoshita et al. 2002 (Forma 17:103) the
     lamella is replaced by an averaged dielectric ε = f·ε_chitin + (1-f) (f ILLUSTRATIVE, as in core/stacks.py).
2. Coherent multilayer: our own batched transfer-matrix (Macleod tilted admittances, s and p, complex n; materials are written
   n + ik and conjugated internally to Macleod's N = n - ik, decaying branch Im(N cosθ) ≤ 0).  Absorptance is computed INDEPENDENTLY (A = 4η0·Re(BC* - η_s)/|η0B+C|²) so that
   R+T+A = 1 is a genuine check, not a definition.  core.film._rt_pol accepts complex n, but works one stack at a
   time and does not return A, hence the re-implementation (validated against it in tests).
3. Thickness disorder: each layer thickness × (1 + σ·N(0,1)), N_ens random stacks, INCOHERENT ensemble average
   of R (different ridges/scales are mutually incoherent).
4. Incoherent backing below the multilayer (scale lumen air gap, then the melanised lower lamina / ground scale):
   R_tot = R_ml + T_ml² R_b / (1 - R_ml,back·R_b), per polarisation, with R_b = Fresnel reflectance of a
   melanin half-space (absorbing, ≈ 0.07).  For the beetle the stack sits directly on melanised cuticle
   (coherent absorbing substrate, no extra backing).
5. Angular spread ('viewing angle' θv under diffuse illumination): a facet whose normal is tilted by α shows
   specular reflectance at local incidence |θv - α|.  α ~ N(0, σ²) with σ² = σ_tilt² + σ_diff(λ)², where
   σ_tilt = lamella/scale/curvature tilt spread and σ_diff(λ) = λ/(π w) is a Gaussian stand-in for diffraction
   by a lamella of finite lateral width w (single-slit first-zero ≈ λ/w; ROUGH, documented approximation — it
   only redistributes R over angle, it does not compute a diffraction pattern).  Local angles ≥ 88° are dropped
   (source below the horizon) and the weights renormalised.
6. Papilio blumei only: concavity walls at ±45° retro-reflect after TWO reflections with s↔p conversion
   (Vukusic, Sambles & Lawrence 2000, Nature 404:457): R_wall = ½[Rs(45+θv/2)Rp(45-θv/2) + Rp(45+θv/2)Rs(45-θv/2)],
   mixed with the flat concavity floor by area fractions (ILLUSTRATIVE 0.55/0.45).

What is NOT modelled (say so wherever these numbers are shown): full 2-D/3-D ridge geometry (FDTD), real
diffraction orders, scale-to-scale overlap of cover/ground scales, fluorescence, measured BRDFs.  Peak wavelengths
are tuned to published colours where the paper gives no thicknesses (labelled ILLUSTRATIVE).
Run `python -m core.butterfly` → results/fig_butterfly_real.png + results/butterfly_real.json.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import colour as col
from . import film

ROOT = Path(__file__).resolve().parent.parent
WL_GRID = np.arange(380.0, 780.0 + 1e-9, 2.0)        # internal wavelength grid (nm)
ANG_GRID = np.arange(0.0, 88.0 + 1e-9, 2.0)           # local incidence angles for the angular kernel (deg)
SPEC_MASK = (col.WL >= 380) & (col.WL <= 780)
DEFAULT_ANGLES = (0, 15, 30, 45, 60, 75)

# ----------------------------------------------------------------------------------------------- materials
CHITIN_A, CHITIN_B = 1.517, 8.80e3                    # MEASURED, Leertouwer et al. 2011
MEL_A, MEL_B = 1.567, 3.563e4                          # APPROXIMATE (fit to 1.79 @400, 1.64 @700; Stavenga 2012)
MEL_K0, MEL_KL = 0.56, 270.0                           # APPROXIMATE melanin absorption k = K0 exp(-λ/KL)


def n_chitin(wl, melanin=0.0):
    wl = np.asarray(wl, float)
    return CHITIN_A + CHITIN_B / wl ** 2 + 1j * melanin * k_melanin(wl)


def k_melanin(wl):
    return MEL_K0 * np.exp(-np.asarray(wl, float) / MEL_KL)


def n_melanin(wl):
    wl = np.asarray(wl, float)
    return MEL_A + MEL_B / wl ** 2 + 1j * k_melanin(wl)


def n_mix(n1, n2, f):
    """Linear permittivity average (Kinoshita-style lamella averaging)."""
    return np.sqrt(f * n1 ** 2 + (1 - f) * n2 ** 2 + 0j)


# ------------------------------------------------------------------------------------------------- species
_CIT = {
    "leertouwer2011": "Leertouwer, Wilts & Stavenga 2011, Opt. Express 19:24061 (chitin Cauchy A=1.517, B=8.80e3 nm²)",
    "stavenga2012": "Stavenga, Leertouwer, Hariyama, De Raedt & Wilts 2012, PLoS ONE 7:e49743 (melanin layer n 1.79→1.64)",
    "vukusic1999": "Vukusic, Sambles, Lawrence & Wootton 1999, Proc. R. Soc. B 266:1403 (single Morpho scales: "
                   "interference + diffraction, ridge lamellae)",
    "kinoshita2002": "Kinoshita, Yoshioka, Fujii & Okamoto 2002, Forma 17:103 (M. didius: 6-8 lamellae, cuticle ~55 nm, "
                     "air ~150 nm; averaged-lamella model)",
    "kinoshita2002b": "Kinoshita, Yoshioka & Kawagoe 2002, Proc. R. Soc. B 269:1417 (Morpho: alternating shelves, broad "
                      "angular reflection, melanised base)",
    "vukusic2000": "Vukusic, Sambles & Lawrence 2000, Nature 404:457 (P. blumei: concave multilayer, yellow centre + "
                   "blue edges via double reflection & polarisation conversion → green)",
    "diao2011": "Diao & Liu 2011, Opt. Express 19:9232 (Papilio concavities: 21 alternating cuticle/air layers)",
    "kolle2010": "Kolle et al. 2010, Nat. Nanotechnol. 5:511 (P. blumei mimic; concavities ~5-10 µm)",
    "yoshioka2008": "Yoshioka, Nakano, Nozue & Kinoshita 2008, J. R. Soc. Interface 5:457 (C. rhipheus area C5 green: "
                    "4 cuticle 270 nm + 3 air 130 nm, n 1.55; higher-order interference)",
    "yoshioka2007": "Yoshioka & Kinoshita 2007, Proc. R. Soc. B 274:1717 (sunset moth: curved scales, polarisation-"
                    "sensitive colour mixing)",
    "stavenga2011": "Stavenga, Wilts, Leertouwer & Hariyama 2011, Phil. Trans. R. Soc. B 366:709 (Chrysochroa "
                    "fulgidissima elytra: chitin / melanin-rich multilayer, polarised iridescence)",
}


def _sp(**kw):
    return kw


SPECIES = {
    "Morpho rhetenor": _sp(
        kind="ridge lamellae", n_pairs=10, d_hi=70.0, d_lo=145.0, hi="lamella", lo="air",
        fill=0.60, melanin=0.12, sigma_d=0.10, tilt_deg=8.0, lamella_width_nm=300.0, backing="melanin",
        published="blue, R peak ≈ 450-470 nm, iridescent over a wide angle (Vukusic 1999)",
        labels=dict(n_pairs="APPROXIMATE (Morpho ridges carry ~6-12 lamellae; rhetenor at the high end)",
                    d_hi="APPROXIMATE (cuticle lamellae ~55-80 nm)", d_lo="APPROXIMATE (air gaps ~100-150 nm)",
                    fill="ILLUSTRATIVE lateral fill of the lamella (tuned so the peak lands in the published band)",
                    melanin="ILLUSTRATIVE (k ≈ 0.016 at 400 nm)", sigma_d="APPROXIMATE (5-15 % layer scatter in TEM)",
                    tilt_deg="APPROXIMATE (lamella + scale tilt spread)",
                    lamella_width_nm="APPROXIMATE (shelf width a few hundred nm)",
                    backing="APPROXIMATE (melanised ground scales / lower lamina)"),
        citations=["vukusic1999", "kinoshita2002b", "leertouwer2011", "stavenga2012"]),
    "Morpho didius": _sp(
        kind="ridge lamellae", n_pairs=7, d_hi=55.0, d_lo=150.0, hi="lamella", lo="air",
        fill=0.85, melanin=0.08, sigma_d=0.10, tilt_deg=10.0, lamella_width_nm=300.0, backing="melanin",
        published="blue, R peak ≈ 440-480 nm; cover scales add diffuse spread (Kinoshita 2002)",
        labels=dict(n_pairs="MEASURED range 6-8 (Kinoshita 2002), 7 used", d_hi="MEASURED ~55 nm (TEM, Kinoshita 2002)",
                    d_lo="MEASURED ~150 nm (TEM, Kinoshita 2002)", fill="ILLUSTRATIVE 0.85 (core/stacks.py uses 0.5; tuned so the realistic peak is blue)",
                    melanin="ILLUSTRATIVE", sigma_d="APPROXIMATE", tilt_deg="APPROXIMATE",
                    lamella_width_nm="APPROXIMATE", backing="APPROXIMATE"),
        citations=["kinoshita2002", "kinoshita2002b", "leertouwer2011", "stavenga2012"]),
    "Papilio blumei": _sp(
        kind="concave multilayer", n_pairs=10, d_hi=85.0, d_lo=150.0, hi="chitin", lo="air",
        fill=1.0, melanin=0.05, sigma_d=0.08, tilt_deg=10.0, lamella_width_nm=None, backing="melanin",
        f_wall=0.30,
        published="green (concavity centre yellow-green + edges blue); P. palinurus is structurally similar",
        labels=dict(n_pairs="APPROXIMATE (~10 cuticle layers; Diao 2011 counts 21 alternating layers)",
                    d_hi="ILLUSTRATIVE (tuned: centre ≈ yellow-green at normal incidence)", d_lo="ILLUSTRATIVE",
                    fill="cuticle layers are continuous (f = 1)", melanin="ILLUSTRATIVE",
                    sigma_d="APPROXIMATE", tilt_deg="APPROXIMATE (concavity floor curvature)",
                    f_wall="ILLUSTRATIVE area fraction of the 45° walls (0.3)", backing="APPROXIMATE"),
        citations=["vukusic2000", "diao2011", "kolle2010", "leertouwer2011"]),
    "Chrysiridia rhipheus": _sp(
        kind="curved-scale multilayer", n_pairs=4, d_hi=270.0, d_lo=130.0, hi="chitin", lo="air",
        fill=1.0, melanin=0.03, sigma_d=0.10, tilt_deg=15.0, lamella_width_nm=None, backing="melanin",
        published="green area C5 (CIE x,y ≈ 0.24, 0.50), second-order interference (Yoshioka 2008)",
        labels=dict(n_pairs="MEASURED 4 cuticle + 3 air layers (area C5)", d_hi="MEASURED 270 nm",
                    d_lo="MEASURED 130 nm", fill="f = 1", melanin="ILLUSTRATIVE", sigma_d="APPROXIMATE (paper notes "
                    "non-uniform thicknesses)", tilt_deg="APPROXIMATE (curved scales)", backing="APPROXIMATE"),
        citations=["yoshioka2008", "yoshioka2007", "leertouwer2011"]),
    "Chrysochroa fulgidissima": _sp(
        kind="beetle elytron multilayer", n_pairs=20, d_hi=95.0, d_lo=80.0, hi="chitin", lo="melanin_chitin",
        fill=1.0, melanin=0.0, mel_frac=0.5, sigma_d=0.05, tilt_deg=3.0, lamella_width_nm=None, backing="substrate",
        published="green elytra, specular (glossy), blue-shifted at oblique angles (Stavenga 2011)",
        labels=dict(n_pairs="APPROXIMATE (tens of layers)", d_hi="ILLUSTRATIVE (tuned to a green peak ≈ 540-560 nm)",
                    d_lo="ILLUSTRATIVE", mel_frac="ILLUSTRATIVE melanin fraction of the high-index layers",
                    sigma_d="APPROXIMATE", tilt_deg="APPROXIMATE (smooth glossy elytron)",
                    backing="melanised cuticle substrate (coherent)"),
        citations=["stavenga2011", "leertouwer2011", "stavenga2012"]),
}


def species():
    return list(SPECIES)


def _layer_n(sp, which, wl):
    kind = sp[which]
    if kind == "air":
        return np.ones_like(wl, complex)
    if kind == "chitin":
        return n_chitin(wl, sp["melanin"])
    if kind == "lamella":
        return n_mix(n_chitin(wl, sp["melanin"]), 1.0, sp["fill"])
    if kind == "melanin_chitin":
        return n_mix(n_melanin(wl), n_chitin(wl), sp["mel_frac"])
    raise ValueError(kind)


def build_stack(name, wl, lossless=False):
    """n: (L+2, W) complex [air, layers..., exit]; d: (L,) nm.  Ridge/scale stacks: hi/lo pairs then a final hi
    layer, exiting into air (then the incoherent backing); beetle: pairs on a melanised substrate."""
    sp = SPECIES[name]
    wl = np.asarray(wl, float)
    nh, nl = _layer_n(sp, "hi", wl), _layer_n(sp, "lo", wl)
    if sp["backing"] == "substrate":
        layers = [nh, nl] * sp["n_pairs"]
        d = [sp["d_hi"], sp["d_lo"]] * sp["n_pairs"]
        exit_n = n_mix(n_melanin(wl), n_chitin(wl), sp["mel_frac"])
    else:
        layers = [nh, nl] * (sp["n_pairs"] - 1) + [nh]
        d = [sp["d_hi"], sp["d_lo"]] * (sp["n_pairs"] - 1) + [sp["d_hi"]]
        exit_n = np.ones_like(wl, complex)
    n = np.stack([np.ones_like(wl, complex)] + layers + [exit_n])
    if lossless:
        n = n.real + 0j
    return n, np.array(d, float)


# --------------------------------------------------------------------------------- batched transfer matrix
def tmm(n, d, wl, theta_deg, pol):
    """n: (L+2, W) complex (incident medium n[0] must be real), d: (B, L) or (L,), wl: (W,), theta: (A,).
    Returns R, T, A of shape (B, A, W).  A is computed independently of R and T."""
    wl = np.asarray(wl, float)
    d = np.atleast_2d(np.asarray(d, float))
    th = np.deg2rad(np.atleast_1d(np.asarray(theta_deg, float)))
    n = np.conj(np.asarray(n, complex))      # materials use n + ik; Macleod's matrices need N = n - ik
    s0 = (n[0].real[None, :] * np.sin(th)[:, None])                     # (A, W), conserved
    s02 = (s0 ** 2).astype(complex)

    def eta_of(nj):
        ncos = np.sqrt(nj[None, :] ** 2 - s02)                            # decaying branch: Im <= 0 (N = n - ik)
        ncos = np.where(ncos.imag > 0, -ncos, ncos)
        return ncos, (ncos if pol == "s" else nj[None, :] ** 2 / ncos)

    _, eta0 = eta_of(n[0])
    _, etas = eta_of(n[-1])
    B = np.ones((d.shape[0],) + eta0.shape, complex)
    C = np.broadcast_to(etas, B.shape).astype(complex)
    for j in range(n.shape[0] - 2, 0, -1):
        ncos, eta = eta_of(n[j])
        delta = 2 * np.pi * ncos[None] * d[:, j - 1, None, None] / wl[None, None, :]
        e = np.exp(1j * delta)
        ie = 1.0 / e
        cs, sn = 0.5 * (e + ie), -0.5j * (e - ie)
        B, C = cs * B + 1j * sn / eta[None] * C, 1j * eta[None] * sn * B + cs * C
    den = eta0[None] * B + C
    r = (eta0[None] * B - C) / den
    R = np.abs(r) ** 2
    T = 4 * eta0.real[None] * etas.real[None] / np.abs(den) ** 2
    A = 4 * eta0.real[None] * np.real(B * np.conj(C) - etas[None]) / np.abs(den) ** 2
    return R, T, A


def fresnel_R(n2, theta_deg, pol):
    R, _, _ = tmm(np.stack([np.ones_like(n2), n2]), np.zeros((1, 0)), np.ones(n2.shape), theta_deg, pol)
    return R[0]


# ---------------------------------------------------------------------------------------------- the model
DEFAULT_FLAGS = dict(disorder=True, tilt=True, diffraction=True, backing=True, absorption=True, walls=True)
IDEAL_FLAGS = {k: False for k in DEFAULT_FLAGS}


def _local_table(name, flags, n_ens, seed, angles=ANG_GRID, wl=WL_GRID):
    """Ensemble-averaged Rs, Rp at local incidence angles (A, W), including the incoherent backing."""
    sp = SPECIES[name]
    n, d0 = build_stack(name, wl, lossless=not flags["absorption"])
    if flags["disorder"] and sp["sigma_d"] > 0:
        rng = np.random.default_rng(seed)
        d = d0[None] * np.clip(1 + sp["sigma_d"] * rng.standard_normal((n_ens, d0.size)), 0.2, None)
    else:
        d = d0[None]
    out = {}
    n_back = n_melanin(wl) if flags["absorption"] else n_melanin(wl).real + 0j
    for pol in "sp":
        R, T, _ = tmm(n, d, wl, angles, pol)
        if flags["backing"] and sp["backing"] == "melanin":
            Rbk, _, _ = tmm(n[::-1], d[:, ::-1], wl, angles, pol)
            Rb = fresnel_R(n_back, angles, pol)[None]
            R = R + T ** 2 * Rb / (1 - Rbk * Rb)
        out[pol] = R.mean(0)
    return out["s"], out["p"]


CACHE = ROOT / "results" / "cache_butterfly_tables.npz"
_MEM = {}


def _key(name, flag_items, n_ens, seed):
    sp = {k: v for k, v in SPECIES[name].items() if k not in ("labels", "citations", "published")}
    return repr((name, sorted(sp.items()), flag_items, n_ens, seed, ANG_GRID[-1], ANG_GRID[1], WL_GRID[1]))


def _table_cached(name, flag_items, n_ens, seed):
    """Memory + disk cache (results/cache_butterfly_tables.npz) keyed by species params, flags, n_ens, seed."""
    import hashlib
    k = hashlib.sha1(_key(name, flag_items, n_ens, seed).encode()).hexdigest()[:16]
    if k not in _MEM:
        if not _MEM and CACHE.exists():
            with np.load(CACHE) as z:
                _MEM.update({f: z[f] for f in z.files})
        if k not in _MEM:
            Rs, Rp = _local_table(name, dict(flag_items), n_ens, seed)
            _MEM[k] = np.stack([Rs, Rp]).astype(np.float32)
            try:
                np.savez_compressed(CACHE, **_MEM)
            except OSError:
                pass
    return _MEM[k][0].astype(float), _MEM[k][1].astype(float)


def _angular_average(Ru, view_deg, sigma_rad, angles=ANG_GRID):
    """Ru: (A, W) on local angles; sigma_rad: (W,).  Returns (V, W): Σ_α p(α) R(|θv-α|)."""
    v = np.deg2rad(np.atleast_1d(np.asarray(view_deg, float)))[:, None, None]
    a = np.deg2rad(angles)[None, :, None]
    s = np.maximum(sigma_rad, 1e-6)[None, None, :]
    w = np.exp(-0.5 * ((v - a) / s) ** 2) + np.exp(-0.5 * ((v + a) / s) ** 2)   # α = θv ∓ θloc
    w = w / w.sum(1, keepdims=True)
    return np.einsum("vaw,aw->vw", w, Ru)


def _sigma(name, flags, wl):
    sp = SPECIES[name]
    s2 = np.zeros_like(wl)
    if flags["tilt"]:
        s2 = s2 + np.deg2rad(sp["tilt_deg"]) ** 2
    if flags["diffraction"] and sp.get("lamella_width_nm"):
        s2 = s2 + (wl / (np.pi * sp["lamella_width_nm"])) ** 2
    return np.sqrt(s2)


def model_R(name, view_deg, flags=None, n_ens=32, seed=0, rng=None, wl=None):
    """Reflectance (V, W) on WL_GRID (or `wl` by interpolation) at viewing angles view_deg."""
    flags = {**DEFAULT_FLAGS, **(flags or {})}
    view = np.atleast_1d(np.asarray(view_deg, float))
    if rng is not None:
        seed = int(rng.integers(2 ** 31))
    Rs, Rp = _table_cached(name, tuple(sorted(flags.items())), n_ens, seed)
    sig = _sigma(name, flags, WL_GRID)
    if np.all(sig < np.deg2rad(0.5)):        # no angular spread: evaluate at the exact angles
        f2 = {**flags}
        Rs_v, Rp_v = _local_table(name, f2, n_ens, seed, angles=view)
        Rflat = 0.5 * (Rs_v + Rp_v)
    else:
        Rflat = _angular_average(0.5 * (Rs + Rp), view, sig)
    sp = SPECIES[name]
    if sp.get("f_wall") and flags["walls"]:
        def at(Rt, ang):
            return np.stack([[np.interp(x, ANG_GRID, Rt[:, k]) for k in range(Rt.shape[1])] for x in ang])
        a1, a2 = np.clip(45 + view / 2, 0, 88), np.clip(45 - view / 2, 0, 88)
        Rwall = 0.5 * (at(Rs, a1) * at(Rp, a2) + at(Rp, a1) * at(Rs, a2))
        Rflat = (1 - sp["f_wall"]) * Rflat + sp["f_wall"] * Rwall
    if wl is None:
        return Rflat
    return np.stack([np.interp(wl, WL_GRID, r) for r in Rflat])


def scale_reflectance(name, wl_nm, theta_deg=0.0, rng=None, n_ens=32, realistic=True, flags=None):
    """R(λ) of one species at viewing angle theta_deg (unpolarised).  realistic=False → ideal 1-D stack
    (no disorder/tilt/diffraction/backing/absorption, Cauchy chitin kept)."""
    fl = flags if flags is not None else (DEFAULT_FLAGS if realistic else IDEAL_FLAGS)
    return model_R(name, [theta_deg], fl, n_ens=n_ens, rng=rng, wl=np.asarray(wl_nm, float))[0]


# --------------------------------------------------------------------------------------------- colour
def _full(R_grid):
    return np.interp(col.WL, WL_GRID, R_grid)


def hex_to_lab(h):
    rgb = np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    XYZ = np.linalg.solve(col.M_XYZ_TO_SRGB, lin) * 100.0
    return col.xyz_to_lab(XYZ)


def spectrum_colour(R_full):
    X = col.spectrum_to_xyz(R_full)
    hx = col.to_hex(col.display_rgb(X))
    return dict(hex=hx, Lab=hex_to_lab(hx), Lab_abs=col.xyz_to_lab(X))


def colour_vs_angle(name, angles=DEFAULT_ANGLES, realistic=True, n_ens=32):
    Rv = model_R(name, angles, DEFAULT_FLAGS if realistic else IDEAL_FLAGS, n_ens=n_ens)
    out = []
    for a, R in zip(angles, Rv):
        c = spectrum_colour(_full(R))
        La = c["Lab_abs"]
        out.append(dict(angle=float(a), hex=c["hex"], Lab=[round(float(x), 2) for x in c["Lab"]],
                        Lab_abs=[round(float(x), 2) for x in La],
                        hue_deg=round(float(np.degrees(np.arctan2(La[2], La[1])) % 360), 1),
                        R_peak=round(float(R.max()), 4), peak_nm=float(WL_GRID[np.argmax(R)]),
                        R_mean=round(float(R.mean()), 4)))
    return out


def effective_film(name):
    """Equivalent ideal 1-D stack in core.film convention [n_inc, layers..., n_sub] (real n at 550 nm, mean
    thicknesses).  Misses disorder, tilt, diffraction, backing and absorption: use it for structure-level
    comparisons only; use scale_reflectance for spectra."""
    n, d = build_stack(name, np.array([550.0]), lossless=True)
    n = n[:, 0].real.copy()
    if SPECIES[name]["backing"] != "substrate":
        n[-1] = float(n_chitin(550.0).real)   # film.py convention: a substrate; scale lower lamina is chitin
    return dict(name=name, n=n, d_nm=d, label="equivalent ideal stack (approximate)",
                note="no disorder/tilt/diffraction/backing/absorption; exit medium = chitin lower lamina")


@lru_cache(maxsize=8)
def _species_refs(theta):
    refs = {}
    for nm in SPECIES:
        R = _full(model_R(nm, [theta])[0])
        refs[nm] = (R, spectrum_colour(R)["Lab"])
    return refs


def compare_film_to_species(n, d_nm, theta_deg=0.0):
    """Phoneme (or any) film vs every REALISTIC species: ΔE00 between displayed colours (exposure-normalised hex
    → Lab, the r9/r10 convention) and Pearson correlation of reflectance spectra over 380-780 nm."""
    Rf, _ = film.film_rt(np.asarray(n), np.asarray(d_nm, float), col.WL, theta_deg)
    lab_f = spectrum_colour(Rf)["Lab"]
    out = {}
    for nm, (R, lab) in _species_refs(float(theta_deg)).items():
        out[nm] = dict(dE00=round(col.delta_e00(lab_f, lab), 3),
                       spectral_corr=round(float(np.corrcoef(Rf[SPEC_MASK], R[SPEC_MASK])[0, 1]), 4))
    return out


# --------------------------------------------------------------------------------------------- report
def _fwhm(R):
    i = int(np.argmax(R))
    half = R[i] / 2
    lo = i
    while lo > 0 and R[lo] > half:
        lo -= 1
    hi = i
    while hi < len(R) - 1 and R[hi] > half:
        hi += 1
    return float(WL_GRID[hi] - WL_GRID[lo])


def _angular_halfwidth(name, flags):
    view = np.arange(0, 81, 2.0)
    Rv = model_R(name, view, flags)
    Y = np.array([col.spectrum_to_xyz(_full(r))[1] for r in Rv])
    below = np.nonzero(Y < Y[0] / 2)[0]
    return float(view[below[0]]) if below.size else 80.0, view, Y


def realism_report():
    rep = {}
    for nm, sp in SPECIES.items():
        Ri = model_R(nm, [0], IDEAL_FLAGS)[0]
        Rr = model_R(nm, [0], DEFAULT_FLAGS)[0]
        ci, cr = spectrum_colour(_full(Ri)), spectrum_colour(_full(Rr))
        ablate = {}
        for k in DEFAULT_FLAGS:
            if k == "walls" and not sp.get("f_wall"):
                continue
            if k == "diffraction" and not sp.get("lamella_width_nm"):
                continue
            Ro = model_R(nm, [0, 45], {**DEFAULT_FLAGS, k: False})
            ablate[k] = round(max(col.delta_e00(spectrum_colour(_full(Ro[j]))["Lab"],
                                                spectrum_colour(_full(model_R(nm, [a])[0]))["Lab"])
                                  for j, a in enumerate((0, 45))), 2)
        hw_i, *_ = _angular_halfwidth(nm, IDEAL_FLAGS)
        hw_r, *_ = _angular_halfwidth(nm, DEFAULT_FLAGS)
        rep[nm] = dict(
            kind=sp["kind"], published=sp["published"],
            ideal=dict(peak_nm=float(WL_GRID[np.argmax(Ri)]), R_max=round(float(Ri.max()), 4),
                       fwhm_nm=_fwhm(Ri), hex=ci["hex"], angular_halfwidth_deg=hw_i),
            realistic=dict(peak_nm=float(WL_GRID[np.argmax(Rr)]), R_max=round(float(Rr.max()), 4),
                           fwhm_nm=_fwhm(Rr), hex=cr["hex"], angular_halfwidth_deg=hw_r),
            dE00_ideal_vs_realistic_0deg=round(col.delta_e00(ci["Lab"], cr["Lab"]), 2),
            ablation_dE00_max_0_45=ablate,
            colours_realistic=colour_vs_angle(nm), colours_ideal=colour_vs_angle(nm, realistic=False),
            params={k: sp[k] for k in sp if k not in ("labels", "citations", "published")},
            param_labels=sp["labels"], citations=[_CIT[c] for c in sp["citations"]])
    return rep


def _figure(rep, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(SPECIES)
    fig, axes = plt.subplots(2, len(names), figsize=(4.0 * len(names), 7.2),
                             gridspec_kw=dict(height_ratios=[2.2, 1]))
    for j, nm in enumerate(names):
        ax = axes[0, j]
        Ri = model_R(nm, [0], IDEAL_FLAGS)[0]
        Rr = model_R(nm, [0, 40], DEFAULT_FLAGS)
        ax.plot(WL_GRID, Ri, color="0.55", lw=1.2, label="ideal 1-D stack, 0°")
        ax.plot(WL_GRID, Rr[0], color="k", lw=1.8, label="realistic, 0°")
        ax.plot(WL_GRID, Rr[1], color="k", lw=1.2, ls="--", label="realistic, 40°")
        ax.set_title(nm, fontsize=10, style="italic")
        ax.set_xlabel("wavelength (nm)")
        ax.set_ylim(0, 1.02)
        ax.set_xlim(380, 780)
        if j == 0:
            ax.set_ylabel("reflectance")
            ax.legend(fontsize=7, frameon=False, loc="upper right")
        ax2 = axes[1, j]
        for row, key in enumerate(("colours_ideal", "colours_realistic")):
            for k, c in enumerate(rep[nm][key]):
                ax2.add_patch(plt.Rectangle((k, 1 - row), 0.95, 0.9, color=c["hex"]))
        ax2.set_xlim(0, len(DEFAULT_ANGLES))
        ax2.set_ylim(0, 2)
        ax2.set_xticks(np.arange(len(DEFAULT_ANGLES)) + 0.47, [f"{a}°" for a in DEFAULT_ANGLES], fontsize=7)
        ax2.set_yticks([1.45, 0.45], ["ideal", "realistic"] if j == 0 else ["", ""], fontsize=8)
        ax2.tick_params(length=0)
        for s in ax2.spines.values():
            s.set_visible(False)
        ax2.set_xlabel("viewing angle (displayed colour, exposure-normalised)", fontsize=7)
    fig.suptitle("Realistic scale optics (disorder, tilt/diffraction spread, melanin absorption + backing, Cauchy "
                 "chitin) vs ideal 1-D multilayer", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def main():
    import datetime
    rep = realism_report()
    _figure(rep, ROOT / "results" / "fig_butterfly_real.png")
    eff = {nm: dict(n=[round(float(x), 4) for x in e["n"]], d_nm=e["d_nm"].tolist(), note=e["note"])
           for nm, e in ((nm, effective_film(nm)) for nm in SPECIES)}
    out = dict(generated_by="core/butterfly.py", date=str(datetime.date.today()),
               settings=dict(wl_nm=[380, 780, 2], illuminant="D65", n_ens=32, seed=0, angles_deg=list(DEFAULT_ANGLES),
                             colour="hex = exposure-normalised display colour; Lab_abs = absolute reflected Lab"),
               model=__doc__.split("What is NOT")[0].strip().splitlines()[0],
               not_modelled="full 2-D/3-D ridge geometry (FDTD), true diffraction orders, cover/ground scale "
                            "overlap, measured BRDFs; ILLUSTRATIVE thicknesses where papers give none",
               species=rep, effective_films=eff, figure="results/fig_butterfly_real.png")
    p = ROOT / "results" / "butterfly_real.json"
    p.write_text(json.dumps(_clean(out), indent=1, allow_nan=False, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    import time
    t = time.time()
    o = main()
    for nm, r in o["species"].items():
        print(f"{nm:26s} ideal {r['ideal']['peak_nm']:.0f}nm R{r['ideal']['R_max']:.2f} fw{r['ideal']['fwhm_nm']:.0f} "
              f"hw{r['ideal']['angular_halfwidth_deg']:.0f}° | real {r['realistic']['peak_nm']:.0f}nm "
              f"R{r['realistic']['R_max']:.2f} fw{r['realistic']['fwhm_nm']:.0f} hw{r['realistic']['angular_halfwidth_deg']:.0f}° "
              + " ".join(c["hex"] + f"/h{c['hue_deg']:.0f}" for c in r["colours_realistic"]))
    print(f"{time.time() - t:.1f}s")
