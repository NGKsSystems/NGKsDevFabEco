# Repo Certification: C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab

- REPO_GATE=FAIL
- OWNER=repo
- PRIMARY_BLOCKER=PROFILE_CONTRACT_MISMATCH
- PROOF_APP_LOCAL=N/A
- PROOF_ZIP_ONLY=FAIL

## Steps
- step=probe rc=2 cmd=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\ngksdevfabric.exe 
  log=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_cert_work_20260318_110011\repo_reports\NGKsMediaLab\probe.log
  summary=usage: ngksdevfabric [-h] |                      {probe,profile,build,doctor,run,certification-status,ngks,eco,term,render-doc,doc-gate,explain,certify,certify-validate,certify-gate,certify-target-check,project-health,bootstrap-certification,predict-risk,plan-validation,run-validation-plan,run-validation-and-certify,run-validation-plugins,deliver-connectors} ... | ngksdevfabric: error: the following arguments are required: cmd | root_cause_stage=COMMAND_DISPATCH_FAILURE | root_cause_code=INVALID_COMMAND_SHAPE | root_cause_confidence=0.98
- step=run rc=-1 cmd=SKIPPED
  summary=SKIPPED: run requires explicit runnable contract and successful build path
