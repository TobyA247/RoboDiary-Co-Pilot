$ErrorActionPreference="Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
try { & "$here\.venv\Scripts\Activate.ps1" } catch { }
if (-not $env:ROTATE_180)      { $env:ROTATE_180="0" }
if (-not $env:CAPTION_TIMEOUT) { $env:CAPTION_TIMEOUT="120" }
if (-not $env:DIARY_TIMEOUT)   { $env:DIARY_TIMEOUT="600" }
Write-Host "Launching Robot Diary at http://127.0.0.1:5055 (offline)..." -ForegroundColor Cyan
python "$here\diary_portal.py" --host 127.0.0.1 --port 5055
