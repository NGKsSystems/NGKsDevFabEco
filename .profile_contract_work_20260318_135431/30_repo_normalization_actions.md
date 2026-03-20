# Repo Normalization Actions

Scope: NGKsUI Runtime, NGKsMediaLab, NGKsFileVisionary, NGKsPlayerNative, NGKsGraph.

## Decision
No `ngksgraph.toml` profile block edits were required in target repositories.

## Evidence
- NGKsUI Runtime: profiles already present (`debug`, `release`).
- NGKsMediaLab: no profiles present, contract expects implicit default mode.
- NGKsFileVisionary: profiles already present (`debug`, `release`).
- NGKsPlayerNative: profiles already present (`debug`, `release`).
- NGKsGraph: profiles already present (`debug`, `release`).

## Normalization Applied
- Invocation normalization only:
  - Repos with profiles: include `--profile debug` for configure/build recert commands.
  - Repos without profiles: run configure/build without `--profile`.

## Notes
Remaining failures are outside profile-contract mismatch scope and are captured in `50_remaining_gaps.md`.
