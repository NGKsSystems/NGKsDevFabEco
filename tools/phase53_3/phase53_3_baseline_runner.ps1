#Requires -Version 5.0
<#
.SYNOPSIS
Phase 53.3 Baseline Certification Runner
Re-executes the Phase 53.2 validation matrix deterministically.

.DESCRIPTION
Frozen harness for reproducing the 4-case Phase 53.2 matrix:
- direct native clean -> ALLOW
- direct native tampered -> BLOCK
- script clean -> ALLOW
- script tampered -> BLOCK

.PARAMETER ProofFolder
Target proof folder (required).

.PARAMETER RuntimeRoot
Path to NGKsUI Runtime (defaults to C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime).
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ProofFolder,
    
    [string]$RuntimeRoot = 'C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $ProofFolder -PathType Container)) {
    Write-Error "ProofFolder not found: $ProofFolder"; exit 1
}

$exe = Join-Path $RuntimeRoot 'build\debug\bin\widget_sandbox.exe'
$launcher = Join-Path $RuntimeRoot 'tools\run_widget_sandbox.ps1'
$artFile = Join-Path $RuntimeRoot 'control_plane\111_trust_chain_ledger_baseline_enforcement_surface_fingerprint_regression_anchor_trust_chain_baseline.json'

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    Write-Error "Executable not found: $exe"
    exit 1
}

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    Write-Error "Launcher not found: $launcher"
    exit 1
}

if (-not (Test-Path -LiteralPath $artFile -PathType Leaf)) {
    Write-Error "Artifact file not found: $artFile"
    exit 1
}

# Case 1: Direct native clean
Push-Location -StackName 'harness' -LiteralPath $RuntimeRoot
try {
    $output = (& $exe '--demo' 2>&1 | Out-String)
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location -StackName 'harness'
}
$actualClass = $(if ($exitCode -ne 0) { 'BLOCK' } else { 'ALLOW' })
@(
    "LABEL=direct_native_clean",
    "CLASSIFICATION=$actualClass",
    "EXIT=$exitCode",
    "UTC=$([DateTime]::UtcNow.ToString('o'))",
    "EXPECTED=ALLOW",
    "---OUTPUT---",
    $output
) | Set-Content -LiteralPath (Join-Path $ProofFolder '10_native_clean.txt') -Encoding UTF8

# Case 2: Direct native tampered
$bakFile = "$artFile.phase53bak"
Copy-Item -LiteralPath $artFile -Destination $bakFile -Force -ErrorAction Stop
try {
    Push-Location -StackName 'harness2' -LiteralPath $RuntimeRoot
    try {
        Add-Content -LiteralPath $artFile -Value "`n " -Encoding UTF8
        $output = (& $exe '--demo' 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location -StackName 'harness2'
    }
    $actualClass = $(if ($exitCode -ne 0) { 'BLOCK' } else { 'ALLOW' })
    @(
        "LABEL=direct_native_tampered",
        "CLASSIFICATION=$actualClass",
        "EXIT=$exitCode",
        "UTC=$([DateTime]::UtcNow.ToString('o'))",
        "EXPECTED=BLOCK",
        "---OUTPUT---",
        $output
    ) | Set-Content -LiteralPath (Join-Path $ProofFolder '11_native_tampered.txt') -Encoding UTF8
} finally {
    if (Test-Path -LiteralPath $bakFile) {
        Move-Item -LiteralPath $bakFile -Destination $artFile -Force
    }
}

# Case 3: Script clean
$output = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command "Set-Location '$RuntimeRoot'; & '$launcher' -Config Debug -PassArgs '--demo'" 2>&1 | Out-String)
$exitCode = $LASTEXITCODE
$actualClass = $(if ($exitCode -ne 0) { 'BLOCK' } else { 'ALLOW' })
@(
    "LABEL=script_clean",
    "CLASSIFICATION=$actualClass",
    "EXIT=$exitCode",
    "UTC=$([DateTime]::UtcNow.ToString('o'))",
    "EXPECTED=ALLOW",
    "---OUTPUT---",
    $output
) | Set-Content -LiteralPath (Join-Path $ProofFolder '20_script_clean.txt') -Encoding UTF8

# Case 4: Script tampered
Copy-Item -LiteralPath $artFile -Destination $bakFile -Force -ErrorAction Stop
try {
    Add-Content -LiteralPath $artFile -Value "`n " -Encoding UTF8
    $output = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command "Set-Location '$RuntimeRoot'; & '$launcher' -Config Debug -PassArgs '--demo'" 2>&1 | Out-String)
    $exitCode = $LASTEXITCODE
    $actualClass = $(if ($exitCode -ne 0) { 'BLOCK' } else { 'ALLOW' })
    @(
        "LABEL=script_tampered",
        "CLASSIFICATION=$actualClass",
        "EXIT=$exitCode",
        "UTC=$([DateTime]::UtcNow.ToString('o'))",
        "EXPECTED=BLOCK",
        "---OUTPUT---",
        $output
    ) | Set-Content -LiteralPath (Join-Path $ProofFolder '21_script_tampered.txt') -Encoding UTF8
} finally {
    if (Test-Path -LiteralPath $bakFile) {
        Move-Item -LiteralPath $bakFile -Destination $artFile -Force
    }
}

Write-Host "HARNESS_COMPLETE=1"
