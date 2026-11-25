"""Headless-Edge smoke test of every page: screenshot + console errors.
User-approved (2026-11-17): uses installed Microsoft Edge with a profile INSIDE .cache/edge-profile.
Run:  . .\\tools\\env.ps1; python -m tools.browser_check [page.html ...]
Output: .cache/shots/<page>.png and a summary of console errors/warnings per page.
Options: --budget <ms> (virtual-time budget, default 12000); --realtime (no virtual time and no screenshot: Web Audio
autotests such as "lab.html?autotest" run in real time until 'AUTOTEST PASS/FAIL' is logged or the budget expires)."""
from __future__ import annotations

import functools
import http.server
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SHOTS = ROOT / ".cache" / "shots"
PROFILE = ROOT / ".cache" / "edge-profile"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PAGES = ["index.html", "theory.html", "lab.html", "garden.html", "results.html", "experiments.html", "video.html", "tests.html"]


def free_port(start=8800):
    for p in range(start, start + 100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("no free port")


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "application/javascript",
                      ".mjs": "application/javascript", ".json": "application/json", ".wasm": "application/wasm"}

    def log_message(self, *a):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass  # browser closed a streaming (video) request early


FINAL = re.compile(r"AUTOTEST (PASS|FAIL) ")


def _realtime(cmd, budget_ms):
    """Run Edge headless in REAL time (no virtual-time fast-forward, which would starve Web Audio): read console
    lines from stderr until a final 'AUTOTEST PASS/FAIL' line or the budget expires, then close the browser."""
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, errors="replace")
    lines, done = [], threading.Event()

    def reader():
        for l in p.stderr:
            lines.append(l.rstrip("\n"))
            if "CONSOLE" in l and FINAL.search(l):
                done.set()
        done.set()

    threading.Thread(target=reader, daemon=True).start()
    done.wait(budget_ms / 1000)
    p.terminate()
    try:
        p.wait(15)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(10)
    return lines


def run(pages, budget_ms=12000, realtime=False):
    SHOTS.mkdir(parents=True, exist_ok=True)
    PROFILE.mkdir(parents=True, exist_ok=True)
    port = free_port()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=str(WEB)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    results = {}
    try:
        for page in pages:
            shot = SHOTS / (re.sub(r"[^A-Za-z0-9_-]+", "_", page.replace(".html", "")) + ".png")
            cmd = [EDGE, "--headless=new", f"--user-data-dir={PROFILE}", "--no-first-run", "--disable-crash-reporter",
                   "--disable-breakpad", "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                   "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist",
                   "--autoplay-policy=no-user-gesture-required", "--use-fake-ui-for-media-stream",
                   "--use-fake-device-for-media-stream", "--enable-logging=stderr", "--v=0",
                   "--window-size=1440,1000", f"--virtual-time-budget={budget_ms}", f"--screenshot={shot}",
                   f"http://127.0.0.1:{port}/{page}"]
            if realtime:
                cmd = [c for c in cmd if not c.startswith(("--virtual-time-budget", "--screenshot"))]
                raw = _realtime(cmd, budget_ms)
            else:
                raw = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=180).stderr.splitlines()
            lines = [l for l in raw if "CONSOLE" in l or "Uncaught" in l]
            # Edge logs every console.* call at the same level, so keep ALL console lines and flag likely errors
            msgs = [re.sub(r"^.*?CONSOLE", "CONSOLE", l)[:300] for l in lines]
            errs = [m for m in msgs if re.search(r"error|uncaught|failed|exception|AUTOTEST FAIL", m, re.I)]
            results[page] = dict(shot=None if realtime else shot.exists(), n_console=len(lines), errors=errs, messages=msgs)
    finally:
        srv.shutdown()
    return results


if __name__ == "__main__":
    args = sys.argv[1:]
    budget = 12000
    if "--budget" in args:  # optional: --budget <virtual ms>
        i = args.index("--budget")
        budget = int(args[i + 1])
        del args[i:i + 2]
    realtime = "--realtime" in args  # optional: real-time run (Web Audio autotests); ends on AUTOTEST PASS/FAIL
    args = [a for a in args if a != "--realtime"]
    pages = args or PAGES
    for page, r in run(pages, budget_ms=budget, realtime=realtime).items():
        print(f"{page:14s} screenshot={'n/a (realtime)' if r['shot'] is None else 'ok' if r['shot'] else 'MISSING'} console_lines={r['n_console']} errors={len(r['errors'])}")
        autotest = any("AUTOTEST" in m for m in r["messages"])
        for m in (r["messages"] if autotest else r["messages"][:12]):
            print("    ", m)
