"""Build web/results/manifest.json for the static site (results.html and video.html).

The web server only serves web/, so this script copies everything those pages need into one JSON:
  - figures:   web/results/*.png|*.svg|*.jpg  (captions from docs/REPORT.md image alt text, else filename)
  - audio:     web/results/audio/*.wav        (captions from REPORT.md link text, else filename)
  - summary:   results/summary.json           (embedded verbatim, if present)
  - report:    docs/REPORT.md                 (embedded markdown, if present)
  - narration: video/NARRATION.md             (embedded markdown, if present)
  - video:     web/video/explainer.mp4        (exists / size)

Safe to run any time (stdlib only, idempotent, writes only web/results/manifest.json):
    python tools/make_results_manifest.py
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
RES = WEB / "results"
OUT = RES / "manifest.json"
FIG_EXT = {".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif"}


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _pretty(stem: str) -> str:
    """fig_2_palette_men -> 'Fig. 2 — palette men'; bfly_morpho_x0p9 -> 'bfly morpho x0.9'."""
    s = re.sub(r"(\d)p(\d)", r"\1.\2", stem)
    m = re.match(r"fig_?(\d+)_?(.*)", s)
    if m:
        return f"Fig. {m.group(1)} — {m.group(2).replace('_', ' ')}".rstrip(" —")
    return s.replace("_", " ")


def _report_captions(md: str | None):
    """basename -> (caption, section heading) for images and links in REPORT.md."""
    imgs, links = {}, {}
    if not md:
        return imgs, links
    section = ""
    for line in md.splitlines():
        h = re.match(r"^#{1,4}\s+(.*)", line)
        if h:
            section = h.group(1).strip()
        for alt, src in re.findall(r"!\[([^\]]*)\]\(([^)\s]+)", line):
            imgs.setdefault(Path(src).name, (alt.strip(), section))
        for text, href in re.findall(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)", line):
            links.setdefault(Path(href).name, (text.strip(), section))
    return imgs, links


def build() -> dict:
    report = _read(ROOT / "docs" / "REPORT.md")
    imgs, links = _report_captions(report)

    figures = []
    if RES.is_dir():
        for p in sorted(RES.iterdir()):
            if p.is_file() and p.suffix.lower() in FIG_EXT:
                cap, sec = imgs.get(p.name, ("", ""))
                figures.append({"file": f"results/{p.name}", "name": p.stem,
                                "caption": cap or _pretty(p.stem), "section": sec,
                                "from_report": bool(cap), "bytes": p.stat().st_size})
    audio = []
    adir = RES / "audio"
    if adir.is_dir():
        for p in sorted(adir.glob("*.wav")):
            cap, sec = links.get(p.name, ("", ""))
            audio.append({"file": f"results/audio/{p.name}", "name": p.stem,
                          "caption": cap or _pretty(p.stem), "section": sec, "bytes": p.stat().st_size})

    summary = None
    for cand in (ROOT / "results" / "summary.json", RES / "summary.json"):
        txt = _read(cand)
        if txt:
            try:
                summary = json.loads(txt)
                break
            except json.JSONDecodeError:
                pass

    narration = _read(ROOT / "video" / "NARRATION.md")
    vid = WEB / "video" / "explainer.mp4"
    return {
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "generated_by": "python tools/make_results_manifest.py",
        "figures": figures,
        "audio": audio,
        "summary": summary,
        "report": {"source": "docs/REPORT.md", "markdown": report} if report else None,
        "narration": {"source": "video/NARRATION.md", "markdown": narration} if narration else None,
        "video": {"file": "video/explainer.mp4", "exists": vid.is_file(),
                  "bytes": vid.stat().st_size if vid.is_file() else 0},
    }


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    man = build()
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT)
    print(f"manifest: {len(man['figures'])} figures, {len(man['audio'])} audio, "
          f"summary={'yes' if man['summary'] else 'no'}, report={'yes' if man['report'] else 'no'}, "
          f"narration={'yes' if man['narration'] else 'no'}, video={'yes' if man['video']['exists'] else 'no'} "
          f"-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
