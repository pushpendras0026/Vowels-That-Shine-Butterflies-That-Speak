"""One-command setup for "Vowels That Shine, Butterflies That Speak" (Linux, macOS or Windows).

    python3 -m venv .venv
    source .venv/bin/activate            # Windows: .venv\\Scripts\\activate
    python setup_project.py              # install + test + build everything

Options:
    --skip-install   do not run pip (packages already installed)
    --quick          skip the research report regeneration (~10 s with caches, ~3 min with --fresh)
    --fresh          rerun research without cached heavy steps
    --video          also install manim and re-render the 1080p video (slow, needs requirements-video.txt)
    --demo           start the website server at the end (same as: python tools/serve.py)

Every cache and temp file goes to ./.cache (nothing is written outside this folder).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"


def env():
    e = dict(os.environ)
    for k, sub in (("MPLCONFIGDIR", "matplotlib"), ("PIP_CACHE_DIR", "pip"), ("XDG_CACHE_HOME", "xdg"),
                   ("PYTHONPYCACHEPREFIX", "pycache"), ("TMPDIR", "tmp"), ("TEMP", "tmp"), ("TMP", "tmp"),
                   ("npm_config_cache", "npm")):
        (CACHE / sub).mkdir(parents=True, exist_ok=True)
        e[k] = str(CACHE / sub)
    e["PYTHONPATH"] = str(ROOT) + os.pathsep + e.get("PYTHONPATH", "")
    e["PYTHONIOENCODING"] = "utf-8"
    e["MPLBACKEND"] = "Agg"
    return e


RESULTS = []


def step(name, cmd, required=True):
    print(f"\n=== {name}\n    $ {' '.join(map(str, cmd))}", flush=True)
    t0 = time.time()
    rc = subprocess.call([str(c) for c in cmd], cwd=ROOT, env=env())
    ok = rc == 0
    RESULTS.append((name, "OK" if ok else ("FAILED" if required else "warning"), time.time() - t0))
    if not ok and required:
        summary()
        sys.exit(f"\nStep failed: {name}. Fix the error above and run setup_project.py again.")
    return ok


def summary():
    print("\n" + "=" * 64)
    for name, status, dt in RESULTS:
        print(f"  {status:8s} {dt:7.1f} s  {name}")
    print("=" * 64)


def main(argv):
    py = sys.executable
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        sys.exit("Please create and activate a virtual environment first:\n"
                 "    python3 -m venv .venv && source .venv/bin/activate\n"
                 "then run:  python setup_project.py")
    if sys.version_info < (3, 11):
        sys.exit(f"Python >= 3.11 needed (tested with 3.13); this is {sys.version.split()[0]}")
    print(f"Python {sys.version.split()[0]} at {py}\nProject: {ROOT}")

    if "--skip-install" not in argv:
        req = "requirements-video.txt" if "--video" in argv else "requirements.txt"
        step("install Python packages", [py, "-m", "pip", "install", "--upgrade", "pip"], required=False)
        step(f"pip install -r {req}", [py, "-m", "pip", "install", "-r", req])

    step("core physics tests (pytest)", [py, "-m", "pytest", "-q", "tests"])
    step("build website data (web/data, web/audio, results/atlas.npz)", [py, "-m", "tools.build_all"])
    if "--quick" not in argv:
        step("research figures, audio and docs/REPORT.md",
             [py, "-m", "research.run_all"] + (["--fresh"] if "--fresh" in argv else []))
    step("results manifest for the website", [py, "tools/make_results_manifest.py"])

    node = shutil.which("node")
    if node:
        for t in ("tools/node_test.mjs", "tools/test_lab_core.mjs", "tools/test_garden_core.mjs"):
            step(f"JS check {t}", [node, t], required=False)
    else:
        RESULTS.append(("JS checks (node not installed; optional)", "skipped", 0.0))

    if "--video" in argv:
        step("render 1080p video (slow)", [py, "-m", "video.render_all", "--quality", "h"], required=False)

    summary()
    print("\nRun the website:   python tools/serve.py          (then open the printed http://localhost URL)\n"
          "Run tests again:   python -m pytest -q\n"
          "Any script:        python -m research.run_all 8   |   python -m tools.build_all   |   ...")
    if "--demo" in argv:
        subprocess.call([py, "tools/serve.py"], cwd=ROOT, env=env())


if __name__ == "__main__":
    main(sys.argv[1:])
