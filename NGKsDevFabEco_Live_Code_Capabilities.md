# NGKsDevFabEco Live Code Capabilities

This document is generated from direct static reading of the current code in this workspace (AST + parser and artifact pattern scans), not from memory.

Generated UTC: 2026-03-15T09:30:03.473731+00:00

## 1) Runtime Entry Points (from pyproject scripts)

- ngks -> ngksdevfabric.cli:main (NGKsDevFabric/pyproject.toml)
- ngksdevfabric -> ngksdevfabric.cli:main (NGKsDevFabric/pyproject.toml)
- ngksenvcapsule -> ngksenvcapsule.cli:main (NGKsEnvCapsule/pyproject.toml)
- ngksgraph -> ngksgraph.cli:main (NGKsGraph/pyproject.toml)
- ngkslibrary -> ngkslibrary.__main__:main (NGKsLibrary/pyproject.toml)

## 2) CLI Command Surfaces (from add_parser calls)

### NGKsBuildCore/ngksbuildcore/cli.py

- run
- doctor
- explain

### NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py

- probe
- profile
- init
- build
- doctor
- run
- ngks
- doctor
- plan
- build
- test
- ship
- analyze-failure
- graph-monitor
- eco
- doctor
- term
- run
- render-doc
- doc-gate
- explain
- file
- rebuild
- route
- dependency
- certify
- certify-validate
- certify-gate
- certify-target-check
- predict-risk
- plan-validation
- run-validation-plan
- run-validation-and-certify
- run-validation-plugins
- deliver-connectors

### NGKsEnvCapsule/src/ngksenvcapsule/cli.py

- doctor
- resolve
- lock
- verify
- print

### NGKsGraph/ngksgraph/cli.py

- init
- import
- scan
- configure
- build
- plan
- buildplan
- planaudit
- run
- clean
- doctor
- graph
- explain
- diff
- trace
- freeze
- thaw
- verify
- why
- rebuild-cause
- selftest

### NGKsLibrary/src/ngkslibrary/__main__.py

- assemble
- render

## 3) Module Capability Inventory (all scanned Python modules)

### NGKsBuildCore

- Python files scanned: 12
- Top-level functions: 31
- Top-level classes: 6

- NGKsBuildCore/ngksbuildcore/__init__.py | functions=0 classes=0
- NGKsBuildCore/ngksbuildcore/__main__.py | functions=0 classes=0
- NGKsBuildCore/ngksbuildcore/adapters/__init__.py | functions=0 classes=0
- NGKsBuildCore/ngksbuildcore/adapters/devfabric_adapter.py | functions=1 classes=0
  functions: build_from_manifest
- NGKsBuildCore/ngksbuildcore/adapters/graph_adapter.py | functions=1 classes=0
  functions: run_graph_plan
- NGKsBuildCore/ngksbuildcore/cli.py | functions=7 classes=0
  functions: _allow_direct_buildcore, _route_to_devfabeco_pipeline, _default_jobs, _doctor, _explain, build_parser, main
- NGKsBuildCore/ngksbuildcore/hashing.py | functions=3 classes=0
  functions: normalize_path, file_fingerprint, input_signature
- NGKsBuildCore/ngksbuildcore/loggingx.py | functions=1 classes=1
  functions: utc_now_iso
  classes: EventLogger
- NGKsBuildCore/ngksbuildcore/plan.py | functions=4 classes=2
  functions: _as_str_list, _legacy_node, _graph_action_node, load_plan
  classes: PlanNode, BuildPlan
- NGKsBuildCore/ngksbuildcore/runner.py | functions=11 classes=1
  functions: _resolve_paths, compute_action_key, should_run, _stream_pipe, _ensure_output_parent_dirs, execute_node, make_proof_dir, _write_summary, _write_env_snapshot, _write_input_records, run_build
  classes: NodeResult
- NGKsBuildCore/ngksbuildcore/scheduler.py | functions=3 classes=1
  functions: build_graph, seed_ready, release_children
  classes: GraphState
- NGKsBuildCore/ngksbuildcore/store.py | functions=0 classes=1
  classes: StateStore

### NGKsDevFabric

- Python files scanned: 68
- Top-level functions: 598
- Top-level classes: 30

- NGKsDevFabric/src/ngk_fabric/component_exec.py | functions=0 classes=0
- NGKsDevFabric/src/ngk_fabric/main.py | functions=0 classes=0
- NGKsDevFabric/src/ngk_fabric/runwrap.py | functions=0 classes=0
- NGKsDevFabric/src/ngksdevfabric/__init__.py | functions=0 classes=0
- NGKsDevFabric/src/ngksdevfabric/__main__.py | functions=0 classes=0
- NGKsDevFabric/src/ngksdevfabric/cli.py | functions=1 classes=0
  functions: main
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/__init__.py | functions=0 classes=0
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/api_contract_validation.py | functions=8 classes=1
  functions: _safe_float, _safe_int, _as_bool, _slug, _parse_version, _type_name, _schema_rows, _expected_map
  classes: APIContractValidationPlugin
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/architectural_complexity_validation.py | functions=7 classes=1
  functions: _safe_float, _safe_int, _slug, _share, _module_name, _module_metric, _depends_on
  classes: ArchitecturalComplexityValidationPlugin
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/assignment_policy.py | functions=7 classes=0
  functions: _write_json, _write_text, _safe_float, _is_strong_evidence, _classify_policy, _resolve_assignee, generate_assignment_safety_operator_actions
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | functions=4 classes=1
  functions: _is_numeric, _write_json, _write_text, run_compatibility_preflight
  classes: CompatibilityResult
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | functions=11 classes=1
  functions: _iso_now, _write_json, _write_text, _zip_dir, _classify_from_decision, _rollup_compatibility, _rollup_decision, _rollup_gate, _normalize_subtarget_rows, run_subtarget_rollup_comparison, run_subtarget_rollup_gate
  classes: RollupPolicy
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_target.py | functions=7 classes=2
  functions: _write_json, _write_text, _resolve_path, _safe_bool, _parse_subtargets, _find_contract, run_target_validation_precheck
  classes: SubtargetSpec, TargetValidationResult
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | functions=18 classes=4
  functions: _iso_now, _read_json, _write_json, _write_text, _zip_dir, _resolve_baseline_bundle, _resolve_current_bundle, _validate_baseline_shape, _scenario_timestamp_key, _score_value, _build_current_from_scenario_proofs, _to_scenario_map, _scenario_metric_value, _safe_float, _classify, _evaluate_decision, _decision_gate_outcome, run_certification_comparison
  classes: ComparisonPolicy, DecisionPolicy, BaselineBundle, CurrentBundle
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_gate.py | functions=4 classes=1
  functions: _iso_now, _write_json, _write_text, run_certification_gate
  classes: GateEnforcementPolicy
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/component_exec.py | functions=1 classes=1
  functions: resolve_component_cmd
  classes: ComponentResolutionError
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/connector_transport.py | functions=16 classes=0
  functions: _iso_now, _read_json, _write_json, _write_text, _normalize_mode, _as_bool, _default_config, load_connector_transport_config, _payload_items, _load_transport_payloads, _request_identifier, _headers_from_payload, _http_send_json, _validate_connector_live_config, _live_send, run_connector_transport
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | functions=10 classes=1
  functions: gate_policy_for, _now_stamp, _read_json, _write_json, _write_text, _clamp, _build_inconclusive_fixture, _build_improvement_fixture, _build_regression_fixture, run_decision_validation
  classes: CaseSpec
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/delivery_adapters.py | functions=5 classes=0
  functions: _write_json, _write_text, _read_json, _read_text, generate_connector_ready_delivery_payloads
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/delivery_reconciliation.py | functions=16 classes=0
  functions: _iso_now, _read_json, _write_json, _write_text, _safe_lower, _extract_issue_id, _parse_issue_parts, _issue_feed_index, _reconciliation_key, _history_store_path, load_acknowledgment_history, append_acknowledgments_history, find_reconciliation_match, build_acknowledgment_record, extract_issue_context, write_reconciliation_artifacts
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/devfabeco_orchestrator.py | functions=12 classes=1
  functions: _iso_now, _write_json, _write_text, _read_json, _tracked_graph_inputs, _file_sha256, ensure_graph_state_current, generate_graph_plan, execute_buildcore_plan, run_devfabric_diagnostics, _write_failure_diagnostics, run_build_pipeline
  classes: StageOutcome
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/devfabeco_validation_plugins.py | functions=3 classes=1
  functions: write_json, write_text, read_json
  classes: ValidationPlugin
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/execution_profiles.py | functions=3 classes=1
  functions: _normalize_profile_name, _load_profile_config, load_execution_profile
  classes: ExecutionProfileState
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/explain_engine.py | functions=19 classes=0
  functions: _now_iso, _read_json, _write_json, _latest_run_by_prefix, _load_context, _component_sets, _owner_for_file, _neighbors, _route_map_for_components, _component_environments, _component_toolchains, _graph_edges_for_components, _explain_file, _explain_rebuild, _explain_route, _explain_dependency, run_explain_query, _load_list, persist_explain_bundle
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/export_adapters.py | functions=6 classes=0
  functions: _write_json, _write_text, _safe_float, _owner_slug, _github_body, generate_ticket_export_adapters
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/external_status_sync.py | functions=16 classes=0
  functions: _iso_now, _read_json, _write_json, _write_text, _safe_lower, _parse_issue_parts, _default_status_sync_config, load_external_status_sync_config, _snapshot_rows, _normalize_external_status, _internal_lifecycle_index, _find_external_match, _closure_state, _next_sync_path, _write_delivery_history_summary, run_external_status_sync_and_closure_reconciliation
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/graph_state_manager.py | functions=16 classes=0
  functions: _iso_now, _write_json, _write_text, _state_file, _read_json, _tracked_files, _toolchain_fingerprint, _workspace_integrity_input, compute_project_fingerprint, load_graph_state, _dirty_reasons, persist_graph_state, evaluate_graph_state, _write_graph_state_artifacts, ensure_graph_state_fresh, mark_graph_state_dirty_if_changed
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/graph_state_monitor.py | functions=1 classes=1
  functions: start_background_graph_monitor
  classes: GraphStateMonitor
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_engine.py | functions=10 classes=0
  functions: _iso_now, _write_json, _write_text, _read_json, _next_run_id, _severity_bucket, _fingerprint_key, _extract_fingerprints_from_root, _collect_detected_fingerprints, record_regression_history
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_trends.py | functions=9 classes=0
  functions: _write_json, _write_text, _read_json, _safe_int, _safe_float, _clamp, _health_class, _run_rows, analyze_historical_trends
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/init.py | functions=0 classes=0
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/intelligence.py | functions=5 classes=0
  functions: _tool_available, _safe_rel, rank_routes, _parse_requirements, infer_dependency_holes
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/issue_update_policy.py | functions=16 classes=0
  functions: _iso_now, _read_json, _write_json, _write_text, _safe_lower, _load_connector_config, _is_connector_live_ready, _has_material_divergence, _decide_update_action, _ack_index, _payload_source_map, _find_create_payload, _build_update_payload, _next_update_path, _write_delivery_history_summary, run_bidirectional_issue_update_policy
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | functions=88 classes=1
  functions: _print_result, _run_root_cause_analysis, _enforce_workspace_integrity, _enforce_graph_state_automation, _enforce_validation_policy, _iso_now, _runid_now, _build_intent, _emit_component_reports_for_build, _default_pf, _canonical_pf, _git_root_for, _resolve_project_root, _project_path_from_argv, _collect_notebook_policy_hits, _record_notebook_policy_violation, _enforce_notebook_policy, _is_interactive_tty, _normalize_backup_root, _validate_backup_root
  classes: StageResult
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/memory_usage_validation.py | functions=6 classes=1
  functions: _safe_float, _safe_int, _share, _slug, _row_memory_mb, _stage_memory_map
  classes: MemoryUsageValidationPlugin
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/node_toolchain.py | functions=4 classes=0
  functions: _load_json_file, _resolve_repo_local_package_json, _load_repo_node_policy, detect_node_toolchain
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/ownership_confidence.py | functions=7 classes=0
  functions: _write_json, _write_text, _safe_float, _normalized, _component_mapping_strength, _confidence_level, generate_ownership_confidence_evidence
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/performance_bottleneck_validation.py | functions=4 classes=1
  functions: _safe_float, _safe_int, _share, _slug
  classes: PerformanceBottleneckValidationPlugin
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/predictive_resolution_refinement.py | functions=9 classes=1
  functions: _write_json, _write_text, _read_json, _safe_float, _safe_int, _clamp, _risk_class, _collect_persisting_by_component, apply_resolution_refinement
  classes: ResolutionRefinementModel
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/predictive_risk.py | functions=12 classes=1
  functions: _write_json, _write_text, _read_json, _safe_int, _safe_float, _clamp, _risk_class, _resolve_change_manifest, _select_trend_root, _select_resolution_root, _load_inputs, analyze_premerge_regression_risk
  classes: PredictionRiskModel
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/probe.py | functions=7 classes=0
  functions: _empty_fingerprints, _build_fingerprints, _classify, _recommended_commands, _bootstrap_candidates, _flatten_fingerprints, probe_project
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/profile.py | functions=1 classes=0
  functions: init_profile
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/proof_contract.py | functions=14 classes=0
  functions: _git_output, repo_state, ensure_unified_pf, _is_log, _is_output, _entry_for_file, collect_component_files, write_component_report, append_ledger, reconcile_ledger, _is_allowed_ledger_entry, doc_gate, _resolve_ngkslibrary_root, run_docengine_render
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/proof_manager.py | functions=16 classes=0
  functions: _now_iso, _parse_timestamp_from_name, _infer_run_type, _read_json, _extract_gate, _extract_route, _extract_dependency_holes, _extract_conflicts, _extract_weaknesses, _canonical_bundle_path, _canonical_zip_path, _create_run_zip, _update_latest_operator_zip, _write_latest, _write_index, register_proof_bundle
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/receipts.py | functions=15 classes=0
  functions: _get_proof_context, set_proof_context, clear_proof_context, _append_ledger_entry_for_path, utc_now_iso, ensure_dir, write_text, write_json, file_sha256, file_sha256_safe, hash_command, run_command_capture, tool_version, is_writable_directory, apply_src_to_env
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/regression_hotspots.py | functions=5 classes=0
  functions: _write_json, _write_text, _safe_float, _scenario_weight, analyze_regression_hotspots
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/regression_intelligence.py | functions=9 classes=0
  functions: _read_json, _write_json, _write_text, _safe_int, _safe_float, _clamp, _watch_class, _recommended_action, analyze_regression_intelligence
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/remediation_guidance.py | functions=6 classes=0
  functions: _write_json, _write_text, _safe_float, _scenario_component_hint, _dominant_metric, generate_remediation_guidance
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolution_tracking.py | functions=11 classes=0
  functions: _write_json, _write_text, _read_json, _safe_int, _safe_float, _run_num, _collect_proof_history_rows, _collect_presence_map, _consecutive_streak_before, _resolution_streak_lengths, analyze_regression_resolution
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolver.py | functions=4 classes=0
  functions: _safe_run, _vswhere_candidates, _detect_dotnet, resolve_tools
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | functions=8 classes=0
  functions: _iso_now, _write_json, _write_text, _read_json, _read_text, _artifact_rel, _discover_capability_reports, analyze_failure
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_rules.py | functions=7 classes=0
  functions: _norm, _bool_payload, _first_existing_ref, _compiler_like, _linker_like, _packaging_like, classify_root_cause
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_types.py | functions=0 classes=2
  classes: RootCauseClassification, RootCauseInputContext
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | functions=36 classes=0
  functions: parse_sln_solution_configs, _mode_to_request, _resolve_sln_config, _quote_if_needed, _normalize_solution_build_log, _classify_failure, _sln_fingerprint_files, _collect_dotnet_fingerprint_files, _collect_strategy_fingerprint_files, _compute_fingerprint, _load_profile, _detect_backend, _select_path, _bootstrap_command, _run_graph_cli_if_available, generate_build_plan, _mode_to_graph_profile, _append_text, _resolve_graph_invocation, _resolve_graph_project
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | functions=7 classes=1
  functions: _safe_int, _as_bool, _slug, _is_secret_value, _local_host, _headers_from_entry, _text_payload
  classes: SecurityMisconfigurationValidationPlugin
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | functions=7 classes=1
  functions: resolve_smart_terminal_enabled, detect_shell, _stream_reader, _execute_and_stream, _allocate_run_dir, run_shell, run_shell_direct
  classes: ShellPlan
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/team_ownership_mapping.py | functions=9 classes=0
  functions: _write_json, _write_text, _read_json, _safe_float, _component_slug, _infer_team, _inferred_assignment, _load_team_map, apply_team_ownership_mapping
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/triage_tickets.py | functions=7 classes=0
  functions: _write_json, _write_text, _safe_float, _priority_class, _issue_id, _issue_title, generate_auto_triage_tickets
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/ui_layout_integrity_validation.py | functions=7 classes=1
  functions: _safe_float, _safe_int, _clamp, _slug, _bounds, _has_explicit_vertical_position, _resolved_child_bounds
  classes: UILayoutIntegrityValidationPlugin
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_orchestrator.py | functions=15 classes=0
  functions: _read_json, _write_json, _write_text, _safe_float, _safe_int, _clamp, _normalize_policy, _has_planning_bundle, _select_latest_plan_run, _row_index, _scenario_signal_score, _result_classification, _detected_regressions, _runtime_seconds, run_validation_orchestrator
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_planner.py | functions=13 classes=0
  functions: _read_json, _write_json, _write_text, _safe_float, _safe_int, _clamp, _resolve_change_manifest, _select_latest_run_with_intelligence, _select_latest_predictive_run, _plan_class, _watch_index, _predictive_component_index, plan_premerge_validation
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_plugin_registry.py | functions=1 classes=1
  functions: execute_validation_plugins
  classes: ValidationPluginRegistry
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_policy_engine.py | functions=7 classes=0
  functions: _write_json, _write_text, _has_any_match, _collect_project_context, _required_subset, _evaluate_policy_row, evaluate_validation_policy
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_policy_loader.py | functions=2 classes=0
  functions: _as_tuple_list, load_validation_policy
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_policy_types.py | functions=0 classes=1
  classes: ValidationPluginPolicy
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_rerun_pipeline.py | functions=8 classes=0
  functions: _read_json, _write_json, _write_text, _safe_int, _is_execution_failure, _combined_state_from_rerun, _chain_gate, run_validation_and_certify_pipeline
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/workflow_recommendation.py | functions=6 classes=0
  functions: _read_json, _write_json, _write_text, _safe_int, _watch_rank, recommend_post_rerun_workflow
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/workspace_integrity.py | functions=9 classes=1
  functions: _resolve_module_file, _is_under_workspace, _collect_module_resolution, _apply_simulated_bad_resolution, _build_result, _write_text, _write_json, write_integrity_artifacts, run_workspace_integrity_check
  classes: IntegrityResult

### NGKsEnvCapsule

- Python files scanned: 24
- Top-level functions: 49
- Top-level classes: 13

- NGKsEnvCapsule/src/ngksenvcapsule/__init__.py | functions=0 classes=0
- NGKsEnvCapsule/src/ngksenvcapsule/__main__.py | functions=0 classes=0
- NGKsEnvCapsule/src/ngksenvcapsule/capsule_schema.py | functions=1 classes=0
  functions: validate_capsule
- NGKsEnvCapsule/src/ngksenvcapsule/cli.py | functions=2 classes=0
  functions: _build_parser, main
- NGKsEnvCapsule/src/ngksenvcapsule/config.py | functions=2 classes=2
  functions: _policy, load_config
  classes: ProviderPolicy, CapsuleConfig
- NGKsEnvCapsule/src/ngksenvcapsule/core/__init__.py | functions=0 classes=0
- NGKsEnvCapsule/src/ngksenvcapsule/core/constraints.py | functions=3 classes=0
  functions: _norm, _strategy, parse_constraints_from_config
- NGKsEnvCapsule/src/ngksenvcapsule/core/engine.py | functions=7 classes=0
  functions: _sort_candidates, build_host_context, collect_candidates, resolve_capsule, verify_capsule, raise_for_resolution_errors, raise_for_verify_errors
- NGKsEnvCapsule/src/ngksenvcapsule/core/errors.py | functions=0 classes=5
  classes: CapsuleError, ConfigError, MissingRequiredError, VerifyFailedError, InternalError
- NGKsEnvCapsule/src/ngksenvcapsule/core/registry.py | functions=1 classes=0
  functions: get_default_registry
- NGKsEnvCapsule/src/ngksenvcapsule/core/types.py | functions=0 classes=5
  classes: HostContext, Constraint, Candidate, Selection, CapsuleFacts
- NGKsEnvCapsule/src/ngksenvcapsule/doctor.py | functions=1 classes=0
  functions: run
- NGKsEnvCapsule/src/ngksenvcapsule/hashing.py | functions=3 classes=0
  functions: sha256_bytes, sha256_file, write_hash_file
- NGKsEnvCapsule/src/ngksenvcapsule/install.py | functions=2 classes=0
  functions: manual_python_instructions, handle_python_missing
- NGKsEnvCapsule/src/ngksenvcapsule/lock.py | functions=1 classes=0
  functions: run
- NGKsEnvCapsule/src/ngksenvcapsule/proof.py | functions=1 classes=1
  functions: utc_now_iso
  classes: ProofSession
- NGKsEnvCapsule/src/ngksenvcapsule/providers/__init__.py | functions=1 classes=0
  functions: get_provider_registry
- NGKsEnvCapsule/src/ngksenvcapsule/providers/node_runtime.py | functions=5 classes=0
  functions: _safe_run, detect, select, fingerprint, verify
- NGKsEnvCapsule/src/ngksenvcapsule/providers/python_runtime.py | functions=5 classes=0
  functions: detect, select, fingerprint, verify, provision
- NGKsEnvCapsule/src/ngksenvcapsule/providers/win_msvc.py | functions=4 classes=0
  functions: detect, select, fingerprint, verify
- NGKsEnvCapsule/src/ngksenvcapsule/providers/win_windows_sdk.py | functions=5 classes=0
  functions: _ver_tuple, detect, select, fingerprint, verify
- NGKsEnvCapsule/src/ngksenvcapsule/resolve.py | functions=1 classes=0
  functions: run
- NGKsEnvCapsule/src/ngksenvcapsule/stablejson.py | functions=2 classes=0
  functions: dumps_stable, write_stable_json
- NGKsEnvCapsule/src/ngksenvcapsule/verify.py | functions=2 classes=0
  functions: verify_payload, run

### NGKsGraph

- Python files scanned: 93
- Top-level functions: 434
- Top-level classes: 39

- NGKsGraph/ngksgraph/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/__main__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/authority/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/authority/authority_engine.py | functions=2 classes=0
  functions: _is_detected, evaluate_authority
- NGKsGraph/ngksgraph/authority/authority_rules.py | functions=3 classes=0
  functions: _rules_file, _load_rules_from_json, default_authority_items
- NGKsGraph/ngksgraph/binary_contract.py | functions=1 classes=0
  functions: inspect_binary_integrity
- NGKsGraph/ngksgraph/build.py | functions=36 classes=0
  functions: _paths, _upsert_build_report, _report_base, _env_get_case_insensitive, _merge_env_case_insensitive, _graph_payload, _snapshot_root, _snapshot_now_dir, _target_closure_hashes, _snapshot_hashes, _prune_snapshots, _write_snapshot, latest_diff_summary, trace_source, _selected_target, _generate_artifacts, _validate_configure_contracts, _inject_qt_target_overrides, _apply_cached_target_overrides, _qt_result_from_plan
- NGKsGraph/ngksgraph/capability/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/capability/capability_detector.py | functions=5 classes=0
  functions: _record, detect_compiler_capabilities, detect_windows_sdk_capability, detect_debug_symbols_capability, detect_qt_capabilities
- NGKsGraph/ngksgraph/capability/capability_inventory.py | functions=1 classes=0
  functions: build_capability_inventory
- NGKsGraph/ngksgraph/capability/capability_reporter.py | functions=1 classes=0
  functions: inventory_payload
- NGKsGraph/ngksgraph/capability/capability_types.py | functions=0 classes=2
  classes: CapabilityRecord, CapabilityInventory
- NGKsGraph/ngksgraph/capsule.py | functions=22 classes=0
  functions: _normalize_newlines, _json_text, _slug, _query_command_text, _detect_cl_version, _read_last_report, build_toolchain_summary, _graph_link_closure, closure_hashes_from_graph, compute_hashes, compute_qt_generated_hashes, verify_hashes, build_capsule_payload_files, write_deterministic_capsule_zip, _load_snapshot_artifacts, _default_capsule_path, _resolve_snapshot_dir, _update_last_report_with_capsule, freeze_capsule, _read_capsule_json
- NGKsGraph/ngksgraph/classify/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/classify/evidence_classifier.py | functions=1 classes=0
  functions: classify
- NGKsGraph/ngksgraph/classify/trust_assigner.py | functions=1 classes=0
  functions: trust_for_evidence
- NGKsGraph/ngksgraph/cli.py | functions=41 classes=1
  functions: _resolve_git_commit, version_string, _repo_root_from_cwd, _resolve_project_root, _resolve_repo_and_config, _first_missing_tool, _config_path, _parse_seed_range, _default_selftest_out, _new_component_proof_dir, _hash_lock_file, _read_capsule_hash_file, _resolve_env_capsule_binding, _write_ecosystem_inputs, _write_ecosystem_outputs, _write_ecosystem_error, _run_target_resolution, _read_init_template_text, cmd_init, cmd_configure
  classes: _VersionAction
- NGKsGraph/ngksgraph/compdb.py | functions=6 classes=0
  functions: _quote, _obj_rel_path, build_compile_command, build_link_command, build_link_command_for_graph, generate_compile_commands
- NGKsGraph/ngksgraph/compdb_contract.py | functions=9 classes=0
  functions: load_compdb, _norm_for_hash, normalize_for_hash, compdb_hash, _path_to_rel, _extract_include_flags, _extract_define_flags, _quote_violations, validate_compdb
- NGKsGraph/ngksgraph/config.py | functions=5 classes=7
  functions: _normalize_lib_name, _as_list, _target_from_raw, load_config, save_config
  classes: QtConfig, AIProviderConfig, AIConfig, SnapshotConfig, ProfileConfig, TargetConfig, Config
- NGKsGraph/ngksgraph/contradiction/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/contradiction/contradiction_engine.py | functions=2 classes=0
  functions: _load_text, detect_contradictions
- NGKsGraph/ngksgraph/contradiction/contradiction_rules.py | functions=4 classes=0
  functions: _rules_file, _load_rules, contradiction_ids, contradiction_policy
- NGKsGraph/ngksgraph/core/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/core/enums.py | functions=0 classes=3
  classes: PreflightStatus, EvidenceType, TrustClass
- NGKsGraph/ngksgraph/core/hashing.py | functions=1 classes=0
  functions: sha256_json
- NGKsGraph/ngksgraph/core/io_json.py | functions=3 classes=0
  functions: write_json, write_text, read_json
- NGKsGraph/ngksgraph/core/models.py | functions=0 classes=2
  classes: ScanRunResult, Subproject
- NGKsGraph/ngksgraph/core/timestamps.py | functions=2 classes=0
  functions: now_utc, scan_stamp
- NGKsGraph/ngksgraph/detect/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/detect/detection_rules_engine.py | functions=4 classes=0
  functions: _rules_file, _load_rules, _expand_brace_glob, evaluate_detection_rules
- NGKsGraph/ngksgraph/detect/framework_detector.py | functions=2 classes=0
  functions: load_text, detect_frameworks
- NGKsGraph/ngksgraph/detect/language_detector.py | functions=4 classes=0
  functions: _classify_m_file, detect_language_for_path, confidence, primary_project_type
- NGKsGraph/ngksgraph/detect/manifest_detector.py | functions=3 classes=0
  functions: detect_manifest_hints, detect_package_ecosystem, detect_build_system
- NGKsGraph/ngksgraph/detect/monorepo_splitter.py | functions=2 classes=0
  functions: _matches_marker, split_subprojects
- NGKsGraph/ngksgraph/detect/repo_detection_engine.py | functions=10 classes=1
  functions: should_skip_dir, bump, classify_ambiguous_m_file, detect_manifest, detect_build_system, language_from_extension, normalize_language, package_ecosystem_from_manifest, walk_repo, main
  classes: RepoDetectionResult
- NGKsGraph/ngksgraph/diff.py | functions=14 classes=0
  functions: list_snapshots, resolve_snapshot, _load_json, _list_diff, _target_fields_diff, analyze_field_root_cause, _hash_changes, _compdb_deltas, _structural_diff_core, structural_diff, structural_diff_from_payloads, summarize_diff, diff_to_text, stable_diff_json
- NGKsGraph/ngksgraph/env/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/env/compiler_contracts.py | functions=1 classes=0
  functions: compiler_family
- NGKsGraph/ngksgraph/env/env_contract.py | functions=4 classes=0
  functions: _has_vcvars, _qt_on_path, _has_project_venv, build_env_contract
- NGKsGraph/ngksgraph/env/runtime_contracts.py | functions=1 classes=0
  functions: has_qt_runtime
- NGKsGraph/ngksgraph/explain/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/explain/markdown_renderer.py | functions=1 classes=0
  functions: render_summary
- NGKsGraph/ngksgraph/explain/summary_builder.py | functions=1 classes=0
  functions: build_summary_data
- NGKsGraph/ngksgraph/forensics.py | functions=18 classes=0
  functions: _edge_attr, _snapshot_root, _load_json, _load_snapshot_payload, _load_capsule_payload, _all_paths, _first_seen_snapshot_for_edge, _target_index, _current_payload, _load_baseline_pair, _find_edge, _build_target_source_map, _extract_missing_symbols, symbol_forensics, why_target, rebuild_cause_target, why_to_text, rebuild_cause_to_text
- NGKsGraph/ngksgraph/graph.py | functions=2 classes=3
  functions: build_graph_from_config, build_graph_from_project
  classes: Edge, Target, BuildGraph
- NGKsGraph/ngksgraph/graph_contract.py | functions=10 classes=0
  functions: _obj_path, _target_output, _canonical_profile_path, _to_out_relative, expected_compile_units, expected_objects, expected_link_inputs, compute_structural_graph_hash, validate_profile_parity, validate_graph_integrity
- NGKsGraph/ngksgraph/hashutil.py | functions=3 classes=0
  functions: stable_json_dumps, sha256_text, sha256_json
- NGKsGraph/ngksgraph/imply/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/imply/implication_engine.py | functions=1 classes=0
  functions: derive_requirements
- NGKsGraph/ngksgraph/imply/implication_rules.py | functions=4 classes=0
  functions: _rules_file, _load_rules, starter_rule_ids, implication_rules
- NGKsGraph/ngksgraph/import_cmake.py | functions=9 classes=2
  functions: _strip_comments, _iter_calls, _tokenize, _expand_token, _expand_tokens, _normalize_src_list, parse_cmake, _to_config, import_cmake_project
  classes: ImportedTarget, CMakeModel
- NGKsGraph/ngksgraph/log.py | functions=4 classes=0
  functions: _atomic_write_text, write_json, write_text, read_tail_lines
- NGKsGraph/ngksgraph/mode.py | functions=2 classes=1
  functions: get_mode, is_ecosystem
  classes: Mode
- NGKsGraph/ngksgraph/msvc.py | functions=15 classes=2
  functions: _strip_wrapping_quotes, find_vswhere_path, find_vs_installation, _latest_msvc_tool_bin, _which_in_env, resolve_msvc_toolchain_paths, resolve_vsdevcmd_path, build_capture_env_command, build_capture_env_invocation, parse_set_output, _env_get, capture_msvc_environment, _tool_on_path, has_cl_link, bootstrap_msvc
  classes: MSVCBootstrapResult, MSVCToolchainPaths
- NGKsGraph/ngksgraph/plan/__init__.py | functions=27 classes=0
  functions: _obj_rel_path, _target_output, _toolchain_label, _normalize_hash_path, _normalize_hash_list, _step_fingerprint, _step_id, _compile_step, _link_step, create_build_plan, write_build_plan_json, _buildcore_target_output, _buildcore_obj_rel_path, _stable_node_id, _staticlib_command, _quote, _target_uses_qt, _target_windeployqt, create_buildcore_plan, write_buildcore_plan_json
- NGKsGraph/ngksgraph/plan/capability_mapper.py | functions=1 classes=0
  functions: capability_map
- NGKsGraph/ngksgraph/plan/native_plan_builder.py | functions=1 classes=0
  functions: build_native_plan
- NGKsGraph/ngksgraph/plan_cache.py | functions=15 classes=0
  functions: cache_paths, ensure_cache_layout, clear_profile_cache, _pattern_root, _target_scope_roots, _qrc_referenced_files, build_scan_fingerprint, _danger_env, _compiler_fingerprint, _qt_tool_fingerprint, build_plan_key, json_sha, save_cache_record, read_json_file, touch_cache_hit
- NGKsGraph/ngksgraph/planner/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/planner/capability_mapper.py | functions=1 classes=0
  functions: capability_map
- NGKsGraph/ngksgraph/planner/native_plan_builder.py | functions=1 classes=0
  functions: build_native_plan
- NGKsGraph/ngksgraph/plugins/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/plugins/base.py | functions=0 classes=1
  classes: AIRepairPlugin
- NGKsGraph/ngksgraph/plugins/loader.py | functions=2 classes=0
  functions: _resolve_plugin_obj, load_plugin
- NGKsGraph/ngksgraph/plugins/stub_ai.py | functions=0 classes=1
  classes: Plugin
- NGKsGraph/ngksgraph/probe/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/probe/file_walker.py | functions=2 classes=0
  functions: iter_repo_files, relative
- NGKsGraph/ngksgraph/probe/ownership_probe.py | functions=1 classes=0
  functions: ownership_for_path
- NGKsGraph/ngksgraph/probe/path_classifier.py | functions=2 classes=0
  functions: directory_hint, is_stale_risk_path
- NGKsGraph/ngksgraph/probe/tool_probe.py | functions=1 classes=0
  functions: probe_tools
- NGKsGraph/ngksgraph/proof.py | functions=6 classes=2
  functions: resolve_repo_root, resolve_proof_root, new_proof_run, gather_git_metadata, write_summary, zip_run
  classes: TeeTextIO, ProofRun
- NGKsGraph/ngksgraph/qt.py | functions=15 classes=2
  functions: _qt_modules_from_libs, resolve_qt_toolchain, _tool_version, _ensure_qt_tools, _pattern_root, _target_scope_roots, _collect_headers_ui_qrc, _contains_q_object, _qrc_referenced_files, _unique_output_path, _run_generator, _node_fingerprint, _fingerprint_file, _maybe_generate, integrate_qt
  classes: QtGeneratorNode, QtIntegrationResult
- NGKsGraph/ngksgraph/repair.py | functions=10 classes=0
  functions: parse_errors, _search_file_by_name, _target_for_action, _validate_graph_integrity, _apply_with_rollback, apply_action, apply_ai_action, deterministic_fix, sanitize_for_ai, validate_ai_actions
- NGKsGraph/ngksgraph/repo_classifier.py | functions=23 classes=1
  functions: _iter_repo_files, _discover_repo_app_mains, _has_engine_sources, _detect_source_globs, _detect_flutter_source_globs, _detect_juce_source_globs, _detect_include_dirs, _detect_flutter_include_dirs, _detect_juce_include_dirs, _read_text_if_exists, _is_flutter_repo, _count_juce_signals, _collect_text_signals, _infer_qt_modules, _detect_qt_root, classify_repo, _render_common_header, _render_qt_block, _render_ai_block, _render_single_target
  classes: RepoClassification
- NGKsGraph/ngksgraph/resolver/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/resolver/target_resolution_engine.py | functions=3 classes=0
  functions: _parse_standard, _row, resolve_target_capabilities
- NGKsGraph/ngksgraph/resolver/target_resolution_report.py | functions=4 classes=0
  functions: _write_json, _write_text, _recommendations, write_resolution_artifacts
- NGKsGraph/ngksgraph/resolver/target_resolution_types.py | functions=0 classes=2
  classes: ResolutionRow, ResolutionReport
- NGKsGraph/ngksgraph/sanitize.py | functions=5 classes=0
  functions: _replace_drive, _sanitize_string, _sanitize_value, sanitize_graph_dict, sanitize_compile_commands
- NGKsGraph/ngksgraph/scan.py | functions=4 classes=0
  functions: scan_target_sources, discover_repo_source_candidates, scan_sources_by_target, scan_sources
- NGKsGraph/ngksgraph/scan_pipeline.py | functions=4 classes=0
  functions: _scan_id, _ensure_project_venv, _write_contract_artifacts, run_scan
- NGKsGraph/ngksgraph/selftest.py | functions=17 classes=1
  functions: _utc_stamp, _hashes, _generator_fps, _cleanup_project, _run_case, _scenario_determinism_core, _scenario_qt_generators, _scenario_paths_with_spaces, _scenario_capsule_integrity, _scenario_tool_corruption_detection, _scenario_parallel_isolation, _scenario_compdb_contract, _scenario_graph_integrity, _scenario_profiles_parity, run_selftest, write_report, print_summary
  classes: SelftestFailure
- NGKsGraph/ngksgraph/stale/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/stale/stale_guard.py | functions=3 classes=0
  functions: _iter_stale_candidates, _append_dead_path_items, evaluate_stale_risk
- NGKsGraph/ngksgraph/stale/stale_rules.py | functions=2 classes=0
  functions: _rules_file, _load_rules
- NGKsGraph/ngksgraph/targetspec/__init__.py | functions=0 classes=0
- NGKsGraph/ngksgraph/targetspec/canonical_target_spec.py | functions=4 classes=0
  functions: _source_roots, _entrypoints, _required_capabilities, derive_canonical_target_spec
- NGKsGraph/ngksgraph/targetspec/target_spec_loader.py | functions=4 classes=0
  functions: _candidate_paths, _to_spec, _validate_required, load_or_derive_target_spec
- NGKsGraph/ngksgraph/targetspec/target_spec_types.py | functions=0 classes=4
  classes: TargetType, TargetLanguage, TargetPlatform, CanonicalTargetSpec
- NGKsGraph/ngksgraph/toolchain.py | functions=6 classes=0
  functions: _exists_on_path, _exists_on_env_path, _get_env_path_case_insensitive, detect_toolchain, doctor_report, doctor_toolchain_report
- NGKsGraph/ngksgraph/torture_project.py | functions=4 classes=1
  functions: _write_fake_qt_tools, _mixed_slash, _apply_mixed_slashes_to_config, gen_project
  classes: GeneratedProject
- NGKsGraph/ngksgraph/util.py | functions=5 classes=0
  functions: normalize_path, rel_path, stable_unique_sorted, sha256_text, sha256_file

### NGKsLibrary

- Python files scanned: 5
- Top-level functions: 7
- Top-level classes: 1

- NGKsLibrary/src/ngkslibrary/__init__.py | functions=0 classes=0
- NGKsLibrary/src/ngkslibrary/__main__.py | functions=4 classes=0
  functions: _resolve_run_id, cmd_assemble, build_parser, main
- NGKsLibrary/src/ngkslibrary/docengine/__init__.py | functions=0 classes=0
- NGKsLibrary/src/ngkslibrary/docengine/proof_context.py | functions=0 classes=1
  classes: ProofContext
- NGKsLibrary/src/ngkslibrary/docengine/report.py | functions=3 classes=0
  functions: _utc_now, _read_kv, render_report

## 4) Artifact Emission Surface (JSON/MD/TXT writes detected)

- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/api_contract_validation.py | write_json -> 260_required_field_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/api_contract_validation.py | write_json -> 261_type_mismatch_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/api_contract_validation.py | write_json -> 262_unknown_field_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/api_contract_validation.py | write_json -> 263_version_drift_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/api_contract_validation.py | write_json -> 264_contract_recommendations.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/api_contract_validation.py | write_text -> 265_contract_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/architectural_complexity_validation.py | write_json -> 250_nesting_depth_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/architectural_complexity_validation.py | write_json -> 251_module_size_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/architectural_complexity_validation.py | write_json -> 252_coupling_hotspots.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/architectural_complexity_validation.py | write_json -> 253_dependency_risk_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/architectural_complexity_validation.py | write_json -> 254_architecture_recommendations.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/architectural_complexity_validation.py | write_text -> 255_architecture_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/assignment_policy.py | _write_text -> 21_operator_action_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_json -> 00_compatibility_inputs.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_json -> 01_baseline_schema_check.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_json -> 02_current_run_schema_check.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_json -> 03_scenario_compatibility.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_json -> 04_metric_schema_compatibility.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_json -> 05_policy_compatibility.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_json -> 06_snapshot_compatibility.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_json -> 07_compatibility_classification.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_compatibility.py | _write_text -> 08_compatibility_report.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 00_rollup_inputs.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 01_subtarget_index.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 02_subtarget_results.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 03_rollup_compatibility.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 04_rollup_decision.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 05_rollup_gate.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 06_classification.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 06_rollup_hotspots.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 07_rollup_remediation.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_json -> 08_rollup_triage_summary.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_rollup.py | _write_text -> 09_rollup_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_target.py | _write_json -> 00_target_inputs.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_target.py | _write_json -> 01_target_contract_load.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_target.py | _write_json -> 02_target_shape_validation.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_target.py | _write_json -> 03_target_artifact_check.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_target.py | _write_json -> 04_target_capability_classification.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_target.py | _write_text -> 05_target_report.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certification_target.py | _write_json -> 06_subtarget_index.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 00_run_manifest.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 01_inputs.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 02_baseline_load.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 03_current_run_load.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 04_metric_diff.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 05_scenario_diff.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 06_classification.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_text -> 07_certification_report.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 09_decision_policy.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 10_decision_evaluation.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 11_regression_hotspots.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_compare.py | _write_json -> 13_execution_profile.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_gate.py | _write_json -> 09_gate_result.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_gate.py | _write_json -> 10_exit_policy.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/certify_gate.py | _write_json -> 11_ci_contract.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/connector_transport.py | _write_text -> 93_transport_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> baseline_manifest.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> baseline_manifest.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> baseline_manifest.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> baseline_matrix.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> baseline_matrix.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> baseline_matrix.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> certification_gate_policy.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> decision_validation_matrix.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_text -> decision_validation_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> diagnostic_metrics.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> diagnostic_metrics.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/decision_validation.py | _write_json -> diagnostic_metrics.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/delivery_adapters.py | _write_json -> 33_delivery_contract.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/delivery_adapters.py | _write_text -> 34_delivery_adapter_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/delivery_reconciliation.py | _write_json -> 94_delivery_acknowledgments.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/delivery_reconciliation.py | _write_json -> 95_reconciliation_matches.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/delivery_reconciliation.py | _write_json -> 96_reconciliation_decisions.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/delivery_reconciliation.py | _write_text -> 97_reconciliation_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/devfabeco_orchestrator.py | _write_json -> build_pipeline_execution.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/devfabeco_orchestrator.py | _write_json -> buildcore_execution_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/devfabeco_orchestrator.py | _write_json -> devfabric_diagnostics_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/devfabeco_orchestrator.py | _write_json -> graph_plan_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/explain_engine.py | _write_json -> 00_run_manifest.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/explain_engine.py | _write_json -> 03_explain_queries.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/explain_engine.py | _write_json -> 04_explain_results.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/explain_engine.py | _write_json -> 05_reason_chains.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/explain_engine.py | _write_json -> 06_explain_graph_edges.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/export_adapters.py | _write_text -> 28_issue_export_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/external_status_sync.py | _write_json -> 100_closure_reconciliation.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/external_status_sync.py | _write_text -> 102_closure_reconciliation_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_engine.py | _write_json -> 40_run_record.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_engine.py | _write_json -> 41_regression_fingerprints_detected.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_engine.py | _write_json -> 42_recurrence_matches.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_engine.py | _write_json -> 43_component_history_context.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_engine.py | _write_text -> 44_history_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_engine.py | _write_text -> history_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_engine.py | _write_json -> {history_run_id}.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_trends.py | _write_json -> 51_component_regression_ranking.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_trends.py | _write_json -> 52_regression_trend_analysis.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_trends.py | _write_json -> 53_recurring_regression_patterns.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/history_trends.py | _write_text -> 54_history_trend_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/issue_update_policy.py | _write_text -> 107_bidirectional_update_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | _write_text -> 00_resolve.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | _write_text -> 01_stdout.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | _write_text -> 02_stderr.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | _write_text -> 03_exit_code.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | _write_text -> 30_errors.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | _write_text -> _ngks_build_receipt.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | _write_text -> conflict_outcome.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py | _write_text -> node_toolchain_decision.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/memory_usage_validation.py | write_json -> 240_peak_memory_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/memory_usage_validation.py | write_json -> 241_stage_memory_hotspots.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/memory_usage_validation.py | write_json -> 242_memory_growth_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/memory_usage_validation.py | write_json -> 243_repeated_high_memory_paths.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/memory_usage_validation.py | write_json -> 244_memory_recommendations.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/memory_usage_validation.py | write_text -> 245_memory_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/ownership_confidence.py | _write_text -> 18_remediation_evidence_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/performance_bottleneck_validation.py | write_json -> 230_total_runtime_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/performance_bottleneck_validation.py | write_json -> 231_stage_hotspots.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/performance_bottleneck_validation.py | write_json -> 232_scenario_hotspots.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/performance_bottleneck_validation.py | write_json -> 233_repeated_slow_paths.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/performance_bottleneck_validation.py | write_json -> 234_performance_recommendations.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/performance_bottleneck_validation.py | write_text -> 235_performance_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/predictive_resolution_refinement.py | _write_text -> 69_predictive_refinement_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/predictive_risk.py | _write_json -> 61_component_risk_scores.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/predictive_risk.py | _write_json -> 62_metric_risk_predictions.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/predictive_risk.py | _write_json -> 63_recommended_validation_targets.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/predictive_risk.py | _write_text -> 65_prediction_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/probe.py | write_json -> probe_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/probe.py | write_json -> probe_scan_stats.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/profile.py | write_json -> profile_write_receipt.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/proof_contract.py | write_json -> 00_run_manifest.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/proof_contract.py | write_json -> component_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/proof_contract.py | write_json -> doc_gate_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/regression_hotspots.py | _write_json -> 09_regression_hotspots.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/regression_hotspots.py | _write_json -> 10_scenario_regression_ranking.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/regression_hotspots.py | _write_json -> 11_metric_regression_ranking.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/regression_hotspots.py | _write_text -> 12_hotspot_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/regression_intelligence.py | _write_text -> 114_intelligence_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/remediation_guidance.py | _write_json -> 14_remediation_priority_list.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/remediation_guidance.py | _write_text -> 15_remediation_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolution_tracking.py | _write_json -> 70_regression_lifecycle_states.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolution_tracking.py | _write_json -> 71_component_resolution_metrics.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolution_tracking.py | _write_json -> 72_resolved_regressions.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolution_tracking.py | _write_json -> 73_unresolved_regressions.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolution_tracking.py | _write_text -> 74_resolution_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolver.py | write_json -> tool_resolve.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolver.py | write_text -> tool_resolve_stderr.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/resolver.py | write_text -> tool_resolve_stdout.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_json -> 40_root_cause_input_context.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_json -> 41_failure_stage_classification.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_json -> 42_root_cause_evidence.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_json -> 43_fix_recommendations.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_json -> 44_confidence_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_text -> 45_failure_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_text -> failure_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_json -> fix_recommendations.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_json -> root_cause_classification.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/root_cause_analyzer.py | _write_json -> root_cause_evidence.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_json -> 00_selected_path.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_json -> 00_selected_path.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 01_bootstrap.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 01_bootstrap.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_json -> 01_config_resolution.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 02_cmd_configure.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 02_cmd_configure.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 03_cmd_build.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 03_cmd_build.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 03_cmd_build.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 06_build_skipped.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 06_build_skipped.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 07_last_successful_fingerprint.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_json -> 98_failure_classification.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> BLOCKER.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_json -> build_receipt.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_json -> build_receipt.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> commands.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> created_dirs.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> created_dirs.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_json -> env_resolution.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> gate_summary.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> gate_summary.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> graph_call.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> graph_plan_id.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_bootstrap.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_bootstrap.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_bootstrap.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_bootstrap.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_bootstrap.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_capture_stdout.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_env_delta.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_env_delta.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_env_delta.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_env_delta.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> msvc_env_delta.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> plan_validation.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> plan_validation.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> plan_validation.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> where_cl.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> where_cl.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> where_cl.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> where_cl.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> where_cl.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> where_cl.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/runwrap.py | write_text -> where_cl.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | write_json -> 270_secret_detection_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | write_json -> 271_protocol_security_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | write_json -> 272_crypto_configuration_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | write_json -> 273_admin_interface_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | write_json -> 274_access_policy_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | write_json -> 275_security_headers_report.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | write_json -> 276_security_recommendations.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/security_misconfiguration_validation.py | write_text -> 277_security_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> 01_request.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> 01_request.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> 03_exec_commandline.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> 03_exec_commandline.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> 98_elapsed_ms.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> 98_elapsed_ms.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> 99_exitcode.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/smart_terminal.py | write_text -> last_run_dir.txt
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/team_ownership_mapping.py | _write_json -> 80_component_team_mapping.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/team_ownership_mapping.py | _write_json -> 81_assignee_resolution_results.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/team_ownership_mapping.py | _write_json -> 82_assignment_confidence_adjustments.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/team_ownership_mapping.py | _write_text -> 83_team_assignment_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/triage_tickets.py | _write_json -> 22_triage_tickets.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/triage_tickets.py | _write_json -> 23_triage_ticket_index.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/triage_tickets.py | _write_text -> 24_triage_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/ui_layout_integrity_validation.py | write_json -> 210_layout_overflow.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/ui_layout_integrity_validation.py | write_json -> 211_layout_collision.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/ui_layout_integrity_validation.py | write_json -> 212_layout_wrapper_waste.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/ui_layout_integrity_validation.py | write_json -> 213_layout_fix_recommendations.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/ui_layout_integrity_validation.py | write_text -> 214_layout_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_orchestrator.py | _write_json -> 131_scenario_execution_order.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_orchestrator.py | _write_json -> 132_execution_receipts.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_orchestrator.py | _write_json -> 133_execution_failures.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_orchestrator.py | _write_text -> 134_execution_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_planner.py | _write_json -> 121_scenario_plan_ranking.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_planner.py | _write_json -> 123_component_focus_plan.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_planner.py | _write_text -> 125_validation_plan_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_plugin_registry.py | write_json -> 220_plugin_execution_plan.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_plugin_registry.py | write_text -> 222_plugin_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_policy_engine.py | _write_json -> 30_policy_input_context.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_policy_engine.py | _write_text -> 35_policy_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_rerun_pipeline.py | _write_json -> 142_certification_rerun_summary.json
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/validation_rerun_pipeline.py | _write_text -> 144_pipeline_chain_summary.md
- NGKsDevFabric/src/ngksdevfabric/ngk_fabric/workflow_recommendation.py | _write_text -> 154_workflow_summary.md
- NGKsGraph/ngksgraph/build.py | write_text -> compdb.json
- NGKsGraph/ngksgraph/build.py | write_json -> graph.json
- NGKsGraph/ngksgraph/build.py | write_json -> meta.json
- NGKsGraph/ngksgraph/resolver/target_resolution_report.py | _write_json -> 14_resolution_report.json
- NGKsGraph/ngksgraph/resolver/target_resolution_report.py | _write_text -> 17_resolution_summary.md
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 01_probe_facts.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 02_classified_evidence.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 03_detected_stack.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 04_downstream_requirements.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 05_build_authority.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 06_stale_risk_report.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 07_contradictions.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 08_environment_contract.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> 09_native_plan.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_text -> SUMMARY.md
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> native_contract.json
- NGKsGraph/ngksgraph/scan_pipeline.py | write_json -> plan_diff.json

## 5) Notes on Scope

- This inventory covers all scanned Python source modules under NGKsDevFabric/src, NGKsGraph/ngksgraph, NGKsBuildCore/ngksbuildcore, NGKsEnvCapsule/src, and NGKsLibrary/src.
- Capabilities are represented by executable entrypoints, CLI command registration, top-level callable inventory, and artifact emission behavior found in code.

## 6) PowerShell and Automation Script Surface

- PowerShell scripts found: 254
- .pypi_smoke_venv/Scripts/Activate.ps1
- NGKsBuildCore/tools/run_example.ps1
- NGKsDevFabric/_proof/pkg01_20260303_165941/_venv_wheeltest/Scripts/Activate.ps1
- NGKsDevFabric/tools/dev/bootstrap_venv.ps1
- NGKsDevFabric/tools/dist/build_portable_suite.ps1
- NGKsDevFabric/tools/e2e_all.ps1
- NGKsDevFabric/tools/e2e_smoke.ps1
- NGKsDevFabric/tools/e2e_suite.ps1
- NGKsDevFabric/tools/eco/build_wheelhouse.ps1
- NGKsDevFabric/tools/eco/e2e_clean_install.ps1
- NGKsDevFabric/tools/gate_buildcore_phaseB.ps1
- NGKsDevFabric/tools/gate_buildcore_phaseD.ps1
- NGKsDevFabric/tools/gate_buildcore_phaseE.ps1
- NGKsDevFabric/tools/gate_phaseF_bootstrap.ps1
- NGKsDevFabric/tools/ngk.ps1
- NGKsDevFabric/tools/ngk_fabric.ps1
- NGKsDevFabric/tools/phase11_no_forbidden_buildref_gate.ps1
- NGKsDevFabric/tools/phase12_graph_only_gate.ps1
- NGKsDevFabric/tools/phase12_runner.ps1
- NGKsDevFabric/tools/phase12_write_report.ps1
- NGKsDevFabric/tools/phase15_graph_only_lock_gate.ps1
- NGKsDevFabric/tools/phase17_verify.ps1
- NGKsDevFabric/tools/phase5_gate_runner.ps1
- NGKsDevFabric/tools/phase7_gate_runner.ps1
- NGKsDevFabric/tools/phase8_gate_runner.ps1
- NGKsGraph/artifacts/selftest/2026-03-08T07-26-27Z/projects/seed_001_spaces/Qt Torture Repo/build tools/qt_tool_impl.ps1
- NGKsGraph/examples/qt_msvc_real/tools/ngksgraph.ps1
- NGKsGraph/tools/gate_buildplan_phaseA.ps1
- NGKsGraph/tools/gate_phaseG_plan_audit.ps1
- NGKsGraph/tools/ngksgraph.ps1
- NGKsGraph/tools/ngksgraph_run.ps1
- NGKsGraph/tools/package_windows.ps1
- NGKsGraph/tools/phase11a_real_qt_msvc_run.ps1
- NGKsGraph/tools/phase11b_painkiller_runner.ps1
- NGKsGraph/tools/smoke_standalone.ps1
- _proof/latest/run/workspaces/scenario_01_compatible_shared_python/certification/run_fault_suite.ps1
- _proof/latest/run/workspaces/scenario_01_compatible_shared_python/tools/bootstrap/preflight.ps1
- _proof/latest/run/workspaces/scenario_01_compatible_shared_python/tools/packaging/package_outputs.ps1
- _proof/latest/run/workspaces/scenario_01_compatible_shared_python/tools/validate/run_phase1_validation.ps1
- _proof/latest/run/workspaces/scenario_02_incompatible_python_split/certification/run_fault_suite.ps1
- _proof/latest/run/workspaces/scenario_02_incompatible_python_split/tools/bootstrap/preflight.ps1
- _proof/latest/run/workspaces/scenario_02_incompatible_python_split/tools/packaging/package_outputs.ps1
- _proof/latest/run/workspaces/scenario_02_incompatible_python_split/tools/validate/run_phase1_validation.ps1
- _proof/latest/run/workspaces/scenario_03_forced_shared_conflict/certification/run_fault_suite.ps1
- _proof/latest/run/workspaces/scenario_03_forced_shared_conflict/tools/bootstrap/preflight.ps1
- _proof/latest/run/workspaces/scenario_03_forced_shared_conflict/tools/packaging/package_outputs.ps1
- _proof/latest/run/workspaces/scenario_03_forced_shared_conflict/tools/validate/run_phase1_validation.ps1
- _proof/latest/run/workspaces/scenario_04_mixed_runtime_map/certification/run_fault_suite.ps1
- _proof/latest/run/workspaces/scenario_04_mixed_runtime_map/tools/bootstrap/preflight.ps1
- _proof/latest/run/workspaces/scenario_04_mixed_runtime_map/tools/packaging/package_outputs.ps1
- _proof/latest/run/workspaces/scenario_04_mixed_runtime_map/tools/validate/run_phase1_validation.ps1
- _proof/medialab_cert_trial_20260311_163312/run_targeted_trials.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/certification/run_fault_suite.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/bootstrap/preflight.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/build/build_all.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/build/build_qt_host.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/build/build_win32_host.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/packaging/package_outputs.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/validate/run_phase1_validation.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/certification/run_fault_suite.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/bootstrap/preflight.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/build/build_all.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/build/build_qt_host.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/build/build_win32_host.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/packaging/package_outputs.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/validate/run_phase1_validation.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/certification/run_fault_suite.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/bootstrap/preflight.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/build/build_all.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/build/build_qt_host.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/build/build_win32_host.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/packaging/package_outputs.ps1
- _proof/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/validate/run_phase1_validation.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/certification/run_fault_suite.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/bootstrap/preflight.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/build/build_all.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/build/build_qt_host.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/build/build_win32_host.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/packaging/package_outputs.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/validate/run_phase1_validation.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/certification/run_fault_suite.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/bootstrap/preflight.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/build/build_all.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/build/build_qt_host.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/build/build_win32_host.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/packaging/package_outputs.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/validate/run_phase1_validation.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/toolchain_conflict_workspace/certification/run_fault_suite.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/toolchain_conflict_workspace/tools/bootstrap/preflight.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/toolchain_conflict_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/toolchain_conflict_workspace/tools/build/build_all.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/toolchain_conflict_workspace/tools/build/build_qt_host.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/toolchain_conflict_workspace/tools/build/build_win32_host.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/toolchain_conflict_workspace/tools/packaging/package_outputs.ps1
- _proof/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/toolchain_conflict_workspace/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/python_mutation/certification/run_fault_suite.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/python_mutation/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/python_mutation/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/python_mutation/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/report_mutation/certification/run_fault_suite.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/report_mutation/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/report_mutation/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/report_mutation/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/sql_mutation/certification/run_fault_suite.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/sql_mutation/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/sql_mutation/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/sql_mutation/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/ts_mutation/certification/run_fault_suite.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/ts_mutation/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/ts_mutation/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_impact_analysis_20260312_093507/workspaces/ts_mutation/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/python_mutation/certification/run_fault_suite.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/python_mutation/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/python_mutation/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/python_mutation/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/report_mutation/certification/run_fault_suite.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/report_mutation/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/report_mutation/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/report_mutation/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/sql_mutation/certification/run_fault_suite.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/sql_mutation/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/sql_mutation/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/sql_mutation/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/ts_mutation/certification/run_fault_suite.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/ts_mutation/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/ts_mutation/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_incremental_rebuild_20260312_101940/workspaces/ts_mutation/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_01_compatible_shared_python/certification/run_fault_suite.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_01_compatible_shared_python/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_01_compatible_shared_python/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_01_compatible_shared_python/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_02_incompatible_python_split/certification/run_fault_suite.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_02_incompatible_python_split/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_02_incompatible_python_split/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_02_incompatible_python_split/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_03_forced_shared_conflict/certification/run_fault_suite.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_03_forced_shared_conflict/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_03_forced_shared_conflict/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_03_forced_shared_conflict/tools/validate/run_phase1_validation.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_04_mixed_runtime_map/certification/run_fault_suite.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_04_mixed_runtime_map/tools/bootstrap/preflight.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_04_mixed_runtime_map/tools/packaging/package_outputs.ps1
- _proof/runs/devfab_runtime_resolution_20260312_104604/workspaces/scenario_04_mixed_runtime_map/tools/validate/run_phase1_validation.ps1
- _proof/runs/medialab_cert_trial_20260311_163312/run_targeted_trials.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/certification/run_fault_suite.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/bootstrap/preflight.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/build/build_all.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/build/build_qt_host.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/build/build_win32_host.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/packaging/package_outputs.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/dependency_hole_workspace/tools/validate/run_phase1_validation.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/certification/run_fault_suite.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/bootstrap/preflight.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/build/build_all.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/build/build_qt_host.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/build/build_win32_host.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/packaging/package_outputs.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/multi_route_workspace/tools/validate/run_phase1_validation.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/certification/run_fault_suite.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/bootstrap/preflight.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/build/build_all.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/build/build_qt_host.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/build/build_win32_host.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/packaging/package_outputs.ps1
- _proof/runs/medialab_stress_refine_routes_deps_conflicts_20260311_211142/workspaces/toolchain_conflict_workspace/tools/validate/run_phase1_validation.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/certification/run_fault_suite.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/bootstrap/preflight.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/build/build_all.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/build/build_qt_host.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/build/build_win32_host.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/packaging/package_outputs.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/dependency_hole_workspace/tools/validate/run_phase1_validation.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/certification/run_fault_suite.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/bootstrap/preflight.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/build/bootstrap_msvc_env.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/build/build_all.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/build/build_qt_host.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/build/build_win32_host.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/packaging/package_outputs.ps1
- _proof/runs/medialab_stress_routes_deps_conflicts_20260311_204652/workspaces/multi_route_workspace/tools/validate/run_phase1_validation.ps1
- _proof/runs/target_fixture_missing_contract_20260313_0841/certification/run_fault_suite.ps1
- _proof/runs/target_fixture_missing_scenario_index_20260313_0841/certification/run_fault_suite.ps1
- ci_pipeline_snippet.ps1
- install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_160552/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_160552/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_160747/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_160747/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_161102/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_161102/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_161251/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_161251/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_183126/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_183126/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_191113/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_191113/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_191129/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_191129/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_214123/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_214123/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_214349/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_214349/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_214459/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_214459/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_224151/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260306_224151/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_073909/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_073909/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_080851/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_080851/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_080914/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_080914/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_084724/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_084724/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_092618/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_092618/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_155122/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_155122/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_160841/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_160841/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_162518/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260307_162518/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_104934/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_104934/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_150154/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_150154/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_151520/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_151520/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_161551/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_161551/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_165015/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_165015/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_170742/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_170742/uninstall_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_174601/install_ngksdevfabeco.ps1
- releases/_mothballed/ngksdevfabeco_release_20260308_174601/uninstall_ngksdevfabeco.ps1
- releases/ngksdevfabeco_release_20260309_073207/install_ngksdevfabeco.ps1
- releases/ngksdevfabeco_release_20260309_073207/uninstall_ngksdevfabeco.ps1
- releases/ngksdevfabeco_release_20260309_171120/install_ngksdevfabeco.ps1
- releases/ngksdevfabeco_release_20260309_171120/uninstall_ngksdevfabeco.ps1
- tools/make_release_bundle.ps1
- tools/prepare_pypi_release.ps1
- tools/run_runtime_resolution_pass.ps1
- tools/run_toolchain_provisioning_pass.ps1
- uninstall_ngksdevfabeco.ps1

## 7) Test Surface (code-backed verification scope)

- Python test files found: 96
- NGKsBuildCore/tests/test_plan_ingest.py
- NGKsBuildCore/tests/test_runner_actionkey.py
- NGKsDevFabric/tests/test_assignment_policy.py
- NGKsDevFabric/tests/test_certification_rollup.py
- NGKsDevFabric/tests/test_certification_target.py
- NGKsDevFabric/tests/test_certify_compare.py
- NGKsDevFabric/tests/test_component_exec_console_vs_module.py
- NGKsDevFabric/tests/test_component_exec_module_fallback.py
- NGKsDevFabric/tests/test_connector_transport.py
- NGKsDevFabric/tests/test_delivery_adapters.py
- NGKsDevFabric/tests/test_doctor_backup_optional.py
- NGKsDevFabric/tests/test_execution_profiles.py
- NGKsDevFabric/tests/test_export_adapters.py
- NGKsDevFabric/tests/test_external_status_sync.py
- NGKsDevFabric/tests/test_history_engine.py
- NGKsDevFabric/tests/test_history_trends.py
- NGKsDevFabric/tests/test_intelligence.py
- NGKsDevFabric/tests/test_issue_update_policy.py
- NGKsDevFabric/tests/test_notebook_policy_guard.py
- NGKsDevFabric/tests/test_ownership_confidence.py
- NGKsDevFabric/tests/test_predictive_resolution_refinement.py
- NGKsDevFabric/tests/test_predictive_risk.py
- NGKsDevFabric/tests/test_probe_detection.py
- NGKsDevFabric/tests/test_profile_node_toolchain.py
- NGKsDevFabric/tests/test_proof_manager.py
- NGKsDevFabric/tests/test_proof_routing_contract.py
- NGKsDevFabric/tests/test_regression_hotspots.py
- NGKsDevFabric/tests/test_regression_intelligence.py
- NGKsDevFabric/tests/test_remediation_guidance.py
- NGKsDevFabric/tests/test_resolution_tracking.py
- NGKsDevFabric/tests/test_run_orchestrator.py
- NGKsDevFabric/tests/test_run_orchestrator_module_fallback_no_scripts.py
- NGKsDevFabric/tests/test_run_orchestrator_noop_semantics.py
- NGKsDevFabric/tests/test_run_orchestrator_writes_stage_logs_on_missing_component.py
- NGKsDevFabric/tests/test_team_ownership_mapping.py
- NGKsDevFabric/tests/test_triage_tickets.py
- NGKsDevFabric/tests/test_validation_orchestrator.py
- NGKsDevFabric/tests/test_validation_planner.py
- NGKsDevFabric/tests/test_validation_plugin_framework.py
- NGKsDevFabric/tests/test_validation_rerun_pipeline.py
- NGKsDevFabric/tests/test_workflow_recommendation.py
- NGKsEnvCapsule/tests/test_hashing.py
- NGKsEnvCapsule/tests/test_lock_verify_cycle.py
- NGKsEnvCapsule/tests/test_stablejson.py
- NGKsEnvCapsule/tests/test_verify_mismatch.py
- NGKsGraph/tests/test_ai_interface.py
- NGKsGraph/tests/test_bootstrap_command_format.py
- NGKsGraph/tests/test_build_target_selection.py
- NGKsGraph/tests/test_buildplan_buildcore_contract.py
- NGKsGraph/tests/test_cached_qt_libdirs_injection.py
- NGKsGraph/tests/test_capsule_deterministic_zip.py
- NGKsGraph/tests/test_capsule_no_secrets.py
- NGKsGraph/tests/test_capsule_verify_roundtrip.py
- NGKsGraph/tests/test_capsule_why_mode.py
- NGKsGraph/tests/test_compdb_contract.py
- NGKsGraph/tests/test_compdb_determinism.py
- NGKsGraph/tests/test_compdb_multitarget.py
- NGKsGraph/tests/test_config.py
- NGKsGraph/tests/test_config_multitarget_parse.py
- NGKsGraph/tests/test_doctor_binary.py
- NGKsGraph/tests/test_ecosystem_mode.py
- NGKsGraph/tests/test_edge_origin_tracking.py
- NGKsGraph/tests/test_error_parse.py
- NGKsGraph/tests/test_explain_in_graph.py
- NGKsGraph/tests/test_freeze_from_snapshot_fallbacks.py
- NGKsGraph/tests/test_graph_contract.py
- NGKsGraph/tests/test_graph_cycle_detection.py
- NGKsGraph/tests/test_graph_export_schema.py
- NGKsGraph/tests/test_import_basic_cmake.py
- NGKsGraph/tests/test_init_repo_classifier.py
- NGKsGraph/tests/test_msvc_auto_report.py
- NGKsGraph/tests/test_msvc_env_parse.py
- NGKsGraph/tests/test_perf_report.py
- NGKsGraph/tests/test_phase5_temporal.py
- NGKsGraph/tests/test_phase_depth_upgrades.py
- NGKsGraph/tests/test_plan_cache.py
- NGKsGraph/tests/test_plan_command.py
- NGKsGraph/tests/test_profiles_cli_gates.py
- NGKsGraph/tests/test_profiles_config_parse.py
- NGKsGraph/tests/test_profiles_determinism.py
- NGKsGraph/tests/test_qt_capsule_verify.py
- NGKsGraph/tests/test_qt_determinism.py
- NGKsGraph/tests/test_qt_moc_detection.py
- NGKsGraph/tests/test_qt_moc_rebuild_trigger.py
- NGKsGraph/tests/test_qt_root_resolution.py
- NGKsGraph/tests/test_qt_torture_abuse.py
- NGKsGraph/tests/test_qt_uic_rcc_generation.py
- NGKsGraph/tests/test_rebuild_cause_structural_change.py
- NGKsGraph/tests/test_sanitize.py
- NGKsGraph/tests/test_scan_pipeline.py
- NGKsGraph/tests/test_selftest_command.py
- NGKsGraph/tests/test_symbol_forensics_missing_link.py
- NGKsGraph/tests/test_target_resolution_pipeline.py
- NGKsGraph/tests/test_toolchain_doctor_parsing.py
- NGKsGraph/tests/test_version_output.py
- NGKsGraph/tests/test_why_direct_and_transitive.py
