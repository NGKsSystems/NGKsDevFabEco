# Repo Certification: C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative

- REPO_GATE=PARTIAL
- OWNER=repo
- PRIMARY_BLOCKER=PROFILE_CONTRACT_MISMATCH
- PROOF_APP_LOCAL=PASS
- PROOF_ZIP_ONLY=PASS

## Steps
- step=probe rc=0 cmd=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\ngksdevfabric.exe probe .
  log=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_cert_work_20260318_110011\repo_reports_pass2\NGKsPlayerNative\probe.log
  summary=Documentation will be located at C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof | Set --backup-root (or NGKS_BACKUP_ROOT) to mirror backup documentation; otherwise backup is disabled. | project_root=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative | backup_root=disabled | proof_dir=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof\runs\probe_20260318_111151 | probe_report=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof\runs\probe_20260318_111151\probe_report.json | primary_path=npm | exit_code=0
- step=doctor rc=0 cmd=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\ngksdevfabric.exe doctor .
  log=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_cert_work_20260318_110011\repo_reports_pass2\NGKsPlayerNative\doctor.log
  summary=Documentation will be located at C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof | Set --backup-root (or NGKS_BACKUP_ROOT) to mirror backup documentation; otherwise backup is disabled. | project_root=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative | backup_root=disabled | proof_dir=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof\runs\doctor_20260318_111152 | toolchain_report=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof\runs\doctor_20260318_111152\toolchain_report.json | exit_code=0 | ----------------------------------------
- step=configure rc=1 cmd=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\ngksgraph.exe configure
  proof_zip=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof\run_20260318_081154.zip
  log=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_cert_work_20260318_110011\repo_reports_pass2\NGKsPlayerNative\configure.log
  summary=PROOF_ZIP=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative\_proof\run_20260318_081154.zip | CONFIG_ERROR: Profiles are defined in config; --profile is required.
- step=run rc=-1 cmd=SKIPPED
  summary=SKIPPED: optional, requires obvious runnable contract
