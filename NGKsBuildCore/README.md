# NGKsBuildCore

NGKsBuildCore is a Python MVP build runner that executes a DAG build plan with deterministic scheduling, parallel workers, and auditable proof logs.

## Commands

- `python -m ngksbuildcore --help`
- `python -m ngksbuildcore doctor`
- `python -m ngksbuildcore run --plan examples\hello_plan.json -j 8`
- `python -m ngksbuildcore explain --plan examples\hello_plan.json`

## Plan Contract

Plan JSON fields:

- `base_dir` optional, defaults to plan file directory
- `nodes` array of objects with:
  - `id` (string)
  - `desc` (string, optional)
  - `cwd` (string, optional)
  - `cmd` (string or string array)
  - `deps` (string array)
  - `inputs` (path array)
  - `outputs` (path array)
  - `env` (dict, optional)

## Proof Output

Each run writes to timestamped proof directory under `_proof` (or `NGKS_PROOF_ROOT`):

- `events.jsonl`
- `commands.jsonl`
- `summary.json`
- `summary.txt`
- `environment.txt`
- `tool_versions.txt`
- `git_status.txt`
- `git_head.txt`

## Integration Adapters

- `ngksbuildcore.adapters.graph_adapter.run_graph_plan`
- `ngksbuildcore.adapters.devfabric_adapter.build_from_manifest`
