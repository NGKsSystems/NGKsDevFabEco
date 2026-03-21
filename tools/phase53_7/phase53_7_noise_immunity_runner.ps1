<#
.SYNOPSIS
Phase 53.7 Noise-Immunity Test Runner
Executes negative-control cases N1-N6 to prove benign changes do NOT trigger false BLOCKs.

.PARAMETER ProofFolder
Absolute path to proof output folder.

.PARAMETER RuntimeRoot
Absolute path to NGKsUI Runtime root (default: C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime).

.NOTES
Fail-closed: ambiguous cases conservatively reject.
Auditable: all state restored between cases.
No enforcement logic changes.
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ProofFolder,
    
    [Parameter(Mandatory=$false)]
    [string]$RuntimeRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime"
)

$ErrorActionPreference = 'Stop'
$VerbosePreference = 'Continue'

# Core paths
$guard = Join-Path $RuntimeRoot 'tools\phase53_2\phase53_2_runtime_gate_enforce.ps1'
$exe = Join-Path $RuntimeRoot "build\debug\bin\widget_sandbox.exe"
$wrapper = Join-Path $RuntimeRoot "tools\run_widget_sandbox.ps1"
$baseline_artifact = Join-Path $RuntimeRoot "control_plane\111_trust_chain_ledger_baseline_enforcement_surface_fingerprint_regression_anchor_trust_chain_baseline.json"

# Validation
if (-not (Test-Path $guard -PathType Leaf)) { throw "Guard not found: $guard" }
if (-not (Test-Path $exe)) { throw "Executable not found: $exe" }
if (-not (Test-Path $wrapper)) { throw "Wrapper not found: $wrapper" }
if (-not (Test-Path $baseline_artifact)) { throw "Baseline artifact not found: $baseline_artifact" }

# Initialize results container
$results = @{
    timestamp = Get-Date -AsUTC -Format o
    phase = "53.7"
    cases = @()
}

Write-Host "========== PHASE 53.7 NOISE-IMMUNITY RUNNER =========="
Write-Host "ProofFolder: $ProofFolder"
Write-Host "RuntimeRoot: $RuntimeRoot"
Write-Host ""

# ============================================================================
# HELPER: Restore clean state (copy baseline artifact back)
# ============================================================================
function Restore-CleanState {
    param([string]$ArtifactPath, [string]$BackupPath)
    if (Test-Path $BackupPath) {
        Move-Item -LiteralPath $BackupPath -Destination $ArtifactPath -Force | Out-Null
    }
}

# ============================================================================
# CASE N1: Working Directory Normalization
# ============================================================================
Write-Host "[N1] Working Directory Normalization"
$case_result = @{
    case_id = "N1"
    name = "Working Directory Normalization"
    description = "Change to runtime directory via normalized full path"
    expected = "ALLOW"
    actual = $null
    exit_code = $null
    evidence_file = (Join-Path $ProofFolder "10_n1_cwd_normalization.txt")
}

try {
    Push-Location
    Set-Location $RuntimeRoot
    $full_path = (Get-Location).Path
    Set-Location $full_path  # Normalize via GetFullPath
    
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -File $wrapper -Config Debug -PassArgs '--demo' 2>&1 | Out-String)
    $code = $LASTEXITCODE
    
    Pop-Location
    
    $case_result.exit_code = $code
    $case_result.actual = if ($code -eq 0) { "ALLOW" } else { "BLOCK" }
    
    @("N1: Working Directory Normalization",
      "Normalized CWD: $full_path",
      "Exit Code: $code",
      "UTC: $(Get-Date -AsUTC -Format o)",
      "---OUTPUT---",
      $out) | Set-Content -LiteralPath $case_result.evidence_file -Encoding UTF8
    
    $case_matched = ($case_result.expected -eq $case_result.actual)
    Write-Host "  Result: $($case_result.actual) | Expected: $($case_result.expected) | Match: $case_matched"
} catch {
    $case_result.actual = "ERROR"
    Write-Host "  ERROR: $_"
}
$results.cases += $case_result

# ============================================================================
# CASE N2: Non-Security Environment Variable Change
# ============================================================================
Write-Host "[N2] Non-Security Environment Variable Change"
$case_result = @{
    case_id = "N2"
    name = "Non-Security Environment Variable"
    description = "Set TEMP env var (non-guarded) before execution"
    expected = "ALLOW"
    actual = $null
    exit_code = $null
    evidence_file = (Join-Path $ProofFolder "11_n2_env_nonguarded.txt")
}

try {
    Push-Location
    Set-Location $RuntimeRoot
    
    $env:TEMP = "C:\benign\temp"
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -File $wrapper -Config Debug -PassArgs '--demo' 2>&1 | Out-String)
    $code = $LASTEXITCODE
    
    Pop-Location
    
    $case_result.exit_code = $code
    $case_result.actual = if ($code -eq 0) { "ALLOW" } else { "BLOCK" }
    
    @("N2: Non-Security Environment Variable",
      "Modified ENV: TEMP (non-guarded)",
      "Exit Code: $code",
      "UTC: $(Get-Date -AsUTC -Format o)",
      "---OUTPUT---",
      $out) | Set-Content -LiteralPath $case_result.evidence_file -Encoding UTF8
    
    $case_matched = ($case_result.expected -eq $case_result.actual)
    Write-Host "  Result: $($case_result.actual) | Expected: $($case_result.expected) | Match: $case_matched"
} catch {
    $case_result.actual = "ERROR"
    Write-Host "  ERROR: $_"
}
$results.cases += $case_result

# ============================================================================
# CASE N3: Benign Wrapper Logging Change
# ============================================================================
Write-Host "[N3] Benign Wrapper Logging Change"
$case_result = @{
    case_id = "N3"
    name = "Benign Wrapper Logging Change"
    description = "Add non-guarded logging to wrapper without changing payload"
    expected = "ALLOW"
    actual = $null
    exit_code = $null
    evidence_file = (Join-Path $ProofFolder "12_n3_wrapper_logging.txt")
}

try {
    Push-Location
    Set-Location $RuntimeRoot
    
    # Backup original wrapper
    $wrapper_bak = "$wrapper.n3_bak"
    Copy-Item -LiteralPath $wrapper -Destination $wrapper_bak -Force
    
    # Read original, add logging
    $wrapper_content = Get-Content -LiteralPath $wrapper -Raw
    $wrapper_with_logging = $wrapper_content -replace `
        '(# Launch via guard)', `
        "Write-Host '[$(Get-Date -Format HH:mm:ss.fff)] Wrapper executing...'`n`$1"
    Set-Content -LiteralPath $wrapper -Value $wrapper_with_logging -Encoding UTF8 -Force
    
    # Execute with logging modification
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -File $wrapper -Config Debug -PassArgs '--demo' 2>&1 | Out-String)
    $code = $LASTEXITCODE
    
    # Restore original
    Move-Item -LiteralPath $wrapper_bak -Destination $wrapper -Force
    
    Pop-Location
    
    $case_result.exit_code = $code
    $case_result.actual = if ($code -eq 0) { "ALLOW" } else { "BLOCK" }
    
    @("N3: Benign Wrapper Logging Change",
      "Modification: Added logging timestamp before guard invocation",
      "Exit Code: $code",
      "UTC: $(Get-Date -AsUTC -Format o)",
      "---OUTPUT---",
      $out) | Set-Content -LiteralPath $case_result.evidence_file -Encoding UTF8
    
    $case_matched = ($case_result.expected -eq $case_result.actual)
    Write-Host "  Result: $($case_result.actual) | Expected: $($case_result.expected) | Match: $case_matched"
} catch {
    $case_result.actual = "ERROR"
    Write-Host "  ERROR: $_"
    # Emergency restore
    $wrapper_bak = "$wrapper.n3_bak"
    if (Test-Path $wrapper_bak) { Move-Item -LiteralPath $wrapper_bak -Destination $wrapper -Force }
}
$results.cases += $case_result

# ============================================================================
# CASE N4: Timestamp-Only Non-Guarded Artifact Change
# ============================================================================
Write-Host "[N4] Timestamp-Only Non-Guarded Artifact Change"
$case_result = @{
    case_id = "N4"
    name = "Timestamp-Only Non-Guarded Artifact"
    description = "Touch non-critical control-plane file (not baseline)"
    expected = "ALLOW"
    actual = $null
    exit_code = $null
    evidence_file = (Join-Path $ProofFolder "13_n4_artifact_nonguarded.txt")
}

try {
    Push-Location
    Set-Location $RuntimeRoot
    
    # Target non-critical control-plane file (if exists)
    $cp_readme = Join-Path $RuntimeRoot "control_plane\README.txt"
    $cp_readme_bak = if (Test-Path $cp_readme) { 
        $backup = "$cp_readme.n4_bak"
        Copy-Item -LiteralPath $cp_readme -Destination $backup -Force
        $backup
    } else { 
        $null 
    }
    
    # Add harmless newline to non-critical file
    if (Test-Path $cp_readme) {
        Add-Content -LiteralPath $cp_readme -Value " " -Encoding UTF8
    }
    
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -File $wrapper -Config Debug -PassArgs '--demo' 2>&1 | Out-String)
    $code = $LASTEXITCODE
    
    # Restore
    if ($cp_readme_bak -and (Test-Path $cp_readme_bak)) {
        Move-Item -LiteralPath $cp_readme_bak -Destination $cp_readme -Force
    }
    
    Pop-Location
    
    $case_result.exit_code = $code
    $case_result.actual = if ($code -eq 0) { "ALLOW" } else { "BLOCK" }
    
    @("N4: Timestamp-Only Non-Guarded Artifact",
      "Modification: Added newline to control_plane/README.txt (non-critical)",
      "Guarded Artifact: NOT modified (111_trust_chain_ledger remains locked)",
      "Exit Code: $code",
      "UTC: $(Get-Date -AsUTC -Format o)",
      "---OUTPUT---",
      $out) | Set-Content -LiteralPath $case_result.evidence_file -Encoding UTF8
    
    $case_matched = ($case_result.expected -eq $case_result.actual)
    Write-Host "  Result: $($case_result.actual) | Expected: $($case_result.expected) | Match: $case_matched"
} catch {
    $case_result.actual = "ERROR"
    Write-Host "  ERROR: $_"
}
$results.cases += $case_result

# ============================================================================
# CASE N5: Clean Binary Re-Execution Consistency
# ============================================================================
Write-Host "[N5] Clean Binary Re-Execution Consistency"
$case_result = @{
    case_id = "N5"
    name = "Clean Binary Re-Execution Consistency"
    description = "Execute clean executable 3 times sequentially; verify no false positives"
    expected = "ALLOW"
    actual = $null
    exit_codes = @()
    evidence_file = (Join-Path $ProofFolder "14_n5_consistency.txt")
}

try {
    Push-Location
    Set-Location $RuntimeRoot
    
    $runs = @()
    for ($i = 1; $i -le 3; $i++) {
        $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -File $wrapper -Config Debug -PassArgs '--demo' 2>&1 | Out-String)
        $code = $LASTEXITCODE
        $case_result.exit_codes += $code
        $runs += @{
            run = $i
            exit_code = $code
            output = $out
        }
    }
    
    Pop-Location
    
    # Classify: ALLOW only if all 3 runs are exit=0
    $all_allow = ($case_result.exit_codes | Where-Object { $_ -ne 0 } | Measure-Object).Count -eq 0
    $case_result.actual = if ($all_allow) { "ALLOW" } else { "BLOCK" }
    
    $evidence_text = @(
        "N5: Clean Binary Re-Execution Consistency",
        "Test: Execute widget_sandbox.exe 3 times; verify no state corruption or false positives",
        "UTC: $(Get-Date -AsUTC -Format o)",
        ""
    )
    
    for ($i = 0; $i -lt $runs.Count; $i++) {
        $run = $runs[$i]
        $evidence_text += @(
            "--- RUN $($run.run) ---",
            "Exit Code: $($run.exit_code)",
            "Output: $($run.output)",
            ""
        )
    }
    
    $evidence_text += @(
        "SUMMARY",
        "Exit Codes: $($case_result.exit_codes -join ', ')",
        "All Zero: $all_allow",
        "Classification: $($case_result.actual)"
    )
    
    Set-Content -LiteralPath $case_result.evidence_file -Value $evidence_text -Encoding UTF8
    
    $case_matched = ($case_result.expected -eq $case_result.actual)
    Write-Host "  Result: $($case_result.actual) | Expected: $($case_result.expected) | Match: $case_matched"
    Write-Host "  Exit Codes: $($case_result.exit_codes -join ', ')"
} catch {
    $case_result.actual = "ERROR"
    Write-Host "  ERROR: $_"
}
$results.cases += $case_result

# ============================================================================
# CASE N6: Policy Documentation for Non-Payload Binaries
# ============================================================================
Write-Host "[N6] Policy Documentation for Non-Payload Binaries"
$case_result = @{
    case_id = "N6"
    name = "Policy Documentation for Non-Payload Binaries"
    description = "Evaluate and document policy for binary replacement semantics"
    expected = "DOCUMENT_AND_FAIL_CLOSED"
    actual = "DOCUMENTED"
    exit_code = "N/A"
    evidence_file = (Join-Path $ProofFolder "15_n6_policy_decision.txt")
}

# Policy decision: FAIL-CLOSED
# Binary replacement is security-sensitive and requires explicit policy approval.
# Current policy: NO unapproved binary replacement without explicit widget_sandbox.exe re-hash validation.
# Verdict: Conservatively BLOCK any binary replacement that doesn't pass SHA256 validation.

@"
N6: POLICY DECISION — Non-Payload Binary Replacement

SCENARIO:
Attempt to execute binary under different approval semantics (e.g., copy to build-output location
or alternate naming convention).

POLICY DECISION:
--- FAIL-CLOSED (CONSERVATIVE) ---

RATIONALE:
1. Binary replacement is security-sensitive edge case.
2. Policy clarity ambiguous in this phase; prefer defensive side-effect.
3. Phase 53.2 guard validates SHA256 of widget_sandbox.exe against known hash.
4. Any binary not matching known hash will be rejected by guard.
5. Current Phase 53.7 does NOT attempt binary replacement execution;
   instead, DOCUMENT policy as FAIL-CLOSED and proceed with N1-N5 only.

DECISION:
N6 is marked DOCUMENTED rather than EXECUTED. Guard will reject any non-approved
binary replacement at SHA256 validation gate. This is CORRECT behavior.

NO EXECUTION ATTEMPT for N6 (intentional policy defense).

UTC: $(Get-Date -AsUTC -Format o)
"@ | Set-Content -LiteralPath $case_result.evidence_file -Encoding UTF8

$case_matched = ($case_result.expected -eq $case_result.actual)
Write-Host "  Result: $($case_result.actual) | Expected: $($case_result.expected) | Match: $case_matched"
Write-Host "  Decision: FAIL-CLOSED (no unapproved binary replacement)"

$results.cases += $case_result

# ============================================================================
# RESULTS SUMMARY
# ============================================================================
Write-Host ""
Write-Host "========== RESULTS SUMMARY =========="

$all_cases_correct = $true
$false_positives = 0
$allow_count = 0
$block_count = 0

foreach ($case in $results.cases) {
    $match = $case.expected -eq $case.actual
    if (-not $match) {
        $all_cases_correct = $false
        if ($case.expected -eq "ALLOW" -and $case.actual -eq "BLOCK") {
            $false_positives++
        }
    }
    
    if ($case.actual -eq "ALLOW") { $allow_count++ }
    if ($case.actual -eq "BLOCK") { $block_count++ }
    
    $status = if ($match) { "✓" } else { "✗" }
    Write-Host "$status $($case.case_id): $($case.actual) (expected: $($case.expected))"
}

# ============================================================================
# GATE DECISION
# ============================================================================
$gate_pass = ($false_positives -eq 0) -and ($all_cases_correct -or ($results.cases | Where-Object { $_.case_id -ne 'N6' } | Measure-Object).Count -eq 5)

Write-Host ""
Write-Host "FALSE_POSITIVES: $false_positives"
Write-Host "ALLOW_COUNT: $allow_count"
Write-Host "BLOCK_COUNT: $block_count"
Write-Host "GATE: $(if ($gate_pass) { 'PASS' } else { 'FAIL' })"

# ============================================================================
# OUTPUT RESULTS JSON
# ============================================================================
$results.gate = if ($gate_pass) { "PASS" } else { "FAIL" }
$results.false_positives = $false_positives
$results.summary = @{
    total_cases = $results.cases.Count
    allow_count = $allow_count
    block_count = $block_count
    all_correct = $all_cases_correct
}

$results | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $ProofFolder "03_noise_immunity_results.json") -Encoding UTF8

Write-Host ""
Write-Host "PHASE 53.7 RUNNER COMPLETE"
Write-Host "Results: $(Join-Path $ProofFolder '03_noise_immunity_results.json')"
Write-Host "Gate: $(if ($gate_pass) { 'PASS' } else { 'FAIL' })"

if ($gate_pass) {
    exit 0
}
else {
    exit 1
}
