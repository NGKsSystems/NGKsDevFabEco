# NGKsLibrary

## ngksdocengine

DocEngine module for rendering unified proof summaries.

### Command

- `python -m ngksdocengine render --pf "<PF_PATH>"`

### Inputs

- `<PF>/00_run_manifest.json`
- Any of:
  - `<PF>/graph/component_report.json`
  - `<PF>/devfabric/component_report.json`
  - `<PF>/buildcore/component_report.json`

### Outputs (summary only)

- `<PF>/summary/index.json`
- `<PF>/summary/SUMMARY.md`

DocEngine also appends write records to `<PF>/00_writes_ledger.jsonl` with `writer: "docengine"` for the summary outputs.
