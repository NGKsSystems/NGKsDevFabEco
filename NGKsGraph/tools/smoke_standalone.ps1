$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'package_windows.ps1')

$latestPathFile = Join-Path $repoRoot 'artifacts\package\phase10\latest_path.txt'
if (-not (Test-Path $latestPathFile)) {
    throw "latest_path.txt not found after packaging"
}

$packageDir = (Get-Content $latestPathFile -Raw).Trim()
if (-not (Test-Path $packageDir)) {
    throw "Package directory not found: $packageDir"
}

Push-Location $packageDir
try {
    .\ngksgraph.exe --help | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "--help failed" }

    .\ngksgraph.exe --version | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "--version failed" }

    $selftestOut = 'artifacts\selftest\phase10_standalone_smoke'
    .\ngksgraph.exe selftest --scale 10 --seeds 1..1 --json-only --out $selftestOut | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "selftest failed" }

    $report = Join-Path $selftestOut 'report.json'
    if (-not (Test-Path $report)) {
        throw "Standalone smoke report missing: $report"
    }
    Write-Host "STANDALONE_SMOKE=PASS"
} finally {
    Pop-Location
}
