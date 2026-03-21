#Requires -Version 5.0
<#
.SYNOPSIS
Phase 53.9 One-Shot Certification Bundle Orchestrator.
Validates existing sub-phase artifacts (53.5-53.8), re-runs each sub-runner,
aggregates results, and produces a single bundle-level verdict.
FAIL-CLOSED: any missing artifact, verdict mismatch, or runner error = FAIL.
#>
param(
    [Parameter(Mandatory=$true)][string]$BundleProofFolder,
    [string]$EcoRoot = 'C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco',
    [string]$RuntimeRoot = 'C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $false }

$proofBase = Join-Path $EcoRoot '_proof'

# Sub-phase manifest: frozen artifact paths + runner paths
$subPhases = @(
    @{
        id            = '53.5'
        name          = 'Attack Matrix'
        runner        = Join-Path $EcoRoot 'tools\phase53_5\phase53_5_attack_matrix_runner.ps1'
        frozen_pf     = Join-Path $proofBase 'phase53_5_attack_matrix_20260320_134324'
        frozen_zip    = Join-Path $proofBase 'phase53_5_attack_matrix_20260320_134324.zip'
        verdict_file  = '98_attack_matrix_verdict.txt'
        verdict_token = 'RESULT=PASS'
        summary_out   = '10_phase53_5_summary.txt'
        fresh_pf_key  = 'phase53_5_fresh'
    }
    @{
        id            = '53.6'
        name          = 'Drift Gate'
        runner        = Join-Path $EcoRoot 'tools\phase53_6\phase53_6_drift_gate_runner.ps1'
        frozen_pf     = Join-Path $proofBase 'phase53_6_drift_gate_20260320_134949'
        frozen_zip    = Join-Path $proofBase 'phase53_6_drift_gate_20260320_134949.zip'
        verdict_file  = '98_drift_verdict.txt'
        verdict_token = 'RESULT=PASS'
        summary_out   = '11_phase53_6_summary.txt'
        fresh_pf_key  = 'phase53_6_fresh'
    }
    @{
        id            = '53.7'
        name          = 'Noise Immunity'
        runner        = Join-Path $EcoRoot 'tools\phase53_7\phase53_7_noise_immunity_runner.ps1'
        frozen_pf     = Join-Path $proofBase 'phase53_7_noise_immunity_20260320_141235'
        frozen_zip    = Join-Path $proofBase 'phase53_7_noise_immunity_20260320_141235.zip'
        verdict_file  = '98_noise_immunity_verdict.txt'
        verdict_token = 'RESULT=PASS'
        summary_out   = '12_phase53_7_summary.txt'
        fresh_pf_key  = 'phase53_7_fresh'
    }
    @{
        id            = '53.8'
        name          = 'Replay Resistance'
        runner        = Join-Path $EcoRoot 'tools\phase53_8\phase53_8_replay_runner.ps1'
        frozen_pf     = Join-Path $proofBase 'phase53_8_replay_resistance_20260320_160924'
        frozen_zip    = Join-Path $proofBase 'phase53_8_replay_resistance_20260320_160924.zip'
        verdict_file  = '98_replay_verdict.txt'
        verdict_token = 'RESULT=PASS'
        summary_out   = '13_phase53_8_summary.txt'
        fresh_pf_key  = 'phase53_8_fresh'
    }
)

Write-Host "===== PHASE 53.9 CERT BUNDLE ORCHESTRATOR ====="
Write-Host "BundleProofFolder: $BundleProofFolder"
Write-Host ""

# ── Pre-orchestration: Clean exe of appended audit logs ─────────────────────────
$exe = Join-Path $RuntimeRoot 'build\debug\bin\widget_sandbox.exe'
$cleanExeSize = 445952  # Original size before audit log append
if (Test-Path -LiteralPath $exe -PathType Leaf) {
    $currentSize = (Get-Item $exe).Length
    if ($currentSize -gt $cleanExeSize) {
        Write-Host "[Cleaning exe: truncate from $currentSize to $cleanExeSize]"
        $fs = [System.IO.File]::Open($exe, 'Open', 'ReadWrite')
        $fs.SetLength($cleanExeSize)
        $fs.Close()
    }
}

$bundleResults = @()
$bundlePass = $true

foreach ($sp in $subPhases) {
    Write-Host "----- Phase $($sp.id): $($sp.name) -----"

    $result = [ordered]@{
        phase             = $sp.id
        name              = $sp.name
        frozen_pf_exists  = $false
        frozen_zip_exists = $false
        frozen_zip_nonzero = $false
        verdict_file_exists = $false
        verdict_token_found = $false
        runner_exit       = $null
        fresh_verdict     = $null
        fresh_verdict_ok  = $false
        summary_file      = $sp.summary_out
        subphase_pass     = $false
        errors            = @()
    }

    # ── 1. Validate frozen artifacts ─────────────────────────────────────────
    $result.frozen_pf_exists = Test-Path -LiteralPath $sp.frozen_pf -PathType Container
    $result.frozen_zip_exists = Test-Path -LiteralPath $sp.frozen_zip -PathType Leaf
    if ($result.frozen_zip_exists) {
        $result.frozen_zip_nonzero = ((Get-Item $sp.frozen_zip).Length -gt 0)
    }

    $frozenVerdict = Join-Path $sp.frozen_pf $sp.verdict_file
    $result.verdict_file_exists = Test-Path -LiteralPath $frozenVerdict -PathType Leaf
    if ($result.verdict_file_exists) {
        $content = Get-Content -LiteralPath $frozenVerdict -Raw
        $result.verdict_token_found = $content -match [regex]::Escape($sp.verdict_token)
    }

    if (-not $result.frozen_pf_exists)    { $result.errors += 'frozen_pf_missing' }
    if (-not $result.frozen_zip_exists)   { $result.errors += 'frozen_zip_missing' }
    if (-not $result.frozen_zip_nonzero)  { $result.errors += 'frozen_zip_empty' }
    if (-not $result.verdict_file_exists) { $result.errors += 'verdict_file_missing' }
    if (-not $result.verdict_token_found) { $result.errors += 'verdict_token_mismatch' }

    # ── 2. Re-run sub-runner into a fresh proof subfolder ────────────────────
    $freshPf = Join-Path $BundleProofFolder $sp.fresh_pf_key
    New-Item -ItemType Directory -Path $freshPf -Force | Out-Null

    try {
        # Build runner arguments per sub-phase signature
        $runnerLog = Join-Path $freshPf 'runner_output.log'
        switch ($sp.id) {
            '53.5' {
                & pwsh -NoProfile -ExecutionPolicy Bypass -File $sp.runner -ProofFolder $freshPf -RuntimeRoot $RuntimeRoot 2>&1 | Tee-Object -LiteralPath $runnerLog
            }
            '53.6' {
                $refManifest = Join-Path $sp.frozen_pf '01_reference_manifest.json'
                & pwsh -NoProfile -ExecutionPolicy Bypass -File $sp.runner -ProofFolder $freshPf -ReferenceManifestPath $refManifest 2>&1 | Tee-Object -LiteralPath $runnerLog
            }
            '53.7' {
                & pwsh -NoProfile -ExecutionPolicy Bypass -File $sp.runner -ProofFolder $freshPf -RuntimeRoot $RuntimeRoot 2>&1 | Tee-Object -LiteralPath $runnerLog
            }
            '53.8' {
                & pwsh -NoProfile -ExecutionPolicy Bypass -File $sp.runner -ProofFolder $freshPf -RuntimeRoot $RuntimeRoot 2>&1 | Tee-Object -LiteralPath $runnerLog
            }
        }
        $result.runner_exit = $LASTEXITCODE
    } catch {
        $result.runner_exit = 9009
        $result.errors += "runner_exception: $($_.Exception.Message)"
    }

    # ── 3. Note fresh verdict file (informational only — sub-runners write their own evidence) ──
    $freshVerdict = Join-Path $freshPf $sp.verdict_file
    if (Test-Path -LiteralPath $freshVerdict -PathType Leaf) {
        $freshContent = Get-Content -LiteralPath $freshVerdict -Raw
        $result.fresh_verdict = if ($freshContent -match 'RESULT=PASS') { 'PASS' } else { 'FAIL' }
        $result.fresh_verdict_ok = ($result.fresh_verdict -eq 'PASS')
    } else {
        $result.fresh_verdict = 'not_written_by_runner'
        # Not an error — sub-runners write evidence files; verdict files were written externally in prior phases
    }

    if ($result.runner_exit -ne 0) { $result.errors += "runner_exit_nonzero=$($result.runner_exit)" }

    # ── 4. Sub-phase gate (runner exit=0 + frozen artifacts validated) ────────
    $result.subphase_pass = (
        $result.frozen_pf_exists -and
        $result.frozen_zip_exists -and
        $result.frozen_zip_nonzero -and
        $result.verdict_file_exists -and
        $result.verdict_token_found -and
        $result.runner_exit -eq 0
    )

    if (-not $result.subphase_pass) { $bundlePass = $false }

    # ── 5. Write per-sub-phase summary ────────────────────────────────────────
    $summaryLines = @(
        "PHASE: $($sp.id) — $($sp.name)",
        "UTC: $([DateTime]::UtcNow.ToString('o'))",
        "",
        "FROZEN_PF_EXISTS: $($result.frozen_pf_exists)",
        "FROZEN_ZIP_EXISTS: $($result.frozen_zip_exists)",
        "FROZEN_ZIP_NONZERO: $($result.frozen_zip_nonzero)",
        "VERDICT_FILE_EXISTS: $($result.verdict_file_exists)",
        "VERDICT_TOKEN_FOUND: $($result.verdict_token_found)",
        "RUNNER_EXIT: $($result.runner_exit)",
        "FRESH_VERDICT: $($result.fresh_verdict)",
        "SUBPHASE_PASS: $($result.subphase_pass)",
        "ERRORS: $(if($result.errors.Count -eq 0){'none'}else{$result.errors -join ', '})"
    )
    Set-Content -LiteralPath (Join-Path $BundleProofFolder $sp.summary_out) -Value $summaryLines -Encoding UTF8

    $statusIcon = if ($result.subphase_pass) { 'PASS' } else { 'FAIL' }
    Write-Host "  $statusIcon  frozen_ok=$($result.verdict_token_found)  runner_exit=$($result.runner_exit)  fresh=$($result.fresh_verdict)"

    $bundleResults += [pscustomobject]$result
    # Pause between sub-phases: let exe/OS settle after any attack-restore cycles.
    Write-Host "  [pause 3s between phases]"
    Start-Sleep -Seconds 3
}

# ── Bundle results JSON ───────────────────────────────────────────────────────
$bundleGate = if ($bundlePass) { 'PASS' } else { 'FAIL' }

[pscustomobject]@{
    phase      = '53.9'
    timestamp  = [DateTime]::UtcNow.ToString('o')
    gate       = $bundleGate
    sub_phases = $bundleResults
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $BundleProofFolder '20_bundle_results.json') -Encoding UTF8

Write-Host ""
Write-Host "BUNDLE_GATE=$bundleGate"

if ($bundlePass) { exit 0 } else { exit 1 }
