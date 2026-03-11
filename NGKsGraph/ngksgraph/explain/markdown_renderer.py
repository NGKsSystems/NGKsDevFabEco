from __future__ import annotations


def render_summary(data: dict[str, object]) -> str:
    subprojects = list(data.get("subprojects", []))
    required_tools = list(data.get("required_tools", []))
    required_flags = list(data.get("required_flags", []))
    required_standards = list(data.get("required_standards", []))
    required_env = list(data.get("required_env", []))
    missing_tools = list(data.get("missing_tools", []))
    missing_env = list(data.get("missing_env", []))
    missing_flags = list(data.get("missing_flags", []))
    unsupported_paths = list(data.get("unsupported_native_paths", []))
    blockers = list(data.get("blockers", []))

    why_build_may_fail: list[str] = []
    if missing_tools:
        why_build_may_fail.append(f"missing tool: {', '.join(sorted(missing_tools))}")
    if missing_env:
        why_build_may_fail.append(f"missing env: {', '.join(sorted(missing_env))}")
    if missing_flags:
        why_build_may_fail.append(f"missing flag: {', '.join(sorted(missing_flags))}")
    if unsupported_paths:
        why_build_may_fail.append(f"unsupported native execution path: {', '.join(sorted(unsupported_paths))}")
    if not why_build_may_fail and blockers:
        why_build_may_fail.extend(blockers)

    lines = [
        "# NGKsGraph Scan Summary",
        "",
        f"- scan_id: {data.get('scan_id', '')}",
        f"- repo_root: {data.get('repo_root', '')}",
        f"- timestamp_utc: {data.get('timestamp_utc', '')}",
        f"- authority_mode: {data.get('authority_mode', '')}",
        f"- preflight_status: {data.get('status', '')}",
        "",
        "## What Graph Detected",
        f"- primary_project_type: {data.get('project_type', 'unknown')}",
        f"- subprojects: {', '.join(subprojects or ['none'])}",
        f"- top_languages: {', '.join(data.get('top_languages', []) or ['none'])}",
        f"- frameworks: {', '.join(data.get('frameworks', []) or ['none'])}",
        f"- package_ecosystems: {', '.join(data.get('ecosystems', []) or ['none'])}",
        "",
        "## What Graph Inferred",
        f"- requirement_count: {int(data.get('requirement_count', 0))}",
        f"- standards: {', '.join(required_standards or ['none'])}",
        f"- required_tools: {', '.join(required_tools or ['none'])}",
        f"- required_flags: {', '.join(required_flags or ['none'])}",
        f"- required_env: {', '.join(required_env or ['none'])}",
        "",
        "## What Graph Ignored",
        f"- stale_items: {int(data.get('stale_count', 0))}",
        f"- generated_artifacts: {int(data.get('ignored_generated_count', 0))}",
        f"- blocked_foreign_files: {int(data.get('ignored_blocked_foreign_count', 0))}",
        "",
        "## Conflicts",
        f"- contradictions: {int(data.get('contradiction_count', 0))}",
        f"- trust_issues: {int(data.get('trust_issue_count', 0))}",
        f"- stale_poisoning_risk_high: {int(data.get('stale_high_count', 0))}",
        "",
        "## Why Build May Fail",
        *([f"- {item}" for item in why_build_may_fail] or ["- none"]),
        "",
        "## Recommended Fix",
        *([f"- resolve: {item}" for item in (why_build_may_fail or blockers)] or ["- proceed with build"]),
        "",
    ]
    return "\n".join(lines)
