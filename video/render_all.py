"""Render all scenes in parallel with manim (subprocesses), then assemble with audio.

Usage (after `. .\\tools\\env.ps1`):
    python -m video.render_all --quality l            # fast test, 480p30
    python -m video.render_all --quality h            # final, 1080p30
    python -m video.render_all --quality l --only S05_Morph
Logs: video/logs/<scene>_<q>.log
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VID = Path(__file__).resolve().parent
ROOT = VID.parent
sys.path.insert(0, str(ROOT))


def scene_list():
    src = (VID / "scenes.py").read_text(encoding="utf-8")
    start = src.index("SCENES = [")
    return eval(src[start + len("SCENES = "): src.index("]", start) + 1])  # noqa: S307 (own file)


def render(scene, q):
    log = VID / "logs" / f"{scene}_{q}.log"
    cmd = [sys.executable, "-m", "manim", "render", str(VID / "scenes.py"), scene, f"-q{q}", "--fps", "30",
           "--media_dir", str(VID / "media"), "--progress_bar", "none", "-v", "WARNING"]
    t0 = time.time()
    env = dict(os.environ)
    # never let manim find a LaTeX install (TinyTeX would write caches outside the project)
    env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if "tinytex" not in p.lower())
    with open(log, "w", encoding="utf-8") as fh:
        r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT), env=env)
    return scene, r.returncode, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quality", default="l", choices=["l", "m", "h"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--no-assemble", action="store_true")
    a = ap.parse_args()
    (VID / "logs").mkdir(exist_ok=True)
    scenes = a.only or scene_list()
    fails = []
    with ThreadPoolExecutor(a.jobs) as ex:
        for scene, rc, dt in ex.map(lambda s: render(s, a.quality), scenes):
            print(f"{scene:22s} rc={rc} {dt:6.1f}s", flush=True)
            if rc:
                fails.append(scene)
    if fails:
        print("FAILED:", fails, "(see video/logs)")
        sys.exit(1)
    if not a.no_assemble and not a.only:
        from video import assemble
        assemble.main(a.quality)


if __name__ == "__main__":
    main()
