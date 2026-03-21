<!-- markdownlint-disable MD013 MD024 -->

# NGKs Proof Contract (ECO.1)

Authoritative local proof root for each DevFabric run:

`<project_root>/_proof/devfabric_run_<run_id>/`

Required files/folders:
- `00_run_header.txt`
- `99_summary.txt`
- `10_envcapsule/`
- `20_graph/`
- `30_buildcore/`
- `40_library/`

Allowed proof locations only:
1) local run PF (authoritative)
2) optional mirror PF under backup root with identical structure

Legacy root-level proof folders (e.g. `build_*`, `doctor_*`, `lock_*`) are forbidden in ecosystem mode and must be routed under stage PF.

Exit semantics:
- `0`: success or noop
- `1`: build_failed (supported build attempted and failed)
- `2`: precondition/tool_missing/profile invalid
