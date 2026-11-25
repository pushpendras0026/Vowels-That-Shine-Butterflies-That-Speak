"""Streamlit entry point: serves the whole interactive website (web/) through Streamlit.

Deploy on Streamlit Community Cloud with:
    Main file path : deploy/streamlit_app.py   (uses deploy/requirements.txt: streamlit only)
    Python version : 3.13 (Advanced settings)
Run locally with:
    streamlit run deploy/streamlit_app.py

How it works: Streamlit >= 1.67 lets `streamlit run` host an `st.App` with extra routes.
The website folder is mounted unchanged at /site/, so every page, ES module, JSON file,
audio clip and the video work exactly as with tools/serve.py. The Streamlit page itself
is a small launcher that embeds the site and links to it full-screen.
"""
from __future__ import annotations

import io
import json
import mimetypes
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import streamlit as st
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
WEB = ROOT.parent / "web"   # this file lives in deploy/, the site in ../web

# Explicit MIME types: browsers refuse ES modules / JSON served with the wrong type
# (the OS registry on some machines maps .js to text/plain).
for ext, kind in {
    ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
    ".wav": "audio/wav", ".mp4": "video/mp4", ".webm": "video/webm", ".svg": "image/svg+xml",
    ".css": "text/css", ".html": "text/html", ".md": "text/markdown", ".wasm": "application/wasm",
}.items():
    mimetypes.add_type(kind, ext)

# ---- voice recorder API for web/record.html (same API as tools/serve.py, under /site/api/).
# Recordings live on the server's disk: they survive page reloads, but Streamlit Cloud wipes
# them when the app restarts or sleeps, so use "Download all" to keep them.
VOICE_IDS = {p["id"] for p in json.loads((WEB / "data" / "record_script.json").read_text("utf-8"))["prompts"]}
VOICE_MAX = 5 * 1024 * 1024   # a 7 s mono 16-bit clip at 96 kHz is ~1.3 MB


def _voice_dir() -> Path:
    for d in (ROOT.parent / "data" / "user_voice", Path(tempfile.gettempdir()) / "user_voice"):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_bytes(b"")
            probe.unlink()
            return d
        except OSError:
            continue
    raise RuntimeError("no writable folder for recordings")


VOICE = _voice_dir()


async def voice_list(request: Request) -> Response:
    return JSONResponse({"have": sorted(p.stem for p in VOICE.glob("*.wav") if p.stem in VOICE_IDS)},
                        headers={"Cache-Control": "no-store"})


async def voice_zip(request: Request) -> Response:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(VOICE.glob("*.wav")):
            if f.stem in VOICE_IDS:
                z.write(f, f"user_voice/{f.name}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="user_voice.zip"',
                             "Cache-Control": "no-store"})


async def voice_item(request: Request) -> Response:
    name = request.path_params["name"]
    if request.method == "GET":
        stem = name[:-4] if name.endswith(".wav") else ""
        f = VOICE / f"{stem}.wav"
        if stem not in VOICE_IDS or not f.is_file():
            return JSONResponse({"error": "not recorded"}, status_code=404)
        return Response(f.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "no-store"})
    if name not in VOICE_IDS:
        return JSONResponse({"error": "bad path"}, status_code=404)
    body = await request.body()
    if not 44 < len(body) <= VOICE_MAX:
        return JSONResponse({"error": "size"}, status_code=413)
    if body[:4] != b"RIFF" or body[8:12] != b"WAVE":
        return JSONResponse({"error": "WAV only"}, status_code=415)
    (VOICE / f"{name}.wav").write_bytes(body)
    return JSONResponse({"ok": True, "id": name, "bytes": len(body)})


app = st.App(
    Path(__file__).resolve(),   # absolute: works whatever folder `streamlit run` is started from
    routes=[
        Route("/site/api/voice", voice_list, methods=["GET"]),
        Route("/site/api/voice.zip", voice_zip, methods=["GET"]),
        Route("/site/api/voice/{name}", voice_item, methods=["GET", "POST"]),
        Mount("/site", app=StaticFiles(directory=str(WEB), html=True), name="site"),
    ],
)

def site_url(page: str) -> str:
    """Absolute URL of a page of the mounted site.

    On Streamlit Community Cloud, https://<name>.streamlit.app/ is Cloud's own shell page;
    the app's server (and so the /site/ route) is reached through the /~/+/ prefix.
    Without that prefix the iframe loads the Cloud shell and spins forever.
    """
    base = st.context.url or ""
    parts = urlsplit(base)
    if not parts.scheme or not parts.netloc:
        return f"/site/{page}"
    path = parts.path
    if parts.netloc.endswith(".streamlit.app") and "/~/+" not in path:
        path = "/~/+/"
    if not path.endswith("/"):
        path = path.rsplit("/", 1)[0] + "/" if "/" in path else "/"
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")) + f"site/{page}"


PAGES = {
    "Home": "index.html",
    "Theory": "theory.html",
    "Voice Lab": "lab.html",
    "Garden": "garden.html",
    "Experiments": "experiments.html",
    "Record voice": "record.html",
    "Results": "results.html",
    "Video": "video.html",
    "Tests": "tests.html",
}

if __name__ == "__main__":  # the Streamlit page (not executed when the ASGI app is imported)
    st.set_page_config(page_title="Vowels That Shine", page_icon="🦋", layout="wide")
    st.title("Vowels That Shine, Butterflies That Speak")
    st.caption("DA321 course project · Pushpendra Singh")

    left, right = st.columns([3, 1])
    with left:
        name = st.radio("Page", list(PAGES), horizontal=True, label_visibility="collapsed")
    url = site_url(PAGES[name])
    with right:
        st.link_button("Open full screen ↗", url, width="stretch")

    st.iframe(url, height=900)
    st.caption("Tip: the Voice Lab needs microphone access. Use **Open full screen** if the embedded view blocks it.")
