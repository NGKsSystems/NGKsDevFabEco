# BuildCore Analysis - NGKsPlayerNative

- repo: C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative
- command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksdevfabric.exe build . --profile debug
- working_directory: C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative
- exit_code: 2
- classification: WORKDIR_ERROR
- ownership: ecosystem
- plan_path: C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\build_graph\debug\ngksgraph_plan.json
- first_failing_node: 20_graph stage invoked with wrong project path under third_party/JUCE/.../javascript and then failed with ECOSYSTEM_GRAPH_REQUIRED_FOR_NON_NODE_PLANS
- buildcore_invocation: not_executed (30_buildcore/00_stage.txt shows status=skipped reason=upstream_failed)

## Key stderr/stdout lines
- root_cause_stage=BUILDCORE_EXECUTION_FAILURE
- root_cause_code=BUILDCORE_NONZERO_EXIT
- exit_code=2
- 20_graph/00_resolve.txt: argv=ngksgraph plan --project C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\third_party\JUCE\modules\juce_gui_extra\native\javascript --mode ecosystem --env-capsule-lock C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\env_capsule.lock.json --pf C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof\runs\devfabric_run_run_20260318_153310\20_graph --profile debug
- 20_graph/02_stderr.txt: CONFIG_ERROR: ECOSYSTEM_GRAPH_REQUIRED_FOR_NON_NODE_PLANS
- 30_buildcore/00_stage.txt: stage=buildcore status=skipped reason=upstream_failed

## Evidence files
- env: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsPlayerNative\00_env_snapshot.json
- configure: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsPlayerNative\10_configure.json
- build: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsPlayerNative\20_build.json
