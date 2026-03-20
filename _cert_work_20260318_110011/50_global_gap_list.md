# Global Gap List

1. PROOF_POLICY_REGRESSION (ecosystem-wide): ngksdevfabric probe/doctor emit proof under app-root _proof\\runs as loose directories, violating zip-only policy for successful runs.
2. PROFILE_CONTRACT_MISMATCH (repo contract): several repos require explicit profile selection; bare ngksgraph configure fails cleanly with actionable error.
3. REPO_CONFIG_ERROR (repo-local): NGKsMediaLab configure currently returns config error under default invocation.
4. Build/Run gating not reached: build and run were skipped after configure gate failures to avoid noisy downstream data.

Counts: PASS=0 PARTIAL=5 FAIL=0 ecosystem=5 repo=0 environment=0
