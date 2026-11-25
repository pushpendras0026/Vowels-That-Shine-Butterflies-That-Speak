# Explainer voice-over script: "Vowels That Shine, Butterflies That Speak"

Video: `video/final/explainer_1080p.mp4` (= `video/final/explainer_original_1080p.mp4`), 1920×1080, 30 fps, **4:05.7** (245.7 s). The website copy `web/video/explainer.mp4` is this video + the phonemes segment S12 at the end (**5:35.7**, 335.7 s; see the last section).
The timestamps below are taken from the rendered timeline (`video/final/timeline_1080p30.json`; to print it,
run `python -m video.assemble --timeline h`).
The mixed audio track already contains:
- a quiet synthetic pad bed at about −32 dBFS,
- every **[CLIP]** below, all real audio synthesised with `core.synth`.

Speak only in the gaps around the clips. The budget is about 2.3–2.8 words/s.

Legend for on-screen honesty tags: **EXACT** (green), **APPROXIMATE** (amber), **ARTISTIC LICENSE** (pink).

---

## S01 · Hook (0:00.0 – 0:16.6)
| time | voice-over / sound |
|---|---|
| 0:00.0 – 0:03.2 | "Listen to this butterfly." |
| 0:03.4 – 0:04.6 | **[CLIP]** Morpho-like film voice, `web/audio/bfly_morpho.wav` |
| 0:05.4 – 0:06.6 | **[CLIP]** same voice again |
| 0:07.0 – 0:16.6 | "That sound is the wing's colour filter, played as a voice. Vowels that shine, butterflies that speak: one equation for tubes of air and for stacks of thin films." |

On screen: ARTISTIC LICENSE tag for the wing flapping. The wing colour at each tilt angle is the computed thin-film reflectance (D65).

## S02 · Light (0:16.6 – 0:39.1)
| time | voice-over |
|---|---|
| 0:16.6 – 0:24.0 | "What colour is a wing? Daylight brings a spectrum, E of lambda. The wing's thin-film stack reflects a fraction R of each wavelength." |
| 0:24.0 – 0:30.0 | "What reaches your eye is the product: C equals E times R." |
| 0:30.0 – 0:39.1 | "Your eye squeezes it into three numbers. Weight it with the CIE colour-matching functions and add up: X, Y, Z. Here, a bright cyan-blue." |

Tags: APPROXIMATE (Morpho-like stack parameters are illustrative); ARTISTIC (swatch brightness normalised).

## S03 · Sound: source and filter (0:39.1 – 1:00.0)
| time | voice-over / sound |
|---|---|
| 0:39.1 – 0:43.0 | "Now sound. Your vocal folds make a buzz:" |
| 0:43.2 – 0:44.1 | **[CLIP]** raw glottal source, `video/audio/glottal_buzz.wav` |
| 0:44.3 – 0:53.0 | "a ladder of harmonics. The vocal tract, a tube of sixteen sections, filters it, and its resonances (the formants) shape the vowel." |
| 0:53.2 – 0:53.9 | **[CLIP]** /ɑ/ "hod", men, `web/audio/vowel_men_ah.wav` |
| 0:54.5 – 0:55.2 | **[CLIP]** same vowel again |
| 0:55.5 – 1:00.0 | "Source times filter. That is 'ah'." |

## S04 · One equation (1:00.0 – 1:24.3)
| time | voice-over |
|---|---|
| 1:00.0 – 1:06.5 | "Here is the bridge. When a sound wave meets a change of tube area, part of it bounces back: A-i minus A-i-plus-one, over their sum." |
| 1:06.5 – 1:12.5 | "When light meets a change of refractive index, at normal incidence: n-i minus n-i-plus-one, over their sum." |
| 1:12.5 – 1:17.0 | "The same rule, with the same sign convention: r equals a minus b over a plus b." |
| 1:17.0 – 1:24.3 | "One more match. Each tube section takes exactly one sample of round-trip time, so each film layer gets the same optical thickness: 428.27 nanometres." |

Tag: EXACT (lossless plane waves, normal incidence).

## S05 · Morph: tube → film (1:24.3 – 1:47.2)
| time | voice-over |
|---|---|
| 1:24.3 – 1:31.0 | "So take the vocal tract of 'ah', turn it on its side, and let every section become a layer," |
| 1:31.0 – 1:37.5 | "with refractive index proportional to its area. In ideal mode that means indices from 1 to 148, and no material does that." |
| 1:37.5 – 1:47.2 | "A realizable version compresses them into 1 to 2.5. Each layer's physical thickness is 428 nanometres divided by n. And this film has a colour." |

Tag: APPROXIMATE (γ compression; finite glottis r = −0.9).

## S06 · Levinson = layer peeling (1:47.2 – 2:16.4)
| time | voice-over |
|---|---|
| 1:47.2 – 1:55.0 | "Speech scientists recover the tract with linear prediction, the Levinson–Durbin recursion. Run it backwards, the step-down," |
| 1:55.0 – 2:04.0 | "and every step peels off one reflection coefficient, starting at the lips. That is layer peeling, the way optical engineers take a thin-film stack apart, one interface at a time." |
| 2:04.0 – 2:10.0 | "Run it forwards and the areas grow back from glottis to lips. The round-trip error is ten to the minus eight." |
| 2:10.0 – 2:16.4 | "Linear prediction of speech is layer peeling of a film." |

## S07 · Frequency mapping (2:16.4 – 2:44.6)
| time | voice-over |
|---|---|
| 2:16.4 – 2:24.0 | "Which colours stand for which pitches? One tube section's phase at sound frequency f equals one layer's phase at light frequency nu." |
| 2:24.0 – 2:31.0 | "The 428-nanometre layers make 400 to 750 terahertz exactly one period. 400 terahertz maps to 2286 hertz, 525 to 8 kilohertz, 700 to zero." |
| 2:31.0 – 2:37.5 | "Folded, the speech band appears twice, mirrored about 700 terahertz. So the formants of 'ah' land between 670 and 730 terahertz: violet." |
| 2:37.5 – 2:44.6 | "And the film's transmittance and the tube's power transfer are the same curve, to nine decimal places." |

Tag: EXACT (isomorphism; max difference 1.8 × 10⁻⁹).

## S08 · The colours of vowels (2:44.6 – 3:08.2)
| time | voice-over / sound |
|---|---|
| 2:44.6 – 2:48.5 | "So here are the vowels of American English, as films." |
| 2:48.7 – 2:53.1 | **[CLIPS]** "heed", "had", "hod", "who'd" (men): `web/audio/vowel_men_{iy,ae,ah,uw}.wav` |
| 2:53.5 – 3:01.0 | "The honest result: they are all violet to lavender. Formants live at the violet end, so the vowels differ only slightly." |
| 3:01.0 – 3:08.2 | "Median colour differences are 4 to 8 units, where 1 or 2 is just noticeable. Realizable films are paler still." |

Tags: ARTISTIC (ideal films transmit only Y ≈ 0.1–0.4 %, brightness normalised); APPROXIMATE (realizable compression).

## S09 · The voices of butterflies (3:08.2 – 3:29.5)
| time | voice-over / sound |
|---|---|
| 3:08.2 – 3:12.0 | "Now run it the other way: a wing becomes a voice." |
| 3:12.1 – 3:15.0 | **[CLIP ×2]** Morpho-like voice, `web/audio/bfly_morpho.wav` |
| 3:15.2 – 3:19.2 | "The Morpho-like stack hums, breathy and bright." |
| 3:19.3 – 3:22.2 | **[CLIP ×2]** beetle-like voice, `web/audio/bfly_beetle.wav` |
| 3:22.4 – 3:29.5 | "The beetle-like stack buzzes flatly. Their layers aren't equal in optical thickness, so these voices are best fits, and neither says a clear vowel." |

Tags: APPROXIMATE (illustrative stack parameters; all-pole fit voices); ARTISTIC (flapping). The colour-vs-angle strips are computed (TMM, D65).

## S10 · Metamers: same colour, different voices (3:29.5 – 3:51.3)
| time | voice-over / sound |
|---|---|
| 3:29.5 – 3:36.8 | "Four films, picked from twenty thousand random stacks. To your eye, the same gold: every pair within 2 colour units." |
| 3:37.0 – 3:44.6 | **[CLIPS]** the four film voices, `video/audio/metamer_{0..3}.wav` |
| 3:45.0 – 3:51.3 | "Four different voices. Colour keeps three numbers from a spectrum; a voice keeps sixteen." |

Data: `results/atlas.npz`, reflected colour under D65, maximum pairwise ΔE00 = 1.93. The voice envelopes differ by at least 6.8 dB RMS.

## S11 · Outro (3:51.4 – 4:05.7)
| time | voice-over / sound |
|---|---|
| 3:51.3 – 3:52.5 | "Finally, a film that sings." |
| 3:52.6 – 3:54.6 | **[CLIP]** "ah – ee – oo", women's vowels sung with `core.synth.sing`, `video/audio/outro_sing.wav` |
| 3:55.0 – 4:05.7 | "Exact, approximate, artistic: it's all on screen. A throat and a butterfly wing share one equation: r equals a minus b over a plus b." |

---

# Extra segment S12 · "Every phoneme: an experiment" (4:05.7 – 5:35.7)

Added 2026-11-23. Rendered with matplotlib + ffmpeg by `python -m video.phonemes_segment --quality h` → `video/final/phonemes_segment_1080p.mp4` (90.0 s), appended to the explainer with `python -m video.phonemes_segment --concat` (original kept as `video/final/explainer_original_1080p.mp4`). No voice-over: the captions below are on screen. Times are in the combined `web/video/explainer.mp4`; segment-local times are in `video/final/timeline_phonemes_1080p.json`. All numbers come from `web/data/phonemes_experiment.json` and `web/data/sounds.json`.

Audio: the same quiet pad bed + a ≈0.4 s excerpt (loudest window) of each IPA recording (`web/audio/ipa/<id>.wav`; the film's own voice `<id>_synth.wav` where no recording exists) as its tile lights up; /s/ recording and its film voice; `ai_synth.wav` ×4 during the diphthong glide.


## S12.1 · Title (4:05.7 – 4:10.7)
| time | on-screen caption |
|---|---|
| 4:06.0 – 4:10.7 | "So far, vowels. Here we push the same film recipe to all 43 phonemes in 8 classes, and report what came out." |

## S12.2 · The IPA chart, class by class (4:10.7 – 4:34.7)
| time | on-screen caption |
|---|---|
| 4:10.9 – 4:22.3 | "The IPA chart, class by class. Each tile lights up in its film's colour while its recording plays (32 real recordings)." |
| 4:22.3 – 4:32.3 | "Recording → averaged LPC polynomial → realizable film (n 1–2.5) → reflected colour under daylight (D65)." |
| 4:32.3 – 4:34.7 | "* modelled (no clean recording: you hear the film's own voice)   † fallback plosive (context vowel averaged in)   ~ trajectory model" |

## S12.3 · One fricative: /s/ (4:34.7 – 4:52.2)
| time | on-screen caption |
|---|---|
| 4:34.9 – 4:38.9 | "One fricative: /s/ as in 'sip'. Its LPC envelope is the hiss shaped by the mouth: most energy high up." |
| 4:38.9 – 4:42.7 | "Layer peeling turns the 16 reflection coefficients into 16 film layers: bars of refractive index, each of equal optical thickness." |
| 4:42.7 – 4:45.7 | "That film reflects daylight as #ab63ff. Played back, the film has a voice too." |
| 4:45.7 – 4:48.7 | "Its nearest butterfly: the Morpho-like ×0.9 film, spectral shape correlation ρ = 0.87, ΔE00 = 10.4." |
| 4:48.7 – 4:52.2 | "Caveat: same shape, not the same strength: peak R 0.18 for /s/ vs 0.91. (Best match overall: [z], ρ = 0.98.)" |

## S12.4 · Gamut per class (4:52.2 – 5:05.7)
| time | on-screen caption |
|---|---|
| 4:52.4 – 5:01.2 | "Every valid colour of each class in the a*b* plane: all frames of every recording, viewed at 0, 15, 30, 45, 60°." |
| 5:01.2 – 5:05.7 | "No class is limited to one or two colours: 39–85 distinct colours per class, and in every class 3 colours lie more than ΔE00 = 10 apart. So we show them all." |

## S12.5 · Iridescence (5:05.7 – 5:14.7)
| time | on-screen caption |
|---|---|
| 5:05.9 – 5:10.2 | "Iridescence: tilt each film from 0° to 60° and its reflected colour drifts, like a wing turning in the light." |
| 5:10.2 – 5:14.7 | "Tilting alone multiplies the colours: one film per phoneme × 5 angles already gives 3–23 distinct colours per class." |

## S12.6 · Diphthong /aɪ/ (5:14.7 – 5:22.2)
| time | on-screen caption |
|---|---|
| 5:14.9 – 5:18.6 | "A diphthong is a moving film. /aɪ/ as in 'price' glides from /a/ to /ɪ/, and its colour glides with it." |
| 5:18.6 – 5:22.2 | "30 interpolation steps between the two vowel polynomials (log-area ratios); the sound is the film's own synthesised voice." |

## S12.7 · Caveats (5:22.2 – 5:30.7)
| time | on-screen caption |
|---|---|
| 5:22.4 – 5:30.7 | "What to keep in mind: these are experiments, labelled as such." |

## S12.8 · End card (5:30.7 – 5:35.7)
| time | on-screen caption |
|---|---|
| 5:31.0 – 5:35.7 | "Every phoneme has a film, and every film has colours. Explore them all on the Experiments page." |

Tags on screen: APPROXIMATE (experimental track; /s/ vs butterfly reflectance; diphthong trajectory model; modelled phonemes, envelope model, fallback plosives), ARTISTIC LICENSE (exposure-normalised swatches), EXACT PHYSICS (all plotted colours from realizable films).
