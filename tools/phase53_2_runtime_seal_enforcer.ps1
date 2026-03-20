#!/usr/bin/env pwsh
<#
.SYNOPSIS
Phase 53.2 Runtime Seal Enforcer for DevFabEco
Mandatory pre-flight gate binding before any runtime-targeted validation can proceed.

.DESCRIPTION
This enforcer ensures that the validation target (NGKsUI Runtime) cannot be built 
or validated without first passing the Phase 53.2 trust chain and enforcement gates.

REQUIREMENTS:
- Fail-closed only (no fallback, no bypass)
- One call per validation session  
- Blocks entire validation pipeline on gate failure
- No regeneration of enforcement artifacts

.PARAMETER ValidationTargetRoot
Root path of the validation target (e.g., NGKsUI Runtime).

.PARAMETER ProofDirectory
Output directory for enforcement proof files.

.PARAMETER ECORoot
Root path of DevFabEco (for context only).

.OUTPUTS
Exit code: 0 if gate PASS, 1 if gate FAIL or error
Console: Gate decision and failure details
Proof file: <ProofDirection>/phase53_2_enforcement_result.json
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateScript({Test-Path $_ -PathType Container})]
    [string]$ValidationTargetRoot,
    
    [Parameter(Mandatory=$true)]
    [ValidateScript({Test-Path $_ -PathType Container})]
    [string]$ProofDirectory,
    
    [Parameter(Mandatory=$false)]
    [string]$ECORoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

# ─── Normalize paths ──────────────────────────────────────────────────────────
$ValidationTargetRoot = Resolve-Path $ValidationTargetRoot -ErrorAction Stop | Select-Object -ExpandProperty Path
$ProofDirectory = Resolve-Path $ProofDirectory -ErrorAction Stop | Select-Object -ExpandProperty Path

Write-Host "[PHASE53.2_RUNTIME_SEAL] Enforcer starting..."
Write-Host "  ValidationTarget: $ValidationTargetRoot"
Write-Host "  ProofDirectory: $ProofDirectory"

# ─── Locate Phase 53.2 Runner ─────────────────────────────────────────────────
$phase53_2_runner = Join-Path $ValidationTargetRoot 'tools\phase53_2\phase53_2_trust_chain_ledger_baseline_enforcement_surface_fingerprint_regression_anchor_trust_chain_baseline_gate_runner.ps1'

if (-not (Test-Path $phase53_2_runner)) {
    Write-Host "[PHASE53.2_RUNTIME_SEAL] FAIL: Phase 53.2 runner not found at $phase53_2_runner"
    exit 1
}

Write-Host "[PHASE53.2_RUNTIME_SEAL] Phase 53.2 runner located: $phase53_2_runner"

# ─── Required enforcement artifacts must exist ────────────────────────────────
$requiredPaths = @(
    (Join-Path $ValidationTargetRoot 'control_plane\70_guard_fingerprint_trust_chain.json'),
    (Join-Path $ValidationTargetRoot 'control_plane\110_trust_chain_ledger_baseline_enforcement_surface_fingerprint_trust_chain_baseline_enforcement_coverage_fingerprint_regression_anchor.json'),
    (Join-Path $ValidationTargetRoot 'control_plane\111_trust_chain_ledger_baseline_enforcement_surface_fingerprint_regression_anchor_trust_chain_baseline.json'),
    (Join-Path $ValidationTargetRoot 'control_plane\112_trust_chain_ledger_baseline_enforcement_surface_fingerprint_regression_anchor_trust_chain_baseline_integrity.json')
)

foreach ($path in $requiredPaths) {
    if (-not (Test-Path $path)) {
        Write-Host "[PHASE53.2_RUNTIME_SEAL] FAIL: Required enforcement artifact missing: $path"
        exit 1
    }
}

Write-Host "[PHASE53.2_RUNTIME_SEAL] All enforcement artifacts present - check"

# ─── Execute Phase 53.2 Gate (must be run from ValidationTargetRoot) ─────────
Write-Host "[PHASE53.2_RUNTIME_SEAL] Invoking Phase 53.2 enforcement gate..."
Push-Location $ValidationTargetRoot
try {
    # Execute runner and capture output
    $gateOutput = & $phase53_2_runner 2>&1
    $gateExitCode = $LASTEXITCODE
    
    if ($gateExitCode -ne 0) {
        Write-Host "[PHASE53.2_RUNTIME_SEAL] FAIL: Gate runner exited with code $gateExitCode"
        Write-Host $gateOutput
        exit 1
    }
    
    # Parse result: look for 98_gate_phase53_2.txt in proof output
    $proofOutput = $gateOutput | Select-String "PROOF_ZIP=|_proof" | Select-Object -First 1
    Write-Host "[PHASE53.2_RUNTIME_SEAL] Gate output: $($gateOutput | Select-String 'GATE=|Gate' | Select-Object -ExpandProperty Line)"
    
} catch {
    Write-Host "[PHASE53.2_RUNTIME_SEAL] FAIL: Exception during gate execution: $($_.Exception.Message)"
    exit 1
} finally {
    Pop-Location
}

# ─── Parse Gate Result ─────────────────────────────────────────────────────
# Look for GATE=PASS or GATE=FAIL in output
$gateDecision = "UNKNOWN"
if ($gateOutput -match 'GATE=PASS') {
    $gateDecision = "PASS"
} elseif ($gateOutput -match 'GATE=FAIL') {
    $gateDecision = "FAIL"
}

Write-Host "[PHASE53.2_RUNTIME_SEAL] Gate decision: $gateDecision"

# ─── Create enforcement record ────────────────────────────────────────────────
$enforcementResult = @{
    timestamp = Get-Date -Format 'o'
    validation_target = $ValidationTargetRoot
    enforcer_version = "1.0"
    gate_decision = $gateDecision
    exit_code = if ($gateDecision -eq "PASS") { 0 } else { 1 }
    phase53_2_runner = $phase53_2_runner
    enforcement_artifacts_verified = $true
    output_sample = ($gateOutput | Select-Object -First 50 | ConvertTo-Json)
}

$resultPath = Join-Path $ProofDirectory "phase53_2_enforcement_result.json"
$enforcementResult | ConvertTo-Json | Out-File $resultPath -Encoding UTF8
Write-Host "[PHASE53.2_RUNTIME_SEAL] Enforcement record written to: $resultPath"

# ─── Enforce gate result ──────────────────────────────────────────────────────
if ($gateDecision -ne "PASS") {
    Write-Host ""
    Write-Host "[PHASE53.2_RUNTIME_SEAL] [BLOCKED] ENFORCEMENT FAILED"
    Write-Host "[PHASE53.2_RUNTIME_SEAL] Runtime validation target cannot proceed without Phase 53.2 PASS"
    Write-Host "[PHASE53.2_RUNTIME_SEAL] Reason: Gate decision = $gateDecision"
    Write-Host ""
    exit 1
}

# ─── Success Path ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[PHASE53.2_RUNTIME_SEAL] Enforcement PASSED"
Write-Host "[PHASE53.2_RUNTIME_SEAL] Runtime validation target cleared for build"
Write-Host ""
exit 0
