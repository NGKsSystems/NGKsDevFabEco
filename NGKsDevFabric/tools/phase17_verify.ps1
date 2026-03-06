param(
    [string]$Root,
    [string]$PfPath
)

$ErrorActionPreference = 'Stop'

if (-not $Root -or [string]::IsNullOrWhiteSpace($Root)) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}
Set-Location $Root

if (-not $PfPath -or [string]::IsNullOrWhiteSpace($PfPath)) {
    $PfPath = ([string](Get-Content ".\_proof\CURRENT_PF_PHASE17_3.txt" -Raw)).Trim()
}

if (-not (Test-Path $PfPath)) {
    New-Item -ItemType Directory -Force -Path $PfPath | Out-Null
}

$failed = $false
$checks = @()

$resolverPath = Join-Path $Root 'src\ngk_fabric\resolver.py'
$resolverText = if (Test-Path $resolverPath) { [string](Get-Content $resolverPath -Raw) } else { '' }

if ($resolverText -match '"builder"\s*:\s*\{[\s\S]*"type"\s*:\s*"external"[\s\S]*"status"\s*:\s*"not-bound"') {
    $checks += 'builder:PASS:neutral abstraction present'
}
else {
    $failed = $true
    $checks += 'builder:FAIL:neutral abstraction missing'
}

$ngkPath = Join-Path $Root 'tools\ngk.ps1'
if (-not (Test-Path $ngkPath)) {
    $failed = $true
    $checks += 'cli:FAIL:tools/ngk.ps1 missing'
}
else {
    $checks += 'cli:PASS:tools/ngk.ps1 present'
}

$checks | Out-File (Join-Path $PfPath 'phase17_verify_checks.txt') -Encoding utf8

if ($failed) {
    Write-Error 'PHASE17 FAIL'
    exit 1
}
else {
    Write-Output 'PHASE17 PASS'
    exit 0
}
