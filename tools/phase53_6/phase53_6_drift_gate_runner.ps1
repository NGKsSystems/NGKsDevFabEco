#Requires -Version 5.0
param(
    [Parameter(Mandatory=$true)]
    [string]$ProofFolder,
    [Parameter(Mandatory=$true)]
    [string]$ReferenceManifestPath,
    [string]$RuntimeRoot = 'C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

if (-not (Test-Path -LiteralPath $ProofFolder -PathType Container)) {
    throw "ProofFolder not found: $ProofFolder"
}
if (-not (Test-Path -LiteralPath $ReferenceManifestPath -PathType Leaf)) {
    throw "ReferenceManifestPath not found: $ReferenceManifestPath"
}

$phase535Runner = Join-Path (Split-Path -Parent $PSScriptRoot) 'phase53_5\phase53_5_attack_matrix_runner.ps1'
if (-not (Test-Path -LiteralPath $phase535Runner -PathType Leaf)) {
    throw "phase53_5 runner missing: $phase535Runner"
}

# Execute current live matrix using existing certified runner.
& $phase535Runner -ProofFolder $ProofFolder -RuntimeRoot $RuntimeRoot | Out-Null

$liveResultsPath = Join-Path $ProofFolder '03_attack_matrix_results.json'
if (-not (Test-Path -LiteralPath $liveResultsPath -PathType Leaf)) {
    throw "Live results missing after runner execution: $liveResultsPath"
}

$reference = Get-Content -LiteralPath $ReferenceManifestPath -Raw | ConvertFrom-Json
$live = Get-Content -LiteralPath $liveResultsPath -Raw | ConvertFrom-Json

$referenceById = @{}
foreach ($c in $reference.cases) { $referenceById[$c.attack_id] = $c }
$liveById = @{}
foreach ($c in $live) { $liveById[$c.attack_id] = $c }

$classificationDrift = New-Object System.Collections.Generic.List[object]
$exitCodeDrift = New-Object System.Collections.Generic.List[object]
$missingEvidenceDrift = New-Object System.Collections.Generic.List[object]
$missingCaseDrift = New-Object System.Collections.Generic.List[object]
$extraCaseDrift = New-Object System.Collections.Generic.List[object]

foreach ($refCase in $reference.cases) {
    if (-not $liveById.ContainsKey($refCase.attack_id)) {
        $missingCaseDrift.Add([pscustomobject]@{ attack_id = $refCase.attack_id; expected_scenario = $refCase.scenario_name })
        continue
    }

    $liveCase = $liveById[$refCase.attack_id]

    if ([string]$liveCase.actual_result -ne [string]$refCase.expected_result) {
        $classificationDrift.Add([pscustomobject]@{
            attack_id = $refCase.attack_id
            expected_result = $refCase.expected_result
            actual_result = $liveCase.actual_result
        })
    }

    $exitCode = [int]$liveCase.exit_code
    $rule = [string]$refCase.exit_code_rule
    $exitOk = $true
    if ($rule -eq 'allow_zero') {
        $exitOk = ($exitCode -eq 0)
    }
    elseif ($rule -eq 'block_nonzero') {
        $exitOk = ($exitCode -ne 0)
    }

    if (-not $exitOk) {
        $exitCodeDrift.Add([pscustomobject]@{
            attack_id = $refCase.attack_id
            exit_code_rule = $rule
            actual_exit_code = $exitCode
        })
    }

    $requiredEvidence = [string]$refCase.required_evidence_file
    if ([string]::IsNullOrWhiteSpace($requiredEvidence)) {
        $missingEvidenceDrift.Add([pscustomobject]@{
            attack_id = $refCase.attack_id
            reason = 'reference_required_evidence_missing'
        })
    }
    else {
        if ([string]$liveCase.evidence_file -ne $requiredEvidence) {
            $missingEvidenceDrift.Add([pscustomobject]@{
                attack_id = $refCase.attack_id
                reason = 'evidence_filename_mismatch'
                expected_evidence_file = $requiredEvidence
                actual_evidence_file = [string]$liveCase.evidence_file
            })
        }

        $evidencePath = Join-Path $ProofFolder $requiredEvidence
        if (-not (Test-Path -LiteralPath $evidencePath -PathType Leaf)) {
            $missingEvidenceDrift.Add([pscustomobject]@{
                attack_id = $refCase.attack_id
                reason = 'evidence_file_missing_on_disk'
                expected_evidence_file = $requiredEvidence
            })
        }
    }
}

foreach ($liveCase in $live) {
    if (-not $referenceById.ContainsKey($liveCase.attack_id)) {
        $extraCaseDrift.Add([pscustomobject]@{ attack_id = $liveCase.attack_id; scenario_name = $liveCase.scenario_name })
    }
}

$driftReport = [ordered]@{
    matrix_name = 'phase53_6_runtime_seal_drift_gate'
    generated_utc = [DateTime]::UtcNow.ToString('o')
    reference_manifest = $ReferenceManifestPath
    live_results = (Join-Path $ProofFolder '03_live_results.json')
    classification_drift = $classificationDrift
    exit_code_drift = $exitCodeDrift
    missing_evidence_drift = $missingEvidenceDrift
    missing_case_drift = $missingCaseDrift
    extra_case_drift = $extraCaseDrift
}

$live | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $ProofFolder '03_live_results.json') -Encoding UTF8
$driftReport | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ProofFolder '04_drift_report.json') -Encoding UTF8

$hasDrift = (
    $classificationDrift.Count -gt 0 -or
    $exitCodeDrift.Count -gt 0 -or
    $missingEvidenceDrift.Count -gt 0 -or
    $missingCaseDrift.Count -gt 0 -or
    $extraCaseDrift.Count -gt 0
)

@(
    'PHASE53.6 DRIFT CHECK',
    "UTC=$([DateTime]::UtcNow.ToString('o'))",
    "CLASSIFICATION_DRIFT_COUNT=$($classificationDrift.Count)",
    "EXIT_CODE_DRIFT_COUNT=$($exitCodeDrift.Count)",
    "MISSING_EVIDENCE_DRIFT_COUNT=$($missingEvidenceDrift.Count)",
    "MISSING_CASE_DRIFT_COUNT=$($missingCaseDrift.Count)",
    "EXTRA_CASE_DRIFT_COUNT=$($extraCaseDrift.Count)",
    ('DRIFT_STATUS=' + $(if ($hasDrift) { 'FAIL' } else { 'PASS' }))
) | Set-Content -LiteralPath (Join-Path $ProofFolder '97_drift_check.txt') -Encoding UTF8

if ($hasDrift) {
    exit 1
}
exit 0
