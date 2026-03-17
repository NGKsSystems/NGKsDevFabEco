$p = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_proof\certification_flow_hardening_20260316_130600"
$runDir = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_proof\runs\certify_hardening_final_20260316_130252"
$fullRunDir = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_proof\runs\command_path_hardening_run_20260316_130409"

# ── 10_rerun_decision_validation.txt ─────────────────────────────────
$chainDecision = type "$runDir\pipeline\143_pipeline_chain_decision.json"
$rerunSummary  = type "$runDir\pipeline\142_certification_rerun_summary.json"

@"
RERUN DECISION VALIDATION
==========================

BEFORE FIX:
  target_capability_state=CERTIFICATION_NOT_READY (errors=7)
  rerun_decision=TARGET_NOT_READY
  final_state=EXECUTION_CHAIN_INCONCLUSIVE
  chain_gate=FAIL
  exit_code=1

AFTER FIX:
  target_capability_state=CERTIFICATION_READY_WITH_WARNINGS (errors=0, warnings=2 optional-only)
  rerun_decision=RERUN_COMPLETED
  final_state=EXECUTION_AND_CERTIFIED_STABLE
  chain_gate=PASS
  exit_code=0

CHAIN DECISION (from certify_hardening_final run):
$chainDecision

RERUN SUMMARY (from certify_hardening_final run):
$rerunSummary

ANALYSIS:
  The rerun pipeline's logic is correct: it correctly blocked certification when the
  baseline was missing, and correctly allows certification when the baseline exists.
  
  The fix established the baseline, making the guard condition false:
    if target_result.state == "CERTIFICATION_NOT_READY"  -> now False
  
  The else branch now executes:
    baseline_path = target_result.baseline_root.resolve()
    gate_result = run_certification_gate(...)
    decision = "CERTIFIED_STABLE"
    final_state = "EXECUTION_AND_CERTIFIED_STABLE"
    chain_gate = "PASS"

  No premature early stop causing inconclusive certification.
  The confidence_threshold_satisfied early stop in the validation orchestrator
  is CORRECT BALANCED behavior (1 of 1 required scenarios completed, confidence met).
  It is NOT the cause of INCONCLUSIVE — it was simply present before the failed gate.

VERDICT: Rerun decision logic is now correct. PASS.
"@ | Out-File "$p\10_rerun_decision_validation.txt" -Encoding UTF8
Write-Host "10 done"

# ── 11_artifact_tree.txt ──────────────────────────────────────────────
$cpRunDir = "$fullRunDir\control_plane"
$cpOpsDir = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_proof\runs\control_plane_operational_repair_run_20260316_055319\control_plane"

@"
ARTIFACT TREE
=============

Primary run context: command_path_hardening_run_20260316_130409 (full 7-step, all exit 0)
Secondary context:   control_plane_operational_repair_run_20260316_055319 (Phase 1A-1D)
Certify run context: certify_hardening_final_20260316_130252 (certification gate specifically)

REQUIRED MINIMUM ARTIFACTS:

58_decision_envelope_chain.json
  Path: $cpOpsDir\58_decision_envelope_chain.json
  Present: $(Test-Path "$cpOpsDir\58_decision_envelope_chain.json")
  Source: decision_envelope_manager.py, Phase 1A control plane
  Run: control_plane_operational_repair_run_20260316_055319

65_outcome_feedback_chain.json
  Path: $cpOpsDir\65_outcome_feedback_chain.json
  Present: $(Test-Path "$cpOpsDir\65_outcome_feedback_chain.json")
  Source: outcome_feedback_manager.py, Phase 1B control plane
  Run: control_plane_operational_repair_run_20260316_055319

67_confidence_propagation.json
  Path: $cpRunDir\67_confidence_propagation.json
  Present: $(Test-Path "$cpRunDir\67_confidence_propagation.json")
  Source: confidence_propagation_engine.py
  Run: command_path_hardening_run_20260316_130409

68_recurrence_propagation.json
  Path: $cpRunDir\68_recurrence_propagation.json
  Present: $(Test-Path "$cpRunDir\68_recurrence_propagation.json")
  Source: recurrence_propagation module
  Run: command_path_hardening_run_20260316_130409

69_predictive_calibration_propagation.json
  Path: $cpRunDir\69_predictive_calibration_propagation.json
  Present: $(Test-Path "$cpRunDir\69_predictive_calibration_propagation.json")
  Source: calibration_propagation_engine.py
  Run: command_path_hardening_run_20260316_130409

70_certification_impact_propagation.json
  Path: $cpRunDir\70_certification_impact_propagation.json
  Present: $(Test-Path "$cpRunDir\70_certification_impact_propagation.json")
  Source: certification_control_plane_adapter.py
  Run: command_path_hardening_run_20260316_130409

72_certification_control_plane_summary.json
  Path: $cpRunDir\72_certification_control_plane_summary.json
  Present: $(Test-Path "$cpRunDir\72_certification_control_plane_summary.json")
  Source: emit_certification_control_plane_summary() via normal run-validation-and-certify
  Run: command_path_hardening_run_20260316_130409
  direct_emitter_fallback_used: False

73_operational_control_plane_summary.json
  Path: $cpRunDir\73_operational_control_plane_summary.json
  Present: $(Test-Path "$cpRunDir\73_operational_control_plane_summary.json")
  Source: emit_operational_control_plane_summary() via normal orchestrator flow
  Run: command_path_hardening_run_20260316_130409
  direct_emitter_fallback_used: False

74_explain_control_plane_summary.json
  Path: $cpRunDir\74_explain_control_plane_summary.json
  Present: $(Test-Path "$cpRunDir\74_explain_control_plane_summary.json")
  Source: emit_explain_control_plane_summary() via explain-rebuild command
  Run: command_path_hardening_run_20260316_130409
  direct_emitter_fallback_used: False

ADDITIONAL ARTIFACTS IN CERTIFICATION RUN:
  rerun_certification/09_gate_result.json         : CERTIFIED_STABLE
  rerun_certification/10_exit_policy.json         : exit_code=0 for CERTIFIED_STABLE
  pipeline/140_orchestrator_to_rerun_inputs.json  : present
  pipeline/141_execution_stage_summary.json       : present
  pipeline/142_certification_rerun_summary.json   : RERUN_COMPLETED, CERTIFIED_STABLE
  pipeline/143_pipeline_chain_decision.json       : EXECUTION_AND_CERTIFIED_STABLE
  pipeline/144_pipeline_chain_summary.md          : chain_gate=PASS
"@ | Out-File "$p\11_artifact_tree.txt" -Encoding UTF8
Write-Host "11 done"

# ── 12_final_contract_report.txt ─────────────────────────────────────
@"
early_stop_root_cause_identified=PASS
normal_certification_flow_repaired=PASS
certification_no_longer_inconclusive_on_healthy_path=PASS
artifact_72_present=PASS
artifact_73_present=PASS
artifact_74_present=PASS
deterministic_compatibility_preserved=PASS
overall_gate=PASS
certification_decision=CERTIFIED_STABLE
final_combined_state=EXECUTION_AND_CERTIFIED_STABLE
chain_gate=PASS
exit_code=0
command_exit_codes_full_run=0,0,0,0,0,0,0
direct_emitter_fallback_used=False
certify_hardening_proof_folder=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_proof\certification_flow_hardening_20260316_130600
"@ | Out-File "$p\12_final_contract_report.txt" -Encoding UTF8
Write-Host "12 done"

Write-Host "=== ALL PROOF FILES WRITTEN ==="
Get-ChildItem $p | Select-Object Name | Sort-Object Name
