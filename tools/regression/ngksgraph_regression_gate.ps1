# NGKsGraph Regression Gate Runner
# Executes real NGKsGraph checks against Baseline v1 and fails closed on regressions.

param(
    [string]$BaselinePath = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_proof\ngksgraph_cert_baseline_v1_20260322_141949",
    [string]$GatePath = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_proof\ngksgraph_regression_gate_20260322_143639",
    [string]$InjectRegressionCapability = ""
)

$ErrorActionPreference = "Stop"

function Write-GateLog {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] [$Level] $Message"
}

function Test-BaselineExists {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        Write-GateLog "Baseline path not found: $Path" "ERROR"
        return $false
    }

    $requiredFiles = @(
        "11_baseline_inventory.json",
        "20_baseline_contract.txt",
        "40_regression_expectations.json",
        "41_certification_capabilities.json"
    )

    foreach ($file in $requiredFiles) {
        $filePath = Join-Path $Path $file
        if (-not (Test-Path $filePath)) {
            Write-GateLog "Required baseline file missing: $file" "ERROR"
            return $false
        }
    }

    return $true
}

function Load-BaselineDefinition {
    param([string]$Path)

    $regressionPath = Join-Path $Path "40_regression_expectations.json"
    $regression = Get-Content $regressionPath -Raw | ConvertFrom-Json

    return @{
        baseline_manifest = $regression.baseline_manifest
        required_capabilities = $regression.required_capabilities
    }
}

function Get-NGKsGraphExecutable {
    $candidate = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\ngksgraph.exe"
    if (Test-Path $candidate) {
        return $candidate
    }

    $cmd = Get-Command ngksgraph -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        return $cmd.Source
    }

    return $null
}

function Invoke-NGKsGraph {
    param(
        [string]$Executable,
        [string[]]$Arguments,
        [string]$OutputFile
    )

    $output = & $Executable @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    $text = ""
    if ($null -ne $output) {
        $text = ($output | Out-String)
    }

    if ($OutputFile) {
        $text | Out-File -FilePath $OutputFile -Encoding utf8 -Force
    }

    return @{
        exit_code = $exitCode
        output = $text
    }
}

function New-CapabilityResult {
    param([object]$Capability)

    return @{
        capability_id = $Capability.capability_id
        name = $Capability.name
        severity = $Capability.severity
        mandatory = [bool]$Capability.mandatory
        expected_state = $Capability.expected_gate_state
        measured_state = "UNKNOWN"
        status = "UNKNOWN"
        details = ""
        break_conditions_triggered = @()
    }
}

function Get-RegexValue {
    param(
        [string]$Text,
        [string]$Pattern
    )

    $m = [regex]::Match($Text, $Pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if ($m.Success -and $m.Groups.Count -gt 1) {
        return $m.Groups[1].Value.Trim()
    }
    return $null
}

function Test-CapabilityReal {
    param(
        [object]$Capability,
        [string]$Executable,
        [string]$GatePath,
        [string]$InjectRegressionCapability
    )

    $result = New-CapabilityResult -Capability $Capability
    $capId = $Capability.capability_id

    if ($InjectRegressionCapability -and ($InjectRegressionCapability -ieq $capId)) {
        $result.measured_state = "FAIL"
        $result.status = "FAIL"
        $result.details = "Injected controlled regression for capability $capId"
        $result.break_conditions_triggered = @("INJECTED_CONTROLLED_REGRESSION")
        return $result
    }

    $repoA = "C:\Users\suppo\Desktop\NGKsSystems\NGKs_Content_Curator"
    $repoB = "C:\Users\suppo\Desktop\NGKsSystems\NGKsMailcpp"

    switch ($capId) {
        "DRIFT_DETECTION" {
            $run = Invoke-NGKsGraph -Executable $Executable -Arguments @("drift", "--project", $repoA, "--output-format", "text") -OutputFile (Join-Path $GatePath "runtime_drift.txt")
            $hasSummary = $run.output -match "DRIFT SUMMARY"
            $hasReviewIndex = $run.output -match "REVIEW_INDEX="
            $exitValid = ($run.exit_code -eq 0 -or $run.exit_code -eq 1)

            if ($exitValid -and $hasSummary -and $hasReviewIndex) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Real drift command executed; summary and review index present"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Drift command validation failed (exit=$($run.exit_code), summary=$hasSummary, review=$hasReviewIndex)"
                $result.break_conditions_triggered = @("missing_targets_not_detected")
            }
        }

        "TOOL_DRIVEN_SYNC" {
            $syncOut = Join-Path $GatePath "runtime_sync_proposal.json"
            Remove-Item $syncOut -ErrorAction SilentlyContinue
            $run = Invoke-NGKsGraph -Executable $Executable -Arguments @("sync", "--project", $repoA, "--out", $syncOut, "--policy", "balanced") -OutputFile (Join-Path $GatePath "runtime_sync.txt")
            $exists = Test-Path $syncOut
            $hasNoop = $run.output -match "SYNC_NOOP|SYNC_SUMMARY"
            $hasPolicy = $run.output -match "Policy:\s+balanced"

            if ($run.exit_code -eq 0 -and $exists -and $hasNoop -and $hasPolicy) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Real sync command executed in dry-run mode with auditable proposal output"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Sync command validation failed (exit=$($run.exit_code), proposal=$exists, noop_or_summary=$hasNoop, policy=$hasPolicy)"
                $result.break_conditions_triggered = @("apply_without_proposal")
            }
        }

        "SAFETY_NO_OVERREACH" {
            $syncLogPath = Join-Path $GatePath "runtime_sync.txt"
            $syncText = if (Test-Path $syncLogPath) { Get-Content $syncLogPath -Raw } else { "" }
            $hasRefusal = $syncText -match "ambiguity refusal|class=refuse|GOV_REFUSE_AMBIGUOUS"

            if ($hasRefusal) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Safety refusal class detected in real sync execution"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Expected safety refusal markers not found in sync output"
                $result.break_conditions_triggered = @("ambiguous_case_NOT_blocked")
            }
        }

        "EXPLAINABILITY" {
            $syncLogPath = Join-Path $GatePath "runtime_sync.txt"
            $syncText = if (Test-Path $syncLogPath) { Get-Content $syncLogPath -Raw } else { "" }
            $hasReason = $syncText -match "reason="
            $hasMessage = $syncText -match "message="
            $hasConfidence = $syncText -match "confidence"

            if ($hasReason -and $hasMessage -and $hasConfidence) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Explainability fields found in real sync governance output"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Explainability markers missing (reason=$hasReason, message=$hasMessage, confidence=$hasConfidence)"
                $result.break_conditions_triggered = @("missing_reasoning")
            }
        }

        "PERSISTENT_REVIEW" {
            $syncLogPath = Join-Path $GatePath "runtime_sync.txt"
            $syncText = if (Test-Path $syncLogPath) { Get-Content $syncLogPath -Raw } else { "" }
            $reviewRoot = Get-RegexValue -Text $syncText -Pattern "REVIEW_ROOT=([^\r\n]+)"
            $reviewIndex = Get-RegexValue -Text $syncText -Pattern "REVIEW_INDEX=([^\r\n]+)"
            $rootExists = ($reviewRoot -and (Test-Path $reviewRoot))
            $indexExists = ($reviewIndex -and (Test-Path $reviewIndex))

            if ($rootExists -and $indexExists) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Review workflow artifacts persisted and accessible"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Review workflow artifacts missing (root=$rootExists, index=$indexExists)"
                $result.break_conditions_triggered = @("Review trail incomplete or corrupted")
            }
        }

        "CONFIDENCE_GOVERNANCE" {
            $syncLogPath = Join-Path $GatePath "runtime_sync.txt"
            $syncText = if (Test-Path $syncLogPath) { Get-Content $syncLogPath -Raw } else { "" }
            $hasGov = $syncText -match "CONFIDENCE GOVERNANCE"

            if ($hasGov) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Confidence governance section present"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Confidence governance section missing"
            }
        }

        "POLICY_PROFILES" {
            $syncLogPath = Join-Path $GatePath "runtime_sync.txt"
            $syncText = if (Test-Path $syncLogPath) { Get-Content $syncLogPath -Raw } else { "" }
            $profilesPath = Get-RegexValue -Text $syncText -Pattern "REVIEW_POLICY_PROFILES=([^\r\n]+)"
            $profilesExists = ($profilesPath -and (Test-Path $profilesPath))

            if ($profilesExists) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Policy profiles artifact present"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Policy profiles artifact missing"
            }
        }

        "BATCH_GOVERNANCE" {
            $batchOut = Join-Path $GatePath "runtime_batch_sync.json"
            Remove-Item $batchOut -ErrorAction SilentlyContinue
            $run = Invoke-NGKsGraph -Executable $Executable -Arguments @("batch-sync", "--project", $repoA, "--project", $repoB, "--out", $batchOut, "--policy", "balanced", "--transaction-mode", "all-or-nothing") -OutputFile (Join-Path $GatePath "runtime_batch_sync.txt")

            $exists = Test-Path $batchOut
            $batchJson = $null
            if ($exists) {
                $batchJson = Get-Content $batchOut -Raw | ConvertFrom-Json
            }
            $modeValid = ($null -ne $batchJson -and $batchJson.transaction_mode -eq "all-or-nothing")
            $repoCountValid = ($null -ne $batchJson -and $batchJson.repo_results.Count -ge 2)

            if ($run.exit_code -eq 0 -and $exists -and $modeValid -and $repoCountValid) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Batch governance executed with all-or-nothing transaction mode"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Batch governance validation failed (exit=$($run.exit_code), out=$exists, mode=$modeValid, repos=$repoCountValid)"
                $result.break_conditions_triggered = @("Batch governance allows partial commits")
            }
        }

        "TRANSACTION_SAFETY" {
            $batchOut = Join-Path $GatePath "runtime_batch_sync.json"
            if (-not (Test-Path $batchOut)) {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Batch summary missing for transaction safety validation"
                $result.break_conditions_triggered = @("transaction_artifacts_missing")
                break
            }

            $batchJson = Get-Content $batchOut -Raw | ConvertFrom-Json
            $allowedOutcomes = @("no_mutation", "applied", "rolled_back")
            $outcomeOk = $allowedOutcomes -contains [string]$batchJson.transaction_outcome
            $txPathOk = ($batchJson.batch_transaction_path -and (Test-Path $batchJson.batch_transaction_path))
            $rollbackPathOk = ($batchJson.rollback_summary_path -and (Test-Path $batchJson.rollback_summary_path))

            if ($outcomeOk -and $txPathOk -and $rollbackPathOk) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Transaction artifacts and outcome validated"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Transaction validation failed (outcome=$outcomeOk, txPath=$txPathOk, rollbackPath=$rollbackPathOk)"
                $result.break_conditions_triggered = @("Transaction safety compromised")
            }
        }

        "IDEMPOTENCE" {
            $run1 = Invoke-NGKsGraph -Executable $Executable -Arguments @("drift", "--project", $repoB, "--output-format", "text") -OutputFile (Join-Path $GatePath "runtime_idempotence_run1.txt")
            $run2 = Invoke-NGKsGraph -Executable $Executable -Arguments @("drift", "--project", $repoB, "--output-format", "text") -OutputFile (Join-Path $GatePath "runtime_idempotence_run2.txt")

            $u1 = Get-RegexValue -Text $run1.output -Pattern "Undeclared targets:\s+([0-9]+)"
            $u2 = Get-RegexValue -Text $run2.output -Pattern "Undeclared targets:\s+([0-9]+)"
            $summary1 = $run1.output -match "DRIFT SUMMARY"
            $summary2 = $run2.output -match "DRIFT SUMMARY"
            $stable = ($run1.exit_code -eq $run2.exit_code -and $u1 -eq $u2)

            if ($summary1 -and $summary2 -and $stable) {
                $result.measured_state = "PASS"
                $result.status = "PASS"
                $result.details = "Drift reruns stable (exit and undeclared count consistent)"
            }
            else {
                $result.measured_state = "FAIL"
                $result.status = "FAIL"
                $result.details = "Idempotence check failed (exit1=$($run1.exit_code), exit2=$($run2.exit_code), u1=$u1, u2=$u2)"
                $result.break_conditions_triggered = @("Different_results_on_rerun")
            }
        }

        default {
            $result.measured_state = "FAIL"
            $result.status = "FAIL"
            $result.details = "Unknown capability ID: $capId"
            if ($result.mandatory) {
                $result.break_conditions_triggered = @("Unknown mandatory capability")
            }
        }
    }

    return $result
}

function Evaluate-Gate {
    param([array]$CapabilityResults)

    $mandatoryFailed = @()
    $optionalFailed = @()
    $passed = 0

    foreach ($r in $CapabilityResults) {
        if ($r.status -eq "PASS") {
            $passed++
        }
        elseif ($r.mandatory) {
            $mandatoryFailed += $r.capability_id
        }
        else {
            $optionalFailed += $r.capability_id
        }
    }

    $verdict = "PASS"
    $reason = "All mandatory capabilities validated against baseline"

    if ($mandatoryFailed.Count -gt 0) {
        $verdict = "FAIL"
        $reason = "Critical regression(s) detected: $($mandatoryFailed -join ', ')"
    }

    return @{
        total = $CapabilityResults.Count
        passed = $passed
        failed = ($CapabilityResults.Count - $passed)
        mandatory_failed = $mandatoryFailed
        optional_failed = $optionalFailed
        verdict = $verdict
        reason = $reason
    }
}

# Main execution
Write-GateLog "========================================" "INFO"
Write-GateLog "NGKsGraph Regression Gate Started" "INFO"
Write-GateLog "========================================" "INFO"
Write-GateLog "Baseline: $BaselinePath" "INFO"
Write-GateLog "Gate Path: $GatePath" "INFO"
if ($InjectRegressionCapability) {
    Write-GateLog "Injected regression capability: $InjectRegressionCapability" "WARN"
}

if (-not (Test-BaselineExists -Path $BaselinePath)) {
    Write-GateLog "GATE FAILED: Baseline verification failed" "ERROR"
    exit 1
}

$baseline = Load-BaselineDefinition -Path $BaselinePath
Write-GateLog "Baseline loaded: $($baseline.baseline_manifest.freeze_id)" "PASS"

$ngksgraphExe = Get-NGKsGraphExecutable
if (-not $ngksgraphExe) {
    Write-GateLog "GATE FAILED: ngksgraph executable not found" "ERROR"
    exit 1
}
Write-GateLog "Using executable: $ngksgraphExe" "PASS"

$capabilityResults = @()
foreach ($cap in $baseline.required_capabilities) {
    Write-GateLog "Testing capability: $($cap.capability_id)" "INFO"
    $res = Test-CapabilityReal -Capability $cap -Executable $ngksgraphExe -GatePath $GatePath -InjectRegressionCapability $InjectRegressionCapability
    $capabilityResults += $res
    Write-GateLog "  Result: $($res.status) - $($res.details)" $(if ($res.status -eq "PASS") { "PASS" } else { "ERROR" })
}

$evaluation = Evaluate-Gate -CapabilityResults $capabilityResults

$report = @{
    gate_execution = @{
        timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        baseline_version = $baseline.baseline_manifest.version
        baseline_id = $baseline.baseline_manifest.freeze_id
        gate_status = $evaluation.verdict
        injected_regression = $InjectRegressionCapability
    }
    capability_results = $capabilityResults
    regression_summary = @{
        total_capabilities = $evaluation.total
        passed = $evaluation.passed
        failed = $evaluation.failed
        critical_regressions = $evaluation.mandatory_failed
        optional_degradations = $evaluation.optional_failed
    }
    gate_verdict = $evaluation.verdict
    gate_reason = $evaluation.reason
}

$reportPath = Join-Path $GatePath "gate_execution_report.json"
$report | ConvertTo-Json -Depth 7 | Out-File -FilePath $reportPath -Encoding utf8 -Force

Write-GateLog "========================================" "INFO"
Write-GateLog "Total: $($evaluation.total)" "INFO"
Write-GateLog "Passed: $($evaluation.passed)" "INFO"
Write-GateLog "Failed: $($evaluation.failed)" "INFO"
Write-GateLog "Verdict: $($evaluation.verdict)" "INFO"
Write-GateLog "Reason: $($evaluation.reason)" "INFO"
Write-GateLog "Report: $reportPath" "INFO"
Write-GateLog "========================================" "INFO"

if ($evaluation.verdict -eq "PASS") {
    exit 0
}

exit 1
