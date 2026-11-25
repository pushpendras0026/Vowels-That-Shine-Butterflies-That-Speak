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

import mimetypes
from pathlib import Path
from urllib.parse import urljoin

import streamlit as st
from starlette.routing import Mount
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

app = st.App(
    Path(__file__).resolve(),   # absolute: works whatever folder `streamlit run` is started from
    routes=[Mount("/site", app=StaticFiles(directory=str(WEB), html=True), name="site")],
)

PAGES = {
    "Home": "index.html",
    "Theory": "theory.html",
    "Voice Lab": "lab.html",
    "Garden": "garden.html",
    "Experiments": "experiments.html",
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
    # Absolute URL built from the app's own address (e.g. https://<name>.streamlit.app),
    # so it also works if the host puts the app under a path prefix.
    base = (st.context.url or "").rstrip("/") + "/"
    url = urljoin(base, f"site/{PAGES[name]}") if base != "/" else f"/site/{PAGES[name]}"
    with right:
        st.link_button("Open full screen ↗", url, width="stretch")

    st.iframe(url, height=900)
    st.caption("Tip: the Voice Lab needs microphone access. Use **Open full screen** if the embedded view blocks it.")
