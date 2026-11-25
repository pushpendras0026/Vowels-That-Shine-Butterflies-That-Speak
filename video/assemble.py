"""Concatenate the rendered scene mp4s and mix the real audio clips at their logged cue times (PyAV only).

    python -m video.assemble h        -> video/final/explainer_1080p.mp4 (+ copy to web/video/explainer.mp4)
    python -m video.assemble l        -> video/final/explainer_480p30.mp4 (test)

Audio = quiet synthetic pad bed (~ -32 dBFS, leaves room for a voice-over) + every cue logged by the scenes
(web/audio/*.wav vowels and butterfly voices, video/audio/*.wav metamer voices etc., all made by core.synth).
Scene offsets come from the decoded frame counts of each scene mp4, so cues cannot drift.
Also writes video/final/timeline_<res>.json (scene start times + global cue times) used for NARRATION.md.
"""
from __future__ import annotations

import json
import shutil
import sys
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from scipy.signal import resample_poly

VID = Path(__file__).resolve().parent
ROOT = VID.parent
FPS = 30
SR = 48000
RES = {"l": "480p30", "m": "720p30", "h": "1080p30"}


def scenes():
    from video.render_all import scene_list
    return scene_list()


def read_wav(rel):
    with wave.open(str(ROOT / rel)) as w:
        fs = w.getframerate()
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    if fs != SR:
        from math import gcd
        g = gcd(SR, fs)
        y = resample_poly(y, SR // g, fs // g)
    return y


def pad_bed(n):
    """Soft A-minor-add9 pad, slow swells; deterministic."""
    t = np.arange(n) / SR
    freqs = [110.0, 164.81, 220.0, 261.63, 329.63, 493.88]
    amps = [1.0, 0.7, 0.6, 0.45, 0.35, 0.18]
    y = np.zeros(n)
    for i, (f, a) in enumerate(zip(freqs, amps)):
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.03 + 0.011 * i) * t + i)
        y += a * lfo * np.sin(2 * np.pi * f * t + 0.7 * i) * (1 + 0.002 * np.sin(2 * np.pi * 0.2 * t))
    y /= np.sqrt(np.mean(y ** 2))
    y *= 10 ** (-32 / 20)
    fade = int(3 * SR)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return y * env


def main(q="h"):
    res = RES[q]
    vdir = VID / "media" / "videos" / "scenes" / res
    cdir = VID / "media" / "cues" / res
    fdir = VID / "final"
    fdir.mkdir(exist_ok=True)
    out_path = fdir / ("explainer_1080p.mp4" if q == "h" else f"explainer_{res}.mp4")
    names = scenes()
    # ---- pass 1: frame counts -> offsets
    info, t = [], 0.0
    for s in names:
        with av.open(str(vdir / f"{s}.mp4")) as c:
            st = c.streams.video[0]
            nf = sum(1 for _ in c.decode(st))
            w, h = st.codec_context.width, st.codec_context.height
        cues = json.loads((cdir / f"{s}.json").read_text(encoding="utf-8"))["cues"]
        info.append(dict(scene=s, start=t, frames=nf, duration=nf / FPS,
                         cues=[dict(c, t_global=t + c["t"]) for c in cues]))
        t += nf / FPS
    total = t
    # ---- audio mix
    n = int(np.ceil(total * SR)) + SR
    mix = pad_bed(n)
    for sc in info:
        for c in sc["cues"]:
            y = read_wav(c["wav"]) * c["gain"]
            i0 = int(round(c["t_global"] * SR))
            mix[i0:i0 + len(y)] += y[: max(0, n - i0)]
    peak = np.max(np.abs(mix))
    if peak > 0.97:
        mix *= 0.97 / peak
    mix = mix.astype(np.float32)
    # ---- encode (interleaved)
    out = av.open(str(out_path), "w", options={"movflags": "faststart"})
    vs = out.add_stream("libx264", rate=FPS)
    vs.width, vs.height, vs.pix_fmt = w, h, "yuv420p"
    vs.options = {"crf": "18", "preset": "medium"}
    aus = out.add_stream("aac", rate=SR, layout="mono")
    aus.bit_rate = 160_000
    fsz = 1024
    apos = 0

    def push_audio(until):
        nonlocal apos
        while apos + fsz <= until:
            fr = av.AudioFrame.from_ndarray(mix[apos:apos + fsz].reshape(1, -1), format="fltp", layout="mono")
            fr.sample_rate = SR
            fr.pts = apos
            fr.time_base = Fraction(1, SR)
            for p in aus.encode(fr):
                out.mux(p)
            apos += fsz

    k = 0
    for sc in info:
        with av.open(str(vdir / f"{sc['scene']}.mp4")) as c:
            for fr in c.decode(c.streams.video[0]):
                if fr.format.name != "yuv420p" or fr.width != w:
                    fr = fr.reformat(width=w, height=h, format="yuv420p")
                fr.pts = k
                fr.time_base = Fraction(1, FPS)
                for p in vs.encode(fr):
                    out.mux(p)
                k += 1
                push_audio(int((k / FPS) * SR))
    for p in vs.encode():
        out.mux(p)
    push_audio(int(total * SR))
    for p in aus.encode():
        out.mux(p)
    out.close()
    (fdir / f"timeline_{res}.json").write_text(json.dumps(dict(total=total, scenes=info), indent=1), encoding="utf-8")
    print(f"wrote {out_path.relative_to(ROOT)}  {total:.1f}s  {w}x{h}  peak={peak:.2f}")
    for sc in info:
        print(f"  {sc['start']:7.2f}s  {sc['scene']:22s} {sc['duration']:6.2f}s  cues={len(sc['cues'])}")
    if q == "h":
        dst = ROOT / "web" / "video"
        dst.mkdir(exist_ok=True)
        shutil.copyfile(out_path, dst / "explainer.mp4")
        print("copied to web/video/explainer.mp4")


def timeline(q="l"):
    """Print scene start times and global cue times from the logged cue files (no video decoding)."""
    t = 0.0
    for s in scenes():
        d = json.loads((VID / "media" / "cues" / RES[q] / f"{s}.json").read_text(encoding="utf-8"))
        cs = ", ".join(f"{t + c['t']:.1f}s {c['wav'].split('/')[-1]}" for c in d["cues"])
        print(f"{t:6.1f}s {s:20s} {d['duration']:5.1f}s  {cs}")
        t += d["duration"]
    print(f"total {t:.1f}s")


def verify(path):
    """Print duration / resolution / fps / streams and audio RMS during cues vs. bed only."""
    with av.open(str(path)) as c:
        vs, aus = c.streams.video, c.streams.audio
        print(f"{path}: duration {c.duration / 1e6:.2f}s, video streams {len(vs)}, audio streams {len(aus)}")
        v = vs[0]
        print(f"  video {v.codec_context.name} {v.codec_context.width}x{v.codec_context.height} @ {float(v.average_rate):.2f} fps,"
              f" frames {v.frames}")
        a = aus[0]
        print(f"  audio {a.codec_context.name} {a.codec_context.sample_rate} Hz, {a.codec_context.layout.name}")
        y = np.concatenate([f.to_ndarray().mean(axis=0) for f in c.decode(a)])
    sr = a.codec_context.sample_rate
    tl = json.loads((Path(path).parent / "timeline_1080p30.json").read_text(encoding="utf-8")) \
        if (Path(path).parent / "timeline_1080p30.json").exists() else None
    rms = lambda t0, t1: float(np.sqrt(np.mean(y[int(t0 * sr):int(t1 * sr)] ** 2)))
    print(f"  audio length {len(y) / sr:.2f}s; RMS bed-only 60-70s: {rms(60, 70):.4f}")
    if tl:
        for sc in tl["scenes"]:
            for cue in sc["cues"][:1]:
                t = cue["t_global"]
                print(f"  RMS during cue {cue['wav'].split('/')[-1]:22s} at {t:6.1f}s: {rms(t + 0.1, t + 0.6):.4f}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--timeline":
        timeline(sys.argv[2] if len(sys.argv) > 2 else "l")
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "h")
