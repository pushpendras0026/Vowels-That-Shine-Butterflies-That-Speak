"""Dev helper: save a contact sheet of frames from a rendered scene for visual QA.
    python -m video.snap S01_Hook [480p30] [n_frames]   -> video/logs/snaps/<scene>.png
"""
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image

VID = Path(__file__).resolve().parent


def main(scene, res="480p30", n=6):
    p = VID / "media" / "videos" / "scenes" / res / f"{scene}.mp4"
    with av.open(str(p)) as c:
        frames = [f.to_ndarray(format="rgb24") for f in c.decode(c.streams.video[0])]
    idx = np.linspace(len(frames) * 0.12, len(frames) - 8, n).astype(int)
    imgs = [frames[i] for i in idx]
    h, w, _ = imgs[0].shape
    cols = 2
    rows = (n + 1) // cols
    sheet = np.zeros((rows * h, cols * w, 3), np.uint8)
    for k, im in enumerate(imgs):
        r, cc = divmod(k, cols)
        sheet[r * h:(r + 1) * h, cc * w:(cc + 1) * w] = im
    out = VID / "logs" / "snaps"
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet).save(out / f"{scene}.png")
    print(f"{scene}: {len(frames)} frames ({len(frames) / 30:.1f}s), sampled {list(idx)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1] if len(a) > 1 else "480p30", int(a[2]) if len(a) > 2 else 6)
