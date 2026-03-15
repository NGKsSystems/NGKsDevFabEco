# DevFabEco Certification Workflow

## Overview

This workflow integrates target capability validation, baseline comparison, compatibility preflight, certification decision policy, and decision validation into the normal DevFabEco command surface.

## Target Capability Front Door

Certification commands validate the project target contract before compare/gate logic.

Target capability states:

- CERTIFICATION_READY
- CERTIFICATION_READY_WITH_WARNINGS
- CERTIFICATION_NOT_READY

Validation artifacts are emitted under a target validation subfolder in the run PF:

- `target_validation/00_target_inputs.json`
- `target_validation/01_target_contract_load.json`
- `target_validation/02_target_shape_validation.json`
- `target_validation/03_target_artifact_check.json`
- `target_validation/04_target_capability_classification.json`
- `target_validation/05_target_report.md`

Standalone target readiness check:

```powershell
python -m ngksdevfabric certify-target-check --project <target_project>
```

## Baseline Compare Flow

1. Run compare against a frozen baseline:

```powershell
python -m ngksdevfabric certify --project <target_project> --baseline <baseline_path>
```

2. Compare engine loads baseline and current result sets.
3. Compatibility preflight validates baseline/schema/scenario/metric/policy/snapshot compatibility.
4. It computes aggregate and scenario-level diffs only when comparison trust is preserved.
5. It emits a certification decision state and gate outcome.

Compatibility states:

- COMPATIBLE: safe to compare directly.
- COMPATIBLE_WITH_WARNINGS: comparison proceeds, warnings are recorded.
- INCOMPATIBLE: fail-closed behavior; decision becomes CERTIFICATION_INCONCLUSIVE.

Compatibility artifacts are emitted under a compatibility subfolder in the run PF:

- `compatibility/00_compatibility_inputs.json`
- `compatibility/01_baseline_schema_check.json`
- `compatibility/02_current_run_schema_check.json`
- `compatibility/03_scenario_compatibility.json`
- `compatibility/04_metric_schema_compatibility.json`
- `compatibility/05_policy_compatibility.json`
- `compatibility/06_snapshot_compatibility.json`
- `compatibility/07_compatibility_classification.json`
- `compatibility/08_compatibility_report.md`

## Decision Policy Flow

Decision policy maps decision states to explicit gate semantics:

- CERTIFIED_IMPROVEMENT -> PASS
- CERTIFIED_STABLE -> PASS
- CERTIFIED_REGRESSION -> FAIL
- CERTIFICATION_INCONCLUSIVE -> FAIL

Policy is defined in [certification_gate_policy.json](certification_gate_policy.json) and mirrored in decision artifacts.

## Validation Flow

1. Run integrated decision validation matrix:

```powershell
python -m ngksdevfabric certify-validate --project <target_project> --baseline <baseline_path>
```

2. Validation executes four controlled cases:
- stable
- inconclusive
- improvement
- regression

3. Outputs include:
- decision_validation_matrix.json
- decision_validation_summary.md
- certification_gate_policy.json

## Gate Behavior

- PASS outcomes: CERTIFIED_IMPROVEMENT, CERTIFIED_STABLE
- FAIL outcomes: CERTIFIED_REGRESSION, CERTIFICATION_INCONCLUSIVE

Compatibility behavior:

- INCOMPATIBLE forces fail-closed behavior.
- compare decision is treated as CERTIFICATION_INCONCLUSIVE.
- certify-gate enforces FAIL and nonzero exit code.

## Normal Closeout Sequence

1. Run `certify` for the active target and baseline.
2. Review decision outputs (`10_decision_evaluation.json`, `12_certification_decision.md`).
3. Run `certify-validate` to confirm state coverage and policy conformance.
4. Treat FAIL gates as release blockers.

## CI Gate Enforcement

Use the deterministic gate command for automation pipelines:

```powershell
python -m ngksdevfabric certify-gate --project <target_project> --baseline <baseline_path> --strict-mode on
```

Gate semantics:

- CERTIFIED_IMPROVEMENT -> PASS (exit 0)
- CERTIFIED_STABLE -> PASS (exit 0)
- CERTIFIED_REGRESSION -> FAIL (exit nonzero)
- CERTIFICATION_INCONCLUSIVE -> FAIL (exit nonzero)

Gate command artifacts include:

- `09_gate_result.json`
- `10_exit_policy.json`
- `11_ci_contract.json`
- `12_gate_summary.md`

Minimal pipeline snippet:

- [ci_pipeline_snippet.ps1](ci_pipeline_snippet.ps1)
