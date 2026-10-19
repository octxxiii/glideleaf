param(
    [Parameter(Mandatory=$true)][string]$AppPath,
    [Parameter(Mandatory=$true)][string]$Publisher,
    [Parameter(Mandatory=$true)][string]$DriverPackageDir,
    [string]$PythonPath
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
if (-not $PythonPath) { $PythonPath = Join-Path $repo ".venv\Scripts\python.exe" }
$signature = Get-AuthenticodeSignature -LiteralPath $AppPath
if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate) {
    throw "Release blocked: application/helper signature is not valid."
}
$name = $signature.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
if ($name -ne $Publisher) { throw "Release blocked: unexpected application publisher. Expected $Publisher; got $name" }
& $PythonPath (Join-Path $repo "scripts\check_native_release.py") --root $DriverPackageDir --report (Join-Path $repo "artifacts\release-driver-check.json")
if ($LASTEXITCODE -ne 0) { throw "Release blocked: driver packages are absent, altered, unsigned or untrusted." }
Write-Host "PASS: application signature, publisher and native driver package trust. Physical-device qualification is still required."
