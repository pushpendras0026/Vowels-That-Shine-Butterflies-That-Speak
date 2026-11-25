"""Run every research result, write results/summary.json, figures, audio, docs/REPORT.md, copy to web/.

    . .\\tools\\env.ps1; python -m research.run_all            # everything (cached heavy steps reused)
    python -m research.run_all 3 5                              # only some sections (merges into summary)
    python -m research.run_all --fresh                          # ignore caches in results/cache_*.npz
"""
from __future__ import annotations

import importlib
import json
import re
import shutil
import sys
import time

import numpy as np

from research.common import ROOT, RES, AUD, FIGS, AUDIO

SECTIONS = {1: "r1_isomorphism", 2: "r2_palette", 3: "r3_fidelity", 4: "r4_butterflies",
            5: "r5_metamers", 6: "r6_angle", 7: "r7_atlas",
            8: "r8_mapping", 9: "r9_sounds", 10: "r10_phonemes"}
SUMMARY = RES / "summary.json"
TEMPLATE = ROOT / "research" / "report_template.txt"
REPORT = ROOT / "docs" / "REPORT.md"


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    return o


def _lookup(summary, key):
    cur, parts = summary, key.split(".")
    i = 0
    while i < len(parts):
        if isinstance(cur, list):
            cur = cur[int(parts[i])]; i += 1
            continue
        for j in range(len(parts), i, -1):      # keys may themselves contain dots (e.g. "-0.7")
            k = ".".join(parts[i:j])
            if k in cur:
                cur = cur[k]; i = j
                break
        else:
            raise KeyError(key)
    return cur


def _fmt(val, spec):
    if isinstance(val, list):
        return ", ".join(_fmt(v, spec) for v in val)
    if spec:
        return format(val, spec)
    if isinstance(val, float):
        return f"{val:.3g}" if (abs(val) < 1e-3 and val != 0) else f"{val:g}"
    return str(val)


def render_report(summary):
    """Fill {{key.path|fmt}} placeholders of research/report_template.txt from summary.json."""
    if not TEMPLATE.exists():
        print("  (no report template yet)")
        return
    text = TEMPLATE.read_text(encoding="utf-8")

    def sub(mt):
        key, _, spec = mt.group(1).partition("|")
        try:
            return _fmt(_lookup(summary, key.strip()), spec.strip())
        except (KeyError, IndexError, TypeError, ValueError):
            print(f"  warning: report value {key.strip()} not available -> '–'")
            return "–"

    out = re.sub(r"\{\{([^}]+)\}\}", sub, text)
    if "{{" in out:
        raise RuntimeError("unfilled placeholder in report")
    REPORT.write_text(out, encoding="utf-8")
    print(f"  wrote {REPORT.relative_to(ROOT)}")


def copy_to_web():
    web = ROOT / "web" / "results"
    (web / "audio").mkdir(parents=True, exist_ok=True)
    nf = na = 0
    for p in RES.glob("fig_*.png"):
        shutil.copy2(p, web / p.name); nf += 1
    for p in AUD.glob("*.wav"):
        shutil.copy2(p, web / "audio" / p.name); na += 1
    shutil.copy2(SUMMARY, web / "summary.json")
    print(f"  copied {nf} figures, {na} wav, summary.json -> web/results/")


def main(argv):
    fresh = "--fresh" in argv
    want = [int(a) for a in argv if a.isdigit()] or list(SECTIONS)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() and len(want) < len(SECTIONS) else {}
    t_all = time.time()
    timings = {}
    for k in want:
        t0 = time.time()
        mod = importlib.import_module(f"research.{SECTIONS[k]}")
        print(f"[{k}] {SECTIONS[k]} ...", flush=True)
        res = mod.run(fresh=fresh) if "fresh" in mod.run.__code__.co_varnames else mod.run()
        timings[f"r{k}"] = round(time.time() - t0, 1)
        summary[f"r{k}"] = _clean(res)
        print(f"    done in {timings[f'r{k}']} s", flush=True)
    timings["total"] = round(time.time() - t_all, 1)
    (RES / "runtime.json").write_text(json.dumps(dict(timings, fresh=bool(fresh), sections=want)), encoding="utf-8")
    summary["meta"] = dict(generated_by="python -m research.run_all", figures=sorted(p.name for p in RES.glob("fig_*.png")),
                           audio=sorted(p.name for p in AUD.glob("*.wav")),
                           sections_run=want)  # timings -> results/runtime.json (untracked) for reproducible diffs
    SUMMARY.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote results/summary.json; {len(FIGS)} figures and {len(AUDIO)} audio files this run")
    render_report(summary)
    copy_to_web()


if __name__ == "__main__":
    main(sys.argv[1:])
