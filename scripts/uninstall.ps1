<#
.SYNOPSIS
    Remove what BloombergBridge added to this machine.

.DESCRIPTION
    BloombergBridge is a portable app (no installer), so "uninstall" just means
    undoing what it created. This script, with NO admin required:
      - stops a running BloombergBridge,
      - removes the "Start on login" entry (HKCU Run value) and clears the
        Settings enable/disable flag so it drops off Apps > Startup,
      - optionally removes a self-signed "Bloomberg Data Bridge" code-signing
        cert from your CurrentUser trust stores (pass -RemoveCert).

    It does NOT delete the .exe / .zip / data-bridge.log for you - it prints
    which files to delete by hand at the end.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\uninstall.ps1
    powershell -ExecutionPolicy Bypass -File scripts\uninstall.ps1 -RemoveCert
#>
param(
    [switch]$RemoveCert,
    [string]$CertSubject = "Bloomberg Data Bridge"
)

$ErrorActionPreference = 'Stop'

# 1. Stop a running instance (best effort).
Get-Process -Name BloombergBridge -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Stopping running BloombergBridge (PID $($_.Id))..."
    $_ | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 2. Remove the start-on-login entry (HKCU - no admin).
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if (Get-ItemProperty -Path $runKey -Name 'BloombergBridge' -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $runKey -Name 'BloombergBridge'
    Write-Host "Removed start-on-login entry." -ForegroundColor Green
} else {
    Write-Host "No start-on-login entry found."
}

# Clear the Settings 'disabled/enabled' flag so it doesn't linger in the list.
$approved = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
Remove-ItemProperty -Path $approved -Name 'BloombergBridge' -ErrorAction SilentlyContinue

# 3. Optionally remove the self-signed trust (CurrentUser stores - no admin).
if ($RemoveCert) {
    foreach ($store in @('Cert:\CurrentUser\Root', 'Cert:\CurrentUser\TrustedPublisher')) {
        Get-ChildItem $store -ErrorAction SilentlyContinue |
            Where-Object { $_.Subject -eq "CN=$CertSubject" } |
            ForEach-Object {
                Remove-Item $_.PSPath -Force -ErrorAction SilentlyContinue
                Write-Host "Removed cert $($_.Thumbprint) from $store" -ForegroundColor Green
            }
    }
    Write-Host "(If you trusted the cert for ALL users with -Scope LocalMachine, re-run this elevated to clear those.)" -ForegroundColor Yellow
}

# 4. Files to delete by hand.
Write-Host ""
Write-Host "Done. Delete these by hand to finish removing the portable app:" -ForegroundColor Cyan
Write-Host "  - BloombergBridge.exe (and the downloaded .zip)"
Write-Host "  - data-bridge.log (next to the exe)"
Write-Host "  - any .env you placed next to the exe"
