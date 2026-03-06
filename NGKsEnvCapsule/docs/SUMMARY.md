<!-- markdownlint-disable -->

# Summary

NGKsEnvCapsule implements policy -> resolve -> lock -> verify:

- Policy is defined in `ngksenvcapsule.toml`.
- Resolve detects host toolchains/runtimes and emits deterministic resolved facts.
- Lock converts resolved facts into deterministic lock artifacts.
- Verify compares current machine facts to lock facts without re-deciding policy.

Integration intent:

- Graph consumes capsule facts for environment graph nodes.
- BuildCore consumes lock hashes as deterministic build inputs.
- DevFabric uses capsule proofs for workstation readiness audits.
- Library tools can validate runtime/toolchain compatibility before execution.
