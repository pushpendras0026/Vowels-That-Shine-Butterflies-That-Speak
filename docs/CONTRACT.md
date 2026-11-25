# CONTRACT — conventions, signatures, schemas (authoritative)

Everything (Python, JS, video, report) MUST follow this file. If you change it, update all consumers.

## 1. Units & global constants (`core/mapping.py`)
| name | value | meaning |
|---|---|---|
| `FS` | 16000 Hz | speech sample rate |
| `ORDER` | 16 | LPC order = number of tube sections = number of film layers |
| `C_SOUND` | 350.0 m/s | speed of sound |
| `L_TRACT` | `ORDER*C_SOUND/(2*FS)` = 0.175 m | tube length (section length ℓ = L/N; one *round trip* per section = one sample) |
| `C_LIGHT` | 299 792 458 m/s | |
| `NU_MIN, NU_MAX` | 400e12, 750e12 Hz | visible band used for the mapping |
| `DNU` | 350e12 Hz | one 2π period of the film response |
| `D_OPT_NM` | `C_LIGHT/(2*DNU)*1e9` = 428.2749 nm | optical thickness n·d of EVERY layer (Goupillaud) |
| `R_GLOTTIS` | −0.9 | **illustrative** glottal termination reflection used for vowel→film (finite glottis) |
| `N_MIN, N_MAX` | 1.0, 2.5 | realizable index range |
| `MATERIALS` | air 1.00, MgF2 1.38, SiO2 1.46, chitin 1.56, Al2O3 1.77, ZnS 2.35, TiO2 2.40 | non-dispersive approximations |

Speech: Hz. Optics: frequency ν in Hz (display THz), wavelength λ in nm, thickness nm, angle degrees (in incident medium).

## 2. The shared object: the media vector
`m = [m_0, m_1, …, m_N, m_{N+1}]`, all finite, > 0.
- Tube: `m_0` = glottis-side termination area, `m_1..m_N` = sections **from glottis (1) to lips (N)**, `m_{N+1}` = radiation (outside) equivalent area.
- Film: `m_0` = incident medium, `m_1..m_N` = layers (light enters at layer 1), `m_{N+1}` = substrate.
- Ideal mode mapping: `n_i = m_i / min(m)` (n ∝ A, smallest medium becomes n = 1).

**Reflection coefficients** (one convention, both domains), i = 0..N:
`c_i = (m_i − m_{i+1}) / (m_i + m_{i+1})`  (N+1 coefficients). Pressure-wave convention for the tube; E-field, normal incidence for the film.

**Characteristic polynomial** `D(z)`, coefficients in powers of z⁻¹, `D[0]=1`, degree N, built by the row recursion
```
[F, G] = [1, c_0]
for i = 1..N:  [F, G] = [F + c_i z⁻¹ G,  c_i F + z⁻¹ G]
D = F
```
**Power transfer** (tube glottis→radiation power transmission = film transmittance T):
`P(ω) = Π_i (1 − c_i²) / |D(e^{jω})|²`, with ω = 2π f / FS (tube) and ω = 2δ, δ = 2π·D_OPT·ν/c (film, normal incidence).
Lossless: R = 1 − P.

## 3. LPC convention (`core/lpc.py`)
`a = [1, a_1, …, a_p]`, `A(z) = Σ a_i z^{-i}`, prediction error `e[n] = Σ a_i x[n−i]`, model `H(z) = g / A(z)`.
Levinson step-up: `a^{(m)}_i = a^{(m−1)}_i + k_m a^{(m−1)}_{m−i}`, `a^{(m)}_m = k_m`.
**Closed glottis ↔ LPC**: with `c_0 = −1` (m_0 → 0) the recursion of §2 equals step-up with **`k_m = −c_m`, m = 1..p**.
Hence areas from LPC (glottis→lips, A_1 = 1 by default):
`A_{m+1} = A_m (1 + k_m)/(1 − k_m)`, m = 1..p → returns p+1 values (p sections + radiation area).
**Vowel → finite-glottis media** (`mapping.vowel_media`): prepend `m_0 = A_1 (1 + R_GLOTTIS)/(1 − R_GLOTTIS)`. This is an approximation of 1/|A|² (glottal loss broadens/shifts formants); its effect is quantified in the report.

## 4. Frequency mapping (tube f ↔ film ν)
`f(ν) = FS · frac(ν / DNU)` (exact phase identity ω = 2δ mod 2π). ν ∈ [400, 750) THz covers exactly one period, but with a forced offset: 400 THz ↦ FS/7 ≈ 2286 Hz, 700 THz ↦ 0 Hz. Because |D|² is even in ω, the speech band 0…FS/2 appears twice, mirrored about 525 THz (↦ 8 kHz) and 700 THz (↦ 0 Hz). F1 therefore lands near the violet end (≈ 690–710 THz).
`nu_images(f)` returns all ν in [NU_MIN, NU_MAX) mapping to ±f.

## 4b. Second exact mapping: "full-band" (added so that vowels do not all look violet)
The isomorphism holds for ANY common optical thickness `d_opt` of the layers: the phase is δ = 2π·d_opt·ν/c, so
ω = 2δ ⇔ `f(ν) = FS·frac(ν/Δν)` with **Δν = c/(2·d_opt)** (tested for 4 thicknesses in `test_isomorphism_any_layer_thickness`).
The brief's choice is d_opt = 428.27 nm (Δν = 350 THz). The **full-band** mapping uses
`DNU_FULL = 750 THz`, `D_OPT_FULL_NM = 199.8617 nm` (every layer half-wave at 400 nm). Then f = 0 sits exactly at
750 THz (400 nm) and the visible band 400–750 THz covers |f| = 7467 → 0 Hz **exactly once** (no mirror image):
formants (0.3–3 kHz) land at 400–500 nm, fricative energy (3–7.5 kHz) at 500–750 nm.
Python: `mp.D_OPT_FULL_NM`, `mp.DNU_FULL`, `mp.MAPPINGS`, `mp.dnu_of(d)`, `f_of_nu(nu, dnu)`, `nu_images(f, dnu)`,
`omega_of_nu(nu, d_opt)`, `goupillaud_d(n, d_opt)`, `film.voice_of_film(..., dnu=)`. JS: `D_OPT_FULL_NM`, `DNU_FULL`,
`MAPPINGS{brief,full}{dnu,dOpt}`, `dnuOf`, `fOfNu(nu, dnu)`, `nuImages(f, dnu)`, `omegaOfNu(nu, dOpt)`,
`goupillaudD(n, dOpt)`, `voiceOfFilm(n, d, th, p, nFreq, dnu)`, `vowelColour(a, mode, ill, q, th, dOpt)`. All default to brief.
vowels.json adds `colours_full` (ideal) and `colours_full_real` (realizable), same schema as `colours`.
**Display defaults (site-wide):** mapping = full-band; each colour shown as a pair — *reflected* (R, how a wing is seen)
and *transmitted* (T). Measured on all 1617 Hillenbrand tokens (displayed sRGB, ΔE00 between vowel centroids, median):
brief ideal-T 0.8–1.6, brief realizable-R 1.9–2.2; full ideal-T 3.4–13.7, **full realizable-R ≈ 16**.
Under full-band, realizable-R vowels are warm (front: pink/salmon, back: orange/amber); ideal-T vowels are blue→violet.
The brief mapping stays available everywhere (toggle) and its "violet vowels" finding stays in the report.

## 5. Python API (all numpy; arrays float64)
### core/lpc.py
- `autocorr(x, p) -> r[0..p]`
- `levinson(r, p) -> (a, k, err)`  k length p
- `lpc(x, p=16, preemph=0.97, window="hamming") -> (a, k, gain)`  gain = sqrt(err)
- `step_up(k) -> a`; `step_down(a) -> k` (raises if |k|≥1)
- `reflection_to_areas(k, A1=1.0) -> areas (p+1)`; `areas_to_reflection(areas) -> k (p)`
- `poly_from_formants(F, B, fs=FS) -> a`; `formants_from_poly(a, fs=FS, fmin=90, max_bw=600) -> (F, B)` sorted
- `envelope_db(a, gain=1.0, nfft=1024, fs=FS) -> (f, dB)`
### core/mapping.py
- constants above; `reflection_from_media(m)`; `media_from_reflection(c, m0=1.0)`
- `poly_from_reflection(c) -> D`; `power_transfer(c, omega) -> P`
- `f_of_nu(nu)`, `nu_images(f)`, `omega_of_nu(nu)`
- `vowel_media(a, r_glottis=R_GLOTTIS) -> m (p+2)`
- `film_from_media(m, mode="ideal"|"realizable"|"materials") -> n (p+2)`  realizable: `n = N_MIN·(m/min m)^γ`, γ = min(1, ln(N_MAX/N_MIN)/ln(max m/min m)); materials: realizable then snap each layer (log-distance) to nearest MATERIALS entry (incident & substrate snapped too).
- `goupillaud_d(n_layers) -> d_nm = D_OPT_NM / n_layers`
### core/tube.py
- `tube_power_transfer(m, f_hz, L=L_TRACT, c=C_SOUND)` — independent acoustic ABCD chain (Z_i = ρc/A_i), semi-infinite end tubes.
- `kl_impulse_response(c, n_samples)` — time-domain Kelly–Lochbaum scattering lattice (one sample per section round trip).
- `uniform_tube_resonances(L, c, n=3)`; `tube_volume_velocity_transfer(areas, f_hz, L, c)` (closed glottis, ideal open lips p=0).
### core/film.py
- `film_rt(n, d_nm, wl_nm, theta_deg=0.0, pol="u") -> (R, T)` Abelès characteristic matrices; `n` includes incident [0] and substrate [-1]; `d_nm` length len(n)−2; complex n allowed; pol ∈ {"s","p","u"}.
- `film_rt_nu(n, d_nm, nu_hz, theta_deg=0, pol="u")`
- `voice_of_film(n, d_nm, theta_deg=0.0, p=ORDER, n_freq=2048) -> (a, gain)`: sample T over exactly one period ν∈[NU_MIN,NU_MIN+DNU), map to f via §4 (uniform grid in ω), treat T as power spectrum → autocorrelation (IFFT) → Levinson. Exact for Goupillaud stacks with N ≤ p; best all-pole fit otherwise.
### core/colour.py
- grid `WL = 360..830 nm step 0.5` (CIE 1931 2° CMFs linearly interpolated from 1 nm).
- `ILLUMINANTS = {"D65","A","F11","LED"}` (LED = CIE LED-B3).
- `spectrum_to_xyz(S, illuminant="D65") -> XYZ` normalised so a perfect transmitter/reflector has Y = 100.
- `xyz_to_lab(XYZ, illuminant)`, `xyz_to_srgb(XYZ) -> rgb in [0,1]` (clip, gamma), `delta_e00(lab1, lab2)`
- `film_colour(n, d_nm, theta_deg=0, illuminant="D65", quantity="T") -> dict(XYZ, Lab, rgb, hex)`
- `display_rgb(XYZ)` = sRGB after scaling Y to 50 if Y>0 (**artistic exposure normalisation, labelled**).
### core/synth.py
- `rosenberg(f0, fs=FS, dur=1.0, oq=0.6, sq=2.0, jitter=0.0) -> u` and `glottal_source(...)` = derivative of Rosenberg flow (includes lip radiation).
- `synth_allpole(a, source, gain=1.0) -> y`; `film_voice(n, d_nm, f0=140, dur=1.2, theta=0) -> y` (peak-normalised 0.9)
- `sing(a_list, durations, f0=140, domain="k")` interpolating in reflection-coefficient domain (always stable); `domain="lar"` interpolates LAR = 2·atanh(k).
- Consonants (added 2026-11-23): `excitation(cls, voiced, f0=120, dur=None, fs=FS, seed=0) -> source` for cls ∈ {vowel, nasal, lateral, approximant, diphthong (glottal), fricative (white noise; voiced: glottal + flow-modulated noise), plosive (closure [voice bar if voiced] 80 ms → noise burst 12 ms, τ 3 ms → aspiration 40 ms if voiceless → voiced onset), affricate (closure + burst → frication, mixed if voiced)}; unknown cls raises ValueError. `speak(a, cls, voiced, f0=120, dur=None, fs=FS, gain=1.0, seed=0) -> y` = excitation → 1/A(z), peak 0.9, 5 ms fades. `noise_source(dur, fs, seed)`. Deterministic per seed.
- `write_wav(path, y, fs=FS)` 16-bit.
### core/stacks.py
- `morpho_like(...)`, `beetle_like(...)`, `random_goupillaud(rng, N, mode)` — parametric, labelled approximate/illustrative.
### core/inverse.py
- `design_stacks(target_lab, n_layers=ORDER, n_solutions=8, mode="realizable", illuminant="D65", seed=0) -> list[dict(n, d_nm, Lab, dE, a, F)]` (Goupillaud stacks; random restarts + L-BFGS-B; diverse voices).
- `exact_films_for_polynomial(a, K_frac, flips)` (optional, spectral factorisation + layer peeling).

## 6. JS port (`web/js/physics.js`, ES module, no deps)
Exports mirroring §5 in camelCase: `autocorr, levinson, lpc, stepUp, stepDown, reflectionToAreas, areasToReflection, formantsFromPoly, polyFromFormants, reflectionFromMedia, polyFromReflection, powerTransfer, fOfNu, vowelMedia, filmFromMedia, goupillaudD, filmRT, voiceOfFilm, spectrumToXYZ, xyzToLab, xyzToSRGB, displayRGB, deltaE00, filmColour, rosenberg, glottalSource, synthAllpole`.
Data loaded once via `await loadPhysicsData(base="data/")` (reads `cie.json`).

**Calling convention (must match `test_vectors.json`):** positional args in the same order as Python
(case `args` is a positional list). Python tuple returns become named objects in JS:
`levinson → {a,k,err}`, `lpc → {a,k,gain}`, `formantsFromPoly → {F,B}`, `filmRT → {R,T}`,
`voiceOfFilm → {a,gain}`, `filmColour → {XYZ,Lab,rgb,hex}`. Arrays are plain JS arrays or Float64Array.
Exact details that matter:
- `lpc(x,p,preemph)`: pre-emphasis keeps x[0] (`y[0]=x[0]; y[i]=x[i]-pe*x[i-1]`); numpy symmetric Hamming
  `w[i]=0.54-0.46cos(2πi/(N-1))`; `r[0] *= 1+1e-9`; gain = sqrt(max(err,0)).
- `levinson(r,p)`: `acc = r[m] + Σ_{i=1}^{m-1} a_i r_{m-i}`, `k_m = -acc/err`, `err *= (1-k²)`.
- `formantsFromPoly(a,fs)`: polynomial roots (Durand–Kerner/Aberth, then Newton polish) of
  `a0 z^p + a1 z^{p-1} + … + ap`; keep Im>1e-9; F = angle·fs/2π, B = −ln|r|·fs/π; filter
  F>90, F<fs/2−50, B<600; sort by F.
- `polyFromFormants(F,B,fs)`: product of `[1, −2r cosθ, r²]`, r = e^{−πB/fs}, θ = 2πF/fs.
- `filmRT(n,d,wl,theta,pol)`: Abelès/Macleod, complex arithmetic; cosθ_j = sqrt(1−(n0 sinθ0/n_j)²) (principal
  complex sqrt); η = n cos (s) or n / cos (p); multiply M_1…M_N onto [1; η_s] from the substrate side;
  T = 4 Re(η0) Re(ηs)/|η0B+C|²; pol "u" = mean of s and p (at θ=0 just s).
- `voiceOfFilm(n,d,theta,p,nFreq)`: f_j = j·FS/nFreq, ν_j = NU_MIN + (((f_j/FS − frac(NU_MIN/DNU)) mod 1))·DNU,
  λ = c/ν·1e9 nm, T_j = filmRT(...).T; r_k = (1/nFreq) Σ_j T_j cos(2π jk/nFreq) for k=0..p (= Re IFFT);
  then levinson(r,p) → a, gain = sqrt(err).
- `spectrumToXYZ(S,ill)`: k = 100/Σ(E·ȳ); XYZ = k·Σ S·E·(x̄,ȳ,z̄) on the cie.json grid (0.5 nm).
- `xyzToLab(XYZ,ill)`: white = spectrumToXYZ(ones, ill); f(t) = cbrt(t) if t>(6/29)³ else t/(3(6/29)²)+4/29.
- `xyzToSRGB`: matrix in cie.json `srgb_matrix` applied to XYZ/100, clip [0,1], sRGB gamma.
  `displayRGB`: scale XYZ so Y=50, matrix, divide by max if >1, clip, gamma (black if Y≤1e-12).
- `glottalSource(f0,fs,dur,oq,sq)`: Rosenberg as in core/synth.py with jitter=0 (period length round(fs/f0)),
  then first difference with prepend 0.

## 7. Data files & JSON schemas (`web/data/`, generated by `python -m tools.build_all`)
- `cie.json`: `{wl:[...nm], xbar,ybar,zbar:[...], illuminants:{D65:[...],A,F11,LED}, materials:{name:n}, constants:{FS,ORDER,DNU,NU_MIN,NU_MAX,D_OPT_NM,R_GLOTTIS,N_MIN,N_MAX}}`
- `test_vectors.json`: `{version, cases:[{name, fn, args:[positional...], expect:..., tol}]}` — fn is a §6
  export name; compare max |abs error| (or max relative error for values with |x|>1) ≤ tol; strings exact.
- `vowels.json`: `{source, items:[{vowel, ipa, example, group:"men"|"women"|"children", F0,F1,F2,F3, a, areas, m, n_ideal, n_real, colours:{D65:{T:hex,R:hex,Lab:[..]},...}}]}`
- `atlas_sample.json`: `{n, total, mode, items:[{arm, n:[...], rgb:hex(T), rgbR:hex(R), Lab, LabR, F1, F2}]}`
  (3000 of 20k; arm 0 = log-uniform n∈[1,2.5], arm 1 = bimodal low/high; F1/F2 null if <2 formants).
  Full atlas: `results/atlas.npz` (arm, n, labT, labR, rgbT, rgbR, F12).
- vowels.json items also carry `gain, n_materials, lpc_formants, colours_real, audio`; colours entries carry
  `{T, R, Lab (of T), LabR, Y_T}`.

## 7b. Measured facts (Phase 1) — everyone should know these
- Canonical mapping puts 0–2.3 kHz at 650–750 THz ⇒ **all vowels are violet/lavender**. Pairwise ΔE00 at equal
  luminance (median): men 4.3, women 5.7, children 7.7 (ideal); realizable 3.6/3.8/6.5. Some pairs ≈0.1.
  A π-shifted mapping (c_i → (−1)^i c_i, exact, f=0 at 525 THz) was tested and separates vowels WORSE
  (1.4/2.9/3.7) — not adopted. Ideal-mode vowel films transmit little (Y≈0.1–0.4) ⇒ display uses the labelled
  exposure normalisation.
- Atlas (full 20k): 34.3% (log-uniform) / ~74% (bimodal) of random realizable stacks have ≥2 formants.
- `butterflies.json`: `{items:[{name, label:"approximate|illustrative", source, n, d_nm, lut:{angles:[0..80], rgb:[hex...]}, a, F}]}`
Audio: `web/audio/*.wav` (16 kHz). Figures: `results/fig_*.png` (copied to `web/results/`).

## 7c. Real IPA recordings → colours (`web/data/sounds.json`, added 2026-11-19)
Sources: Wikimedia Commons IPA-chart recordings, fetched by `python -m tools.fetch_ipa` into `data/ipa/raw/<id>.ogg`
(sha1-verified; only CC/PD licences kept) with `data/ipa/ATTRIBUTION.json|.md` (title, URL, author, licence).
Built by `python -m tools.build_sounds` (NOT part of build_all; never crashes — bad/silent files go to `skipped`).
Ids are lowercase ASCII, unique ignoring case (Windows). Audio: `web/audio/ipa/<id>.wav` (16 kHz mono, resample_poly, peak 0.9).
Analysis: 512-sample Hamming frames, hop 256, `lpc.lpc(frame, 16, 0.97)`; the TARGET sound's frames are selected by a
per-class rule (stored verbatim in `rules`); their k are averaged as LAR = 2·atanh(k) (|k| ≤ 0.995) → k → `a = step_up(k)`
→ `vowel_media(a)` → `film_from_media(mode)` → Goupillaud stack with d_opt = `D_OPT_FULL_NM` (full) or `D_OPT_NM` (brief)
→ `film_rt` on `col.WL` → D65 XYZ → hex = `display_rgb` (exposure-normalised), Lab = `xyz_to_lab` (true luminance).
```
{source, generated_by, analysis:{fs, frame, hop, order, preemph, window, average, illuminant, strip, d_opt_nm:{full,brief}},
 rules:{vowel, nasal, lateral, approximant, fricative, plosive, affricate, diphthong, fallback: text},
 items:[{id, ipa, name, example, kind:"vowel"|"consonant", class:"vowel"|"plosive"|"nasal"|"fricative"|"lateral"|"approximant"|"affricate",
         voiced, audio:"audio/ipa/<id>.wav", audio_synth:"audio/ipa/<id>_synth.wav", source_rate, duration_s, frames_total, frames_used, rule (class or "fallback"),
         segment_note, a:[17], k:[16], gain, lpc_formants:[≤4 Hz], n_ideal_max,
         colours:{full|brief:{ideal|realizable:{T|R:{hex, Lab:[L,a,b] (D65, true luminance), Y}}}},
         strip:[≤60 hex: one per frame ≤ 40 dB below the loudest, time order, full-band realizable R],
         attribution:{title, page, url, author, license, license_url}}],
 skipped:[{id, reason}]}
```
**Additions 2026-11-23 (PHONEMES track):**
- `analysis` gains `trajectory` and `audio_synth` (text). Class `"affricate"` (tʃ = `ch`, dʒ = `jh`, recordings; rule
  in `rules.affricate`: burst frame + following fricated frames).
- Every item has `audio_synth` = the film's OWN voice: `synth.speak(a, class, voiced, f0=120, seed=crc32(id))`
  (the item's LPC polynomial re-spoken with class excitation, §5). Approximate (envelope model), not a recording.
- Diphthong items (eɪ `ei`, aɪ `ai`, ɔɪ `oi`, aʊ `au`, oʊ `ou`): `kind:"diphthong", class:"diphthong", voiced:true,
  recorded:false, from:<start vowel id>, to:<end vowel id>` (ei: e→ɪ, ai: a→ɪ, oi: ɔ→ɪ, au: a→ʊ, ou: o→ʊ; offglides
  on lax ɪ/ʊ), `trajectory:[30 hex]` = LAR-domain linear interpolation start→end, full-band realizable R (same
  convention as `strip`; `strip` = `trajectory`), `endpoints:{start:{id,ipa,hex}, mid:{hex}, end:{id,ipa,hex}}`;
  `a, k, colours, lpc_formants, n_ideal_max` are those of the midpoint t = 0.5; `gain` = geometric mean of endpoints;
  `audio` = `audio_synth` = `audio/ipa/<id>_synth.wav` (`synth.sing([a_start, a_end], [0.25, 0.25], domain="lar")`);
  no `source_rate, frames_total, frames_used`; `attribution:{derived_from:[start attribution, end attribution]}`.
  Missing endpoint vowel → diphthong goes to `skipped`.
- Modelled items (recording unavailable — Wikimedia 429 on 2026-11-23): `modelled:true, rule:"modelled"`,
  `audio` = `audio_synth` (no recording; no `source_rate, duration_s, frames_*`). e/ɛ/o: `source:"hillenbrand-model"`
  (a, gain from `vowels.json` men /ei eh oa/). ʒ, tʃ, dʒ: `source:"relatives-model", modelled_from:[ids]` —
  ʒ ← ʃ polynomial + voiced excitation; tʃ ← LAR mix 0.25·t + 0.75·ʃ; dʒ ← 0.25·d + 0.75·ʃ (voiced excitation);
  `strip` = relatives' strips; `attribution:{derived_from:…}`. A later successful fetch replaces them automatically.
JSON is written with `allow_nan=False`. Research: `research/r9_sounds.py` → `results/fig_r9_sounds.png`, `results/r9_sounds.json`
(ΔE00 on displayed sRGB, as §4b). Honest limits: all-pole LPC is an envelope model for nasals (zeros) and
fricatives/plosives (source inside the tract); one speaker per sound, often in syllable context.

## 9. Website shell (all pages)
Pages in `web/`: index.html (Story), theory.html, lab.html, garden.html, results.html, experiments.html (phoneme experiments, 2026-11-23), video.html, tests.html.
experiments.html also renders the optional r10 fields `real_butterflies`, `items[].nearest_real_butterfly`
(core/butterfly.py realistic scales), `fluorescence` (D65 / UV-A 365 / violet 405 tiles, core/fluorescence.py) and
`fluorescence_proof` (docs/PHONEMES.md, optional fields); absent fields hide their sections; badged approx/illustrative.
Each page: `<link rel="stylesheet" href="css/site.css">`, `<nav id="site-nav"></nav>`, `<script type="module" src="js/nav.js"></script>`;
use the CSS tokens/classes in site.css (`.page .panel .btn .badge.exact/.approx/.art`). Label every visual as exact/approx/artistic with those badges.
Three.js import map (paths relative to web/): `{"imports":{"three":"./vendor/three.module.js","three/addons/":"./vendor/addons/"}}`.
Page-specific JS in `web/js/<page>.js`; physics only from `web/js/physics.js`. No CDN, no network. Served by `python -m http.server` from web/ (localhost ⇒ mic allowed).

## 8. Exact vs artistic
Exact physics: everything in §2–§5 at stated idealisations (lossless, non-dispersive, normal incidence unless angle given, unpolarised average). Approximations: finite glottis R_GLOTTIS, realizable compression, material snapping, voice_of_film for non-Goupillaud stacks, butterfly parameters. Artistic: exposure normalisation for display, flapping/flight animation, neon glow, room scene.
