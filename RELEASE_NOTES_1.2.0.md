# NGKsDevFabEco 1.2.0 Release Snapshot

This snapshot captures the post-release stabilization baseline for 1.2.0.

## Included Capabilities

- Certification compare workflow
- Gate enforcement workflow
- Compatibility preflight behavior
- Target contract and readiness handling
- Subtarget roll-up certification
- Persistent historical regression memory
- Historical trend analysis
- Component health scoring
- Pre-merge predictive risk estimation
- Closed-loop resolution lifecycle tracking
- Resolution-informed predictive refinement
- Export adapter payload generation
- Delivery adapter payload generation
- Execution profile scaling and gating

## Stabilization Validation (Post-PyPI)

- Clean PyPI install tested in fresh virtual environment
- CLI command availability validated:
  - ngksdevfabric --help
  - ngksdevfabric certify --help
  - ngksdevfabric certify-gate --help
  - ngksdevfabric predict-risk --help
- Real MediaLab smoke from installed package:
  - certify-target-check: PASS
  - certify: PASS
  - certify-gate: PASS

## Reference Smoke Artifacts

- _proof/runs/certification_target_check_20260313_235903
- _proof/runs/certification_compare_20260313_235904
- _proof/runs/certification_gate_20260313_235909
