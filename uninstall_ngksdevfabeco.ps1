param(
    [switch]$RemoveInstallProof
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path $repoRoot)) {
    throw "REPO_ROOT_NOT_FOUND: $repoRoot"
}

$venvDir = Join-Path $repoRoot '.venv'
if (Test-Path $venvDir) {
    Remove-Item -Recurse -Force $venvDir
    Write-Host "Removed $venvDir"
} else {
    Write-Host "No .venv found at $venvDir"
}

if ($RemoveInstallProof) {
    $proofRoot = Join-Path $repoRoot '_proof'
    if (Test-Path $proofRoot) {
        Get-ChildItem -Path $proofRoot -Directory -Filter 'install_*' | ForEach-Object {
            Remove-Item -Recurse -Force $_.FullName
            Write-Host "Removed $($_.FullName)"
        }
    }
}

Write-Host 'UNINSTALL_OK'
Write-Host 'Hint: install_ngksdevfabeco.ps1 supports -UserInstall, -CleanupInvalidUserDistributions, and -PersistUserScriptsPath for smoother runtime installs.'
