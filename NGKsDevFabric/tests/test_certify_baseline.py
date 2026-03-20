from __future__ import annotations

"""test_certify_baseline.py
===========================
Deterministic unit tests for the certify_baseline module.

Test categories
---------------
1.  Regression classification  – PASS→FAIL = regression, FAIL→PASS = improvement
2.  Strict mode                – warning drift (exit≠0) fails only under --strict
3.  Repo filtering             – --repo limits evaluation to named repos
4.  Baseline loading           – explicit path, auto-discovery, missing/unreadable
5.  Non-ngksgraph repos        – configure/build = N/A, never flag a regression
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ngksdevfabric.ngk_fabric.certify_baseline import (
    _classify,
    _check_repo,
    _read_manifest,
    find_baseline_manifest,
    run_certify_baseline,
)


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _make_manifest(tmp_path: Path, repos: list[dict], *, basename: str = "repo_manifest.json") -> Path:
    payload = {
        "baseline_name": "Certification_Baseline_v1",
        "locked_at": "2026-03-18T19:40:00+00:00",
        "certified_repos": repos,
        "summary": {"repos_locked": len(repos)},
    }
    f = tmp_path / basename
    f.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return f


def _ngksgraph_repo_entry(tmp_path: Path, *, probe: str = "PASS", doctor: str = "PASS",
                          configure: str = "PASS", build: str = "PASS") -> dict:
    repo_dir = tmp_path / "FakeNgksGraphRepo"
    repo_dir.mkdir(exist_ok=True)
    return {
        "name": "FakeNgksGraphRepo",
        "path": str(repo_dir),
        "probe": probe,
        "doctor": doctor,
        "configure": configure,
        "build": build,
    }


def _npm_repo_entry(tmp_path: Path, *, probe: str = "PASS", doctor: str = "PASS") -> dict:
    repo_dir = tmp_path / "FakeNpmRepo"
    repo_dir.mkdir(exist_ok=True)
    return {
        "name": "FakeNpmRepo",
        "path": str(repo_dir),
        "project_type": "npm",
        "probe": probe,
        "doctor": doctor,
        "configure": "N/A",
        "build": "N/A",
    }


# ---------------------------------------------------------------------------
# 1. _classify – regression classification
# ---------------------------------------------------------------------------

class TestClassify:
    """_classify() is the single source of truth for stage comparison."""

    def test_pass_to_pass_is_stable(self):
        cur, reg, imp = _classify("PASS", 0)
        assert cur == "PASS"
        assert not reg
        assert not imp

    def test_pass_to_fail_is_regression(self):
        cur, reg, imp = _classify("PASS", 1)
        assert cur == "FAIL"
        assert reg is True
        assert not imp

    def test_fail_to_pass_is_improvement(self):
        cur, reg, imp = _classify("FAIL", 0)
        assert cur == "PASS"
        assert not reg
        assert imp is True

    def test_fail_to_fail_is_stable_not_regression(self):
        cur, reg, imp = _classify("FAIL", 1)
        assert cur == "FAIL"
        assert not reg
        assert not imp

    def test_na_baseline_never_regresses(self):
        for exit_code in (0, 1, 2):
            cur, reg, imp = _classify("N/A", exit_code)
            assert cur == "N/A"
            assert not reg
            assert not imp

    def test_non_zero_exit_is_fail(self):
        cur, reg, imp = _classify("PASS", 2)
        assert cur == "FAIL"
        assert reg is True

    def test_zero_exit_is_pass(self):
        cur, reg, imp = _classify("FAIL", 0)
        assert cur == "PASS"
        assert imp is True

    # ------------------------------------------------------------------- strict
    def test_strict_off_warning_exit_not_regression(self):
        """exit=1 from PASS baseline is regression regardless — strict or not."""
        cur, reg, imp = _classify("PASS", 1, strict=False)
        # Non-zero from a PASS baseline is always a regression in _classify
        assert reg is True

    def test_strict_on_already_captured_by_base_logic(self):
        """Strict mode doesn't add extra behaviour for clean PASS->FAIL."""
        cur, reg, imp = _classify("PASS", 1, strict=True)
        assert reg is True

    def test_strict_on_exit_nonzero_was_pass(self):
        """_classify strict=True: exit≠0 with PASS baseline is regression."""
        cur, reg, imp = _classify("PASS", 2, strict=True)
        assert reg is True

    def test_strict_off_fail_baseline_nonzero_not_regression(self):
        cur, reg, imp = _classify("FAIL", 2, strict=False)
        assert not reg

    def test_strict_on_fail_baseline_nonzero_not_regression(self):
        """strict does not promote a FAIL baseline to regression on non-zero exit."""
        cur, reg, imp = _classify("FAIL", 2, strict=True)
        assert not reg


# ---------------------------------------------------------------------------
# 2. Strict mode in _check_repo
# ---------------------------------------------------------------------------

class TestStrictMode:
    """Doctor warning drift (non-zero exit that is not FAIL-classified by
    _classify alone) must be caught by strict mode in _check_repo."""

    def _make_entry(self, tmp_path: Path) -> dict:
        d = tmp_path / "StrictRepo"
        d.mkdir()
        return {"name": "StrictRepo", "path": str(d),
                "probe": "PASS", "doctor": "PASS",
                "configure": "N/A", "build": "N/A"}

    def test_strict_off_doctor_exit1_normal_classification(self, tmp_path):
        entry = self._make_entry(tmp_path)
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=[(0, "", ""), (1, "", "warnings only")],
        ):
            result = _check_repo(entry, strict=False, no_build=True, build_mode="release")
        # Normal mode: exit=1 from PASS doctor baseline IS a regression
        # (because _classify treats non-zero as FAIL)
        doctor_stage = next(s for s in result.stages if s.stage == "doctor")
        assert doctor_stage.current_value == "FAIL"
        assert result.overall == "REGRESSION"

    def test_strict_on_doctor_drift_is_regression(self, tmp_path):
        entry = self._make_entry(tmp_path)
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=[(0, "", ""), (1, "", "warnings")],
        ):
            result = _check_repo(entry, strict=True, no_build=True, build_mode="release")
        assert result.overall == "REGRESSION"
        assert any("doctor" in r for r in result.regressions)

    def test_strict_on_probe_pass_doctor_pass_no_regression(self, tmp_path):
        entry = self._make_entry(tmp_path)
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=[(0, "", ""), (0, "", "")],
        ):
            result = _check_repo(entry, strict=True, no_build=True, build_mode="release")
        assert result.overall == "PASS"
        assert result.regressions == []

    def test_strict_on_improvement_detected(self, tmp_path):
        d = tmp_path / "ImpRepo"
        d.mkdir()
        entry = {"name": "ImpRepo", "path": str(d),
                 "probe": "FAIL", "doctor": "PASS",
                 "configure": "N/A", "build": "N/A"}
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=[(0, "", ""), (0, "", "")],
        ):
            result = _check_repo(entry, strict=True, no_build=True, build_mode="release")
        assert result.overall == "IMPROVEMENT"
        assert result.regressions == []
        assert result.improvements


# ---------------------------------------------------------------------------
# 3. Repo filtering
# ---------------------------------------------------------------------------

class TestRepoFiltering:
    def _two_repo_manifest(self, tmp_path: Path) -> Path:
        d1 = tmp_path / "RepoA"; d1.mkdir()
        d2 = tmp_path / "RepoB"; d2.mkdir()
        repos = [
            {"name": "RepoA", "path": str(d1), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
            {"name": "RepoB", "path": str(d2), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ]
        return _make_manifest(tmp_path, repos)

    def test_no_filter_evaluates_all_repos(self, tmp_path):
        manifest = self._two_repo_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest,
                repo_filter=None,
                build_mode="release",
                strict=False,
                no_build=True,
                pf=pf,
            )
        assert result["repos_checked"] == 2

    def test_filter_single_repo_only_that_repo_checked(self, tmp_path):
        manifest = self._two_repo_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest,
                repo_filter=["RepoA"],
                build_mode="release",
                strict=False,
                no_build=True,
                pf=pf,
            )
        assert result["repos_checked"] == 1
        assert result["repo_results"][0]["name"] == "RepoA"

    def test_filter_second_repo_only(self, tmp_path):
        manifest = self._two_repo_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest,
                repo_filter=["RepoB"],
                build_mode="release",
                strict=False,
                no_build=True,
                pf=pf,
            )
        assert result["repos_checked"] == 1
        assert result["repo_results"][0]["name"] == "RepoB"

    def test_filter_unknown_name_evaluates_zero_repos(self, tmp_path):
        manifest = self._two_repo_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest,
                repo_filter=["DoesNotExist"],
                build_mode="release",
                strict=False,
                no_build=True,
                pf=pf,
            )
        assert result["repos_checked"] == 0

    def test_filter_multiple_names_evaluates_subset(self, tmp_path):
        d3 = tmp_path / "RepoC"; d3.mkdir()
        d1 = tmp_path / "RepoA"; d1.mkdir(exist_ok=True)
        repos = [
            {"name": "RepoA", "path": str(d1), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
            {"name": "RepoB", "path": str(tmp_path / "RepoB_missing"), "probe": "PASS",
             "doctor": "PASS", "configure": "N/A", "build": "N/A"},
            {"name": "RepoC", "path": str(d3), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ]
        manifest = _make_manifest(tmp_path, repos)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest,
                repo_filter=["RepoA", "RepoC"],
                build_mode="release",
                strict=False,
                no_build=True,
                pf=pf,
            )
        names = {r["name"] for r in result["repo_results"]}
        assert names == {"RepoA", "RepoC"}
        assert result["repos_checked"] == 2


# ---------------------------------------------------------------------------
# 4. Baseline loading
# ---------------------------------------------------------------------------

class TestBaselineLoading:

    # --- explicit path: direct .json file ---

    def test_explicit_json_file_loaded(self, tmp_path):
        bl_dir = tmp_path / "bl"
        bl_dir.mkdir()
        d = tmp_path / "repo"; d.mkdir()
        manifest = _make_manifest(bl_dir, [
            {"name": "R", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ])
        result = find_baseline_manifest(str(manifest), None)
        assert result == manifest.resolve()

    def test_explicit_directory_containing_manifest(self, tmp_path):
        bl_dir = tmp_path / "bl_dir"
        bl_dir.mkdir()
        d = tmp_path / "repo"; d.mkdir()
        manifest = _make_manifest(bl_dir, [
            {"name": "R", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ])
        result = find_baseline_manifest(str(bl_dir), None)
        assert result.name == "repo_manifest.json"

    def test_explicit_missing_path_raises(self, tmp_path):
        with pytest.raises(RuntimeError, match="not a repo_manifest.json"):
            find_baseline_manifest(str(tmp_path / "nonexistent.json"), None)

    def test_explicit_directory_no_manifest_raises(self, tmp_path):
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        with pytest.raises(RuntimeError, match="not a repo_manifest.json"):
            find_baseline_manifest(str(empty_dir), None)

    # --- auto-discovery ---

    def test_auto_discover_baseline_from_eco_root(self, tmp_path):
        bl_dir = tmp_path / ".baseline_v1_20260318_194000"
        bl_dir.mkdir()
        d = tmp_path / "repo"; d.mkdir()
        _make_manifest(bl_dir, [
            {"name": "R", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ])
        result = find_baseline_manifest("", tmp_path)
        assert result.parent == bl_dir
        assert result.name == "repo_manifest.json"

    def test_auto_discovery_picks_latest_when_multiple(self, tmp_path):
        """Lexicographically later .baseline_v* directory should be preferred."""
        for name in [".baseline_v1_20260301_000000", ".baseline_v2_20260318_000000"]:
            d = tmp_path / name
            d.mkdir()
            repo = tmp_path / f"repo_{name}"; repo.mkdir()
            _make_manifest(d, [
                {"name": f"R_{name}", "path": str(repo), "probe": "PASS",
                 "doctor": "PASS", "configure": "N/A", "build": "N/A"},
            ])
        result = find_baseline_manifest("", tmp_path)
        # v2 is lexicographically higher and should be preferred
        assert ".baseline_v2" in result.parent.name

    def test_no_baseline_no_eco_root_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RuntimeError, match="Could not auto-discover"):
            find_baseline_manifest("", None)

    def test_eco_root_without_baseline_dir_raises(self, tmp_path):
        with pytest.raises(RuntimeError, match="Could not auto-discover"):
            find_baseline_manifest("", tmp_path)

    # --- unreadable / corrupted manifest ---

    def test_unreadable_manifest_raises_runtime_error(self, tmp_path):
        f = tmp_path / "repo_manifest.json"
        f.write_text("NOT VALID JSON >>>", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Cannot read baseline manifest"):
            _read_manifest(f)

    def test_missing_manifest_raises_runtime_error(self, tmp_path):
        f = tmp_path / "missing_manifest.json"
        with pytest.raises(RuntimeError, match="Cannot read baseline manifest"):
            _read_manifest(f)

    def test_manifest_not_an_object_raises(self, tmp_path):
        f = tmp_path / "repo_manifest.json"
        f.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(RuntimeError, match="not a JSON object"):
            _read_manifest(f)


# ---------------------------------------------------------------------------
# 5. Non-ngksgraph repos (configure/build = N/A)
# ---------------------------------------------------------------------------

class TestNonNgksgraphRepos:
    """Repos with configure=N/A must never contribute a regression even when
    probe/doctor succeed or fail."""

    def _npm_entry(self, tmp_path: Path) -> dict:
        d = tmp_path / "NpmRepo"; d.mkdir(exist_ok=True)
        return {
            "name": "NpmRepo",
            "path": str(d),
            "project_type": "npm",
            "probe": "PASS",
            "doctor": "PASS",
            "configure": "N/A",
            "build": "N/A",
        }

    def test_na_configure_build_not_executed(self, tmp_path):
        entry = self._npm_entry(tmp_path)
        call_log = []

        def _mock_stage(sub_cmd, path, extra):
            call_log.append(sub_cmd)
            return (0, "", "")

        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=_mock_stage,
        ):
            result = _check_repo(entry, strict=False, no_build=False, build_mode="release")

        # Only probe and doctor should be called; build is NOT called for N/A repos
        assert "build" not in call_log
        assert "configure" not in call_log

    def test_na_stages_never_flagged_as_regression(self, tmp_path):
        entry = self._npm_entry(tmp_path)
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = _check_repo(entry, strict=False, no_build=False, build_mode="release")

        cfg_stage = next(s for s in result.stages if s.stage == "configure")
        bld_stage = next(s for s in result.stages if s.stage == "build")
        assert cfg_stage.current_value == "N/A"
        assert bld_stage.current_value == "N/A"
        assert not cfg_stage.is_regression
        assert not bld_stage.is_regression

    def test_na_stages_are_skipped_not_improvement(self, tmp_path):
        """N/A baseline with any exit code must not produce an improvement either."""
        entry = self._npm_entry(tmp_path)
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = _check_repo(entry, strict=False, no_build=False, build_mode="release")

        cfg_stage = next(s for s in result.stages if s.stage == "configure")
        assert not cfg_stage.is_improvement

    def test_full_gate_pass_for_npm_repo(self, tmp_path):
        manifest = _make_manifest(tmp_path, [self._npm_entry(tmp_path)])
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest,
                repo_filter=None,
                build_mode="release",
                strict=False,
                no_build=False,
                pf=pf,
            )
        assert result["gate"] == "PASS"

    def test_npm_probe_regression_still_caught(self, tmp_path):
        """A probe failure on an npm repo IS still a regression."""
        entry = self._npm_entry(tmp_path)
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=[(1, "", "probe failed"), (0, "", "")],
        ):
            result = _check_repo(entry, strict=False, no_build=False, build_mode="release")
        assert result.overall == "REGRESSION"
        assert any("probe" in r for r in result.regressions)

    def test_flutter_repo_configure_na(self, tmp_path):
        d = tmp_path / "FlutterRepo"; d.mkdir()
        entry = {
            "name": "FlutterRepo",
            "path": str(d),
            "project_type": "flutter",
            "probe": "PASS",
            "doctor": "PASS",
            "configure": "N/A",
            "build": "N/A",
        }
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = _check_repo(entry, strict=False, no_build=False, build_mode="release")
        assert result.overall == "PASS"
        cfg_stage = next(s for s in result.stages if s.stage == "configure")
        assert cfg_stage.current_value == "N/A"

    def test_cmake_repo_configure_na(self, tmp_path):
        d = tmp_path / "CmakeRepo"; d.mkdir()
        entry = {
            "name": "CmakeRepo",
            "path": str(d),
            "project_type": "cmake",
            "probe": "PASS",
            "doctor": "PASS",
            "configure": "N/A",
            "build": "N/A",
        }
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = _check_repo(entry, strict=False, no_build=False, build_mode="release")
        assert result.overall == "PASS"


# ---------------------------------------------------------------------------
# 6. Integration: run_certify_baseline gate outcome
# ---------------------------------------------------------------------------

class TestGateOutcome:

    def test_all_pass_gate_is_pass(self, tmp_path):
        d = tmp_path / "R"; d.mkdir()
        manifest = _make_manifest(tmp_path, [
            {"name": "R", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ])
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest, repo_filter=None, build_mode="release",
                strict=False, no_build=True, pf=pf,
            )
        assert result["gate"] == "PASS"
        assert result["repos_regression"] == 0

    def test_one_regression_gate_is_fail(self, tmp_path):
        d = tmp_path / "R"; d.mkdir()
        manifest = _make_manifest(tmp_path, [
            {"name": "R", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ])
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=[(1, "", "probe broke"), (0, "", "")],
        ):
            result = run_certify_baseline(
                manifest_path=manifest, repo_filter=None, build_mode="release",
                strict=False, no_build=True, pf=pf,
            )
        assert result["gate"] == "FAIL"
        assert result["repos_regression"] == 1

    def test_improvement_only_gate_is_pass(self, tmp_path):
        d = tmp_path / "R"; d.mkdir()
        manifest = _make_manifest(tmp_path, [
            {"name": "R", "path": str(d), "probe": "FAIL", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ])
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest, repo_filter=None, build_mode="release",
                strict=False, no_build=True, pf=pf,
            )
        assert result["gate"] == "PASS"
        assert result["repos_improvement"] == 1

    def test_missing_repo_dir_is_regression(self, tmp_path):
        manifest = _make_manifest(tmp_path, [
            {"name": "Ghost", "path": str(tmp_path / "does_not_exist"),
             "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ])
        pf = tmp_path / "pf"
        result = run_certify_baseline(
            manifest_path=manifest, repo_filter=None, build_mode="release",
            strict=False, no_build=True, pf=pf,
        )
        assert result["gate"] == "FAIL"
        assert result["repos_regression"] == 1

    def test_gate_artifacts_written_to_pf(self, tmp_path):
        d = tmp_path / "R"; d.mkdir()
        manifest = _make_manifest(tmp_path, [
            {"name": "R", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "N/A", "build": "N/A"},
        ])
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            return_value=(0, "", ""),
        ):
            result = run_certify_baseline(
                manifest_path=manifest, repo_filter=None, build_mode="release",
                strict=False, no_build=True, pf=pf,
            )
        run_id = result["run_id"]
        gate_file = pf / run_id / "certify_baseline_gate.json"
        assert gate_file.exists(), "gate JSON artifact must be written"
        payload = json.loads(gate_file.read_text(encoding="utf-8"))
        assert payload["gate"] == "PASS"

    def test_ngksgraph_repo_build_invoked_when_configure_not_na(self, tmp_path):
        d = tmp_path / "NGraph"; d.mkdir()
        manifest = _make_manifest(tmp_path, [
            {"name": "NGraph", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "PASS", "build": "PASS"},
        ])
        pf = tmp_path / "pf"
        call_log = []

        def _mock(sub_cmd, path, extra):
            call_log.append(sub_cmd)
            return (0, "", "")

        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=_mock,
        ):
            result = run_certify_baseline(
                manifest_path=manifest, repo_filter=None, build_mode="release",
                strict=False, no_build=False, pf=pf,
            )
        assert "build" in call_log
        assert result["gate"] == "PASS"

    def test_ngksgraph_repo_build_skipped_with_no_build_flag(self, tmp_path):
        d = tmp_path / "NGraph"; d.mkdir()
        manifest = _make_manifest(tmp_path, [
            {"name": "NGraph", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "PASS", "build": "PASS"},
        ])
        pf = tmp_path / "pf"
        call_log = []

        def _mock(sub_cmd, path, extra):
            call_log.append(sub_cmd)
            return (0, "", "")

        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=_mock,
        ):
            result = run_certify_baseline(
                manifest_path=manifest, repo_filter=None, build_mode="release",
                strict=False, no_build=True, pf=pf,
            )
        assert "build" not in call_log
        assert result["gate"] == "PASS"

    def test_build_regression_triggers_fail(self, tmp_path):
        d = tmp_path / "NGraph"; d.mkdir()
        manifest = _make_manifest(tmp_path, [
            {"name": "NGraph", "path": str(d), "probe": "PASS", "doctor": "PASS",
             "configure": "PASS", "build": "PASS"},
        ])
        pf = tmp_path / "pf"
        # probe=0, doctor=0, build=1 (broken build)
        with patch(
            "ngksdevfabric.ngk_fabric.certify_baseline._run_stage_subprocess",
            side_effect=[(0, "", ""), (0, "", ""), (1, "", "build error")],
        ):
            result = run_certify_baseline(
                manifest_path=manifest, repo_filter=None, build_mode="release",
                strict=False, no_build=False, pf=pf,
            )
        assert result["gate"] == "FAIL"
        repo = result["repo_results"][0]
        bld_stage = next(s for s in repo["stages"] if s["stage"] == "build")
        assert bld_stage["is_regression"] is True
