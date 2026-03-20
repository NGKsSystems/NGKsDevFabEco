# Minimal Fix Plan

## Ecosystem fixes

- repo: NGKsPlayerNative | root_cause: WORKDIR_ERROR (graph stage planning with nested third_party path instead of repo root) | smallest_fix: fix project-root resolution in DevFabric build->graph handoff so `--project` remains repository root | risk: M

## Repo fixes

- repo: NGKsMediaLab | root_cause: BAD_GLOB_OR_TARGET_CONFIG | smallest_fix: adjust src_glob/target mapping in ngksgraph.toml to match actual source layout | risk: L
- repo: NGKsGraph | root_cause: BAD_GLOB_OR_TARGET_CONFIG | smallest_fix: adjust src_glob/target mapping in ngksgraph.toml to match actual source layout | risk: L

## Environment requirements

- repo: NGKsFileVisionary | root_cause: TOOLCHAIN_MISSING (required capability `qt.entrypoint` unavailable at graph resolution) | smallest_fix: install/configure Qt capability expected by target or lower target capability requirement if Qt is not intended | risk: M
