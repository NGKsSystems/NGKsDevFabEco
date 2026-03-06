<!-- markdownlint-disable -->

# NGKsEnvCapsule (Phase 1)

Deterministic environment capsule system for policy-driven environment detection and locking.

## Commands

- `ngksenvcapsule doctor`
- `ngksenvcapsule resolve [--config <path>] [--auto-install]`
- `ngksenvcapsule lock [--in <resolved.json>] [--out env_capsule.lock.json]`
- `ngksenvcapsule verify [--lock env_capsule.lock.json]`

## Quick Start

1. `python -m pip install -e .`
2. `ngksenvcapsule doctor`
3. `ngksenvcapsule resolve`
4. `ngksenvcapsule lock`
5. `ngksenvcapsule verify`

## Policy

- Config file: `ngksenvcapsule.toml` (optional)
- Default strategy: `prefer` for Python/MSVC/Windows SDK, `off` for Node
- `strategy=require` enforces exact runtime/toolchain match and fails with code 3

## Proof Artifacts

Every command writes proof files under `_proof/<command>_<timestamp>/` with `00_cmdline.txt`, `10_inputs.txt`, `20_outputs.txt`, and `30_errors.txt` on failure.
