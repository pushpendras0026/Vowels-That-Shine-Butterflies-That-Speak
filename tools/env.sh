# Source before running scripts by hand on Linux/macOS:   source tools/env.sh
# Keeps every cache/temp file inside the project folder (same as tools/env.ps1 on Windows).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MPLCONFIGDIR="$ROOT/.cache/matplotlib" PIP_CACHE_DIR="$ROOT/.cache/pip" XDG_CACHE_HOME="$ROOT/.cache/xdg"
export PYTHONPYCACHEPREFIX="$ROOT/.cache/pycache" TMPDIR="$ROOT/.cache/tmp" npm_config_cache="$ROOT/.cache/npm"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" MPLBACKEND=Agg
mkdir -p "$MPLCONFIGDIR" "$PIP_CACHE_DIR" "$TMPDIR"
[ -f "$ROOT/.venv/bin/activate" ] && [ -z "${VIRTUAL_ENV:-}" ] && . "$ROOT/.venv/bin/activate"
