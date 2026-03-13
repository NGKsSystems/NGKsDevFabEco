from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.profile import init_profile


def test_profile_init_records_node_toolchain_contract(tmp_path: Path):
    project = tmp_path / "target"
    project.mkdir(parents=True, exist_ok=True)
    (project / "package.json").write_text('{"name":"app","scripts":{"build":"node app.js"}}\n', encoding="utf-8")
    (project / "tsconfig.json").write_text('{"compilerOptions":{}}\n', encoding="utf-8")

    pf = tmp_path / "proof"
    init_profile(project, pf, write_project=True)

    profile_path = project / ".ngk" / "profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))

    assert "node_toolchain" in payload
    assert "contracts" in payload
    entries = payload["contracts"].get("node_toolchain", [])
    assert len(entries) == 1
    entry = entries[0]
    assert entry["build_system"] == "node"
    assert entry["package_manager"] in {"pnpm", "npm", "yarn"}
    assert entry["reason"] in {
        "lockfile_detected",
        "repo_configured",
        "policy_default_no_lockfile",
        "fallback_tool_unavailable",
    }
