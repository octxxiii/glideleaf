# Build a development portable app, or a signed application release.
param(
    [switch]$Release,
    [string]$DriverPackageDir,
    [string]$CertificateThumbprint,
    [string]$Publisher,
    [string]$SignToolPath,
    [string]$TimestampUrl = 'http://timestamp.digicert.com',
    [switch]$SkipInstallDependencies,
    [switch]$FetchFirmware
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Create .venv and install requirements-dev.txt first." }
Push-Location $repo
$previousPackages = $env:GLIDELEAF_DRIVER_PACKAGES
try {
    if ($Release) {
        if (-not $CertificateThumbprint -or -not $Publisher) {
            throw "Release needs CertificateThumbprint and Publisher for application signing."
        }
        if ($CertificateThumbprint -notmatch '^[0-9a-fA-F]{40}$') { throw "Invalid certificate thumbprint." }
        $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object Thumbprint -eq $CertificateThumbprint
        if (-not $cert -or -not $cert.HasPrivateKey -or $cert.NotAfter -le (Get-Date)) {
            throw "No usable code-signing certificate/private key in CurrentUser\My."
        }
        if ($cert.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false) -ne $Publisher) {
            throw "The signing certificate does not match Publisher."
        }
        if (-not $SignToolPath) {
            $tool = Get-Command signtool.exe -ErrorAction SilentlyContinue
            if ($tool) { $SignToolPath = $tool.Source }
        }
        if (-not $SignToolPath) { throw "Windows SDK signtool.exe is required for release." }
        if ($DriverPackageDir) {
            $DriverPackageDir = (Resolve-Path -LiteralPath $DriverPackageDir).Path
            & $python scripts/check_native_release.py --root $DriverPackageDir
            if ($LASTEXITCODE -ne 0) { throw "Optional signed driver package preflight failed." }
            $env:GLIDELEAF_DRIVER_PACKAGES = $DriverPackageDir
        } else {
            Remove-Item Env:\GLIDELEAF_DRIVER_PACKAGES -ErrorAction SilentlyContinue
        }
    } elseif ($DriverPackageDir) {
        $env:GLIDELEAF_DRIVER_PACKAGES = (Resolve-Path -LiteralPath $DriverPackageDir).Path
    } else {
        Remove-Item Env:\GLIDELEAF_DRIVER_PACKAGES -ErrorAction SilentlyContinue
    }
    if (-not $SkipInstallDependencies) {
        & $python -m pip install --disable-pip-version-check -r requirements-dev.txt pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
    }
    if ($FetchFirmware) {
        New-Item -ItemType Directory -Force (Join-Path $repo 'firmware') | Out-Null
        & (Join-Path $repo '.venv\Scripts\bumble-rtk-fw-download.exe') --output-dir (Join-Path $repo 'firmware')
        if ($LASTEXITCODE -ne 0) { throw "Firmware download failed." }
    }
    & $python scripts/collect_licenses.py
    if ($LASTEXITCODE -ne 0) { throw "License collection failed." }
    & $python -m PyInstaller --noconfirm packaging/winuc.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    $app = Join-Path $repo 'dist\Glideleaf\Glideleaf.exe'
    if ($Release) {
        & $SignToolPath sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $app
        if ($LASTEXITCODE -ne 0) { throw "Application/helper signing failed." }
        & (Join-Path $PSScriptRoot 'verify_release.ps1') -AppPath $app -Publisher $Publisher -PythonPath $python -DriverPackageDir $(if ($DriverPackageDir) { Join-Path $repo 'dist\Glideleaf\_internal\driver-packages' })
    } else {
        Write-Host 'DEVELOPMENT BUILD: unsigned app; Windows inbox WinUSB is used for dongle setup.'
    }
    Write-Host "Portable app: $app"
} finally {
    if ($null -eq $previousPackages) { Remove-Item Env:\GLIDELEAF_DRIVER_PACKAGES -ErrorAction SilentlyContinue }
    else { $env:GLIDELEAF_DRIVER_PACKAGES = $previousPackages }
    Pop-Location
}
