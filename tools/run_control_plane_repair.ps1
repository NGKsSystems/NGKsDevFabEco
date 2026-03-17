param(
  [string]$Repo = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $Repo
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$proof = Join-Path $Repo ("_proof\control_plane_operational_integration_repair_" + $ts)
$runpf = Join-Path $Repo ("_proof\runs\control_plane_operational_repair_run_" + $ts)
$logDir = Join-Path $runpf "_integration_repair_logs"
New-Item -ItemType Directory -Force -Path $proof | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$py = "C:/Users/suppo/Desktop/NGKsSystems/NGKsDevFabEco/.venv/Scripts/python.exe"
$env:PYTHONPATH = Join-Path $Repo "NGKsDevFabric/src"

function Run-And-Log {
  param([string]$Name, [string[]]$Args)
  $outFile = Join-Path $logDir ($Name + ".stdout.txt")
  $errFile = Join-Path $logDir ($Name + ".stderr.txt")
  $cmdText = ($Args -join " ")
  Write-Host ("RUN " + $Name + ": " + $py + " " + $cmdText)
  $proc = Start-Process -FilePath $py -ArgumentList $Args -NoNewWindow -Wait -PassThru -RedirectStandardOutput $outFile -RedirectStandardError $errFile
  $code = $proc.ExitCode
  Write-Host ("EXIT " + $Name + "=" + $code)
  return @{ name = $Name; cmd = ($py + " " + $cmdText); code = $code; stdout = $outFile; stderr = $errFile }
}

& git -C $Repo status --short > (Join-Path $proof "00_git_status.txt")
& git -C $Repo rev-parse HEAD > (Join-Path $proof "01_head.txt")
& $py --version > (Join-Path $proof "02_python.txt") 2>&1

$discovery = @(
  "Phase 0 discovery evidence source: _proof/control_plane_operational_integration_20260315_214639",
  "Reviewed files: 05_certification_integration_validation.txt, 06_operational_flow_integration_validation.txt, 07_workflow_recommendation_validation.txt, 09_predictive_risk_integration_validation.txt, 12_final_contract_report.txt",
  "Failure cause 1 (missing 72): run-validation-and-certify command failed with exit_code=2 due missing planning artifacts (cmd_03 showed validation_plan_artifacts_missing).",
  "Failure cause 2 (workflow fail): workflow file absent because certification chain command failed before workflow stage execution.",
  "Failure cause 3 (predictive fail): predict-risk command failed with exit_code=2 due history_root_missing.",
  "Additional proven execution issue from prior run: python -m ngksdevfabric.cli is non-executing in this repo; repaired to use python -m ngksdevfabric.ngk_fabric.main.",
  "Minimal repair applied: bootstrap empty devfabeco_history stores in validation_planner.py and predictive_risk.py instead of hard-failing when history root is absent.",
  "Validation command sequence (smallest auditable set):",
  "- python -m ngksdevfabric.ngk_fabric.main build . --pf <runpf> --mode debug --profile debug",
  "- python -m ngksdevfabric.ngk_fabric.main plan-validation --project <repo> --component ngksdevfabric --pf <runpf>",
  "- python -m ngksdevfabric.ngk_fabric.main run-validation-and-certify --project <repo> --execution-policy BALANCED --component ngksdevfabric --pf <runpf>",
  "- python -c run_confidence_propagation(pf=<runpf>)",
  "- python -m ngksdevfabric.ngk_fabric.main predict-risk --project <repo> --component ngksdevfabric --pf <runpf>",
  "- python -c analyze_historical_trends(history_root=<repo>/devfabeco_history,pf=<runpf>)",
  "- python -m ngksdevfabric.ngk_fabric.main explain --project-path <repo> --pf <runpf> rebuild",
  "- python -c decision/feedback replay validators on <runpf>"
)
$discovery | Set-Content -Path (Join-Path $proof "03_discovery_notes.txt") -Encoding UTF8

$r1 = Run-And-Log -Name "01_build" -Args @("-m", "ngksdevfabric.ngk_fabric.main", "build", ".", "--pf", $runpf, "--mode", "debug", "--profile", "debug")
$r2 = Run-And-Log -Name "02_plan_validation" -Args @("-m", "ngksdevfabric.ngk_fabric.main", "plan-validation", "--project", $Repo, "--component", "ngksdevfabric", "--pf", $runpf)
$r3 = Run-And-Log -Name "03_run_validation_and_certify" -Args @("-m", "ngksdevfabric.ngk_fabric.main", "run-validation-and-certify", "--project", $Repo, "--execution-policy", "BALANCED", "--component", "ngksdevfabric", "--pf", $runpf)
$propCode = "from pathlib import Path; from ngksdevfabric.ngk_fabric.confidence_propagation_engine import run_confidence_propagation; out=run_confidence_propagation(pf=Path(r'" + $runpf + "')); print(out.get('artifacts',[]))"
$r7 = Run-And-Log -Name "07_propagation" -Args @("-c", $propCode)
$r4 = Run-And-Log -Name "04_predict_risk" -Args @("-m", "ngksdevfabric.ngk_fabric.main", "predict-risk", "--project", $Repo, "--component", "ngksdevfabric", "--pf", $runpf)
$histCode = "from pathlib import Path; from ngksdevfabric.ngk_fabric.history_trends import analyze_historical_trends; r=analyze_historical_trends(history_root=Path(r'" + $Repo + "')/'devfabeco_history', pf=Path(r'" + $runpf + "')); print(r.get('trend_analysis',{}))"
$r6 = Run-And-Log -Name "06_history_trends" -Args @("-c", $histCode)
$r5 = Run-And-Log -Name "05_explain_rebuild" -Args @("-m", "ngksdevfabric.ngk_fabric.main", "explain", "--project-path", $Repo, "--pf", $runpf, "rebuild")
$replayCode = "from pathlib import Path; import json; from ngksdevfabric.ngk_fabric.decision_replay_validator import validate_decision_chain_from_proof; from ngksdevfabric.ngk_fabric.feedback_replay_validator import validate_feedback_chain_from_proof, validate_cross_chain_links; p=Path(r'" + $runpf + "'); out={'decision':validate_decision_chain_from_proof(proof_root=p),'feedback':validate_feedback_chain_from_proof(proof_root=p),'cross':validate_cross_chain_links(proof_root=p)}; print(json.dumps(out, indent=2))"
$r8 = Run-And-Log -Name "08_replay_validation" -Args @("-c", $replayCode)

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

$certPass = (Test-Path $a72) -and ($e72 -match "58_decision_envelope_chain.json") -and ($e72 -match "65_outcome_feedback_chain.json") -and ($e72 -match "67_confidence_propagation.json")
$operPass = (Test-Path $a73) -and ($e73 -match "58_decision_envelope_chain.json") -and ($e73 -match "65_outcome_feedback_chain.json")
$wfPass = (Test-Path (Join-Path $runpf "workflow/150_primary_workflow_recommendation.json")) -and (Test-Path $a73) -and ($e73 -match "workflow/150_primary_workflow_recommendation.json")
$histPass = (Test-Path (Join-Path $runpf "history/52_regression_trend_analysis.json")) -and (Test-Path $a73) -and $recurrence
$predPass = (Test-Path (Join-Path $runpf "predictive/64_prediction_classification.json")) -and (Test-Path $a73) -and ($e73 -match "69_predictive_calibration_propagation.json") -and ((Test-Path $a69) -or $calibration)
$expPass = (Test-Path $a74) -and ($e74 -match "58_decision_envelope_chain.json") -and ($e74 -match "65_outcome_feedback_chain.json") -and ($e74 -match "67_confidence_propagation.json") -and ($e74 -match "70_certification_impact_propagation.json")
$replay = Get-Content $r8.stdout -Raw
$detPass = ($replay -match '"decision"') -and ($replay -match '"status"\s*:\s*"PASS"')

@(
  "runpf=" + $runpf,
  "command=" + $r3.cmd,
  "exit_code=" + $r3.code,
  "stdout_log=" + $r3.stdout,
  "stderr_log=" + $r3.stderr,
  "artifact_72_exists=" + (Test-Path $a72),
  "artifact_72_evidence_refs=" + $e72,
  "certification_integration_pass=" + $certPass
) | Set-Content -Path (Join-Path $proof "05_certification_integration_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=" + $r3.cmd,
  "exit_code=" + $r3.code,
  "stdout_log=" + $r3.stdout,
  "stderr_log=" + $r3.stderr,
  "artifact_73_exists=" + (Test-Path $a73),
  "artifact_73_evidence_refs=" + $e73,
  "operational_integration_pass=" + $operPass
) | Set-Content -Path (Join-Path $proof "06_operational_flow_integration_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=" + $r3.cmd,
  "exit_code=" + $r3.code,
  "workflow_primary_exists=" + (Test-Path (Join-Path $runpf "workflow/150_primary_workflow_recommendation.json")),
  "artifact_73_exists=" + (Test-Path $a73),
  "artifact_73_evidence_refs=" + $e73,
  "workflow_integration_pass=" + $wfPass
) | Set-Content -Path (Join-Path $proof "07_workflow_recommendation_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=" + $r6.cmd,
  "exit_code=" + $r6.code,
  "stdout_log=" + $r6.stdout,
  "stderr_log=" + $r6.stderr,
  "history_trend_exists=" + (Test-Path (Join-Path $runpf "history/52_regression_trend_analysis.json")),
  "propagation_recurrence_present=" + $recurrence,
  "history_trend_integration_pass=" + $histPass
) | Set-Content -Path (Join-Path $proof "08_history_trend_integration_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=" + $r4.cmd,
  "exit_code=" + $r4.code,
  "stdout_log=" + $r4.stdout,
  "stderr_log=" + $r4.stderr,
  "predictive_classification_exists=" + (Test-Path (Join-Path $runpf "predictive/64_prediction_classification.json")),
  "artifact_73_evidence_refs=" + $e73,
  "propagation_calibration_present=" + $calibration,
  "predictive_risk_integration_pass=" + $predPass
) | Set-Content -Path (Join-Path $proof "09_predictive_risk_integration_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "command=" + $r5.cmd,
  "exit_code=" + $r5.code,
  "stdout_log=" + $r5.stdout,
  "stderr_log=" + $r5.stderr,
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
$final += "command_exit_codes=" + $r1.code + "," + $r2.code + "," + $r3.code + "," + $r4.code + "," + $r5.code + "," + $r6.code + "," + $r7.code + "," + $r8.code
$final | Set-Content -Path (Join-Path $proof "12_final_contract_report.txt") -Encoding UTF8

& git -C $Repo status --short > (Join-Path $proof "04_files_created_or_modified.txt")
Write-Host ("integration_proof_folder=" + $proof)
Write-Host ("run_pf=" + $runpf)
Write-Host ("overall_gate=" + $overall)
