"""Local web server for the website in web/.

It is Python's http.server (stdlib only) with four small additions:
  * picks the first free port starting at --port (default 8000), binding 127.0.0.1 only;
  * explicit MIME types (.js/.mjs as text/javascript, .json, .wav, .mp4 ...) independent of the registry;
  * HTTP Range requests (so the explainer video can seek) and no-cache headers;
  * refreshes web/results/manifest.json first and opens the browser after the socket is bound
    (skip with --no-browser).

    python tools/serve.py [--port 8000] [--no-browser] [--page index.html]
Equivalent bare command (no port search / range support):
    python -m http.server 8000 --bind 127.0.0.1 --directory web
"""
from __future__ import annotations

import argparse
import http.server
import os
import re
import socket
import sys
import threading
import webbrowser
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
VOICE = ROOT / "data" / "user_voice"          # recordings made on web/record.html
VOICE_ID = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
VOICE_MAX = 30 * 1024 * 1024

EXTRA_TYPES = {
    ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
    ".wav": "audio/wav", ".mp4": "video/mp4", ".webm": "video/webm", ".svg": "image/svg+xml",
    ".png": "image/png", ".css": "text/css", ".html": "text/html", ".md": "text/markdown",
    ".wasm": "application/wasm", ".txt": "text/plain",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **EXTRA_TYPES}

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):  # quieter console: only errors
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            super().log_message(fmt, *args)

    # ---- user-voice recorder API (web/record.html); localhost only, WAV only, fixed folder
    def _json(self, code, obj):
        import json
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/voice":
            VOICE.mkdir(parents=True, exist_ok=True)
            return self._json(200, {"have": sorted(p.stem for p in VOICE.glob("*.wav"))})
        if self.path.split("?")[0] == "/api/voice.zip":
            import io
            import zipfile
            VOICE.mkdir(parents=True, exist_ok=True)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(VOICE.glob("*.wav")):
                    z.write(f, f"user_voice/{f.name}")
            b = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="user_voice.zip"')
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return None
        m = re.match(r"^/api/voice/([a-z0-9_]+)\.wav", self.path)
        if m:
            f = VOICE / f"{m.group(1)}.wav"
            if not (VOICE_ID.match(m.group(1)) and f.is_file()):
                return self._json(404, {"error": "not recorded"})
            b = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return None
        return super().do_GET()

    def do_POST(self):
        m = re.match(r"^/api/voice/([a-z0-9_]+)$", self.path)
        if not m or not VOICE_ID.match(m.group(1)):
            return self._json(404, {"error": "bad path"})
        n = int(self.headers.get("Content-Length") or 0)
        if not 44 < n <= VOICE_MAX:
            return self._json(413, {"error": "size"})
        body = self.rfile.read(n)
        if body[:4] != b"RIFF" or body[8:12] != b"WAVE":
            return self._json(415, {"error": "WAV only"})
        VOICE.mkdir(parents=True, exist_ok=True)
        (VOICE / f"{m.group(1)}.wav").write_bytes(body)
        return self._json(200, {"ok": True, "id": m.group(1), "bytes": n})

    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        size = os.path.getsize(path)
        if not m or (not m.group(1) and not m.group(2)):
            return super().send_head()
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        else:  # suffix range: last N bytes
            start, end = max(0, size - int(m.group(2))), size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._range_left = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_range_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        try:
            while left > 0:
                buf = source.read(min(65536, left))
                if not buf:
                    break
                outputfile.write(buf)
                left -= len(buf)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        finally:
            self._range_left = None


class Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows SO_REUSEADDR would let us bind a port that is already in use
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--tries", type=int, default=30)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--page", default="index.html")
    a = ap.parse_args()
    if os.environ.get("DEMO_NO_BROWSER"):
        a.no_browser = True

    try:  # keep the results/video pages fresh (cheap, stdlib only)
        sys.path.insert(0, str(ROOT))
        from tools.make_results_manifest import main as make_manifest
        make_manifest()
    except Exception as e:  # never block the demo on this
        print(f"(manifest refresh skipped: {e})")

    handler = partial(Handler, directory=str(WEB))
    httpd = None
    for port in range(a.port, a.port + a.tries):
        try:
            httpd = Server(("127.0.0.1", port), handler)
            break
        except OSError:
            print(f"port {port} busy, trying {port + 1} ...")
    if httpd is None:
        print("No free port found.")
        return 1
    try:  # also answer on IPv6 loopback so "localhost" (often ::1 first on Windows) connects instantly
        class Server6(Server):
            address_family = socket.AF_INET6
        httpd6 = Server6(("::1", port), handler)
        threading.Thread(target=httpd6.serve_forever, daemon=True).start()
    except OSError:
        pass
    url = f"http://localhost:{port}/{a.page}"
    print(f"\n  Serving {WEB}\n  Open:  {url}\n  Stop:  Ctrl+C (or close this window)\n", flush=True)
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
