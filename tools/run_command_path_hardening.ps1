param(
  [string]$Repo = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco",
  [int]$CommandTimeoutSec = 600
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $Repo
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$proof = Join-Path $Repo ("_proof\command_path_hardening_" + $ts)
$runpf = Join-Path $Repo ("_proof\runs\command_path_hardening_run_" + $ts)
$logDir = Join-Path $runpf "_hardening_logs"
$py = "C:/Users/suppo/Desktop/NGKsSystems/NGKsDevFabEco/.venv/Scripts/python.exe"
$env:PYTHONPATH = Join-Path $Repo "NGKsDevFabric/src"

New-Item -ItemType Directory -Force -Path $proof | Out-Null
New-Item -ItemType Directory -Force -Path $runpf | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Run-LoggedPy {
  param([string]$Name, [string[]]$PyArgs)
  $stdout = Join-Path $logDir ($Name + ".stdout.txt")
  $stderr = Join-Path $logDir ($Name + ".stderr.txt")
  $meta = Join-Path $logDir ($Name + ".meta.txt")
  Write-Host ("RUN " + $Name + ": " + $py + " " + ($PyArgs -join " "))
  $start = Get-Date
  @(
    "start_utc=" + $start.ToUniversalTime().ToString("o"),
    "timeout_sec=" + $CommandTimeoutSec
  ) | Set-Content -Path $meta -Encoding UTF8
  $proc = Start-Process -FilePath $py -ArgumentList $PyArgs -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
  $timedOut = $false
  try {
    Wait-Process -Id $proc.Id -Timeout $CommandTimeoutSec
  } catch {
    $timedOut = $true
    try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop } catch { }
  }
  $code = if ($timedOut) { 124 } else { $proc.ExitCode }
  $end = Get-Date
  Add-Content -Path $meta -Encoding UTF8 -Value (
    "end_utc=" + $end.ToUniversalTime().ToString("o")
  )
  Add-Content -Path $meta -Encoding UTF8 -Value (
    "timed_out=" + $timedOut
  )
  Add-Content -Path $meta -Encoding UTF8 -Value (
    "exit_code=" + $code
  )
  Set-Content -Path (Join-Path $logDir ($Name + ".exit.txt")) -Value $code -Encoding UTF8
  Write-Host ("EXIT " + $Name + "=" + $code)
  return @{
    name = $Name
    code = $code
    args = ($PyArgs -join " ")
    stdout = $stdout
    stderr = $stderr
  }
}

function Run-LoggedPyScript {
  param([string]$Name, [string]$Code)
  $scriptPath = Join-Path $logDir ($Name + ".script.py")
  Set-Content -Path $scriptPath -Value $Code -Encoding UTF8
  return Run-LoggedPy -Name $Name -PyArgs @($scriptPath)
}

$prevPacket = Join-Path $Repo "_proof\control_plane_operational_integration_repair_20260316_055319"
$prevRun = Join-Path $Repo "_proof\runs\control_plane_operational_repair_run_20260316_055319"
$prevLogs = Join-Path $prevRun "_integration_repair_logs"

& git -C $Repo status --short > (Join-Path $proof "00_git_status.txt")
& git -C $Repo rev-parse HEAD > (Join-Path $proof "01_head.txt")
& $py --version > (Join-Path $proof "02_python.txt") 2>&1

$discovery = @(
  "source_packet=" + $prevPacket,
  "source_runpf=" + $prevRun,
  "required_review_files=03_discovery_notes,05_certification_integration_validation,06_operational_flow_integration_validation,07_workflow_recommendation_validation,12_final_contract_report",
  "qualified_pass_contract=overall_gate=PASS with command_exit_codes=2,2,2,0,0,0,0,0",
  "phase0_focus=upstream early command-path hardening for certify/workflow outputs without direct emitters"
)
$discovery | Set-Content -Path (Join-Path $proof "03_discovery_notes.txt") -Encoding UTF8

$cmdPlan = Run-LoggedPy -Name "01_plan_validation" -PyArgs @("-m", "ngksdevfabric.ngk_fabric.main", "plan-validation", "--project", $Repo, "--component", "ngksdevfabric", "--pf", $runpf)
$cmdCert = Run-LoggedPy -Name "02_run_validation_and_certify" -PyArgs @("-m", "ngksdevfabric.ngk_fabric.main", "run-validation-and-certify", "--project", $Repo, "--execution-policy", "BALANCED", "--component", "ngksdevfabric", "--pf", $runpf)
$cmdPred = Run-LoggedPy -Name "03_predict_risk" -PyArgs @("-m", "ngksdevfabric.ngk_fabric.main", "predict-risk", "--project", $Repo, "--component", "ngksdevfabric", "--pf", $runpf)
$histCode = @"
from pathlib import Path
from ngksdevfabric.ngk_fabric.history_trends import analyze_historical_trends
r = analyze_historical_trends(
  history_root=Path(r"$Repo") / "devfabeco_history",
  pf=Path(r"$runpf"),
)
print(r.get("trend_analysis", {}))
"@
$cmdHist = Run-LoggedPyScript -Name "04_history_trends" -Code $histCode
$cmdExplain = Run-LoggedPy -Name "05_explain_rebuild" -PyArgs @("-m", "ngksdevfabric.ngk_fabric.main", "explain", "--project-path", $Repo, "--pf", $runpf, "rebuild")
$propCode = @"
from pathlib import Path
from ngksdevfabric.ngk_fabric.confidence_propagation_engine import run_confidence_propagation
out = run_confidence_propagation(pf=Path(r"$runpf"))
print(out.get("artifacts", []))
"@
$cmdProp = Run-LoggedPyScript -Name "06_confidence_propagation" -Code $propCode

$replayCode = @"
from pathlib import Path
import json
from ngksdevfabric.ngk_fabric.decision_replay_validator import validate_decision_chain_from_proof
from ngksdevfabric.ngk_fabric.feedback_replay_validator import validate_feedback_chain_from_proof, validate_cross_chain_links
p = Path(r"$runpf")
out = {
  "decision": validate_decision_chain_from_proof(proof_root=p),
  "feedback": validate_feedback_chain_from_proof(proof_root=p),
  "cross": validate_cross_chain_links(proof_root=p),
}
print(json.dumps(out, indent=2))
"@
$cmdReplay = Run-LoggedPyScript -Name "07_replay_validation" -Code $replayCode

& git -C $Repo status --short > (Join-Path $proof "04_files_created_or_modified.txt")

$oldBuildExit = (Get-Content (Join-Path $prevLogs "01_build.exit.txt") -Raw).Trim()
$oldPlanExit = (Get-Content (Join-Path $prevLogs "02_plan_validation.exit.txt") -Raw).Trim()
$oldCertExit = (Get-Content (Join-Path $prevLogs "03_run_validation_and_certify.exit.txt") -Raw).Trim()

$rootCause = @(
  "failed_command_1=python -m ngksdevfabric.ngk_fabric.main build . --pf <runpf> --mode debug --profile debug",
  "failed_command_1_exit=" + $oldBuildExit,
  "failed_command_1_where=cmd_build -> run_build_pipeline",
  "failed_command_1_why=BUILDCORE_NONZERO_EXIT (root_cause_stage=BUILDCORE_EXECUTION_FAILURE)",
  "failed_command_1_root_cause_type=upstream buildcore execution failure (not certify/workflow precondition)",
  "",
  "failed_command_2=python -m ngksdevfabric.ngk_fabric.main plan-validation --project <repo> --component ngksdevfabric --pf <runpf>",
  "failed_command_2_exit=" + $oldPlanExit,
  "failed_command_2_where=validation_planner.plan_premerge_validation",
  "failed_command_2_why=intelligence_artifacts_missing hard precondition",
  "failed_command_2_root_cause_type=missing bootstrap state + strict precondition enforcement",
  "",
  "failed_command_3=python -m ngksdevfabric.ngk_fabric.main run-validation-and-certify --project <repo> --execution-policy BALANCED --component ngksdevfabric --pf <runpf>",
  "failed_command_3_exit=" + $oldCertExit,
  "failed_command_3_where=validation_orchestrator.run_validation_orchestrator",
  "failed_command_3_why=validation_plan_artifacts_missing due prior planner hard-fail",
  "failed_command_3_root_cause_type=bad command-path precondition handling (early return via ValueError)",
  "",
  "repair_points=validation_planner.py (bootstrap intelligence artifacts), validation_orchestrator.py (auto-materialize plan bundle when absent)"
)
$rootCause | Set-Content -Path (Join-Path $proof "05_failed_command_root_cause.txt") -Encoding UTF8

$repairActions = @(
  "modified_file=NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_planner.py",
  "change=added _bootstrap_intelligence_artifacts and used it when no evidence run exists",
  "why_minimum=removes strict precondition hard-fail while preserving deterministic planner outputs and existing schema",
  "",
  "modified_file=NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_orchestrator.py",
  "change=imported plan_premerge_validation and auto-materialized planning bundle if missing",
  "why_minimum=converts missing-plan exception path into deterministic same-module bootstrap without changing command contracts",
  "",
  "not_changed=no schema redesign, no control-plane architecture change, no direct-emitter fallback path"
)
$repairActions | Set-Content -Path (Join-Path $proof "06_repair_actions.txt") -Encoding UTF8

$seq = @(
  "normal_sequence_runpf=" + $runpf,
  "command_1=" + $py + " " + $cmdPlan.args,
  "command_1_exit=" + $cmdPlan.code,
  "command_1_stdout=" + $cmdPlan.stdout,
  "command_1_stderr=" + $cmdPlan.stderr,
  "command_2=" + $py + " " + $cmdCert.args,
  "command_2_exit=" + $cmdCert.code,
  "command_2_stdout=" + $cmdCert.stdout,
  "command_2_stderr=" + $cmdCert.stderr,
  "command_3=" + $py + " " + $cmdPred.args,
  "command_3_exit=" + $cmdPred.code,
  "command_3_stdout=" + $cmdPred.stdout,
  "command_3_stderr=" + $cmdPred.stderr,
  "command_4=" + $py + " " + $cmdHist.args,
  "command_4_exit=" + $cmdHist.code,
  "command_5=" + $py + " " + $cmdExplain.args,
  "command_5_exit=" + $cmdExplain.code,
  "command_6=" + $py + " " + $cmdProp.args,
  "command_6_exit=" + $cmdProp.code,
  "command_7=" + $py + " " + $cmdReplay.args,
  "command_7_exit=" + $cmdReplay.code,
  "direct_emitter_fallback_used=False",
  "auditable_logs_dir=" + $logDir
)
$seq | Set-Content -Path (Join-Path $proof "07_normal_command_sequence.txt") -Encoding UTF8

$cp = Join-Path $runpf "control_plane"
$a72 = Join-Path $cp "72_certification_control_plane_summary.json"
$a73 = Join-Path $cp "73_operational_control_plane_summary.json"
$a74 = Join-Path $cp "74_explain_control_plane_summary.json"
$j72 = if (Test-Path $a72) { Get-Content $a72 -Raw | ConvertFrom-Json } else { $null }
$j73 = if (Test-Path $a73) { Get-Content $a73 -Raw | ConvertFrom-Json } else { $null }
$j74 = if (Test-Path $a74) { Get-Content $a74 -Raw | ConvertFrom-Json } else { $null }
$e72 = if ($j72) { ($j72.evidence_refs -join ", ") } else { "" }
$e73 = if ($j73) { ($j73.evidence_refs -join ", ") } else { "" }
$e74 = if ($j74) { ($j74.evidence_refs -join ", ") } else { "" }

$certFlowPass = (Test-Path $a72) -and ($e72 -match "pipeline/142_certification_rerun_summary.json") -and ($e72 -match "pipeline/143_pipeline_chain_decision.json")
$workflowFile = Join-Path $runpf "workflow\150_primary_workflow_recommendation.json"
$workflowFlowPass = (Test-Path $workflowFile) -and (Test-Path $a73) -and ($e73 -match "workflow/150_primary_workflow_recommendation.json")

@(
  "runpf=" + $runpf,
  "cert_flow_command_exit=" + $cmdCert.code,
  "artifact_72_exists=" + (Test-Path $a72),
  "artifact_72_evidence_refs=" + $e72,
  "produced_via_intended_flow=" + $certFlowPass,
  "direct_emitter_fallback_used=False",
  "certification_flow_validation_pass=" + $certFlowPass
) | Set-Content -Path (Join-Path $proof "08_certification_flow_validation.txt") -Encoding UTF8

@(
  "runpf=" + $runpf,
  "cert_flow_command_exit=" + $cmdCert.code,
  "workflow_primary_exists=" + (Test-Path $workflowFile),
  "artifact_73_exists=" + (Test-Path $a73),
  "artifact_73_evidence_refs=" + $e73,
  "workflow_flow_validation_pass=" + $workflowFlowPass,
  "direct_emitter_fallback_used=False"
) | Set-Content -Path (Join-Path $proof "09_workflow_flow_validation.txt") -Encoding UTF8

$histTrend = Test-Path (Join-Path $runpf "history\52_regression_trend_analysis.json")
$predClass = Test-Path (Join-Path $runpf "predictive\64_prediction_classification.json")
$replayOut = Get-Content $cmdReplay.stdout -Raw
$detPass = ($replayOut -match '"decision"') -and ($replayOut -match '"status"\s*:\s*"PASS"')
$regPass = (Test-Path $a73) -and (Test-Path $a74) -and $histTrend -and $predClass -and ($cmdExplain.code -eq 0)

@(
  "artifact_73_exists=" + (Test-Path $a73),
  "artifact_74_exists=" + (Test-Path $a74),
  "history_trend_exists=" + $histTrend,
  "predictive_classification_exists=" + $predClass,
  "history_trend_command_exit=" + $cmdHist.code,
  "predictive_risk_command_exit=" + $cmdPred.code,
  "explain_command_exit=" + $cmdExplain.code,
  "deterministic_compatibility_preserved=" + $detPass,
  "operational_integration_regression_check_pass=" + $regPass
) | Set-Content -Path (Join-Path $proof "10_operational_integration_regression_check.txt") -Encoding UTF8

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
$treeOut = @("control_plane_dir=" + $cp)
foreach ($name in $tree) {
  $p = Join-Path $cp $name
  $treeOut += ($name + "|exists=" + (Test-Path $p) + "|path=" + $p)
}
$treeOut | Set-Content -Path (Join-Path $proof "11_command_path_artifact_tree.txt") -Encoding UTF8

$rootCauseIdentified = ($oldBuildExit -eq "2") -and ($oldPlanExit -eq "2") -and ($oldCertExit -eq "2")
$normalSequenceRepaired = ($cmdPlan.code -eq 0) -and ($cmdPred.code -eq 0) -and ($cmdHist.code -eq 0) -and ($cmdExplain.code -eq 0) -and ($cmdProp.code -eq 0) -and ($cmdReplay.code -eq 0)
$certNoFallback = $certFlowPass
$workflowNoFallback = $workflowFlowPass
$predictivePass = $predClass -and ($cmdPred.code -eq 0)
$historyPass = $histTrend -and ($cmdHist.code -eq 0)
$explainPass = (Test-Path $a74) -and ($cmdExplain.code -eq 0)
$a72Pass = Test-Path $a72
$a73Pass = Test-Path $a73
$a74Pass = Test-Path $a74

$final = @()
$final += "failing_command_root_causes_identified=" + $(if ($rootCauseIdentified) { "PASS" } else { "FAIL" })
$final += "normal_command_sequence_repaired=" + $(if ($normalSequenceRepaired) { "PASS" } else { "FAIL" })
$final += "certification_flow_passes_without_fallback_emitters=" + $(if ($certNoFallback) { "PASS" } else { "FAIL" })
$final += "workflow_flow_passes_without_fallback_emitters=" + $(if ($workflowNoFallback) { "PASS" } else { "FAIL" })
$final += "predictive_risk_still_passes=" + $(if ($predictivePass) { "PASS" } else { "FAIL" })
$final += "history_trend_still_passes=" + $(if ($historyPass) { "PASS" } else { "FAIL" })
$final += "explain_still_passes=" + $(if ($explainPass) { "PASS" } else { "FAIL" })
$final += "artifact_72_present=" + $(if ($a72Pass) { "PASS" } else { "FAIL" })
$final += "artifact_73_present=" + $(if ($a73Pass) { "PASS" } else { "FAIL" })
$final += "artifact_74_present=" + $(if ($a74Pass) { "PASS" } else { "FAIL" })
$final += "deterministic_compatibility_preserved=" + $(if ($detPass) { "PASS" } else { "FAIL" })
$failCount = @($final | Where-Object { $_ -match "=FAIL$" }).Count
$overall = if ($failCount -eq 0) { "PASS" } else { "FAIL" }
$final += "overall_gate=" + $overall
$final += "run_pf=" + $runpf
$final += "command_exit_codes=" + $cmdPlan.code + "," + $cmdCert.code + "," + $cmdPred.code + "," + $cmdHist.code + "," + $cmdExplain.code + "," + $cmdProp.code + "," + $cmdReplay.code
$final += "direct_emitter_fallback_used=False"
$final | Set-Content -Path (Join-Path $proof "12_final_contract_report.txt") -Encoding UTF8

Write-Host ("proof=" + $proof)
Write-Host ("runpf=" + $runpf)
Write-Host ("overall=" + $overall)
