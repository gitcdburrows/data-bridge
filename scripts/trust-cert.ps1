<#
.SYNOPSIS
    Trust a code-signing certificate on this machine.

.DESCRIPTION
    Imports the public cert (.cer) into the certificate stores so Windows
    trusts apps signed with it - removing the "unknown publisher" warning and
    letting AV/EDR allowlist by publisher. Run once per target machine.

      -Scope LocalMachine  (default) trusts it for all users; needs admin.
      -Scope CurrentUser   trusts it for you only; no admin required.

    Root          => the signing cert's chain is trusted.
    TrustedPublisher => signed apps run without a trust prompt.
#>
param(
    [Parameter(Mandatory = $true)][string]$CerPath,
    [ValidateSet('LocalMachine', 'CurrentUser')][string]$Scope = 'LocalMachine'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $CerPath)) { throw "Certificate not found: $CerPath" }

Import-Certificate -FilePath $CerPath -CertStoreLocation "Cert:\$Scope\Root" | Out-Null
Import-Certificate -FilePath $CerPath -CertStoreLocation "Cert:\$Scope\TrustedPublisher" | Out-Null

Write-Host "Trusted '$CerPath' in $Scope (Root + TrustedPublisher)." -ForegroundColor Green
