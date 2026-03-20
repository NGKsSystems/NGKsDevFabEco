# Repo Certification: C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab

- REPO_GATE=PARTIAL
- OWNER=repo
- PRIMARY_BLOCKER=REPO_CONFIG_ERROR
- PROOF_APP_LOCAL=PASS
- PROOF_ZIP_ONLY=PASS

## Steps
- step=probe rc=0 cmd=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\ngksdevfabric.exe probe .
  log=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_cert_work_20260318_110011\repo_reports_pass2\NGKsMediaLab\probe.log
  summary=Documentation will be located at C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\_proof | Set --backup-root (or NGKS_BACKUP_ROOT) to mirror backup documentation; otherwise backup is disabled. | project_root=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab | backup_root=disabled | proof_dir=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\_proof\runs\probe_20260318_111147 | probe_report=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\_proof\runs\probe_20260318_111147\probe_report.json | primary_path=npm | exit_code=0
- step=doctor rc=0 cmd=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\ngksdevfabric.exe doctor .
  log=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_cert_work_20260318_110011\repo_reports_pass2\NGKsMediaLab\doctor.log
  summary=Documentation will be located at C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\_proof | Set --backup-root (or NGKS_BACKUP_ROOT) to mirror backup documentation; otherwise backup is disabled. | project_root=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab | backup_root=disabled | proof_dir=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\_proof\runs\doctor_20260318_111148 | toolchain_report=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\_proof\runs\doctor_20260318_111148\toolchain_report.json | exit_code=0 | ----------------------------------------
- step=configure rc=1 cmd=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\ngksgraph.exe configure
  proof_zip=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\_proof\run_20260318_081150.zip
  log=C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_cert_work_20260318_110011\repo_reports_pass2\NGKsMediaLab\configure.log
  summary=NGKSGRAPH_CONFIG_NORMALIZATION: qt.version='6.9.9' normalized_to_major=6 | PROOF_ZIP=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\_proof\run_20260318_081150.zip | CONFIG_ERROR: NO_SOURCES_MATCHED: target='app' src_glob=[src/**/*.cpp] matched 0 files, but repository contains source files (sample: app/cpp_host/src/main.cpp, app/cpp_host/src/mainwindow.cpp, app/win32_host/src/main.cpp).
- step=run rc=-1 cmd=SKIPPED
  summary=SKIPPED: optional, requires obvious runnable contract
