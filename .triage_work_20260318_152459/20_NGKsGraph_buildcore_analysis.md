# BuildCore Analysis - NGKsGraph

- repo: C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph
- command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksdevfabric.exe build . --profile debug
- working_directory: C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph
- exit_code: 2
- classification: INVALID_PLAN_STRUCTURE
- ownership: repo
- plan_path: not_found
- first_failing_node: target='app' in 20_graph stage with NO_SOURCES_MATCHED
- buildcore_invocation: not_executed (30_buildcore/00_stage.txt shows status=skipped reason=upstream_failed)

## Key stderr/stdout lines
- root_cause_stage=BUILDCORE_EXECUTION_FAILURE
- root_cause_code=BUILDCORE_NONZERO_EXIT
- exit_code=2
- 20_graph/00_resolve.txt: argv=ngksgraph plan --project C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph --mode ecosystem --env-capsule-lock C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\env_capsule.lock.json --pf C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\_proof\runs\devfabric_run_run_20260318_153321\20_graph --profile debug
- 20_graph/02_stderr.txt: ERROR: NO_SOURCES_MATCHED: target='app' src_glob=[src/**/*.cpp] matched 0 files ...
- 30_buildcore/00_stage.txt: stage=buildcore status=skipped reason=upstream_failed

## Evidence files
- env: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsGraph\00_env_snapshot.json
- configure: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsGraph\10_configure.json
- build: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsGraph\20_build.json
