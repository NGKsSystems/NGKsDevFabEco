# NGKsDevFabEco — Release Gate Contract
**Version:** 1.0  
**Established:** 2026-03-19  
**Command:** `ngksdevfabric release-gate`  
**Baseline:** Certification_Baseline_v1

---

## Purpose

`release-gate` is the mandatory pre-release certification check for the NGKsDevFabEco ecosystem.  
**No release bundle is valid unless `release-gate` exits 0.**

It wraps `certify-baseline` internally and produces a compact, machine-readable verdict artifact.  
The verdict artifact must be retained alongside every release bundle.

---

## Inputs

| Input | Argument | Default |
|---|---|---|
| Ecosystem root | `--eco-root <path>` | cwd |
| Baseline override | `--baseline <manifest-path-or-dir>` | auto-discover latest `.baseline_v*` under `--eco-root` |
| Build mode | `--mode release\|debug\|...` | `release` |
| Strict mode | `--strict` | off |
| Skip builds | `--no-build` | off |
| Proof folder | `--pf <path>` | `<eco-root>/_proof/release_gate_runs/` |
| JSON output | `--json` | off |

---

## Required Command

```
ngksdevfabric release-gate --eco-root <path>
```

For manual milestone releases:
```
ngksdevfabric release-gate --eco-root . --strict
```

For CI (no build rebuild, probe+doctor only):
```
ngksdevfabric release-gate --eco-root . --no-build
```

---

## Pass / Fail Rules

| Condition | Exit Code | Meaning |
|---|---|---|
| All repos pass, no regressions | `0` | PASS — release may proceed |
| Any regression detected | `1` | FAIL — release is BLOCKED |
| Misconfiguration / missing baseline | `2` | ERROR — release cannot proceed |

### PASS criteria

The gate passes if and only if:
1. `certify-baseline` returns `GATE=PASS` for all repos in scope
2. No TIER_1 repo has `configure` or `build` regress from PASS → FAIL
3. No TIER_2 repo has `probe` or `doctor` regress from PASS → FAIL
4. (Strict mode only) No `doctor` exits non-zero

### FAIL criteria

The gate fails on **any** of:
- A TIER_1 repo: `probe`, `doctor`, `configure`, or `build` exits non-zero when baseline was PASS
- A TIER_2 repo: `probe` or `doctor` exits non-zero when baseline was PASS
- Tier contract violation: TIER_1 repo missing configure in baseline, or TIER_2 with configure set
- (Strict mode) Doctor warning drift (non-zero exit even from PASS baseline)

---

## Tier Evaluation

### TIER_1 — NGKSGRAPH_CERTIFIED

All four stages are mandatory:

| Stage | Required result |
|---|---|
| `probe` | PASS (same or better than baseline) |
| `doctor` | PASS (same or better than baseline) |
| `configure` | PASS (same or better than baseline) |
| `build` | PASS (same or better than baseline) |

A single FAIL in any stage blocks the gate.

### TIER_2 — EXTERNAL_GOVERNED

Only probe and doctor are in scope:

| Stage | Required result |
|---|---|
| `probe` | PASS (same or better than baseline) |
| `doctor` | PASS (same or better than baseline) |
| `configure` | N/A — not evaluated |
| `build` | N/A — not evaluated |

---

## Strict Mode

Use `--strict` for:
- Milestone releases (alpha, beta, RC, final)
- Any release that will be shipped externally

Normal mode (`--no-strict`) is suitable for:
- Daily internal builds
- CI smoke checks

In strict mode, any `doctor` exit with a non-zero code (even warnings) is treated as a regression.

---

## Verdict Artifact

The gate emits a compact JSON file:

**Path:** `<pf>/release_gate_runs/<run_id>/release_gate_verdict.json`

**Required fields:**

```json
{
  "verdict": "PASS | FAIL",
  "baseline_name": "Certification_Baseline_v1",
  "baseline_path": "/abs/path/to/repo_manifest.json",
  "git_head": "<40-char SHA>",
  "timestamp": "<ISO-8601 UTC>",
  "strict": false,
  "no_build": false,
  "build_mode": "release",
  "repos_checked": 10,
  "repos_pass": 10,
  "regression_count": 0,
  "improvement_count": 0,
  "tier_1_count": 6,
  "tier_2_count": 4,
  "certify_baseline_run_id": "certify_baseline_20260319_HHMMSS"
}
```

**Retention policy:** The `release_gate_verdict.json` must be zipped into the release bundle proof packet. Any release bundle that cannot produce a retained `release_gate_verdict.json` with `verdict=PASS` is not a valid release.

---

## How a Release Is Blocked

1. `ngksdevfabric release-gate` exits `1` (FAIL) or `2` (ERROR)
2. The `verdict` field in `release_gate_verdict.json` is `"FAIL"`
3. `regression_count > 0`

In all three cases:
- The release bundle **must not be cut**
- The `regression_count` regressions must be diagnosed and fixed
- `certify-baseline` must be re-run until it exits 0
- `release-gate` must be re-run until it exits 0
- The `release_gate_verdict.json` from the passing run must be retained

---

## Relationship to certify-baseline

```
release-gate
  └── internally calls run_certify_baseline()
        ├── probe  (all repos)
        ├── doctor (all repos)
        ├── configure+build (TIER_1 repos only, unless --no-build)
        └── tier contract enforcement
```

`certify-baseline` is the underlying engine. `release-gate` adds:
- Git HEAD capture
- Tier count summary
- Compact verdict JSON (machine-readable, archivable)
- Release-specific exit code semantics

Both commands write to `_proof/`. Only `release-gate` produces `release_gate_verdict.json`.

---

## CI Integration

For CI pipelines, the recommended usage is:

```yaml
- name: Release Gate
  run: |
    python -m ngksdevfabric.ngk_fabric.main release-gate \
      --eco-root $WORKSPACE \
      --no-build \
      --json
```

The `--json` flag emits the full verdict to stdout for structured log capture.  
Exit code `0` = green, `1` or `2` = block the pipeline.

---

## Proof Retention

| Artifact | Path | Required |
|---|---|---|
| Verdict JSON | `_proof/release_gate_runs/<run_id>/release_gate_verdict.json` | YES |
| certify-baseline gate JSON | `_proof/certify_baseline_runs/<run_id>/certify_baseline_gate.json` | YES |
| Release bundle zip | Per-release location | YES |

Both `release_gate_verdict.json` and `certify_baseline_gate.json` must be retained.  
See [certification_tiers.md](certification_tiers.md) for tier definitions.  
See [baseline_governance.md](baseline_governance.md) for baseline update rules.
