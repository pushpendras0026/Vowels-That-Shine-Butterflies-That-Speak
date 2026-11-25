# Render the explainer video end-to-end (run from the project root):
#   .\video\render.ps1            # final 1080p30 -> video\final\explainer_1080p.mp4 (+ copy web\video\explainer.mp4)
#   .\video\render.ps1 -Quality l # fast 480p30 test -> video\final\explainer_480p30.mp4
# Steps: data (core/ physics) -> equations (mathtext SVG, no LaTeX) -> manim scenes in parallel -> PyAV assemble + audio mix.
# Logs: video\logs\*.log   Media/cache: video\media (gitignored)
param([ValidateSet("l", "m", "h")][string]$Quality = "h", [int]$Jobs = 6)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
. .\tools\env.ps1
# never let manim find TinyTeX (it would write caches outside the project folder)
$env:PATH = ($env:PATH -split ";" | Where-Object { $_ -notmatch "(?i)tinytex" }) -join ";"
New-Item -ItemType Directory -Force video\logs | Out-Null
python -m video.prep_data *> video\logs\prep.log
if ($LASTEXITCODE -ne 0) { throw "prep_data failed (video\logs\prep.log)" }
python -m video.make_eqs *> video\logs\eqs.log
if ($LASTEXITCODE -ne 0) { throw "make_eqs failed (video\logs\eqs.log)" }
python -m video.render_all --quality $Quality --jobs $Jobs
if ($LASTEXITCODE -ne 0) { throw "render failed (see video\logs)" }
