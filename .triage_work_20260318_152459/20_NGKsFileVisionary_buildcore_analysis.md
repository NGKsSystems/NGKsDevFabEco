# BuildCore Analysis - NGKsFileVisionary

- repo: C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary
- command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksdevfabric.exe build . --profile debug
- working_directory: C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary
- exit_code: 2
- classification: TOOLCHAIN_MISSING
- ownership: environment
- plan_path: C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary\build_graph\debug\ngksgraph_plan.json
- first_failing_node: 20_graph stage blocked for target=app by missing required capability qt.entrypoint
- buildcore_invocation: not_executed (30_buildcore/00_stage.txt shows status=skipped reason=upstream_failed)

## Key stderr/stdout lines
- root_cause_stage=BUILDCORE_EXECUTION_FAILURE
- root_cause_code=BUILDCORE_NONZERO_EXIT
- exit_code=2
- 20_graph/00_resolve.txt: argv=ngksgraph plan --project C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary --mode ecosystem --env-capsule-lock C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary\env_capsule.lock.json --pf C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary\_proof\runs\devfabric_run_run_20260318_153230\20_graph --profile debug
- 20_graph/02_stderr.txt: TARGET_RESOLUTION_BLOCKED: missing=1 conflicting=0 downgraded=0
- 20_graph/graph_resolution/17_resolution_summary.md: capability=qt.entrypoint classification=missing detail=Required capability is unavailable.
- 30_buildcore/00_stage.txt: stage=buildcore status=skipped reason=upstream_failed

## Evidence files
- env: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsFileVisionary\00_env_snapshot.json
- configure: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsFileVisionary\10_configure.json
- build: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsFileVisionary\20_build.json
