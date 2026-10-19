# Open the app-owned adapter setup; no external executable download.
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Push-Location $repo
try {
    & (Join-Path $repo '.venv\Scripts\python.exe') -m glideleaf --setup
    if ($LASTEXITCODE -ne 0) { throw 'Glideleaf adapter setup failed.' }
} finally { Pop-Location }
