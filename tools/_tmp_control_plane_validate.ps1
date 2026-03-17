param([string]$RepoRoot)
$ErrorActionPreference = "Stop"
if((Get-Location).Path -ne $RepoRoot){ Write-Output 'hey stupid Fucker, wrong window again'; exit 0 }
$ts=Get-Date -Format 'yyyyMMdd_HHmmss'
$proof=Join-Path $RepoRoot ('_proof\\control_plane_operational_integration_' + $ts)
$runpf=Join-Path $RepoRoot ('_proof\\runs\\control_plane_operational_run_' + $ts)
New-Item -ItemType Directory -Force -Path $proof | Out-Null
New-Item -ItemType Directory -Force -Path $runpf | Out-Null
$py='C:/Users/suppo/Desktop/NGKsSystems/NGKsDevFabEco/.venv/Scripts/python.exe'
$env:PYTHONPATH=(Join-Path $RepoRoot 'NGKsDevFabric/src')

git -C $RepoRoot status --short > (Join-Path $proof '00_git_status.txt')
git -C $RepoRoot rev-parse HEAD > (Join-Path $proof '01_head.txt')
& $py --version > (Join-Path $proof '02_python.txt') 2>&1

$notes=@(
'Discovery command surface verified from NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py',
'Selected minimal auditable sequence:',
"- $py -m ngksdevfabric.cli build . --pf '$runpf' --mode debug --profile debug",
"- $py -m ngksdevfabric.cli plan-validation --project '$RepoRoot' --component ngksdevfabric --pf '$runpf'",
"- $py -m ngksdevfabric.cli run-validation-and-certify --project '$RepoRoot' --execution-policy BALANCED --component ngksdevfabric --pf '$runpf'",
"- $py -m ngksdevfabric.cli predict-risk --project '$RepoRoot' --component ngksdevfabric --pf '$runpf'",
"- $py -m ngksdevfabric.cli explain --project-path '$RepoRoot' --pf '$runpf' rebuild",
"- $py -c <history_trends direct module entrypoint>",
"- $py -c <confidence_propagation direct module entrypoint>",
"- $py -c <decision+feedback replay validators>"
)
$notes | Set-Content -Path (Join-Path $proof '03_discovery_notes.txt') -Encoding UTF8

& $py -m ngksdevfabric.cli build . --pf "$runpf" --mode debug --profile debug *> (Join-Path $proof 'cmd_01_build.log'); $rc1=$LASTEXITCODE
& $py -m ngksdevfabric.cli plan-validation --project "$RepoRoot" --component ngksdevfabric --pf "$runpf" *> (Join-Path $proof 'cmd_02_plan_validation.log'); $rc2=$LASTEXITCODE
& $py -m ngksdevfabric.cli run-validation-and-certify --project "$RepoRoot" --execution-policy BALANCED --component ngksdevfabric --pf "$runpf" *> (Join-Path $proof 'cmd_03_run_validation_and_certify.log'); $rc3=$LASTEXITCODE
& $py -m ngksdevfabric.cli predict-risk --project "$RepoRoot" --component ngksdevfabric --pf "$runpf" *> (Join-Path $proof 'cmd_04_predict_risk.log'); $rc4=$LASTEXITCODE
& $py -m ngksdevfabric.cli explain --project-path "$RepoRoot" --pf "$runpf" rebuild *> (Join-Path $proof 'cmd_05_explain_rebuild.log'); $rc5=$LASTEXITCODE
& $py -c "from pathlib import Path; from ngksdevfabric.ngk_fabric.history_trends import analyze_historical_trends; r=analyze_historical_trends(history_root=Path(r'$RepoRoot')/'devfabeco_history', pf=Path(r'$runpf')); print(r.get('trend_analysis',{}))" *> (Join-Path $proof 'cmd_06_history_trends.log'); $rc6=$LASTEXITCODE
& $py -c "from pathlib import Path; from ngksdevfabric.ngk_fabric.confidence_propagation_engine import run_confidence_propagation; out=run_confidence_propagation(pf=Path(r'$runpf')); print(out.get('artifacts',[]))" *> (Join-Path $proof 'cmd_07_propagation.log'); $rc7=$LASTEXITCODE
& $py -c "from pathlib import Path; import json; from ngksdevfabric.ngk_fabric.decision_replay_validator import validate_decision_chain_from_proof; from ngksdevfabric.ngk_fabric.feedback_replay_validator import validate_feedback_chain_from_proof, validate_cross_chain_links; p=Path(r'$runpf'); out={'decision':validate_decision_chain_from_proof(proof_root=p), 'feedback':validate_feedback_chain_from_proof(proof_root=p), 'cross':validate_cross_chain_links(proof_root=p)}; print(json.dumps(out, indent=2))" *> (Join-Path $proof 'cmd_08_replay_validation.log'); $rc8=$LASTEXITCODE

$cp=Join-Path $runpf 'control_plane'
$a72=Join-Path $cp '72_certification_control_plane_summary.json'
$a73=Join-Path $cp '73_operational_control_plane_summary.json'
$a74=Join-Path $cp '74_explain_control_plane_summary.json'
$j72 = if(Test-Path $a72){ Get-Content $a72 -Raw | ConvertFrom-Json } else { $null }
$j73 = if(Test-Path $a73){ Get-Content $a73 -Raw | ConvertFrom-Json } else { $null }
$j74 = if(Test-Path $a74){ Get-Content $a74 -Raw | ConvertFrom-Json } else { $null }

$e72refs = if($j72){ ($j72.evidence_refs -join ', ') } else { '' }
$e73refs = if($j73){ ($j73.evidence_refs -join ', ') } else { '' }
$e74refs = if($j74){ ($j74.evidence_refs -join ', ') } else { '' }

$certPass = (Test-Path $a72) -and ($e72refs -match '58_decision_envelope_chain.json') -and ($e72refs -match '65_outcome_feedback_chain.json') -and ($e72refs -match '67_confidence_propagation.json')
$operPass = (Test-Path $a73) -and ($e73refs -match '58_decision_envelope_chain.json') -and ($e73refs -match '65_outcome_feedback_chain.json') -and ($e73refs -match '69_predictive_calibration_propagation.json')
$wfPass = (Test-Path (Join-Path $runpf 'workflow/150_primary_workflow_recommendation.json')) -and (Test-Path $a73) -and ($j73.integration_source -ne $null)
$histPass = (Test-Path (Join-Path $runpf 'history/52_regression_trend_analysis.json')) -and (Test-Path $a73) -and ($j73.control_plane_context.propagation.recurrence_present -eq $true)
$predPass = (Test-Path (Join-Path $runpf 'predictive/64_prediction_classification.json')) -and (Test-Path $a73) -and ($j73.control_plane_context.propagation.calibration_present -eq $true)
$expPass = (Test-Path $a74) -and ($e74refs -match '58_decision_envelope_chain.json') -and ($e74refs -match '65_outcome_feedback_chain.json') -and ($e74refs -match '67_confidence_propagation.json') -and ($e74refs -match '70_certification_impact_propagation.json')
$replayText = if(Test-Path (Join-Path $proof 'cmd_08_replay_validation.log')){ Get-Content (Join-Path $proof 'cmd_08_replay_validation.log') -Raw } else { '' }
$detPass = ($replayText -match '"status"\s*:\s*"PASS"')

@("runpf=$runpf","cmd_01_build_exit_code=$rc1","cmd_02_plan_validation_exit_code=$rc2","cmd_03_run_validation_and_certify_exit_code=$rc3","artifact_72_exists=" + (Test-Path $a72),"artifact_72_evidence_refs=$e72refs","certification_integration_pass=$certPass") | Set-Content -Path (Join-Path $proof '05_certification_integration_validation.txt') -Encoding UTF8
@("runpf=$runpf","cmd_01_build_exit_code=$rc1","cmd_03_run_validation_and_certify_exit_code=$rc3","cmd_07_propagation_exit_code=$rc7","artifact_73_exists=" + (Test-Path $a73),"artifact_73_evidence_refs=$e73refs","operational_integration_pass=$operPass") | Set-Content -Path (Join-Path $proof '06_operational_flow_integration_validation.txt') -Encoding UTF8
@("runpf=$runpf","workflow_primary_exists=" + (Test-Path (Join-Path $runpf 'workflow/150_primary_workflow_recommendation.json')),"artifact_73_exists=" + (Test-Path $a73),"artifact_73_integration_source=" + (if($j73){$j73.integration_source}else{''}),"workflow_integration_pass=$wfPass") | Set-Content -Path (Join-Path $proof '07_workflow_recommendation_validation.txt') -Encoding UTF8
@("runpf=$runpf","history_trend_exists=" + (Test-Path (Join-Path $runpf 'history/52_regression_trend_analysis.json')),"propagation_recurrence_present=" + (if($j73){$j73.control_plane_context.propagation.recurrence_present}else{$false}),"history_trend_integration_pass=$histPass") | Set-Content -Path (Join-Path $proof '08_history_trend_integration_validation.txt') -Encoding UTF8
@("runpf=$runpf","predictive_classification_exists=" + (Test-Path (Join-Path $runpf 'predictive/64_prediction_classification.json')),"propagation_calibration_present=" + (if($j73){$j73.control_plane_context.propagation.calibration_present}else{$false}),"predictive_risk_integration_pass=$predPass") | Set-Content -Path (Join-Path $proof '09_predictive_risk_integration_validation.txt') -Encoding UTF8
@("runpf=$runpf","artifact_74_exists=" + (Test-Path $a74),"artifact_74_evidence_refs=$e74refs","explain_integration_pass=$expPass") | Set-Content -Path (Join-Path $proof '10_explain_engine_integration_validation.txt') -Encoding UTF8

$treeTargets=@('58_decision_envelope_chain.json','65_outcome_feedback_chain.json','67_confidence_propagation.json','68_recurrence_propagation.json','69_predictive_calibration_propagation.json','70_certification_impact_propagation.json','72_certification_control_plane_summary.json','73_operational_control_plane_summary.json','74_explain_control_plane_summary.json')
$treeOut=@("control_plane_dir=$cp")
foreach($t in $treeTargets){ $p=Join-Path $cp $t; $treeOut += ("$t|exists=" + (Test-Path $p) + "|path=" + $p) }
$treeOut | Set-Content -Path (Join-Path $proof '11_control_plane_artifact_tree.txt') -Encoding UTF8

$final=@()
$final += "certification_integration=" + ($(if($certPass){'PASS'}else{'FAIL'}))
$final += "operational_flow_integration=" + ($(if($operPass){'PASS'}else{'FAIL'}))
$final += "workflow_recommendation_integration=" + ($(if($wfPass){'PASS'}else{'FAIL'}))
$final += "history_trend_integration=" + ($(if($histPass){'PASS'}else{'FAIL'}))
$final += "predictive_risk_integration=" + ($(if($predPass){'PASS'}else{'FAIL'}))
$final += "explain_integration=" + ($(if($expPass){'PASS'}else{'FAIL'}))
$final += "artifact_72_present=" + ($(if(Test-Path $a72){'PASS'}else{'FAIL'}))
$final += "artifact_73_present=" + ($(if(Test-Path $a73){'PASS'}else{'FAIL'}))
$final += "artifact_74_present=" + ($(if(Test-Path $a74){'PASS'}else{'FAIL'}))
$final += "deterministic_compatibility_preserved=" + ($(if($detPass){'PASS'}else{'FAIL'}))
$overall = if(($final | Where-Object { $_ -match '=FAIL$' }).Count -eq 0){'PASS'}else{'FAIL'}
$final += "overall_gate=$overall"
$final += "run_pf=$runpf"
$final += "command_exit_codes=$rc1,$rc2,$rc3,$rc4,$rc5,$rc6,$rc7,$rc8"
$final | Set-Content -Path (Join-Path $proof '12_final_contract_report.txt') -Encoding UTF8

git -C $RepoRoot status --short > (Join-Path $proof '04_files_created_or_modified.txt')
Write-Output "integration_proof_folder=$proof"
Write-Output "integration_run_pf=$runpf"
Write-Output "overall_gate=$overall"
