<#
.SYNOPSIS
    Create a self-signed code-signing certificate for internal distribution.

.DESCRIPTION
    Use this when the app only runs on a few machines you control. It creates
    a code-signing cert and exports two files into .\certs:

      codesign.pfx  - private key; KEEP SECRET. Used to sign the .exe.
      codesign.cer  - public cert; install on each target machine to trust it
                      (see scripts/trust-cert.ps1).

    No CA, no cost, no USB token. Run on your build/dev machine.
#>
param(
    [string]$Subject = "Bloomberg Data Bridge",
    [string]$OutDir = "certs",
    [int]$ValidYears = 5,
    [securestring]$Password = $(Read-Host -AsSecureString "Choose a PFX password")
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject "CN=$Subject" `
    -KeyAlgorithm RSA -KeyLength 3072 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears($ValidYears)

$pfx = Join-Path $OutDir "codesign.pfx"
$cer = Join-Path $OutDir "codesign.cer"
Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $Password | Out-Null
Export-Certificate    -Cert $cert -FilePath $cer | Out-Null

Write-Host ""
Write-Host "Created self-signed code-signing certificate." -ForegroundColor Green
Write-Host "  Thumbprint : $($cert.Thumbprint)"
Write-Host "  PFX (keep secret) : $pfx"
Write-Host "  CER (install on targets) : $cer"
Write-Host ""
Write-Host "Sign locally:"
Write-Host "  `$env:SIGN_PFX_PATH = '$pfx'"
Write-Host "  `$env:SIGN_PFX_PASSWORD = '<your password>'"
Write-Host "  scripts\build.ps1"
Write-Host ""
Write-Host "Trust it on each target machine:  scripts\trust-cert.ps1 -CerPath $cer"
