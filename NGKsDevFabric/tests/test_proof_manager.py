from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.proof_manager import register_proof_bundle


def test_register_proof_bundle_creates_latest_and_index(tmp_path: Path):
    devfab_root = tmp_path / "NGKsDevFabric"
    devfab_root.mkdir(parents=True, exist_ok=True)

    source_bundle = tmp_path / "project" / "_proof" / "medialab_onboarding_build_20260312_010203"
    source_bundle.mkdir(parents=True, exist_ok=True)
    (source_bundle / "18_summary.md").write_text(
        "# Summary\n\n- Selected route: node_ts_panel\n- Final gate: PASS\n",
        encoding="utf-8",
    )

    result = register_proof_bundle(bundle_path=source_bundle, devfab_root=devfab_root)
    assert result["status"] == "ok"

    hub = tmp_path / "_proof"
    assert (hub / "runs" / result["run_id"]).is_dir()
    assert (hub / "latest" / "latest_summary.md").is_file()
    assert (hub / "latest" / "latest_summary.json").is_file()
    assert (hub / "latest" / "latest_run_pointer.json").is_file()
    assert (hub / "latest_proof.zip").is_file()
    assert (hub / "index" / "runs_index.json").is_file()
    assert (hub / "index" / "runs_index.md").is_file()

    pointer = json.loads((hub / "latest" / "latest_run_pointer.json").read_text(encoding="utf-8"))
    assert pointer["latest_proof_zip"] == str((hub / "latest_proof.zip").resolve())

    index = json.loads((hub / "index" / "runs_index.json").read_text(encoding="utf-8"))
    assert index["runs"]
    assert index["runs"][0]["run_id"] == result["run_id"]
