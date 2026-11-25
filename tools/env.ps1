# Source this before running anything: . .\tools\env.ps1
# Keeps every cache/temp file INSIDE the project folder.
$root = Split-Path -Parent $PSScriptRoot
$env:MPLCONFIGDIR   = "$root\.cache\matplotlib"
$env:PIP_CACHE_DIR  = "$root\.cache\pip"
$env:XDG_CACHE_HOME = "$root\.cache\xdg"
$env:PYTHONPYCACHEPREFIX = "$root\.cache\pycache"
$env:TEMP = "$root\.cache\tmp"; $env:TMP = "$root\.cache\tmp"
$env:npm_config_cache = "$root\.cache\npm"
New-Item -ItemType Directory -Force $env:MPLCONFIGDIR,$env:PIP_CACHE_DIR,$env:TEMP | Out-Null
$env:PATH = "$root\.venv\Scripts;$env:PATH"
