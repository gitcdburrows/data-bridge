# Build the Bloomberg Data Bridge into a single Windows executable.
#
# Run on the Bloomberg workstation (PowerShell) so that blpapi is available
# and gets bundled into the .exe. The result is dist\BloombergBridge.exe,
# which end users can run with no Python installed.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
# --extra-index-url lets pip resolve blpapi from Bloomberg while everything
# else comes from PyPI.
pip install --extra-index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ -r requirements-dev.txt

pyinstaller --clean --noconfirm data_bridge.spec

# Optional Authenticode signing - a no-op unless SIGN_* env vars are set.
& "$PSScriptRoot\sign.ps1" -Path "dist\BloombergBridge.exe"

Write-Host ""
Write-Host "Built dist\BloombergBridge.exe" -ForegroundColor Green
