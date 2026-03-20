# Baseline Governance Rules

## Certification_Baseline_v1 — Governance Note

**Baseline:** `Certification_Baseline_v1`  
**Frozen:** 2026-03-18  
**Gate command:** `ngksdevfabric certify-baseline`  
**Release gate command:** `ngksdevfabric release-gate` *(mandatory pre-release — see [release_gate.md](release_gate.md))*  
**Scope:** 10 repos — 6 TIER_1 (NGKSGRAPH_CERTIFIED) + 4 TIER_2 (EXTERNAL_GOVERNED)

---

## When to Create v2

A new baseline version (`Certification_Baseline_v2`) must be created when:

1. **A new repo is added** to the certified set that requires full ngksgraph configure/build coverage.
2. **A tool-chain update** changes the expected gate signature (e.g. new Qt major version, new MSVC major version, new Python minor version that changes probe output).
3. **A deliberate capability change** is made to `canonical_target_spec.py` or the capability model that intentionally alters what `build_allowed` resolves to for any certified repo.
4. **A previously-failing stage is permanently resolved** and the FAIL baseline value is no longer valid as the reference point.
5. **A repo is removed** from the project ecosystem and should no longer gate releases.

Creating v2 does not invalidate v1. Both can coexist and be referenced by separate governance contexts.

---

## When a Baseline May Be Updated In-Place

The **existing** baseline (`repo_manifest.json`) may be updated in-place only for:

| Allowed update | Condition |
|---|---|
| Add a new repo with `PASS` gate | The repo has passing probe + doctor; no ngksgraph pipeline yet |
| Update a `commit` hash | The repo advanced HEAD without breaking any gate stage |
| Add a `github_url` or `note` field | Metadata-only; no stage values change |
| Update `repos_locked` count | After adding/removing repos in the same version |

**Not allowed in-place:**
- Changing any `probe`, `doctor`, `configure`, or `build` field from PASS → FAIL
- Removing a repo that previously had PASS gate (demote to a separate `_mothballed` entry or create v2)
- Re-classifying a stage from `N/A` to `PASS` without running and confirming the pipeline

---

## Who / What Can Approve Baseline Replacement

| Approver | Authority |
|---|---|
| Repository owner (NGKsSystems) | Full authority — can approve any baseline change |
| `certify-baseline GATE=PASS` run | Programmatic confirmation that no regression occurred; sufficient for metadata-only in-place updates |
| Manual review + commit on `master` | Required for any in-place stage value change or creation of v2 |
| CI pipeline | May update `commit` hashes automatically **only** after `certify-baseline` exits 0 and `release-gate` exits 0 |

A baseline replacement or v2 creation must always be recorded as a **git commit** on the `master` branch of `NGKsDevFabEco` with a commit message referencing the baseline name, change reason, and the `certify-baseline` run ID that justified the change.

---

## Regression vs. Accepted Change

### Regression (must be blocked)

A regression is any case where a stage that recorded `PASS` in the frozen baseline now exits non-zero. This means the environment, the source, or the toolchain degraded in a way that was not intentionally accepted.

- `certify-baseline` exits **1** and prints `[REGRESSION]` for the affected repo.
- The release pipeline **must not proceed**.
- The root cause must be diagnosed and fixed, or the change must be formally accepted (see below).

### Accepted Change (must be recorded)

An accepted change is a deliberate decision that a previously-passing stage will now produce a different result due to an intentional modification (new API, removed target, toolchain upgrade). The process is:

1. Run `certify-baseline` — confirm it exits 1 (regression detected).
2. Determine that the regression is intentional and documented.
3. Create a new baseline version (`v2`) with the new PASS values, or update the in-place entry with approver sign-off (see approval table above).
4. Commit the updated manifest to `master`.
5. Re-run `certify-baseline` against the new manifest — must exit 0 before the release proceeds.
6. Re-run `release-gate` — must exit 0 and produce `verdict=PASS` before the release bundle is cut.

### Improvement (auto-accepted)

A stage that recorded `FAIL` in the baseline now exits 0. This is an improvement. `certify-baseline` exits **0**, reports `[IMPROVEMENT]`, and no blocking action is required. The baseline may be updated in-place to record the new `PASS` value after the next successful run.

---

## Summary Decision Table

| Scenario | `certify-baseline` exit | Action required |
|---|---|---|
| All stages identical to baseline | 0 (PASS) | None — release may proceed |
| Any PASS→FAIL stage | 1 (FAIL) | Block release; fix or formally accept the regression |
| Any FAIL→PASS stage (no regressions) | 0 (PASS) | None; optionally update baseline in-place |
| Unreadable/missing manifest | 2 (ERROR) | Fix manifest; do not proceed |
| Warning drift under `--strict` | 1 (FAIL) | Investigate doctor output; remediate tool-chain |
