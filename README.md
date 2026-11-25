# Vowels That Shine, Butterflies That Speak

**DA321 course project by Pushpendra Singh.**

When you say a vowel, sound bounces back and forth inside your throat and mouth.
When light hits a butterfly wing, it bounces back and forth between very thin layers inside the wing scale.

This project shows that **both follow the same equation**. So we can turn one into the other:

- **every vowel has a colour**: record a vowel → find the shape of the vocal tract → build a thin film with
  the same shape → compute the colour of that film;
- **every butterfly has a voice**: take a wing film → read off its layers → build a vocal tract with the same
  shape → play the sound it makes.

Everything is simulated on your own computer. No internet is needed after setup.

---

## The idea in one paragraph

Model the vocal tract as N short tubes of equal length (the Kelly–Lochbaum model), and the wing scale as N thin
layers of equal optical thickness (a Goupillaud stack). At each tube joint, part of the sound is reflected:
`r = (A_i − A_{i+1}) / (A_i + A_{i+1})`, where A is the tube area. At each layer boundary, part of the light is
reflected: `r = (n_i − n_{i+1}) / (n_i + n_{i+1})`, where n is the refractive index. These are **the same
formula**. Both systems share one polynomial, and the speech tool LPC (Levinson–Durbin) does exactly the same
job as "layer peeling" in optics.

---

## What is inside

- a tested **Python core** with all the physics (`core/`, tests in `tests/`);
- an **interactive website** that runs the same physics in the browser (`web/`);
- **research figures** and a full **report** (`results/`, `docs/REPORT.md`);
- an **explainer video** (`video/`, also playable on the website).

---

## Setup

You need **Python 3.11 or newer** (tested with 3.13). Node.js 18+ is optional; it is only used for the extra
JavaScript checks.

Open a terminal **inside this folder** and run:

**Windows**

```powershell
python -m venv .venv
.venv\Scripts\activate
python setup_project.py
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
bash setup.sh
```

The setup script does these steps in order and prints an OK / FAILED table at the end:

1. installs the packages from `requirements.txt` into the `.venv` folder;
2. runs the physics tests;
3. builds the data files the website uses;
4. rebuilds the research figures and `docs/REPORT.md`;
5. runs the JavaScript checks (only if Node.js is installed).

Useful options:

| option | what it does |
|---|---|
| `--quick` | skip step 4 (the research step is the slowest) |
| `--fresh` | redo the research from scratch, ignoring saved caches |
| `--skip-install` | skip step 1 if the packages are already installed |
| `--video` | also install the video tools and render the 1080p video |
| `--demo` | open the website when setup finishes |

All caches and temporary files go into `./.cache`. Nothing is written outside this folder, so deleting the
folder removes everything. The `.venv` folder is not part of the repository; the setup creates it.

---

## Open the website

```bash
python tools/serve.py
```

This starts a small local server and opens the site in your browser (Chrome, Edge or Firefox).
Options: `--port 8100` to use another port, `--no-browser` to not open a browser tab.

Do not open the HTML files by double-clicking them. Browsers block modules, data files and the microphone on
`file://` pages, so the site must be opened through the server (`http://localhost:...`).

| page | what you can do |
|---|---|
| **Story** (`index.html`) | the idea in plain words; play the colour of each vowel; hear the butterflies |
| **Theory** (`theory.html`) | move the reflection-coefficient sliders and watch a tube turn into a film |
| **Live Voice Lab** (`lab.html`) | speak into the microphone and see your vocal tract and its colour live |
| **Butterfly Garden** (`garden.html`) | 3-D shiny butterflies; click one to hear its voice; pick a colour to find matching films |
| **Results** (`results.html`) | all figures, key numbers, audio clips and the full report |
| **Experiments** (`experiments.html`) | every phoneme (consonants too) as a colour, compared with real butterflies |
| **Record your voice** (`record.html`) | record every phoneme in your own voice |
| **Video** (`video.html`) | the explainer video and its narration |
| **Tests** (`tests.html`) | checks the browser physics against the Python results |

The Voice Lab and the recorder will ask for microphone permission.

---

## Put it online (Streamlit Community Cloud)

1. Go to [share.streamlit.io](https://share.streamlit.io) and choose **Create app**.
2. Pick this repository, branch `main`, and set **Main file path** to `deploy/streamlit_app.py`.
3. Under **Advanced settings**, choose **Python 3.13**.
4. Click **Deploy**.

`deploy/` has its own small `requirements.txt` (only Streamlit), so the online install is quick.
To try the same thing on your computer: `pip install -r deploy/requirements.txt`, then
`streamlit run deploy/streamlit_app.py`.

---

## Other commands

Run these with the `.venv` activated.

| what | command |
|---|---|
| physics tests | `python -m pytest -q` |
| rebuild the website data | `python -m tools.build_all` |
| run all research sections | `python -m research.run_all` |
| run only some sections (e.g. 3 and 8) | `python -m research.run_all 3 8` |
| refresh the list of results shown on the site | `python tools/make_results_manifest.py` |
| check the browser physics against Python | `node tools/node_test.mjs` |
| check the page logic | `node tools/test_lab_core.mjs`, `node tools/test_garden_core.mjs`, `node tools/test_experiments_core.mjs` |
| render the video (needs `requirements-video.txt`) | `python -m video.render_all --quality h` (`--quality l` for a quick 480p test) |

To run a single script by hand in a new terminal, first run `source tools/env.sh` (Linux / macOS) or
`. .\tools\env.ps1` (Windows PowerShell). It activates the venv and keeps caches inside `.cache`.

**Video on Linux:** if `pip` has to build `pycairo` or `manimpango`, install the system libraries first:
`sudo apt install build-essential pkg-config python3-dev libcairo2-dev libpango1.0-dev ffmpeg`.
No LaTeX is needed.

---

## Folder map

```
core/        the physics in Python: LPC, mapping, tube, film, colour, sound synthesis, butterflies
tests/       pytest tests for the physics
data/        input data: Hillenbrand 1995 vowel measurements, IPA-chart recordings (with attribution)
tools/       build scripts, the local web server, JavaScript checks
research/    research scripts (sections 1 to 10) -> results/ and docs/REPORT.md
results/     figures, audio clips and numbers produced by the research scripts
video/       the explainer video: scenes, equation images, narration
web/         the website (HTML, CSS, JavaScript, data, audio, video)
deploy/      Streamlit app for putting the website online
docs/        REPORT.md (full report), CONTRACT.md (conventions and data formats), PHONEMES.md (phoneme extension)
setup_project.py, setup.sh       one-command setup
requirements.txt                 packages for the project
requirements-video.txt           extra packages for rendering the video
```

---

## Key settings

All conventions (signs, constants, function signatures and data formats) are written down in
[`docs/CONTRACT.md`](docs/CONTRACT.md). The main ones:

- 16 kHz audio, LPC order 16 (16 tube sections = 16 film layers), vocal tract length 17.5 cm;
- the shared "media vector" `m = [m_0, m_1 … m_N, m_{N+1}]`, with `c_i = (m_i − m_{i+1}) / (m_i + m_{i+1})`;
  an ideal film uses `n = m / min(m)`;
- **brief mapping:** every layer has optical thickness `n·d = 428.27 nm`, so `f(ν) = 16000 · frac(ν / 350 THz)`;
- **full-band mapping:** `n·d = 199.86 nm` (Δν = 750 THz). It is just as exact, and it makes vowel colours
  much easier to tell apart. The website uses it by default.

---

## What is exact and what is not

- **Exact** (lossless, no dispersion, one dimension): the reflection coefficients and the shared polynomial;
  tube power transfer equals film transmittance (checked to about 1e-10); LPC equals layer peeling; the
  frequency mapping and the CIE colour maths.
- **Approximate:** the finite glottis (reflection −0.9); "realizable" films (indices squeezed into 1.0–2.5);
  snapping to real materials; the voice of films that are not Goupillaud stacks; the butterfly stack
  parameters; consonants (see `docs/PHONEMES.md`).
- **Artistic:** brightness scaling of the displayed colours, glow effects, butterfly flight and the 3-D scene.

The "Limitations" section of `docs/REPORT.md` lists every known weak point.
