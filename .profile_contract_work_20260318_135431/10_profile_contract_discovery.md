# Profile Contract Discovery

- Current NGKsGraph profile enforcement lives in Config.apply_profile and build.configure_project/resolve_plan_context.
- Existing behavior already errors when profiles exist and no --profile is supplied, but message does not list available profile names.
- Existing unknown profile error uses "Known profiles" wording; contract requires clear "Available profiles" guidance.
- configure_project currently auto-selects default profile when profile is omitted; this conflicts with explicit profile-required contract.
- DevFabric doctor currently does not report project profile inventory; small addition can surface this in toolchain_report.json.

## Target Repo Inventory Summary
- repo=C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime
  has_profiles=True; profile_names=debug, release; expectation=explicit_profile_required; blocker=unknown_until_retest; normalization=ensure configure commands use explicit profile
- repo=C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab
  has_profiles=False; profile_names=; expectation=implicit_default_allowed; blocker=unknown_until_retest; normalization=none
- repo=C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary
  has_profiles=True; profile_names=debug, release; expectation=explicit_profile_required; blocker=unknown_until_retest; normalization=ensure configure commands use explicit profile
- repo=C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative
  has_profiles=True; profile_names=debug, release; expectation=explicit_profile_required; blocker=unknown_until_retest; normalization=ensure configure commands use explicit profile
- repo=C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph
  has_profiles=True; profile_names=debug, release; expectation=explicit_profile_required; blocker=unknown_until_retest; normalization=ensure configure commands use explicit profile
