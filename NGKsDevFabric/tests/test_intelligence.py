from __future__ import annotations

from pathlib import Path

from ngksdevfabric.ngk_fabric.intelligence import infer_dependency_holes, rank_routes  # pyright: ignore[reportMissingImports]


def test_rank_routes_returns_factorized_scores(tmp_path: Path):
    ts_dir = tmp_path / "app" / "ts_panel"
    ts_dir.mkdir(parents=True, exist_ok=True)
    (ts_dir / "package.json").write_text('{"name":"ts","scripts":{"build":"node build.js"}}\n', encoding="utf-8")
    (ts_dir / "package-lock.json").write_text("{}\n", encoding="utf-8")

    py_dir = tmp_path / "app" / "python_workers"
    py_dir.mkdir(parents=True, exist_ok=True)
    (py_dir / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")

    result = rank_routes(tmp_path)

    assert result["selected_route"]
    assert result["route_candidates"]
    top = result["route_candidates"][0]
    assert "factors" in top
    assert "toolchain_availability_score" in top["factors"]
    assert "entrypoint_confidence_score" in top["factors"]
    assert "dependency_readiness_score" in top["factors"]
    assert "backend_completeness_score" in top["factors"]
    assert "validation_readiness_score" in top["factors"]
    assert "risk_penalty" in top["factors"]
    assert "final_score" in top


def test_infer_dependency_holes_has_trace_lines(tmp_path: Path):
    py_dir = tmp_path / "app" / "python_workers"
    py_dir.mkdir(parents=True, exist_ok=True)
    (py_dir / "requirements.txt").write_text("\n", encoding="utf-8")
    (py_dir / "worker.py").write_text("import requests\n", encoding="utf-8")

    result = infer_dependency_holes(tmp_path)

    assert result["holes"]
    hole = result["holes"][0]
    assert hole["dependency_name"] == "requests"
    assert hole["confidence"] == "high"
    assert hole["confidence_reason"]
    assert hole["evidence_files"]
    assert hole["evidence_lines"]

    assert result["trace_report"]
    trace = result["trace_report"][0]
    assert trace["trace_chain"]
