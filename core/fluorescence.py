"""Fluorescence inside thin-film stacks: real butterfly fluorescence (Papilio nireus group, birdwings) and the
phoneme films acting as the photonic structure around a fluorophore. Status: APPROXIMATE model.

Biology (cited, see CITATIONS):
- Papilio nireus-group scales hold a fluorescent papiliochrome-type pigment in the upper lamina, a 2-D photonic
  crystal (PC) slab of air cylinders in cuticle, ~1500 nm above a 3-layer lower-lamina distributed Bragg
  reflector (DBR). Peak excitation ~420 nm, peak emission ~505 nm, broad band ~450-650 nm. The PC slab and DBR
  control the direction of the emitted light (Vukusic & Hooper 2005; Van Hooijdonk et al. 2012).
- Birdwing (Ornithoptera / Troides) scales also contain distinctly fluorescing papiliochrome pigments, violet- or
  UV-absorbing, green-fluorescing under violet-blue excitation (Wilts et al. 2015).

Model (all approximate, documented):
1. Fluorophore: excitation/absorption band = Gaussian in WAVENUMBER (centre 420 nm); emission = asymmetric
   Gaussian in wavelength (peak 505 nm, sigma 25 nm blue side / 50 nm red side -> band ~450-650 nm). These are
   SHAPE FITS to the quoted peaks/band edges, not digitised spectra. Quantum yield: no literature value found for
   papiliochrome -> QY = 0.3 is ILLUSTRATIVE.
2. Absorption: the fluorophore is an imaginary index k(lambda) = k_max * eps(lambda) in the dye-bearing layers.
   The absorbing stack is solved with the Abeles matrix (same formulas as core.film, dispersive index): A = 1 - R - T exactly (energy
   conserving). All of A is attributed to the dye (the host layers are lossless).
3. Emission / extraction (Purcell-free): an in-plane dipole sheet at depth z radiates equal tangential fields
   up (+) and down (-). With r_t, r_b the amplitude reflectances seen from the emitter plane looking up/down
   (each including the phase of the remaining sub-layer), the self-consistent amplitudes are
       U = (1 + r_b) / (1 - r_t r_b),   D = (1 + r_t) / (1 - r_t r_b)
   and the powers leaving the top / bottom are P_t = T_t |U|^2, P_b = T_b |D|^2 (T from the emitter medium).
   Escape factor eta(lambda, theta) = P_t / (P_t + P_b) in [0, 1]: the fraction of the (unknown, Purcell-changed)
   total radiated power that leaves through the viewer's side in the plane-wave channel that exits at theta.
   eta = 1/2 for an emitter in a uniform medium. s and p are averaged (power-weighted). Emitters are spread
   uniformly in depth (2 sample planes per dye-bearing layer, thickness-weighted). Re-absorption of the emission
   and the vertical-dipole component are ignored. Emission is lossless in the stack (real indices).
4. Appearance: L(lambda) = R(lambda) I(lambda) + QY * N_abs * e(lambda) * eta(lambda, theta) * (hc/lambda), with
   N_abs = int A I lambda/(hc) dlambda the absorbed photon flux and e the area-normalised photon emission
   spectrum. So emitted photons <= QY * absorbed photons <= absorbed photons. XYZ uses the CIE 1931 2deg CMF with
   k = 100 / int I_D65 ybar for every illuminant (all illuminants scaled to the same total irradiance as D65
   over 300-830 nm), Lab against the D65 white, display hex = core.colour.display_rgb (ARTISTIC exposure
   normalisation, so a dim blacklight scene still shows its hue).
Caveat: R is a specular (mirror) quantity while fluorescence is spread over angles; their sum is a
"same-detector-channel" approximation, so fluor_fraction is indicative, not a radiometric measurement.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import colour as _cs

from . import colour as col
from . import mapping as mp
from .film import film_rt

WL = np.arange(300.0, 830.0 + 1e-9, 1.0)  # nm; extends below 360 so the 365 nm LED is fully resolved
CMF = np.stack([np.interp(WL, col.WL, col.CMF[:, i], left=0.0, right=0.0) for i in range(3)], 1)
_d65 = _cs.SDS_ILLUMINANTS["D65"]
_D65 = np.interp(WL, _d65.wavelengths, _d65.values, left=0.0, right=0.0)
_POWER = float(np.sum(_D65))
K_NORM = 100.0 / float(np.sum(_D65 * CMF[:, 1]))

CITATIONS = [
    "Vukusic P. & Hooper I. (2005) Directionally controlled fluorescence emission in butterflies. "
    "Science 310:1151. doi:10.1126/science.1116612",
    "Van Hooijdonk E., Vandenbem C., Berthier S. & Vigneron J.P. (2012) Bi-functional photonic structure in the "
    "Papilio nireus (Papilionidae): modeling by scattering-matrix optical simulations. Opt. Express 20:22001. "
    "doi:10.1364/OE.20.022001 (peak excitation ~420 nm, peak emission ~505 nm, band 450-650 nm; 2-D PC 1300 nm "
    "thick, air cylinders 240 nm diameter / 340 nm hexagonal spacing; lamina gap 1500 nm; DBR 75/35/75 nm)",
    "Wilts B.D., Matsushita A., Arikawa K. & Stavenga D.G. (2015) Spectrally tuned structural and pigmentary "
    "coloration of birdwing butterfly wing scales. J. R. Soc. Interface 12:20150717. doi:10.1098/rsif.2015.0717 "
    "(fluorescent papiliochromes in Ornithoptera/Troides scales; violet- and UV-absorbing pigments)",
    "CIE 1931 2deg observer and D65 via the colour-science package (as core.colour).",
]


# ------------------------------------------------------------------ fluorophore + illuminants
@dataclass
class Fluorophore:
    name: str = "papiliochrome-type (P. nireus)"
    exc_peak_nm: float = 420.0      # Van Hooijdonk 2012 / Vukusic & Hooper 2005 (approximate)
    exc_fwhm_cm1: float = 4500.0    # ILLUSTRATIVE width (~ 385-465 nm at half maximum)
    em_peak_nm: float = 505.0       # idem (approximate)
    em_sigma_blue_nm: float = 25.0  # shape fit to the quoted 450-650 nm band (approximate)
    em_sigma_red_nm: float = 50.0
    qy: float = 0.3                 # ILLUSTRATIVE (no literature value found)
    k_max: float = 0.02             # ILLUSTRATIVE peak extinction coefficient of the dye-bearing layers
    label: str = "approximate (peaks cited; shapes fitted; QY and k_max illustrative)"

    def excitation(self, wl=WL):
        nu, nu0 = 1e7 / np.asarray(wl, float), 1e7 / self.exc_peak_nm
        s = self.exc_fwhm_cm1 / 2.3548
        return np.exp(-0.5 * ((nu - nu0) / s) ** 2)

    def emission(self, wl=WL):
        """Photon emission spectrum, normalised to unit area on the 1 nm grid."""
        wl = np.asarray(wl, float)
        s = np.where(wl < self.em_peak_nm, self.em_sigma_blue_nm, self.em_sigma_red_nm)
        e = np.exp(-0.5 * ((wl - self.em_peak_nm) / s) ** 2)
        return e / np.sum(e)

    def stokes_shift(self):
        return dict(nm=self.em_peak_nm - self.exc_peak_nm,
                    cm1=1e7 / self.exc_peak_nm - 1e7 / self.em_peak_nm)


PAPILIOCHROME = Fluorophore()


def _led(peak, fwhm):
    s = fwhm / 2.3548
    e = np.exp(-0.5 * ((WL - peak) / s) ** 2)
    return e * _POWER / np.sum(e)


# All scaled to the same integrated irradiance as D65 (300-830 nm). LED shapes are ILLUSTRATIVE Gaussians.
ILLUMINANTS = {"D65": _D65, "UV365": _led(365.0, 10.0), "violet405": _led(405.0, 15.0)}


def illuminant(name_or_array):
    if isinstance(name_or_array, str):
        return ILLUMINANTS[name_or_array]
    return np.asarray(name_or_array, float)


# ------------------------------------------------------------------ colour helpers
def xyz_of(L):
    return K_NORM * np.asarray(L, float) @ CMF


def colour_of(L):
    XYZ = xyz_of(L)
    rgb = col.display_rgb(XYZ)
    return dict(XYZ=XYZ, Lab=col.xyz_to_lab(XYZ, "D65"), hex=col.to_hex(rgb))


# ------------------------------------------------------------------ amplitude transfer matrix (lossless emission)
def _r_t(n, d_nm, wl, s0, pol):
    """Macleod characteristic matrix. n = [incident, layers..., exit] (may be 2-D: [P, L] for P stacks with
    the same layer count). Returns amplitude r and power T for incidence from n[0]."""
    n = np.asarray(n, complex)
    cos_t = np.sqrt(1 - (s0 / n) ** 2 + 0j)
    eta = n * cos_t if pol == "s" else n / cos_t
    B = np.ones((n.shape[0], len(wl)), complex)
    C = np.repeat(eta[:, -1:], len(wl), 1)
    for j in range(n.shape[1] - 2, 0, -1):
        delta = 2 * np.pi * (n[:, j] * cos_t[:, j] * d_nm[:, j - 1])[:, None] / wl[None, :]
        cs, sn = np.cos(delta), np.sin(delta)
        e = eta[:, j][:, None]
        B, C = cs * B + 1j * sn / e * C, 1j * e * sn * B + cs * C
    e0 = eta[:, :1]
    den = e0 * B + C
    r = (e0 * B - C) / den
    T = 4 * np.real(e0) * np.real(eta[:, -1:]) / np.abs(den) ** 2
    return r, T


def _sub_stacks(n, d, layer, frac):
    """Emitter at fraction `frac` (from the top) inside layer `layer` (1-based in n). Returns the upward-looking
    and downward-looking stacks (incident = emitter medium) as (n, d) lists."""
    ne = n[layer]
    dl = d[layer - 1]
    up_n = [ne, ne] + list(n[1:layer][::-1]) + [n[0]]
    up_d = [frac * dl] + list(d[:layer - 1][::-1])
    dn_n = [ne, ne] + list(n[layer + 1:-1]) + [n[-1]]
    dn_d = [(1 - frac) * dl] + list(d[layer:])
    return (up_n, up_d), (dn_n, dn_d)


def escape_factor(n, d_nm, wl=WL, theta_deg=0.0, emitter_layers=None, planes=(0.25, 0.75)):
    """eta(lambda): thickness-weighted mean over emitter planes of P_top / (P_top + P_bottom), s/p averaged.
    n uses the real part (emission is treated as lossless). emitter_layers: 1-based layer indices (default all)."""
    n = np.real(np.asarray(n, complex))
    d = np.asarray(d_nm, float)
    wl = np.asarray(wl, float)
    N = len(d)
    layers = list(range(1, N + 1)) if emitter_layers is None else list(emitter_layers)
    s0 = n[0] * np.sin(np.deg2rad(theta_deg))
    ups, dns, w = [], [], []
    for j in layers:
        for f in planes:
            u, dn = _sub_stacks(n, d, j, f)
            ups.append(u), dns.append(dn), w.append(d[j - 1])
    w = np.asarray(w) / np.sum(w)

    def stack(lst):
        # pad with zero-thickness layers (identity matrices) before the exit medium -> equal layer counts
        L = max(len(x[1]) for x in lst)
        ns = [list(x[0][:-1]) + [x[0][-1]] * (L - len(x[1]) + 1) for x in lst]
        ds = [list(x[1]) + [0.0] * (L - len(x[1])) for x in lst]
        return np.array(ns, float), np.array(ds, float)

    un, ud = stack(ups)
    dn_, dd = stack(dns)
    Pt = np.zeros((len(w), len(wl)))
    Pb = np.zeros_like(Pt)
    for pol in ("s", "p"):
        rt, Tt = _r_t(un, ud, wl, s0, pol)
        rb, Tb = _r_t(dn_, dd, wl, s0, pol)
        den = np.abs(1 - rt * rb) ** 2
        Pt += Tt * np.abs(1 + rb) ** 2 / den
        Pb += Tb * np.abs(1 + rt) ** 2 / den
    eta = Pt / np.maximum(Pt + Pb, 1e-300)
    return w @ eta


# ------------------------------------------------------------------ appearance
def appearance(n, d_nm, illuminant="D65", theta_deg=0.0, fluor=PAPILIOCHROME, dye_layers=None, eta=None):
    """Apparent colour of stack (n, d_nm) with fluorophore `fluor` in `dye_layers` (1-based; default all layers).
    fluor=None -> pure reflection. Returns dict(spectrum, refl, fluo, XYZ, Lab, hex, fluor_fraction,
    absorbed_photons, emitted_photons, eta, A)."""
    n = np.asarray(n, complex)
    d = np.asarray(d_nm, float)
    I = globals()["illuminant"](illuminant)
    N = len(d)
    layers = list(range(1, N + 1)) if dye_layers is None else list(dye_layers)
    if fluor is None or fluor.k_max == 0:
        R, _ = film_rt(np.real(n), d, WL, theta_deg)
        A = np.zeros_like(WL)
        fluo = np.zeros_like(WL)
        Nabs = Nem = 0.0
        eta_v = None
    else:
        kap = fluor.k_max * fluor.excitation(WL)
        # wavelength-dependent complex index of the dye layers -> own dispersive Abeles solver (vectorised)
        nn = np.repeat(np.real(n)[None, :], len(WL), 0).astype(complex)
        for j in layers:
            nn[:, j] = np.real(n[j]) - 1j * kap  # Macleod convention N = n - ik
        R, T = _rt_dispersive(nn, d, WL, theta_deg)
        A = np.clip(1 - R - T, 0, 1)
        Nabs = float(np.sum(A * I * WL))                       # photon flux (units of 1/hc)
        eta_v = escape_factor(n, d, WL, theta_deg, layers) if eta is None else eta
        em = fluor.emission(WL)
        Nem = float(fluor.qy * Nabs * np.sum(em * eta_v))      # photons leaving the top
        fluo = fluor.qy * Nabs * em * eta_v / WL               # energy spectrum (x hc)
    refl = R * I
    S = refl + fluo
    c = colour_of(S)
    Yr, Yf = float(xyz_of(refl)[1]), float(xyz_of(fluo)[1])
    return dict(spectrum=S, refl=refl, fluo=fluo, XYZ=c["XYZ"], Lab=c["Lab"], hex=c["hex"],
                fluor_fraction=Yf / (Yr + Yf) if Yr + Yf > 0 else 0.0,
                absorbed_photons=Nabs, emitted_photons=Nem, eta=eta_v, A=A, R=R)


def _rt_dispersive(nn, d, wl, theta_deg):
    """R, T for a stack whose indices depend on wavelength: nn[lambda, layer]. Unpolarised average."""
    out_R = np.zeros(len(wl))
    out_T = np.zeros(len(wl))
    s0 = np.real(nn[0, 0]) * np.sin(np.deg2rad(theta_deg))
    for pol in ("s", "p") if theta_deg else ("s",):
        cos_t = np.sqrt(1 - (s0 / nn) ** 2 + 0j)
        eta = nn * cos_t if pol == "s" else nn / cos_t
        B = np.ones(len(wl), complex)
        C = eta[:, -1].copy()
        for j in range(nn.shape[1] - 2, 0, -1):
            delta = 2 * np.pi * nn[:, j] * d[j - 1] * cos_t[:, j] / wl
            cs, sn = np.cos(delta), np.sin(delta)
            B, C = cs * B + 1j * sn / eta[:, j] * C, 1j * eta[:, j] * sn * B + cs * C
        den = eta[:, 0] * B + C
        out_R += np.abs((eta[:, 0] * B - C) / den) ** 2
        out_T += 4 * np.real(eta[:, 0]) * np.real(eta[:, -1]) / np.abs(den) ** 2
    k = 2 if theta_deg else 1
    return out_R / k, out_T / k


# ------------------------------------------------------------------ Papilio nireus preset
PC_FILL_AIR = np.pi / (2 * np.sqrt(3)) * (240.0 / 340.0) ** 2   # hexagonal lattice of air cylinders, ~0.45
N_PC = float(np.sqrt((1 - PC_FILL_AIR) * mp.MATERIALS["chitin"] ** 2 + PC_FILL_AIR))  # effective medium ~1.33


def papilio_nireus_scale(gap_nm=1500.0, dbr=True):
    """1-D approximation of a P. nireus scale (Van Hooijdonk et al. 2012 dimensions):
    air | 2-D PC slab as effective medium (1300 nm, n_eff, DYE) | air gap | DBR cuticle 75 / air 35 / cuticle 75 |
    air. The 2-D PC is replaced by its effective index (its in-plane band structure, which suppresses in-plane
    emission, is NOT modelled). Layer materials of the DBR (cuticle/air/cuticle) are our reading of the paper."""
    nc = mp.MATERIALS["chitin"]
    n = [1.0, N_PC, 1.0]
    d = [1300.0, gap_nm]
    if dbr:
        n += [nc, 1.0, nc]
        d += [75.0, 35.0, 75.0]
    n += [1.0]
    return dict(name="Papilio nireus scale (1-D approx.)", n=np.array(n), d_nm=np.array(d), dye_layers=[1],
                label="approximate", source=CITATIONS[1])


def papilio_appearance(illuminant="D65", theta_deg=0.0, fluor=PAPILIOCHROME, dbr=True,
                       gaps=np.linspace(1200.0, 1800.0, 7)):
    """Average over the lamina gap (trabeculae make it vary across a scale; also removes unphysical
    coherent fringes of a 1.5 um air gap) -> incoherent mean spectrum."""
    S = refl = fluo = eta = 0.0
    Nabs = Nem = 0.0
    for g in gaps:
        p = papilio_nireus_scale(g, dbr)
        a = appearance(p["n"], p["d_nm"], illuminant, theta_deg, fluor, p["dye_layers"])
        S, refl, fluo = S + a["spectrum"], refl + a["refl"], fluo + a["fluo"]
        eta = eta + (a["eta"] if a["eta"] is not None else 0.0)
        Nabs, Nem = Nabs + a["absorbed_photons"], Nem + a["emitted_photons"]
    k = len(gaps)
    S, refl, fluo, eta = S / k, refl / k, fluo / k, eta / k
    c = colour_of(S)
    Yr, Yf = float(xyz_of(refl)[1]), float(xyz_of(fluo)[1])
    return dict(spectrum=S, refl=refl, fluo=fluo, eta=eta, XYZ=c["XYZ"], Lab=c["Lab"], hex=c["hex"],
                fluor_fraction=Yf / (Yr + Yf) if Yr + Yf > 0 else 0.0,
                absorbed_photons=Nabs / k, emitted_photons=Nem / k,
                peak_emission_nm=float(WL[np.argmax(fluo)]) if np.any(fluo > 0) else None)


# ------------------------------------------------------------------ phonemes
def phoneme_film(a_poly, mode="realizable", mapping="full"):
    """Same film as tools/build_sounds.py: vowel_media(a) -> film_from_media(mode) -> Goupillaud thicknesses."""
    n = mp.film_from_media(mp.vowel_media(np.asarray(a_poly, float)), mode)
    d_opt = mp.MAPPINGS[mapping]["d_opt"]
    return n, mp.goupillaud_d(n[1:-1], d_opt)


def phoneme_fluorescence(a_poly, fluor=PAPILIOCHROME, theta_deg=0.0, mode="realizable", mapping="full"):
    """Fluorophore spread through every layer of the phoneme's film; colour under D65, UV-A 365 nm and 405 nm.
    The escape factor depends only on the film, so it is computed once."""
    n, d = phoneme_film(a_poly, mode, mapping)
    eta = escape_factor(n, d, WL, theta_deg)
    out = {}
    for ill in ILLUMINANTS:
        a = appearance(n, d, ill, theta_deg, fluor, eta=eta)
        out[ill] = a
    return dict(n=n, d_nm=d, eta=eta, by_illuminant=out,
                peak_emission_nm=float(WL[np.argmax(fluor.emission(WL) * eta)]))
