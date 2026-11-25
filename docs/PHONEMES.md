# Every phoneme: the experimental extension

The main project gives every **vowel** a colour. This extension does the same for the other sounds of
English: consonants, affricates and diphthongs. It also compares each sound with **butterfly wing films**,
not just with spectrograms.

## What it does

1. Takes 38 IPA-chart recordings (14 vowels and 24 consonants), plus the affricates tʃ dʒ and the
   diphthongs eɪ aɪ ɔɪ aʊ oʊ.
2. Turns each sound into a film stack (sound → LPC → film → colour) and compares that film with real
   butterfly and beetle films.
3. Reports honestly what came out. Different groups of sounds can give different colours, and that is a
   result in itself.
4. Colour rule: if a group of sounds can only make one or two colours, we give a **mathematical proof** of
   why, plus a numeric check. Otherwise we show **every valid colour** the group can make, across
   recordings, frames, mappings and viewing angles.

The results are on the website's **Experiments** page, in section 10 of `docs/REPORT.md`, and in the extra
segment of the explainer video.

## Where the pieces live

| file | job |
|---|---|
| `tools/fetch_ipa.py` | downloads the IPA-chart recordings into `data/ipa/raw/` (with attribution) |
| `tools/build_sounds.py` | picks frames, runs LPC, builds films and colours → `web/data/sounds.json`, `web/audio/ipa/*.wav` |
| `core/synth.py` | makes sound from a film: voiced, noise, mixed, burst and affricate sources |
| `research/r10_phonemes.py` | section 10 of the report → `results/r10_phonemes.json`, `results/fig_r10_*.png`, `web/data/phonemes_experiment.json` |
| `core/butterfly.py` | realistic butterfly and beetle scale models |
| `core/fluorescence.py` | how each film would glow under UV light |
| `web/experiments.html`, `web/js/experiments.js` | the Experiments page |

## Honest limits of the physics

- LPC is an all-pole model, so it only captures the spectral envelope. Nasals have zeros (a side branch),
  and fricatives and plosives have their source *inside* the tract (turbulence or a burst). So the **tube**
  picture is only approximate for these sounds.
- The **film** is still exact: any LPC polynomial with |k| < 1 gives a real, passive film stack. So the
  colour is always well defined.
- Some sounds could not be downloaded and are modelled instead (`modelled: true`): e ɛ o (from Hillenbrand
  vowel data), ʒ (the ʃ polynomial plus voicing), and tʃ dʒ (a mix of the t/d burst and ʃ).
- p b t d use a fallback rule (the neighbouring vowel is averaged in), because the burst detector misses them.
- Every visual on the site carries an **exact**, **approx** or **artistic** badge (see `docs/CONTRACT.md` §8–§9).

## Data format: `web/data/phonemes_experiment.json`

Written by `research/r10_phonemes.py`, read by the Experiments page and the video. JSON with no NaN or inf.

```
{generated_by, date,
 settings:{view:"full·realizable·R", views:[...], angles_deg:[0,15,30,45,60], cluster_dE00:<number>, illuminant:"D65"},
 findings:[string],                       // 4-8 headline sentences with numbers
 classes:[{class, label, n_items, distinct_colours:int, verdict:"few"|"many",
           gamut:{hexes:[hex...], ab:[[a,b]...], hull_ab:[[a,b]...]},   // all valid colours of the class
           proof:null | {title, claim, steps:[string], numeric_check:string, holds:bool},   // required when verdict=="few"
           note}],
 items:[{id, ipa, example, class, modelled:bool, hex, Lab:[L,a,b], angle_hexes:[hex x5],
         nearest_butterfly:{name, dE00, spectral_corr},       // compares films (reflectance + colour)
         twin:{materials:string, n_layers:int, dE00, hex},   // a buildable stack with the same colour
         voice_lsd_db:{<butterfly name>: dB}}],               // log-spectral distance to each butterfly's voice
 butterflies:[{name, hex, source}],
 figures:[{file:"results/fig_r10_*.png", caption}]}
```

Proof text uses plain Unicode maths (the site does not load KaTeX).

**Optional fields** (the page hides a section when its field is missing):

```
settings.butterfly_models:{nearest_butterfly:"idealised 1-D stacks …", nearest_real_butterfly:"realistic scale models …"}
items[].nearest_real_butterfly:{name, dE00, spectral_corr}   // core.butterfly.compare_film_to_species, 0°, best correlation
items[].nearest_real_by_colour:{name, dE00, spectral_corr}   // same, smallest ΔE00
real_butterflies:[{name, hex, angle_hexes:[hex x5], peak_nm, R_peak, kind, published, source}]
fluorescence:{label, model, fluorophore:{…}, reference_hex_UV, illuminants, hex_note,
              items:[{id, ipa, class, hex_D65, hex_UV, hex_violet, fluor_fraction_D65, peak_emission_nm}],
              distinct_colours_UV:int, stats:{…}}
fluorescence_proof:{title, claim, steps:[string], numeric_check, holds:bool}
figures += results/fig_r10_real_butterflies{TAG}.png, results/fig_r10_fluor{TAG}.png
```

`{TAG}` is empty for the IPA-chart voices and `_user` for your own recorded voice.
Cache: `results/cache_r10_fluor{TAG}.json`.
