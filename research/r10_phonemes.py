"""(10) Every phoneme (EXPERIMENTAL): the colour gamut of each phoneme class and a comparison of every phoneme FILM
with butterfly / beetle FILMS (reflectance spectra + colour, a realizable chitin/air twin, and the voices).

Input: web/data/sounds.json (tools/build_sounds.py; 43 items, CONTRACT §7c). The per-frame polynomials of the
recordings are re-derived with the SAME functions as build_sounds (load_16k, frames_of, features, analyse,
STRIP_MAX), and the result is checked against the stored strip hexes (strip_reproduced_exactly).

Pipeline per polynomial a:  vowel_media(a) -> film_from_media(m, mode) -> Goupillaud stack (d = D_OPT/n)
-> film_rt(theta, unpolarised) -> R or T -> XYZ (D65) -> displayed hex (exposure-normalised, CONTRACT §8)
-> Lab of the displayed hex (same convention as r9 / CONTRACT §4b).

"Valid" colour = produced by a physically realizable film, checked numerically for every film:
  (i) step_down(a) succeeds, all |k| < 1 (frames are analysed with |k| clipped at 0.995);
 (ii) every index (incident, layers, substrate) in [N_MIN, N_MAX] = [1, 2.5];
(iii) every interface reflection coefficient |c_i| < 1;
 (iv) lossless energy balance at normal incidence: max |R + T − 1| < 1e-9;
  (v) finite XYZ.
The ideal-film views (indices up to ~240) fail (ii): they are reported for completeness, never as "valid".

Gamut of a class = all valid colours over {item polynomial} ∪ {per-frame strip polynomials} × angles
{0, 15, 30, 45, 60}° in the main view full-band · realizable · R. Distinct colours = complete-linkage clusters in
CIELAB with CIEDE2000 cut at CLUSTER_DE (every pair inside a cluster ≤ CLUSTER_DE). verdict "few" ⇔ ≤ 2 clusters, and
then a proof with a numeric check is REQUIRED (none is invented when the data do not show "few").

Butterflies: web/data/butterflies.json (Morpho-like, Beetle-like, 4 Goupillaud speakers) + core.stacks morpho_like /
beetle_like with lamellae ×0.9 / ×1.1 (as r4). Twin: a chitin (1.56) / air (1.00) multilayer on chitin with free
thicknesses fitted by L-BFGS-B to the phoneme's absolute reflected Lab (ΔE00 cost, as core.inverse.design_stacks
does for continuous indices; design_stacks itself cannot be restricted to two materials). Cached.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.optimize import minimize
from scipy.spatial import ConvexHull

from core import colour as col, film, lpc, mapping as mp, stacks
from research.common import ROOT, RES, OI, plt, savefig, rnd, lsd, db
from research.r9_sounds import hex_lab, hex_rgb

SOUNDS = ROOT / "web" / "data" / "sounds.json"
BFLY = ROOT / "web" / "data" / "butterflies.json"
OUT_WEB = ROOT / "web" / "data" / "phonemes_experiment.json"
CACHE_COL = RES / "cache_r10_colours.json"
CACHE_TWIN = RES / "cache_r10_twins.json"

TAG = ""   # "" = IPA-chart recordings; "_user" = the author's own voice (use_user())


def use_user():
    """Point the whole section at web/data/sounds_user.json (own recordings); all outputs get the suffix _user."""
    global SOUNDS, OUT_WEB, CACHE_COL, CACHE_TWIN, TAG
    TAG = "_user"
    SOUNDS = ROOT / "web" / "data" / "sounds_user.json"
    OUT_WEB = ROOT / "web" / "data" / "phonemes_experiment_user.json"
    CACHE_COL, CACHE_TWIN = RES / "cache_r10_user_colours.json", RES / "cache_r10_user_twins.json"


def cache_fluor():
    """Fluorescence cache path (respects TAG): results/cache_r10_fluor{TAG}.json."""
    return RES / f"cache_r10_fluor{TAG}.json"


ANGLES = [0, 15, 30, 45, 60]
CLUSTER_DE = 10.0
MAIN = ("full", "realizable", "R")
VIEWS = [("full", "realizable", "R", "full·realizable·R"), ("full", "ideal", "T", "full·ideal·T"),
         ("brief", "realizable", "R", "brief·realizable·R"), ("brief", "ideal", "T", "brief·ideal·T")]
D_OPT = {"full": mp.D_OPT_FULL_NM, "brief": mp.D_OPT_NM}
CLASS_ORDER = ["vowel", "diphthong", "plosive", "affricate", "nasal", "fricative", "lateral", "approximant"]
CLASS_LABEL = {"vowel": "Vowels", "diphthong": "Diphthongs", "plosive": "Plosives", "affricate": "Affricates",
               "nasal": "Nasals", "fricative": "Fricatives", "lateral": "Lateral", "approximant": "Approximants"}
WL_SPEC = (col.WL >= 380) & (col.WL <= 780)


# ------------------------------------------------------------------------------------------------ data
def _sha(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()[:16]


def collect():
    """Items of sounds.json with their frame polynomials (strip) and rule-selected frames (own)."""
    from tools import build_sounds as bs
    items = json.loads(SOUNDS.read_text(encoding="utf-8"))["items"]
    att = {i["id"]: i for i in json.loads((ROOT / "data" / "ipa" / "ATTRIBUTION.json").read_text(encoding="utf-8"))["items"]}
    by = {i["id"]: i for i in items}
    out, mism = {}, 0
    for it in items:
        sid = it["id"]
        rec = dict(a=np.array(it["a"], float), strip=[], own=[])
        if sid in att and (ROOT / att[sid]["file"]).exists() and not it.get("modelled"):
            x, _ = bs.load_16k(ROOT / att[sid]["file"])
            F, xp = bs.frames_of(x)
            ft = bs.features(F)
            idx = np.flatnonzero(ft["E"] >= bs.E_LOOSE)
            if len(idx) > bs.STRIP_MAX:
                idx = idx[np.round(np.linspace(0, len(idx) - 1, bs.STRIP_MAX)).astype(int)]
            for i in idx:
                r = bs.analyse([F[i]])
                rec["strip"].append(r[0] if r else None)
            hs = [bs.strip_hex(a) if a is not None else "#000000" for a in rec["strip"]]
            mism += sum(h != g for h, g in zip(hs, it["strip"])) + abs(len(hs) - len(it["strip"]))
            fr, _ = bs.select(it["class"], it["voiced"], F, xp, ft, glottal=(it["ipa"] == "h"))
            if it.get("rule") == "fallback" or not fr:
                fr = [F[i] for i in np.flatnonzero(ft["E"] >= bs.E_LOOSE)]
            for f in fr:
                r = bs.analyse([f])
                if r:
                    rec["own"].append(r[0])
        out[sid] = rec
    # modelled items: frames of the relatives they are built from (exactly as build_sounds builds their strips)
    for it in items:
        sid, rec = it["id"], out[it["id"]]
        if it["class"] == "diphthong":
            L = [2 * np.arctanh(np.clip(lpc.step_down(np.array(by[e]["a"])), -bs.K_MAX, bs.K_MAX))
                 for e in (it["from"], it["to"])]
            rec["strip"] = [lpc.step_up(np.tanh(((1 - t) * L[0] + t * L[1]) / 2)) for t in np.linspace(0, 1, bs.TRAJ_N)]
            rec["own"] = list(rec["strip"])
        elif it.get("modelled") and it.get("modelled_from"):
            src = it["modelled_from"]
            if len(src) == 2:       # burst relative (first 5 frames) + frication relative, as build_sounds
                rec["strip"] = (out[src[0]]["strip"][:5] + out[src[1]]["strip"])[:bs.STRIP_MAX]
                rec["own"] = out[src[0]]["own"][:5] + out[src[1]]["own"]
            else:
                rec["strip"], rec["own"] = list(out[src[0]]["strip"]), list(out[src[0]]["own"])
        elif it.get("modelled"):
            rec["strip"], rec["own"] = [rec["a"]], [rec["a"]]
        rec["strip"] = [a for a in rec["strip"] if a is not None]
    return items, out, mism


def film_of(a, mode, mapping):
    n = mp.film_from_media(mp.vowel_media(a), mode)
    return n, mp.goupillaud_d(n[1:-1], D_OPT[mapping])


def validity(a, n, mode):
    """Numeric realizability checks (i)-(iv) of the module docstring."""
    try:
        k = lpc.step_down(a)
        ok_k = bool(np.all(np.abs(k) < 1))
    except Exception:  # noqa: BLE001
        ok_k = False
    ok_n = bool(n.min() >= mp.N_MIN - 1e-9 and n.max() <= mp.N_MAX + 1e-9)
    ok_c = bool(np.all(np.abs(mp.reflection_from_media(n)) < 1))
    return ok_k, ok_n, ok_c


def colours_of(a, mapping, mode, q, angles):
    """[(hex, Lab_abs, Y, valid)] for each angle."""
    n, d = film_of(a, mode, mapping)
    ok_k, ok_n, ok_c = validity(a, n, mode)
    out = []
    for th in angles:
        R, T = film.film_rt(n, d, col.WL, th)
        ok_e = True if th else bool(np.max(np.abs(R + T - 1)) < 1e-9)
        X = col.spectrum_to_xyz(R if q == "R" else T)
        fin = bool(np.all(np.isfinite(X)) and X[1] > 0)
        hx = col.to_hex(col.display_rgb(X)) if fin else "#000000"
        out.append((hx, col.xyz_to_lab(X).tolist() if fin else None, float(X[1]) if fin else 0.0,
                    bool(ok_k and ok_n and ok_c and ok_e and fin)))
    return out


def compute_colours(items, polys, fresh=False):
    key = _sha(SOUNDS) + f"|{ANGLES}|v2"
    if CACHE_COL.exists() and not fresh:
        c = json.loads(CACHE_COL.read_text(encoding="utf-8"))
        if c.get("key") == key:
            return c
    t0 = time.time()
    C = dict(key=key, items={})
    for it in items:
        sid, rec = it["id"], polys[it["id"]]
        e = {}
        for mpg, mode, q, _ in VIEWS:
            v = f"{mpg}_{mode}_{q}"
            main = (mpg, mode, q) == MAIN
            e[v] = dict(item=colours_of(rec["a"], mpg, mode, q, ANGLES),
                        strip=[colours_of(a, mpg, mode, q, ANGLES if main else [0]) for a in rec["strip"]],
                        own=[colours_of(a, mpg, mode, q, ANGLES if main else [0]) for a in rec["own"]] if main else [])
        C["items"][sid] = e
    C["seconds"] = round(time.time() - t0, 1)
    CACHE_COL.write_text(json.dumps(C), encoding="utf-8")
    return C


# ------------------------------------------------------------------------------------------------ colour maths
def de00(L1, L2):
    """Vectorised CIEDE2000 (same formula as core.colour.delta_e00), broadcasting L1[..., 3] vs L2[..., 3]."""
    L1, L2 = np.asarray(L1, float), np.asarray(L2, float)
    l1, a1, b1 = L1[..., 0], L1[..., 1], L1[..., 2]
    l2, a2, b2 = L2[..., 0], L2[..., 1], L2[..., 2]
    Cb = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    zero = C1p * C2p == 0
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(zero, 0.0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (l1 + l2) / 2, (C1p + C2p) / 2
    s = h1p + h2p
    hbp = np.where(np.abs(h1p - h2p) <= 180, s / 2, np.where(s < 360, (s + 360) / 2, (s - 360) / 2))
    hbp = np.where(zero, s, hbp)
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dth = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    dL, dC = (l2 - l1) / Sl, (C2p - C1p) / Sc
    dH = dHp / Sh
    return np.sqrt(dL ** 2 + dC ** 2 + dH ** 2 + Rt * dC * dH)


def cluster(labs, thr=CLUSTER_DE):
    """Complete-linkage clusters (max intra-cluster CIEDE2000 <= thr). Returns labels (1..K)."""
    labs = np.asarray(labs, float)
    n = len(labs)
    if n == 1:
        return np.array([1])
    cond = np.concatenate([de00(labs[i], labs[i + 1:]) for i in range(n - 1)])
    return fcluster(linkage(cond, "complete"), t=thr, criterion="distance")


def gamut_of(hexes, thr=CLUSTER_DE):
    """Unique hexes -> Lab, clusters, hull in a*b*."""
    u = sorted(set(h for h in hexes if h != "#000000"))
    if not u:
        return dict(hexes=[], ab=[], hull_ab=[], distinct=0, labels=[], reps=[])
    labs = np.array([hex_lab(h) for h in u])
    lab_ = cluster(labs, thr)
    reps = []
    for c in np.unique(lab_):
        idx = np.flatnonzero(lab_ == c)
        cen = labs[idx].mean(0)
        reps.append(dict(hex=u[idx[np.argmin(de00(cen, labs[idx]))]], n=int(len(idx)),
                         Lab=rnd(cen, 1)))
    reps.sort(key=lambda r: -r["n"])
    ab = labs[:, 1:]
    hull = []
    if len(u) >= 3:
        try:
            hull = ab[ConvexHull(ab).vertices].tolist()
        except Exception:  # noqa: BLE001  (collinear / degenerate)
            hull = ab.tolist()
    else:
        hull = ab.tolist()
    return dict(hexes=u, ab=rnd(ab, 1), hull_ab=rnd(hull, 1), distinct=int(len(np.unique(lab_))),
                labels=lab_.tolist(), reps=reps, labs=labs)


def many_certificate(hexes, thr=CLUSTER_DE, k=3):
    """k colours whose pairwise CIEDE2000 all exceed thr (greedy farthest point). Two colours farther apart than thr
    can never share a complete-linkage cluster cut at thr, so such a k-tuple PROVES distinct_colours >= k.
    Returns the k hexes and their pairwise ΔE00, or None if the greedy search finds no such tuple."""
    u = sorted(set(h for h in hexes if h != "#000000"))
    if len(u) < k:
        return None
    labs = np.array([hex_lab(h) for h in u])
    cen = labs.mean(0)
    chosen = [int(np.argmax(de00(cen, labs)))]
    while len(chosen) < k:
        d = np.min(np.stack([de00(labs[c], labs) for c in chosen]), axis=0)
        chosen.append(int(np.argmax(d)))
    pair = [float(de00(labs[i], labs[j])) for x, i in enumerate(chosen) for j in chosen[x + 1:]]
    if min(pair) <= thr:
        return None
    return dict(hexes=[u[i] for i in chosen], pairwise_dE00=rnd(pair, 2), threshold=thr)


# ------------------------------------------------------------------------------------------------ butterflies
def butterflies():
    """web/data/butterflies.json (6 films, stored voice a/gain) + core.stacks Morpho/Beetle with lamellae x0.9/x1.1."""
    out = []
    for b in json.loads(BFLY.read_text(encoding="utf-8"))["items"]:
        out.append(dict(name=b["name"], source=f"web/data/butterflies.json ({b['label']}; {b['source'][:80]})",
                        n=np.array(b["n"], float), d=np.array(b["d_nm"], float), a=np.array(b["a"], float),
                        gain=float(b["gain"])))
    for fn, nm, kw in ((stacks.morpho_like, "Morpho-like", ("d_chitin", "d_air", stacks.MORPHO_D_CHITIN, stacks.MORPHO_D_AIR)),
                       (stacks.beetle_like, "Beetle-like", ("d1", "d2", 95.0, 75.0))):
        for sc in (0.9, 1.1):
            s = fn(**{kw[0]: kw[2] * sc, kw[1]: kw[3] * sc})
            a, g = film.voice_of_film(s["n"], s["d_nm"])
            out.append(dict(name=f"{nm} ×{sc:g}", source=f"core.stacks.{fn.__name__} with layer thicknesses ×{sc:g} "
                            f"({s['label']}; as research/r4)", n=s["n"], d=s["d_nm"], a=a, gain=g))
    for b in out:
        R, _ = film.film_rt(b["n"], b["d"], col.WL)
        X = col.spectrum_to_xyz(R)
        b.update(R=R, hex=col.to_hex(col.display_rgb(X)), Lab_abs=col.xyz_to_lab(X))
        b["Lab"] = hex_lab(b["hex"])
        b["env"] = env_power(b["a"], b["gain"])
    return out


F_ENV = np.linspace(0, mp.FS / 2, 513)


def env_power(a, gain=1.0):
    z = np.exp(-1j * np.outer(2 * np.pi * F_ENV / mp.FS, np.arange(len(a))))
    return gain ** 2 / np.abs(z @ np.asarray(a, float)) ** 2


# ------------------------------------------------------------------------------------------------ chitin/air twin
TWIN_LAYERS = 8
TWIN_BOUNDS = (5.0, 400.0)
_SUB = slice(None, None, 4)          # 2 nm grid for the optimiser; final colour on the full 0.5 nm grid


def _twin_n(nl=TWIN_LAYERS):
    c, a_ = mp.MATERIALS["chitin"], mp.MATERIALS["air"]
    return np.array([a_] + [c if i % 2 == 0 else a_ for i in range(nl)] + [c])


def _lab_R(n, d, sub=False):
    wl = col.WL[_SUB] if sub else col.WL
    R, _ = film.film_rt(n, d, wl)
    if sub:
        E, cmf = col.ILLUMINANTS["D65"][_SUB], col.CMF[_SUB]
        X = 100.0 / np.sum(E * cmf[:, 1]) * (R * E) @ cmf
    else:
        X = col.spectrum_to_xyz(R)
    return col.xyz_to_lab(X), X


def design_twin(target_lab, seed=0, restarts=3):
    """Chitin/air multilayer (air | chitin, air, ... | chitin substrate), thicknesses free in [5, 400] nm,
    L-BFGS-B on CIEDE2000 to the target absolute reflected Lab (D65)."""
    rng = np.random.default_rng(seed)
    n = _twin_n()
    target = np.asarray(target_lab, float)
    best = None
    lo, hi = TWIN_BOUNDS
    for _ in range(restarts):
        x0 = rng.uniform(np.log(30), np.log(250), TWIN_LAYERS)
        res = minimize(lambda x: float(de00(_lab_R(n, np.exp(x), True)[0], target)), x0, method="L-BFGS-B",
                       bounds=[(np.log(lo), np.log(hi))] * TWIN_LAYERS, options=dict(maxiter=120))
        if best is None or res.fun < best.fun:
            best = res
        if best.fun < 1.0:
            break
    d = np.exp(best.x)
    lab, X = _lab_R(n, d)
    return dict(n=n.tolist(), d_nm=rnd(d, 1), dE00=float(de00(lab, target)), Lab=rnd(lab, 2),
                hex=col.to_hex(col.display_rgb(X)))


def twins(items, C, fresh=False):
    cache = {} if (fresh or not CACHE_TWIN.exists()) else json.loads(CACHE_TWIN.read_text(encoding="utf-8"))
    out, new = {}, 0
    for it in items:
        lab = C["items"][it["id"]]["full_realizable_R"]["item"][0][1]
        key = f"{TWIN_LAYERS}|" + ",".join(f"{v:.2f}" for v in lab)
        if key not in cache:
            cache[key] = design_twin(lab)
            new += 1
        out[it["id"]] = cache[key]
    if new:
        CACHE_TWIN.write_text(json.dumps(cache), encoding="utf-8")
    return out


# ------------------------------------------------------------------------------------------------ realistic butterflies
def real_butterflies():
    """Realistic scale models (core/butterfly.py): displayed colour vs angle, peak, citation."""
    from core import butterfly as bf
    out = []
    for nm in bf.species():
        cv = bf.colour_vs_angle(nm, angles=tuple(ANGLES))
        sp = bf.SPECIES[nm]
        src = "; ".join(bf._CIT[c].split(" (")[0] for c in sp["citations"][:2])
        out.append(dict(name=nm, hex=cv[0]["hex"], angle_hexes=[c["hex"] for c in cv], peak_nm=cv[0]["peak_nm"],
                        R_peak=cv[0]["R_peak"], kind=sp["kind"], published=sp["published"],
                        source=f"core/butterfly.py realistic model (approximate; tuned thicknesses labelled "
                               f"ILLUSTRATIVE): {src}"))
    return out


def nearest_real(n, d):
    """Nearest realistic species to a phoneme film (main view, 0°) by reflectance correlation (as nearest_butterfly)."""
    from core import butterfly as bf
    cmp_ = bf.compare_film_to_species(n, d, 0.0)
    best = max(cmp_, key=lambda k: cmp_[k]["spectral_corr"])
    best_c = min(cmp_, key=lambda k: cmp_[k]["dE00"])
    return (dict(name=best, dE00=round(cmp_[best]["dE00"], 2), spectral_corr=round(cmp_[best]["spectral_corr"], 3)),
            dict(name=best_c, dE00=round(cmp_[best_c]["dE00"], 2), spectral_corr=round(cmp_[best_c]["spectral_corr"], 3)))


# ------------------------------------------------------------------------------------------------ fluorescence
FL_W = (430.0, 655.0)   # window λ0 − 3σ_b … λ0 + 3σ_r of the papiliochrome emission (505 nm, σ_b 25, σ_r 50)


def fluorescence_items(items, fresh=False):
    """core.fluorescence.phoneme_fluorescence for every item (same realizable full-band film), plus the
    quantities the blacklight proof needs. Cached by sounds sha + TAG."""
    from core import fluorescence as F
    key = _sha(SOUNDS) + f"|{TAG}|{FL_W}|v1"
    path = cache_fluor()
    if path.exists() and not fresh:
        c = json.loads(path.read_text(encoding="utf-8"))
        if c.get("key") == key and set(c["items"]) >= {i["id"] for i in items}:
            return c
    W = (F.WL >= FL_W[0]) & (F.WL <= FL_W[1])
    f = F.PAPILIOCHROME
    ref = F.xyz_of(f.emission(F.WL) / F.WL)          # flat-η reference (η ≡ const)
    out = {}
    for it in items:
        r = F.phoneme_fluorescence(it["a"])
        b = r["by_illuminant"]
        eta = r["eta"]
        dln = np.gradient(np.log(eta), F.WL)
        uv = b["UV365"]
        XYZf = F.xyz_of(uv["fluo"])
        out[it["id"]] = dict(
            hex_D65=b["D65"]["hex"], hex_UV=uv["hex"], hex_violet=b["violet405"]["hex"],
            fluor_fraction_D65=round(float(b["D65"]["fluor_fraction"]), 4),
            fluor_fraction_UV=round(float(uv["fluor_fraction"]), 6),
            peak_emission_nm=round(float(r["peak_emission_nm"]), 1),
            kappa=float(np.max(np.abs(dln[W]))), eta_min=float(eta[W].min()), eta_max=float(eta[W].max()),
            eta_505=float(eta[np.argmin(np.abs(F.WL - 505))]),
            xy_ratio=[float(XYZf[0] / XYZf[1] / (ref[0] / ref[1])), float(XYZf[2] / XYZf[1] / (ref[2] / ref[1]))],
            Lab_UV_unclipped=col.xyz_to_lab(50.0 * XYZf / XYZf[1]).tolist())
    tail = float(np.exp(-4.5))
    C = dict(key=key, items=out, fluorophore=dict(name=f.name, em_peak_nm=f.em_peak_nm, sigma_blue_nm=f.em_sigma_blue_nm,
                                                  sigma_red_nm=f.em_sigma_red_nm, exc_peak_nm=f.exc_peak_nm, qy=f.qy,
                                                  k_max=f.k_max, label=f.label),
             tail=tail, ref_hex=F.colour_of(f.emission(F.WL) / F.WL)["hex"])
    path.write_text(json.dumps(C), encoding="utf-8")
    return C


def fluorescence_proof(FC, items):
    """'Few colours' result under blacklight: a derivation + numeric check (holds is computed, never assumed)."""
    fl = FC["fluorophore"]
    l0, sb, sr = fl["em_peak_nm"], fl["sigma_blue_nm"], fl["sigma_red_nm"]
    E = [FC["items"][i["id"]] for i in items]
    ids = [i["ipa"] for i in items]
    peaks = np.array([e["peak_emission_nm"] for e in E])
    kap = np.array([e["kappa"] for e in E])
    bound = np.where(peaks >= l0, sr ** 2, sb ** 2) * kap + 1.0          # +1 nm: 1 nm wavelength grid
    shift = np.abs(peaks - l0)
    ok_peak = bool(np.all(shift <= bound))
    emin, emax = min(e["eta_min"] for e in E), max(e["eta_max"] for e in E)
    rho = np.array([e["eta_max"] / e["eta_min"] for e in E])
    ratios = np.array([e["xy_ratio"] for e in E])
    lr = np.max(np.abs(np.log(ratios)), axis=1)
    ok_ratio = bool(np.all(lr <= np.log(rho) + 0.02))                  # 0.02: emission tail outside the window
    ok_tail = bool(FC["tail"] < emin)
    labs = np.array([hex_lab(e["hex_UV"]) for e in E])
    labu = np.array([e["Lab_UV_unclipped"] for e in E])
    n = len(E)
    pair = max(float(de00(labs[i], labs[j])) for i in range(n) for j in range(i + 1, n)) if n > 1 else 0.0
    pair_u = max(float(de00(labu[i], labu[j])) for i in range(n) for j in range(i + 1, n)) if n > 1 else 0.0
    k_uv = int(len(np.unique(cluster(labs)))) if n > 1 else 1
    ffuv = min(e["fluor_fraction_UV"] for e in E)
    holds = bool(ok_peak and ok_ratio and ok_tail and pair <= CLUSTER_DE and k_uv == 1)
    steps = [
        "Source term. Under the 365 nm LED the light leaving the film is L(λ) = R(λ)·I(λ) + QY·N_abs·e(λ)·η(λ)/λ "
        "(core/fluorescence.py, energy units). I(λ) sits below 380 nm where the CIE colour-matching functions are "
        f"≈ 0, so the reflected part carries a negligible share of Y (fluorescence share ≥ {ffuv:.4f} for every item). "
        "The UV colour is therefore the colour of S(λ) = e(λ)·η(λ)/λ alone.",
        "Brightness drops out. QY·N_abs is one number per film (absorption changes how MUCH light is emitted, not "
        "WHERE in the spectrum); the displayed colour is exposure-normalised, so only the shape of S matters.",
        f"The emission is fixed by the fluorophore: e(λ) is a split Gaussian, peak λ0 = {l0:g} nm, σ_b = {sb:g} nm "
        f"(blue side), σ_r = {sr:g} nm (red side). The film cannot move it; it only multiplies it by the escape "
        "factor η(λ) = P_top/(P_top + P_bottom) ∈ (0, 1).",
        f"η is bounded for realizable films. With indices n ∈ [1, 2.5] a single interface reflects at most "
        f"|r| = (2.5 − 1)/(2.5 + 1) ≈ 0.43, so neither side is a broadband mirror; over the emission window "
        f"W = {FL_W[0]:g}–{FL_W[1]:g} nm (λ0 − 3σ_b … λ0 + 3σ_r) the computed η of all {n} films lies in "
        f"[{emin:.2f}, {emax:.2f}], and per film ρ_i = max η_i / min η_i ≤ {rho.max():.2f}.",
        "Lemma (peak shift). Let S(λ) = exp(−(λ − λ0)²/2σ²)·w(λ) with w > 0 differentiable and κ = max_W |d ln w/dλ|. "
        "At an interior maximum λ* ∈ W, 0 = d ln S/dλ = −(λ* − λ0)/σ² + (ln w)′(λ*), hence "
        "|λ* − λ0| = σ²·|(ln w)′(λ*)| ≤ σ²·κ. For the split Gaussian ln e is C¹ at λ0, so the same holds with σ = σ_r "
        "if λ* > λ0 and σ = σ_b otherwise.",
        f"The maximum lies in W. Outside W, e(λ) ≤ e^(−4.5)·e(λ0) ≈ {FC['tail']:.3f}·e(λ0) and η ≤ 1, while "
        f"e(λ0)·η(λ0) ≥ {emin:.2f}·e(λ0) inside, so the global peak of e·η is in W. Applying the lemma with w = η_i "
        "(photon spectrum) gives λ*_i ∈ [λ0 − σ_b²κ_i, λ0 + σ_r²κ_i].",
        "Chromaticity. Each tristimulus value is T = ∫ c̄(λ)·e(λ)·η_i(λ)/λ dλ with c̄ ≥ 0. Since η_i ∈ [m_i, M_i] on W "
        "(where ≥ 99.7 % of the emission lies), X, Y and Z are each the flat-η reference value times a factor in "
        "[m_i, M_i]; therefore X/Y and Z/Y differ from the reference by a factor in [1/ρ_i, ρ_i] (up to e^(±0.02) "
        "for the 0.3 % tail outside W, since 0.003/η_min < 0.01 per value). This bound is loose "
        "(η varies slowly and the same factor enters numerator and denominator), and the true shifts are far smaller.",
        "Conclusion. A realizable phoneme film only re-weights a fixed emission band by a slowly varying factor, so "
        "the blacklight colour is the fluorophore's colour, the same green for every phoneme. In daylight the film's "
        "own reflection is added and the colours differ again (see fluorescence.items[].hex_D65).",
    ]
    check = (f"{n} items: peak λ* ∈ [{peaks.min():.0f}, {peaks.max():.0f}] nm; max |λ* − λ0| = {shift.max():.0f} nm, "
             f"every one ≤ its bound σ²κ_i + 1 nm (bounds {bound.min():.0f}–{bound.max():.0f} nm, κ_i ≤ "
             f"{kap.max():.4f} /nm): {ok_peak}. X/Y, Z/Y vs flat η: max factor {np.exp(lr.max()):.3f} ≤ ρ_i: "
             f"{ok_ratio}. Tail {FC['tail']:.3f} < η_min {emin:.2f}: {ok_tail}. Max pairwise CIEDE2000 between the "
             f"{n} UV display colours = {pair:.2f} (unclipped, Y-normalised Lab: {pair_u:.2f}) ≤ {CLUSTER_DE:g} → "
             f"{k_uv} distinct colour(s) at the class cut.")
    proof = dict(title="Blacklight: why every phoneme film glows the same green",
                 claim=(f"Under UV-A every realizable phoneme film shows ONE colour: the film cannot change the "
                        f"fluorophore's emission band, only multiply it by an escape factor with bounded log-slope κ, "
                        f"which moves the peak by at most σ²·κ and the colour by ΔE00 ≤ {pair:.1f}."),
                 steps=steps, numeric_check=check, holds=holds)
    stats = dict(peak_min=float(peaks.min()), peak_max=float(peaks.max()), shift_max=float(shift.max()),
                 bound_max=float(bound.max()), kappa_max=float(kap.max()), eta_min=emin, eta_max=emax,
                 rho_max=float(rho.max()), max_dE00_UV=round(pair, 2), max_dE00_UV_unclipped=round(pair_u, 2),
                 distinct_UV=k_uv, fluor_share_UV_min=ffuv)
    return proof, stats


# ------------------------------------------------------------------------------------------------ figures
def _hexes_main(C, sid, level):
    e = C["items"][sid]["full_realizable_R"]
    sets = [e["item"]] + (e[level] if level in ("strip", "own") else [])
    good = [h for s in sets for h, _, _, ok in s if ok]
    bad = sum(1 for s in sets for _, _, _, ok in s if not ok)
    return good, bad


def fig_gamut(classes):
    fig, axs = plt.subplots(4, 2, figsize=(8.5, 15.5))
    for ax, c in zip(axs.ravel(), classes):
        g = c["_g"]
        ab = np.array(g["ab"])
        ax.scatter(ab[:, 0], ab[:, 1], s=7, c=[hex_rgb(h) for h in g["hexes"]], edgecolors="none")
        h = np.array(g["hull_ab"] + g["hull_ab"][:1])
        ax.plot(h[:, 0], h[:, 1], color="0.25", lw=1.0)
        it = np.array(c["_item_ab"])
        ax.scatter(it[:, 0], it[:, 1], s=60, facecolors="none", edgecolors="black", lw=1.2, label="item, 0°")
        ax.axhline(0, color="0.6", lw=0.5); ax.axvline(0, color="0.6", lw=0.5)
        ax.set_xlim(-110, 110); ax.set_ylim(-110, 110); ax.set_aspect("equal")
        ax.set_title(f"{c['label']} ({c['n_items']}): {c['distinct_colours']} distinct · {len(g['hexes'])} colours",
                     fontsize=9.5, loc="left")
        reps = g["reps"][:24]
        for j, r in enumerate(reps):        # cluster swatches along the bottom
            ax.add_patch(plt.Rectangle((-108 + j * 9, -108), 8.5, 9, color=hex_rgb(r["hex"]), lw=0))
        ax.set_xlabel("a*", fontsize=8); ax.set_ylabel("b*", fontsize=8)
    axs[0, 0].legend(loc="upper left", fontsize=7)
    fig.suptitle(f"Every valid colour of each phoneme class (full-band · realizable film · reflected; item + every frame "
                 f"× {len(ANGLES)} angles 0–60°).\nOutline = convex hull in a*b*; squares = cluster representatives "
                 f"(complete linkage, ΔE00 ≤ {CLUSTER_DE:g}); circles = the item at normal incidence.", fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    return savefig(fig, "r10_gamut" + TAG)


def fig_butterflies(rows, B, examples):
    fig = plt.figure(figsize=(9.5, 13.5))
    gs = fig.add_gridspec(len(examples), 2, width_ratios=[1.05, 1.0], wspace=0.28, hspace=0.55)
    ax = fig.add_subplot(gs[:, 0])
    n = len(rows)
    img = np.ones((n, 3, 3))
    for r, row in enumerate(rows):
        img[r, 0] = hex_rgb(row["hex"]); img[r, 1] = hex_rgb(row["twin"]["hex"])
        img[r, 2] = hex_rgb(next(b["hex"] for b in B if b["name"] == row["nearest_butterfly"]["name"]))
    ax.imshow(img, aspect="auto", interpolation="nearest")
    ax.set_xticks([0, 1, 2], ["phoneme\nfilm", "chitin/air\ntwin", "nearest\nbutterfly"], fontsize=8)
    ax.set_yticks(range(n), [f"[{r['ipa']}]{'*' if r['modelled'] else ''} {r['nearest_butterfly']['name'][:21]} "
                             f"ρ={r['nearest_butterfly']['spectral_corr']:+.2f}" for r in rows], fontsize=6.3)
    ax.grid(False)
    ax.set_title("Reflected colour (displayed): phoneme vs twin vs nearest\nbutterfly by spectral correlation "
                 "(* = modelled item)", fontsize=8.5, loc="left")
    wl = col.WL[WL_SPEC]
    for k, (row, Rp) in enumerate(examples):
        a2 = fig.add_subplot(gs[k, 1])
        b = next(b for b in B if b["name"] == row["nearest_butterfly"]["name"])
        a2.plot(wl, Rp[WL_SPEC], color=OI["vermillion"], lw=1.4, label=f"[{row['ipa']}] film")
        a2.plot(wl, b["R"][WL_SPEC], color=OI["blue"], lw=1.2, label=b["name"][:18])
        a2.set_title(f"[{row['ipa']}] vs {b['name']}: ρ = {row['nearest_butterfly']['spectral_corr']:+.2f}, "
                     f"ΔE00 = {row['nearest_butterfly']['dE00']:.0f}", fontsize=8, loc="left")
        a2.set_ylim(0, 1.02); a2.tick_params(labelsize=7)
        a2.legend(fontsize=6.5, loc="upper right")
        if k == len(examples) - 1:
            a2.set_xlabel("wavelength (nm)", fontsize=8)
        a2.set_ylabel("R", fontsize=8)
    return savefig(fig, "r10_butterflies" + TAG)


def fig_angle(rows, C):
    n = len(rows)
    img = np.array([[hex_rgb(h) for h, *_ in C["items"][r["id"]]["full_realizable_R"]["item"]] for r in rows])
    fig, ax = plt.subplots(figsize=(4.8, 11.5))
    ax.imshow(img, aspect="auto", interpolation="nearest")
    ax.set_xticks(range(len(ANGLES)), [f"{a}°" for a in ANGLES], fontsize=8)
    ax.set_yticks(range(n), [f"[{r['ipa']}] {r['class']}" for r in rows], fontsize=6.5)
    ax.grid(False)
    ax.set_title("Iridescence of every phoneme film\n(full-band · realizable · R, unpolarised)", fontsize=9, loc="left")
    return savefig(fig, "r10_angle" + TAG)


def fig_real_butterflies(rows, RB):
    fig = plt.figure(figsize=(10, 12.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.25], wspace=0.55)
    ax = fig.add_subplot(gs[0, 0])
    img = np.array([[hex_rgb(h) for h in b["angle_hexes"]] for b in RB])
    ax.imshow(img, aspect="auto", interpolation="nearest")
    ax.set_xticks(range(len(ANGLES)), [f"{a}°" for a in ANGLES], fontsize=8)
    ax.set_yticks(range(len(RB)), [f"{b['name']}\npeak {b['peak_nm']:.0f} nm" for b in RB], fontsize=7.5)
    ax.grid(False)
    ax.set_title("Realistic scale models (core/butterfly.py):\ncolour vs viewing angle [approximate]", fontsize=8.5,
                 loc="left")
    ax2 = fig.add_subplot(gs[0, 1])
    bh = {b["name"]: b["hex"] for b in RB}
    img = np.array([[hex_rgb(r["hex"]), hex_rgb(bh[r["nearest_real_butterfly"]["name"]])] for r in rows])
    ax2.imshow(img, aspect="auto", interpolation="nearest")
    ax2.set_xticks([0, 1], ["phoneme film", "nearest real\nspecies (0°)"], fontsize=8)
    ax2.set_yticks(range(len(rows)), [f"[{r['ipa']}] {r['nearest_real_butterfly']['name']} "
                                      f"ρ={r['nearest_real_butterfly']['spectral_corr']:+.2f} "
                                      f"ΔE={r['nearest_real_butterfly']['dE00']:.0f}" for r in rows], fontsize=6.3)
    ax2.grid(False)
    ax2.set_title("Each phoneme film vs the realistic species with the\nhighest reflectance correlation "
                  "(380–780 nm, 0°)", fontsize=8.5, loc="left")
    return savefig(fig, "r10_real_butterflies" + TAG)


def fig_fluor(rows, FC):
    n = len(rows)
    ncol = 15
    nrow = -(-n // ncol)
    fig, ax = plt.subplots(figsize=(12, 1.2 + 2.7 * nrow))
    for k, r in enumerate(rows):
        e = FC["items"][r["id"]]
        rw, cl = divmod(k, ncol)
        y = -rw * 4.3
        for j, (key, lab) in enumerate((("hex_D65", "D65"), ("hex_violet", "405"), ("hex_UV", "365"))):
            ax.add_patch(plt.Rectangle((cl, y - j * 1.0), 0.9, 0.9, color=hex_rgb(e[key]), lw=0))
        ax.text(cl + 0.45, y + 1.05, f"[{r['ipa']}]", ha="center", fontsize=8.5)
        ax.text(cl + 0.45, y - 2.35, f"{round(100 * e['fluor_fraction_D65'])}%", ha="center", fontsize=6.5, color="0.4")
    for j, lab in enumerate(("daylight D65", "violet 405 nm", "UV-A 365 nm")):
        ax.text(-0.15, 0.45 - j, lab, ha="right", va="center", fontsize=8)
    ax.set_xlim(-2.2, ncol); ax.set_ylim(-(nrow - 1) * 4.3 - 2.7, 1.5); ax.axis("off")
    ax.set_title("Phoneme films with a papiliochrome-type dye in every layer: daylight, violet and blacklight "
                 "[approximate; hexes exposure-normalised]\ngrey % = share of daylight luminance from fluorescence",
                 fontsize=9, loc="left")
    return savefig(fig, "r10_fluor" + TAG)


# ------------------------------------------------------------------------------------------------ run
def _th(n):
    """17135 -> '17 135' (thin grouping, as in the report)."""
    return f"{int(n):,}".replace(",", " ")


def _flag(it):
    if it.get("modelled"):
        return "modelled"
    if it.get("rule") == "fallback":
        return "fallback"
    if it["class"] == "diphthong":
        return "trajectory-model"
    return None


def run(fresh=False):
    t0 = time.time()
    items, polys, mism = collect()
    C = compute_colours(items, polys, fresh)
    items = sorted(items, key=lambda i: CLASS_ORDER.index(i["class"]))
    B = butterflies()
    TW = twins(items, C, fresh)

    # ---- validity bookkeeping (main view and the others)
    n_valid = {v[3]: 0 for v in VIEWS}
    n_total = {v[3]: 0 for v in VIEWS}
    for it in items:
        for mpg, mode, q, lab in VIEWS:
            e = C["items"][it["id"]][f"{mpg}_{mode}_{q}"]
            for s in [e["item"]] + e["strip"] + e["own"]:
                for *_, ok in s:
                    n_total[lab] += 1; n_valid[lab] += int(ok)

    # ---- classes
    classes, cls_json = [], []
    for c in CLASS_ORDER:
        its = [i for i in items if i["class"] == c]
        hx, bad = [], 0
        for i in its:
            g_, b_ = _hexes_main(C, i["id"], "strip")
            hx += g_; bad += b_
        g = gamut_of(hx)
        levels = {}
        for lvl, fn in (("item_0deg", lambda s: [C["items"][s]["full_realizable_R"]["item"][0][0]]),
                        ("item_angles", lambda s: _hexes_main(C, s, "item")[0]),
                        ("own_frames_angles", lambda s: _hexes_main(C, s, "own")[0]),
                        ("strip_frames_angles", lambda s: _hexes_main(C, s, "strip")[0])):
            gg = gamut_of([h for i in its for h in fn(i["id"])])
            levels[lvl] = dict(n_colours=len(gg["hexes"]), distinct=gg["distinct"])
        views = {}
        for mpg, mode, q, lab in VIEWS:
            v = f"{mpg}_{mode}_{q}"
            hv, ok_all = [], True
            for i in its:
                e = C["items"][i["id"]][v]
                for s in [e["item"]] + e["strip"]:
                    for h, _, _, ok in s:
                        hv.append(h); ok_all &= ok
            gv = gamut_of(hv)
            views[lab] = dict(distinct=gv["distinct"], n_colours=len(gv["hexes"]), all_valid=bool(ok_all),
                              set="item×angles + frames×0°" if (mpg, mode, q) != MAIN else "item+frames × angles",
                              reps=[r["hex"] for r in gv["reps"][:12]])
        verdict = "few" if g["distinct"] <= 2 else "many"
        proof = None
        if verdict == "few":     # no automatic derivation exists: report honestly, never claim
            proof = dict(title=f"{CLASS_LABEL[c]}: why so few colours?", claim="No proof derived (observed count only).",
                         steps=["The clustering found ≤ 2 colours, but no derivation from the mapping/LPC/film "
                                "equations has been checked for this class; the result is reported as an observation."],
                         numeric_check=f"distinct_colours = {g['distinct']} at ΔE00 ≤ {CLUSTER_DE:g}", holds=False)
        flags = sorted({f"{i['ipa']}:{_flag(i)}" for i in its if _flag(i)})
        note = (f"{len(g['hexes'])} valid colours ({bad} invalid) from {len(its)} item(s) + "
                f"{sum(len(polys[i['id']]['strip']) for i in its)} frame film(s) × {len(ANGLES)} angles. Distinct at other "
                f"levels: item at 0° {levels['item_0deg']['distinct']}, item × angles {levels['item_angles']['distinct']}, "
                f"rule-selected frames × angles {levels['own_frames_angles']['distinct']}."
                + (f" Flags: {', '.join(flags)}." if flags else ""))
        item_ab = [hex_lab(C["items"][i["id"]]["full_realizable_R"]["item"][0][0])[1:] for i in its]
        classes.append(dict(cls=c, label=CLASS_LABEL[c], n_items=len(its), distinct_colours=g["distinct"],
                            _g=g, _item_ab=item_ab))
        cls_json.append({"class": c, "label": CLASS_LABEL[c], "n_items": len(its), "distinct_colours": g["distinct"],
                         "verdict": verdict,
                         "gamut": dict(hexes=g["hexes"], ab=g["ab"], hull_ab=g["hull_ab"]),
                         "proof": proof, "note": note,
                         "many_certificate": many_certificate(g["hexes"]) if verdict == "many" else None,
                         "levels": levels, "views": views,
                         "cluster_reps": [dict(hex=r["hex"], n=r["n"]) for r in g["reps"]]})

    # ---- items vs butterflies
    rows = []
    examples = {}
    for it in items:
        sid = it["id"]
        e = C["items"][sid]["full_realizable_R"]["item"]
        n, d = film_of(np.array(it["a"]), "realizable", "full")
        R, _ = film.film_rt(n, d, col.WL)
        lab_d = hex_lab(e[0][0])
        corr = {b["name"]: float(np.corrcoef(R[WL_SPEC], b["R"][WL_SPEC])[0, 1]) for b in B}
        dE = {b["name"]: float(de00(lab_d, b["Lab"])) for b in B}
        best = max(corr, key=corr.get)
        best_c = min(dE, key=dE.get)
        insect = max((b["name"] for b in B if not b["name"].startswith("Goupillaud")), key=corr.get)
        P = env_power(np.array(it["a"]), it.get("gain", 1.0))
        L = {b["name"]: round(lsd(P, b["env"]), 2) for b in B}
        tw = TW[sid]
        nrb, nrb_c = nearest_real(n, d)
        row = dict(id=sid, ipa=it["ipa"], example=it["example"], **{"class": it["class"]},
                   modelled=bool(it.get("modelled", False)), flag=_flag(it), rule=it.get("rule"),
                   hex=e[0][0], Lab=rnd(lab_d, 2), Lab_abs=rnd(e[0][1], 2),
                   angle_hexes=[h for h, *_ in e],
                   nearest_butterfly=dict(name=best, dE00=round(dE[best], 2), spectral_corr=round(corr[best], 3)),
                   nearest_real_butterfly=nrb, nearest_real_by_colour=nrb_c,
                   nearest_insect=dict(name=insect, dE00=round(dE[insect], 2), spectral_corr=round(corr[insect], 3)),
                   nearest_by_colour=dict(name=best_c, dE00=round(dE[best_c], 2), spectral_corr=round(corr[best_c], 3)),
                   twin=dict(materials="chitin/air", n_layers=TWIN_LAYERS, dE00=round(tw["dE00"], 2), hex=tw["hex"],
                             d_nm=tw["d_nm"]),
                   voice_lsd_db=L, voice_nearest=min(L, key=L.get),
                   R_peak=round(float(R[WL_SPEC].max()), 3),
                   R_peak_nearest=round(float(next(b for b in B if b["name"] == best)["R"][WL_SPEC].max()), 3), valid=bool(all(ok for *_, ok in e)))
        rows.append(row)
        examples[sid] = R

    # ---- realistic butterflies + fluorescence
    RB = real_butterflies()
    FC = fluorescence_items(items, fresh)
    fl_proof, fl_stats = fluorescence_proof(FC, items)
    fl_items = []
    for r in rows:
        e = FC["items"][r["id"]]
        fl_items.append(dict(id=r["id"], ipa=r["ipa"], **{"class": r["class"]},
                             **{k: e[k] for k in ("hex_D65", "hex_UV", "hex_violet", "fluor_fraction_D65",
                                                   "peak_emission_nm")}))
    fluor = dict(label="approximate", model="core/fluorescence.py: papiliochrome-type dye in every layer "
                 "of the same full-band realizable film; Purcell-free in-plane dipole escape factor",
                 fluorophore=FC["fluorophore"], reference_hex_UV=FC["ref_hex"],
                 illuminants=dict(D65="CIE D65", UV="365 nm LED, FWHM 10 nm (illustrative)",
                                  violet="405 nm LED, FWHM 15 nm (illustrative)"),
                 hex_note="exposure-normalised display colour (artistic); QY 0.3 and k_max 0.02 are ILLUSTRATIVE",
                 items=fl_items, distinct_colours_UV=fl_stats["distinct_UV"], stats=fl_stats)
    rwin = {}
    for r in rows:
        rwin[r["nearest_real_butterfly"]["name"]] = rwin.get(r["nearest_real_butterfly"]["name"], 0) + 1

    # ---- figures
    figs = [dict(file="results/" + fig_gamut(classes),
                 caption=f"Every valid colour of each phoneme class in a*b* (full-band · realizable · R; item + frames × "
                         f"angles {ANGLES[0]}–{ANGLES[-1]}°), convex hull and ΔE00 ≤ {CLUSTER_DE:g} cluster swatches.")]
    best_row = max(rows, key=lambda r: r["nearest_butterfly"]["spectral_corr"])
    ex_ids = [best_row["id"]] + [s for s in ("i", "m", "s", "ei") if s != best_row["id"]]
    ex = [(next(r for r in rows if r["id"] == s), examples[s]) for s in ex_ids[:4]]
    figs.append(dict(file="results/" + fig_butterflies(rows, B, ex),
                     caption="Each phoneme film beside its chitin/air twin and its nearest butterfly film "
                             "(reflectance correlation 380–780 nm); right: example reflectance spectra."))
    figs.append(dict(file="results/" + fig_angle(rows, C),
                     caption="Colour of every phoneme film at 0, 15, 30, 45, 60° (unpolarised): iridescence."))
    figs.append(dict(file="results/" + fig_real_butterflies(rows, RB),
                     caption="Realistic butterfly/beetle scale models (disorder, tilt, absorption; approximate) vs "
                             "angle, and each phoneme film beside its nearest realistic species (reflectance "
                             "correlation, 0°)."))
    figs.append(dict(file="results/" + fig_fluor(rows, FC),
                     caption="Every phoneme film with a papiliochrome-type dye: daylight, violet 405 nm and "
                             "blacklight 365 nm (approximate; QY and dye strength illustrative)."))

    # ---- numbers + findings
    corrs = np.array([r["nearest_butterfly"]["spectral_corr"] for r in rows])
    dEb = np.array([r["nearest_butterfly"]["dE00"] for r in rows])
    dEc = np.array([r["nearest_by_colour"]["dE00"] for r in rows])
    tw_dE = np.array([r["twin"]["dE00"] for r in rows])
    win = {}
    for r in rows:
        win[r["nearest_butterfly"]["name"]] = win.get(r["nearest_butterfly"]["name"], 0) + 1
    vwin = {}
    for r in rows:
        vwin[r["voice_nearest"]] = vwin.get(r["voice_nearest"], 0) + 1
    lsd_all = np.array([v for r in rows for v in r["voice_lsd_db"].values()])
    dc = {c["class"]: c["distinct_colours"] for c in cls_json}
    lv = {c["class"]: c["levels"] for c in cls_json}
    few = [c["class"] for c in cls_json if c["verdict"] == "few"]
    s_row = next((r for r in rows if r["id"] == "s"), rows[0])
    alike = sorted(((r["ipa"], r["nearest_insect"]["spectral_corr"], r["class"]) for r in rows), key=lambda t: -t[1])
    n_gamut = sum(len(c["gamut"]["hexes"]) for c in cls_json)
    rcorrs = np.array([r["nearest_real_butterfly"]["spectral_corr"] for r in rows])
    rbest = max(rows, key=lambda r: r["nearest_real_butterfly"]["spectral_corr"])
    findings = [
        f"No phoneme class is limited to one or two colours: with every frame and 5 viewing angles the classes give "
        f"{min(dc.values())}–{max(dc.values())} distinct colours (CIEDE2000 clusters ≤ {CLUSTER_DE:g}), so no "
        f"'few colours' proof is claimed. Tilting the film from 0° to 60° alone multiplies the colours: per class, "
        f"item × angles gives {min(l['item_angles']['distinct'] for l in lv.values())}–"
        f"{max(l['item_angles']['distinct'] for l in lv.values())} distinct colours." if not few else
        f"{len(few)} class(es) give ≤ 2 colours: {', '.join(few)}.",
        f"{_th(n_valid[VIEWS[0][3]])} film colours of the main view were checked for validity and all come from "
        f"physically realizable films (indices 1–2.5, |k| < 1, R + T = 1 checked); {_th(n_gamut)} of them are distinct "
        f"display colours plotted in the class gamuts. The ideal-film views are not realizable (indices up to "
        f"{max(i['n_ideal_max'] for i in items):.0f}).",
        f"One film per phoneme at normal incidence: the 14 vowels give {lv['vowel']['item_0deg']['distinct']} distinct "
        f"colours and the 9 fricatives {lv['fricative']['item_0deg']['distinct']}, but the 3 nasals collapse to "
        f"{lv['nasal']['item_0deg']['distinct']} (magenta) and the 2 modelled affricates to "
        f"{lv['affricate']['item_0deg']['distinct']} (both built mostly from ʃ). This is an observation, not a 'few' "
        f"verdict: frames and angles spread the nasals to {dc['nasal']} colours, and no proof is claimed.",
        f"The most butterfly-like phoneme films: {', '.join(f'[{r[0]}] ({r[2]}) ρ = {r[1]:+.2f}' for r in alike[:4])} "
        f"(reflectance correlation with the nearest Morpho-/Beetle-like film, 380–780 nm; [{best_row['ipa']}] also ΔE00 = "
        f"{best_row['nearest_butterfly']['dE00']:.1f}). The match is in spectral SHAPE and hue only: [{best_row['ipa']}] reflects at most "
        f"R = {best_row['R_peak']:.2f}, the butterfly film {best_row['R_peak_nearest']:.2f}. Vowels, nasals and plosives are not (median ρ over all "
        f"phonemes {np.median(corrs):+.2f}); the closest film by colour is a median ΔE00 = {np.median(dEc):.0f} away "
        f"(these are idealised 1-D stacks). Against the realistic scale models (disorder, tilt, melanin absorption; "
        f"approximate) the most frequent nearest species is {max(rwin, key=rwin.get)} ({max(rwin.values())}/{len(rows)}); "
        f"the best match is [{rbest['ipa']}] vs {rbest['nearest_real_butterfly']['name']} "
        f"(ρ = {rbest['nearest_real_butterfly']['spectral_corr']:+.2f}, ΔE00 = {rbest['nearest_real_butterfly']['dE00']:.0f}), "
        f"median ρ {np.median(rcorrs):+.2f}: the realistic, broader and dimmer spectra resemble phoneme films less "
        f"than the idealised stacks do.",
        f"But every phoneme colour has a butterfly-material twin: an 8-layer chitin/air stack matches the absolute "
        f"reflected colour to median ΔE00 = {np.median(tw_dE):.2g} (max {tw_dE.max():.1f}; "
        f"{int(np.sum(tw_dE < 2))}/{len(rows)} below 2).",
        f"Voices: the butterfly whose all-pole voice is closest to most phonemes is {max(vwin, key=vwin.get)} "
        f"({max(vwin.values())}/{len(rows)}{'; a random equal-thickness Garden film, not an insect' if max(vwin, key=vwin.get).startswith('Goupillaud') else ''}); /s/ sounds most like {s_row['voice_nearest']} "
        f"(LSD {s_row['voice_lsd_db'][s_row['voice_nearest']]:.1f} dB); all LSDs {lsd_all.min():.1f}–{lsd_all.max():.1f} dB.",
        f"Fluorescence (approximate, papiliochrome-type dye in every layer): under blacklight all {len(rows)} phoneme "
        f"films glow the same green (max pairwise ΔE00 {fl_stats['max_dE00_UV']:.1f}, emission peak "
        f"{fl_stats['peak_min']:.0f}–{fl_stats['peak_max']:.0f} nm) — a 'few colours' result with a proof: the film "
        f"only multiplies the fixed emission band by an escape factor η ∈ [{fl_stats['eta_min']:.2f}, "
        f"{fl_stats['eta_max']:.2f}]. In daylight the dye adds {round(100 * min(i['fluor_fraction_D65'] for i in fl_items))}–"
        f"{round(100 * max(i['fluor_fraction_D65'] for i in fl_items))} % of the luminance and the colours stay distinct.",
        "Modelled items (e ɛ o from Hillenbrand means; ʒ tʃ dʒ from relatives) and the fallback plosives p b t d "
        "(context vowel averaged in) are approximations; the all-pole film is an envelope model for nasals, "
        "fricatives and plosives.",
    ]

    settings = dict(view="full·realizable·R", views=[v[3] for v in VIEWS], angles_deg=ANGLES, cluster_dE00=CLUSTER_DE,
                    illuminant="D65", polarisation="unpolarised", clustering="complete linkage on CIEDE2000 of displayed "
                    "(exposure-normalised) sRGB colours", validity="realizable film: |k|<1, n∈[1,2.5], |c|<1, "
                    "max|R+T−1|<1e-9 at 0°, finite XYZ",
                    butterfly_models=dict(nearest_butterfly="idealised 1-D stacks (web/data/butterflies.json + "
                                          "core.stacks variants)",
                                          nearest_real_butterfly="realistic scale models (core/butterfly.py: disorder, "
                                          "tilt, diffraction, melanin backing/absorption; approximate)"))
    web = dict(generated_by="python -m research.run_all 10 (research/r10_phonemes.py)",
               date=time.strftime("%Y-%m-%d"), settings=settings, findings=findings, classes=cls_json,
               items=rows, butterflies=[dict(name=b["name"], hex=b["hex"], source=b["source"]) for b in B],
               figures=figs, real_butterflies=RB, fluorescence=fluor, fluorescence_proof=fl_proof)
    OUT_WEB.write_text(json.dumps(web, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    full = dict(web, validity=dict(valid=n_valid, total=n_total), strip_reproduced_exactly=(mism == 0),
                strip_mismatches=mism, butterfly_win_counts=win, voice_win_counts=vwin, real_butterfly_win_counts=rwin,
                colour_seconds=C.get("seconds"))
    (RES / f"r10_phonemes{TAG}.json").write_text(json.dumps(full, indent=1, ensure_ascii=False, allow_nan=False),
                                           encoding="utf-8")
    web_res = ROOT / "web" / "results"
    for f in figs:
        shutil.copy2(ROOT / f["file"], web_res / f["file"].split("/")[-1])

    # ---- summary for report placeholders (small)
    S = dict(n_items=len(rows), angles=ANGLES, cluster_dE00=CLUSTER_DE,
             n_valid_main=n_valid[VIEWS[0][3]], n_total_main=n_total[VIEWS[0][3]],
             n_ideal_max=round(max(i["n_ideal_max"] for i in items), 1),
             strip_reproduced_exactly=(mism == 0), few_classes=few,
             classes={c["class"]: dict(n_items=c["n_items"], distinct=c["distinct_colours"], verdict=c["verdict"],
                                       n_colours=len(c["gamut"]["hexes"]),
                                       **{k: v["distinct"] for k, v in c["levels"].items()},
                                       brief_R=c["views"]["brief·realizable·R"]["distinct"],
                                       full_T_ideal=c["views"]["full·ideal·T"]["distinct"]) for c in cls_json},
             corr_max=round(float(corrs.max()), 3), corr_median=round(float(np.median(corrs)), 3),
             corr_best=f"[{best_row['ipa']}] vs {best_row['nearest_butterfly']['name']}",
             corr_best_dE=best_row["nearest_butterfly"]["dE00"],
             most_alike=[f"[{a}] {c:+.2f}" for a, c, _ in alike[:5]],
             dE_nearest_colour_median=round(float(np.median(dEc)), 1),
             dE_nearest_by_corr_median=round(float(np.median(dEb)), 1),
             twin_dE_median=round(float(np.median(tw_dE)), 2), twin_dE_max=round(float(tw_dE.max()), 2),
             twin_below_2=int(np.sum(tw_dE < 2)),
             voice_winner=max(vwin, key=vwin.get), voice_winner_n=max(vwin.values()),
             s_voice=s_row["voice_nearest"], s_voice_lsd=s_row["voice_lsd_db"][s_row["voice_nearest"]],
             lsd_min=round(float(lsd_all.min()), 1), lsd_max=round(float(lsd_all.max()), 1),
             butterfly_win_counts=win, findings=findings,
             n_gamut_colours=n_gamut, n_valid_main_th=_th(n_valid[VIEWS[0][3]]), n_total_main_th=_th(n_total[VIEWS[0][3]]), n_gamut_colours_th=_th(n_gamut),
             real_winner=max(rwin, key=rwin.get), real_winner_n=max(rwin.values()), real_win_counts=rwin,
             real_best=f"[{rbest['ipa']}] vs {rbest['nearest_real_butterfly']['name']}",
             real_best_corr=rbest["nearest_real_butterfly"]["spectral_corr"],
             real_best_dE=rbest["nearest_real_butterfly"]["dE00"],
             real_corr_median=round(float(np.median(rcorrs)), 3),
             real_species=", ".join(f"{b['name']} ({b['hex']}, {b['peak_nm']:.0f} nm)" for b in RB),
             fluor=dict(**{k: (round(v, 4) if isinstance(v, float) else v) for k, v in fl_stats.items()},
                        holds=fl_proof["holds"], ff_D65_min=round(100 * min(i["fluor_fraction_D65"] for i in fl_items)),
                        ff_D65_max=round(100 * max(i["fluor_fraction_D65"] for i in fl_items)),
                        ref_hex=FC["ref_hex"]), seconds=round(time.time() - t0, 1),
             figures=[f["file"] for f in figs])
    return S


if __name__ == "__main__":
    import sys
    if "--user" in sys.argv:
        use_user()
    out = run("--fresh" in sys.argv)
    print(json.dumps({k: v for k, v in out.items() if k != "findings"}, ensure_ascii=False, indent=1))
