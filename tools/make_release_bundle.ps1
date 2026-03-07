param(
    [string]$OutputRoot,
    [string]$WheelhousePath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path $repoRoot)) {
    throw "REPO_ROOT_NOT_FOUND: $repoRoot"
}

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repoRoot 'releases'
}
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$wheelSource = $null
if ($WheelhousePath) {
    $wheelSource = (Resolve-Path $WheelhousePath).Path
} else {
    $wheelRoot = Join-Path $repoRoot 'wheelhouse'
    if (-not (Test-Path $wheelRoot)) {
        throw "WHEELHOUSE_ROOT_NOT_FOUND: $wheelRoot"
    }
    $latest = Get-ChildItem -Path $wheelRoot -Directory -Filter 'e2e_*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        throw "NO_E2E_WHEELHOUSE_FOUND under $wheelRoot"
    }
    $wheelSource = $latest.FullName
}
if (-not (Test-Path $wheelSource)) {
    throw "WHEEL_SOURCE_NOT_FOUND: $wheelSource"
}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$bundleDir = Join-Path $OutputRoot ("ngksdevfabeco_release_" + $ts)
New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null

$readmeCandidate = Join-Path $repoRoot 'README.md'
if (-not (Test-Path $readmeCandidate)) {
    $readmeCandidate = Join-Path $repoRoot 'NGKsDevFabric\README.md'
}
if (-not (Test-Path $readmeCandidate)) {
    throw "README_NOT_FOUND"
}
Copy-Item -Force $readmeCandidate (Join-Path $bundleDir 'README.md')

$licenseCandidate = Join-Path $repoRoot 'LICENSE'
if (-not (Test-Path $licenseCandidate)) {
    $licenseCandidate = Join-Path $repoRoot 'NGKsGraph\LICENSE'
}
if (Test-Path $licenseCandidate) {
    Copy-Item -Force $licenseCandidate (Join-Path $bundleDir 'LICENSE')
}

Copy-Item -Force (Join-Path $repoRoot 'install_ngksdevfabeco.ps1') (Join-Path $bundleDir 'install_ngksdevfabeco.ps1')
Copy-Item -Force (Join-Path $repoRoot 'uninstall_ngksdevfabeco.ps1') (Join-Path $bundleDir 'uninstall_ngksdevfabeco.ps1')

$bundleWheelDir = Join-Path $bundleDir 'wheelhouse'
New-Item -ItemType Directory -Force -Path $bundleWheelDir | Out-Null
Get-ChildItem -Path $wheelSource -Filter '*.whl' -File | ForEach-Object {
    Copy-Item -Force $_.FullName (Join-Path $bundleWheelDir $_.Name)
}

$wheelCount = (Get-ChildItem -Path $bundleWheelDir -Filter '*.whl' -File | Measure-Object).Count
if ($wheelCount -eq 0) {
    throw "BUNDLE_WHEEL_COPY_EMPTY from $wheelSource"
}

Write-Host "BUNDLE_OK path=$bundleDir"
