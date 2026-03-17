$s = Get-Content _proof/_latest_repair_state.json -Raw | ConvertFrom-Json
$proof = $s.proof
$runpf = $s.runpf
$logDir = $s.logDir

$cp = Join-Path $runpf "control_plane"
$a69 = Join-Path $cp "69_predictive_calibration_propagation.json"
$a72 = Join-Path $cp "72_certification_control_plane_summary.json"
$a73 = Join-Path $cp "73_operational_control_plane_summary.json"
$a74 = Join-Path $cp "74_explain_control_plane_summary.json"
$j72 = if (Test-Path $a72) { Get-Content $a72 -Raw | ConvertFrom-Json } else { $null }
$j73 = if (Test-Path $a73) { Get-Content $a73 -Raw | ConvertFrom-Json } else { $null }
$j74 = if (Test-Path $a74) { Get-Content $a74 -Raw | ConvertFrom-Json } else { $null }
$e72 = if ($j72) { ($j72.evidence_refs -join ", ") } else { "" }
$e73 = if ($j73) { ($j73.evidence_refs -join ", ") } else { "" }
$e74 = if ($j74) { ($j74.evidence_refs -join ", ") } else { "" }
$recurrence = $false
$calibration = $false
if ($j73) {
  $recurrence = [bool]$j73.control_plane_context.propagation.recurrence_present
  $calibration = [bool]$j73.control_plane_context.propagation.calibration_present
}

$certExit = (Get-Content (Join-Path $logDir "03_run_validation_and_certify.exit.txt") -Raw).Trim()
$predExit = (Get-Content (Join-Path $logDir "04_predict_risk.exit.txt") -Raw).Trim()
$histExit = (Get-Content (Join-Path $logDir "06_history_trends.exit.txt") -Raw).Trim()
$explExit = (Get-Content (Join-Path $logDir "05_explain_rebuild.exit.txt") -Raw).Trim()
$buildExit = (Get-Content (Join-Path $logDir "01_build.exit.txt") -Raw).Trim()
$planExit = (Get-Content (Join-Path $logDir "02_plan_validation.exit.txt") -Raw).Trim()
$propExit = (Get-Content (Join-Path $logDir "07_propagation.exit.txt") -Raw).Trim()
$replExit = (Get-Content (Join-Path $logDir "08_replay_validation.exit.txt") -Raw).Trim()

$certPass = (Test-Path $a72) -and ($e72 -match "58_decision_envelope_chain.json") -and ($e72 -match "65_outcome_feedback_chain.json") -and ($e72 -match "67_confidence_propagation.json")
$operPass = (Test-Path $a73) -and ($e73 -match "58_decision_envelope_chain.json") -and ($e73 -match "65_outcome_feedback_chain.json")
$wfPass = (Test-Path (Join-Path $runpf "workflow/150_primary_workflow_recommendation.json")) -and (Test-Path $a73) -and ($e73 -match "workflow/150_primary_workflow_recommendation.json")
$histPass = (Test-Path (Join-Path $runpf "history/52_regression_trend_analysis.json")) -and (Test-Path $a73) -and $recurrence
$predPass = (Test-Path (Join-Path $runpf "predictive/64_prediction_classification.json")) -and (Test-Path $a73) -and ($e73 -match "69_predictive_calibration_propagation.json") -and ((Test-Path $a69) -or $calibration)
$expPass = (Test-Path $a74) -and ($e74 -match "58_decision_envelope_chain.json") -and ($e74 -match "65_outcome_feedback_chain.json") -and ($e74 -match "67_confidence_propagation.json") -and ($e74 -match "70_certification_impact_propagation.json")
$replay = if (Test-Path (Join-Path $logDir "08_replay_validation.stdout.txt")) { Get-Content (Join-Path $logDir "08_replay_validation.stdout.txt") -Raw } else { "" }
$detPass = ($replay -match '"decision"') -and ($replay -match '"status"\s*:\s*"PASS"')

@(
  "runpf=" + $runpf,
  "command=python -m ngksdevfabric.ngk_fabric.main run-validation-and-certify --project " + $s.repo + " --execution-policy BALANCED --component ngksdevfabric --pf " + $runpf,
  "exit_code=" + $certExit,
  "stdout_log=" + (Join-Path $logDir "03_run_validation_and_certify.stdout.txt"),
  "stderr_log=" + (Join-Path $logDir "03_run_validation_and_certify.stderr.txt"),
  "artifact_72_exists=" + (Test-Path $a72),
  "artifact_72_evidence_refs=" + $e72,
  "certification_integration_pass=" + $certPass
) | Set-Content -Path (Join-Path $proof "05_certification_integration_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=python -m ngksdevfabric.ngk_fabric.main run-validation-and-certify --project " + $s.repo + " --execution-policy BALANCED --component ngksdevfabric --pf " + $runpf,
  "exit_code=" + $certExit,
  "stdout_log=" + (Join-Path $logDir "03_run_validation_and_certify.stdout.txt"),
  "stderr_log=" + (Join-Path $logDir "03_run_validation_and_certify.stderr.txt"),
  "artifact_73_exists=" + (Test-Path $a73),
  "artifact_73_evidence_refs=" + $e73,
  "operational_integration_pass=" + $operPass
) | Set-Content -Path (Join-Path $proof "06_operational_flow_integration_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=python -m ngksdevfabric.ngk_fabric.main run-validation-and-certify --project " + $s.repo + " --execution-policy BALANCED --component ngksdevfabric --pf " + $runpf,
  "exit_code=" + $certExit,
  "workflow_primary_exists=" + (Test-Path (Join-Path $runpf "workflow/150_primary_workflow_recommendation.json")),
  "artifact_73_exists=" + (Test-Path $a73),
  "artifact_73_evidence_refs=" + $e73,
  "workflow_integration_pass=" + $wfPass
) | Set-Content -Path (Join-Path $proof "07_workflow_recommendation_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=python -c analyze_historical_trends(...)" ,
  "exit_code=" + $histExit,
  "stdout_log=" + (Join-Path $logDir "06_history_trends.stdout.txt"),
  "stderr_log=" + (Join-Path $logDir "06_history_trends.stderr.txt"),
  "history_trend_exists=" + (Test-Path (Join-Path $runpf "history/52_regression_trend_analysis.json")),
  "propagation_recurrence_present=" + $recurrence,
  "history_trend_integration_pass=" + $histPass
) | Set-Content -Path (Join-Path $proof "08_history_trend_integration_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=python -m ngksdevfabric.ngk_fabric.main predict-risk --project " + $s.repo + " --component ngksdevfabric --pf " + $runpf,
  "exit_code=" + $predExit,
  "stdout_log=" + (Join-Path $logDir "04_predict_risk.stdout.txt"),
  "stderr_log=" + (Join-Path $logDir "04_predict_risk.stderr.txt"),
  "predictive_classification_exists=" + (Test-Path (Join-Path $runpf "predictive/64_prediction_classification.json")),
  "artifact_73_evidence_refs=" + $e73,
  "propagation_calibration_present=" + $calibration,
  "predictive_risk_integration_pass=" + $predPass
) | Set-Content -Path (Join-Path $proof "09_predictive_risk_integration_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=python -m ngksdevfabric.ngk_fabric.main explain --project-path " + $s.repo + " --pf " + $runpf + " rebuild",
  "exit_code=" + $explExit,
  "stdout_log=" + (Join-Path $logDir "05_explain_rebuild.stdout.txt"),
  "stderr_log=" + (Join-Path $logDir "05_explain_rebuild.stderr.txt"),
  "artifact_74_exists=" + (Test-Path $a74),
  "artifact_74_evidence_refs=" + $e74,
  "explain_integration_pass=" + $expPass
) | Set-Content -Path (Join-Path $proof "10_explain_engine_integration_validation.txt") -Encoding UTF8

$tree = @(
  "58_decision_envelope_chain.json",
  "65_outcome_feedback_chain.json",
  "67_confidence_propagation.json",
  "68_recurrence_propagation.json",
  "69_predictive_calibration_propagation.json",
  "70_certification_impact_propagation.json",
  "72_certification_control_plane_summary.json",
  "73_operational_control_plane_summary.json",
  "74_explain_control_plane_summary.json"
)
$out = @("control_plane_dir=" + $cp)
foreach ($f in $tree) {
  $p = Join-Path $cp $f
  $out += ($f + "|exists=" + (Test-Path $p) + "|path=" + $p)
}
$out | Set-Content -Path (Join-Path $proof "11_control_plane_artifact_tree.txt") -Encoding UTF8

$final = @()
$final += "certification_integration=" + $(if ($certPass) { "PASS" } else { "FAIL" })
$final += "operational_flow_integration=" + $(if ($operPass) { "PASS" } else { "FAIL" })
$final += "workflow_recommendation_integration=" + $(if ($wfPass) { "PASS" } else { "FAIL" })
$final += "history_trend_integration=" + $(if ($histPass) { "PASS" } else { "FAIL" })
$final += "predictive_risk_integration=" + $(if ($predPass) { "PASS" } else { "FAIL" })
$final += "explain_integration=" + $(if ($expPass) { "PASS" } else { "FAIL" })
$final += "artifact_72_present=" + $(if (Test-Path $a72) { "PASS" } else { "FAIL" })
$final += "artifact_73_present=" + $(if (Test-Path $a73) { "PASS" } else { "FAIL" })
$final += "artifact_74_present=" + $(if (Test-Path $a74) { "PASS" } else { "FAIL" })
$final += "deterministic_compatibility_preserved=" + $(if ($detPass) { "PASS" } else { "FAIL" })
$overall = if (($final | Where-Object { $_ -match "=FAIL$" }).Count -eq 0) { "PASS" } else { "FAIL" }
$final += "overall_gate=" + $overall
$final += "run_pf=" + $runpf
$final += "command_exit_codes=" + $buildExit + "," + $planExit + "," + $certExit + "," + $predExit + "," + $explExit + "," + $histExit + "," + $propExit + "," + $replExit
$final | Set-Content -Path (Join-Path $proof "12_final_contract_report.txt") -Encoding UTF8

git -C $s.repo status --short > (Join-Path $proof "04_files_created_or_modified.txt")
Write-Output ("proof=" + $proof)
Write-Output ("runpf=" + $runpf)
Write-Output ("overall=" + $overall)
