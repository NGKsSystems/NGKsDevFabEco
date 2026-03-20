# BuildCore Root Causes

## NGKsFileVisionary
- failure_type: TOOLCHAIN_MISSING
- ownership: environment
- command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksdevfabric.exe build . --profile debug
- exit_code: 2
- working_directory: C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary
- buildcore_invocation: not_executed (30_buildcore/00_stage.txt status=skipped reason=upstream_failed)
- first_failing_node: 20_graph target=app blocked by TARGET_RESOLUTION_BLOCKED (missing qt.entrypoint)
- evidence: 20_graph/00_resolve.txt argv=ngksgraph plan --project C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary ... --profile debug
- evidence: 20_graph/02_stderr.txt TARGET_RESOLUTION_BLOCKED: missing=1 conflicting=0 downgraded=0
- evidence: 20_graph/graph_resolution/17_resolution_summary.md capability=qt.entrypoint classification=missing detail=Required capability is unavailable.
- evidence: 30_buildcore/00_stage.txt stage=buildcore status=skipped reason=upstream_failed

## NGKsPlayerNative
- failure_type: WORKDIR_ERROR
- ownership: ecosystem
- command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksdevfabric.exe build . --profile debug
- exit_code: 2
- working_directory: C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative
- buildcore_invocation: not_executed (30_buildcore/00_stage.txt status=skipped reason=upstream_failed)
- first_failing_node: 20_graph invoked against unexpected nested path third_party\\JUCE\\modules\\juce_gui_extra\\native\\javascript
- evidence: 20_graph/00_resolve.txt argv=ngksgraph plan --project C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\third_party\JUCE\modules\juce_gui_extra\native\javascript ... --profile debug
- evidence: 20_graph/02_stderr.txt CONFIG_ERROR: ECOSYSTEM_GRAPH_REQUIRED_FOR_NON_NODE_PLANS
- evidence: 30_buildcore/00_stage.txt stage=buildcore status=skipped reason=upstream_failed

## NGKsGraph
- failure_type: INVALID_PLAN_STRUCTURE
- ownership: repo
- command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksdevfabric.exe build . --profile debug
- exit_code: 2
- working_directory: C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph
- buildcore_invocation: not_executed (30_buildcore/00_stage.txt status=skipped reason=upstream_failed)
- first_failing_node: 20_graph target='app' failed with NO_SOURCES_MATCHED
- evidence: 20_graph/00_resolve.txt argv=ngksgraph plan --project C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph ... --profile debug
- evidence: 20_graph/02_stderr.txt ERROR: NO_SOURCES_MATCHED: target='app' src_glob=[src/**/*.cpp] matched 0 files ...
- evidence: 30_buildcore/00_stage.txt stage=buildcore status=skipped reason=upstream_failed

