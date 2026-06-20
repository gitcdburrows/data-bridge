<#
.SYNOPSIS
    Authenticode-sign a file, if signing material is provided.

.DESCRIPTION
    Provide EITHER a PFX (as a base64 string or a file path) OR the thumbprint
    of a certificate already in the user's store. If none is provided the
    script prints a note and exits 0 — so it is always safe to call from the
    build (an unsigned binary is still produced).

    Signing material is read from parameters or these environment variables:
      SIGN_PFX_BASE64    base64-encoded .pfx (handy for CI secrets)
      SIGN_PFX_PATH      path to a .pfx on disk
      SIGN_PFX_PASSWORD  password for the .pfx
      SIGN_THUMBPRINT    SHA1 thumbprint of an installed cert
      SIGN_TIMESTAMP_URL RFC3161 timestamp server (default: DigiCert)

    For locked-down/EV scenarios, point SIGN_THUMBPRINT at a cert backed by a
    cloud HSM (Azure Trusted Signing, DigiCert KeyLocker, SignPath, …).
#>
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$PfxBase64    = $env:SIGN_PFX_BASE64,
    [string]$PfxPath      = $env:SIGN_PFX_PATH,
    [string]$PfxPassword  = $env:SIGN_PFX_PASSWORD,
    [string]$Thumbprint   = $env:SIGN_THUMBPRINT,
    [string]$TimestampUrl = $(if ($env:SIGN_TIMESTAMP_URL) { $env:SIGN_TIMESTAMP_URL } else { 'http://timestamp.digicert.com' })
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Path)) { throw "File to sign not found: $Path" }

function Find-SignTool {
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $roots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "${env:ProgramFiles}\Windows Kits\10\bin"
    )
    foreach ($root in $roots) {
        if (Test-Path $root) {
            $st = Get-ChildItem -Path $root -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
                  Where-Object { $_.FullName -match '\\x64\\' } |
                  Sort-Object FullName -Descending | Select-Object -First 1
            if ($st) { return $st.FullName }
        }
    }
    throw "signtool.exe not found. Install the Windows SDK."
}

$hasPfx = $PfxBase64 -or $PfxPath
if (-not $hasPfx -and -not $Thumbprint) {
    Write-Host "No signing material (SIGN_PFX_* / SIGN_THUMBPRINT) provided — skipping signing." -ForegroundColor Yellow
    exit 0
}

$signtool = Find-SignTool
$tempPfx = $null
try {
    $signArgs = @('sign', '/fd', 'SHA256', '/tr', $TimestampUrl, '/td', 'SHA256')
    if ($hasPfx) {
        if ($PfxBase64) {
            $tempPfx = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName() + '.pfx')
            [System.IO.File]::WriteAllBytes($tempPfx, [System.Convert]::FromBase64String($PfxBase64))
            $pfx = $tempPfx
        } else {
            $pfx = $PfxPath
        }
        $signArgs += @('/f', $pfx)
        if ($PfxPassword) { $signArgs += @('/p', $PfxPassword) }
    } else {
        $signArgs += @('/sha1', $Thumbprint)
    }
    $signArgs += $Path

    Write-Host "Signing $Path …"
    & $signtool @signArgs
    if ($LASTEXITCODE -ne 0) { throw "signtool failed with exit code $LASTEXITCODE" }
    & $signtool verify /pa /v $Path
    Write-Host "Signed and verified: $Path" -ForegroundColor Green
}
finally {
    if ($tempPfx -and (Test-Path $tempPfx)) { Remove-Item $tempPfx -Force }
}
