from __future__ import annotations

"""test_release_gate.py
=======================
Deterministic unit tests for the release_gate module.

Test categories
---------------
1.  PASS path     – release-gate passes when certify-baseline returns GATE=PASS
2.  FAIL path     – release-gate fails when certify-baseline returns GATE=FAIL
3.  ERROR path    – release-gate errors on missing/unreadable baseline
4.  Verdict file  – artifact is written with all required fields
5.  Strict mode   – --strict flag is threaded through to certify-baseline
6.  Explicit path – --baseline override bypasses auto-discovery
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ngksdevfabric.ngk_fabric.release_gate import run_release_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(tmp_path: Path, *, name: str = "Certification_Baseline_v1") -> Path:
    bl_dir = tmp_path / ".baseline_v1_20260318_000000"
    bl_dir.mkdir()
    repos = [
        {
            "name": "RepoA",
            "path": str(tmp_path / "RepoA"),
            "tier": "TIER_1",
            "probe": "PASS",
            "doctor": "PASS",
            "configure": "PASS",
            "build": "PASS",
        },
        {
            "name": "RepoB",
            "path": str(tmp_path / "RepoB"),
            "tier": "TIER_2",
            "probe": "PASS",
            "doctor": "PASS",
            "configure": "N/A",
            "build": "N/A",
        },
    ]
    manifest = bl_dir / "repo_manifest.json"
    manifest.write_text(
        json.dumps({"baseline_name": name, "certified_repos": repos, "summary": {}}),
        encoding="utf-8",
    )
    (tmp_path / "RepoA").mkdir(exist_ok=True)
    (tmp_path / "RepoB").mkdir(exist_ok=True)
    return manifest


_PASS_CERTIFY_RESULT = {
    "gate": "PASS",
    "baseline_name": "Certification_Baseline_v1",
    "repos_checked": 2,
    "repos_pass": 2,
    "repos_regression": 0,
    "repos_improvement": 0,
    "repo_results": [],
    "run_id": "certify_baseline_20260319_120000",
}

_FAIL_CERTIFY_RESULT = {
    "gate": "FAIL",
    "baseline_name": "Certification_Baseline_v1",
    "repos_checked": 2,
    "repos_pass": 1,
    "repos_regression": 1,
    "repos_improvement": 0,
    "repo_results": [],
    "run_id": "certify_baseline_20260319_120001",
}


# ---------------------------------------------------------------------------
# 1. PASS path
# ---------------------------------------------------------------------------

class TestReleaseGatePass:

    def test_gate_pass_returns_exit_zero(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_PASS_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["gate"] == "PASS"
        assert result["exit_code"] == 0
        assert result["error"] is None

    def test_gate_pass_no_regressions_in_verdict(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_PASS_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["verdict"]["regression_count"] == 0
        assert result["verdict"]["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# 2. FAIL path
# ---------------------------------------------------------------------------

class TestReleaseGateFail:

    def test_gate_fail_returns_exit_one(self, tmp_path):
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_FAIL_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="dead1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["gate"] == "FAIL"
        assert result["exit_code"] == 1
        assert result["error"] is None

    def test_gate_fail_regression_count_in_verdict(self, tmp_path):
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_FAIL_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="dead1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["verdict"]["regression_count"] == 1
        assert result["verdict"]["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# 3. ERROR path
# ---------------------------------------------------------------------------

class TestReleaseGateError:

    def test_missing_baseline_returns_exit_two(self, tmp_path):
        """When find_baseline_manifest cannot discover a manifest, gate must return ERROR."""
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.find_baseline_manifest",
            side_effect=RuntimeError("Could not auto-discover a repo_manifest.json."),
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["gate"] == "ERROR"
        assert result["exit_code"] == 2
        assert result["error"] is not None

    def test_explicit_nonexistent_baseline_returns_exit_two(self, tmp_path):
        pf = tmp_path / "pf"
        result = run_release_gate(
            eco_root=None,
            baseline_arg=str(tmp_path / "does_not_exist.json"),
            strict=False,
            no_build=True,
            build_mode="release",
            pf=pf,
        )
        assert result["gate"] == "ERROR"
        assert result["exit_code"] == 2
        assert result["error"] is not None

    def test_corrupt_manifest_returns_exit_two(self, tmp_path):
        bl_dir = tmp_path / ".baseline_v1_20260318_000000"
        bl_dir.mkdir()
        manifest = bl_dir / "repo_manifest.json"
        manifest.write_text("NOT VALID JSON >>>", encoding="utf-8")
        pf = tmp_path / "pf"
        result = run_release_gate(
            eco_root=tmp_path,
            baseline_arg="",
            strict=False,
            no_build=True,
            build_mode="release",
            pf=pf,
        )
        assert result["gate"] == "ERROR"
        assert result["exit_code"] == 2


# ---------------------------------------------------------------------------
# 4. Verdict artifact — required fields
# ---------------------------------------------------------------------------

class TestVerdictArtifact:

    _REQUIRED_FIELDS = {
        "verdict",
        "baseline_name",
        "baseline_path",
        "git_head",
        "timestamp",
        "strict",
        "no_build",
        "build_mode",
        "repos_checked",
        "repos_pass",
        "regression_count",
        "improvement_count",
        "tier_1_count",
        "tier_2_count",
        "certify_baseline_run_id",
    }

    def test_verdict_file_written_on_pass(self, tmp_path):
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_PASS_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["verdict_path"] is not None
        assert Path(result["verdict_path"]).exists()

    def test_verdict_file_has_all_required_fields(self, tmp_path):
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_PASS_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        verdict_data = json.loads(Path(result["verdict_path"]).read_text(encoding="utf-8"))
        missing = self._REQUIRED_FIELDS - set(verdict_data.keys())
        assert missing == set(), f"Missing fields in verdict: {missing}"

    def test_tier_counts_reflect_manifest(self, tmp_path):
        """Manifest has 1 TIER_1 + 1 TIER_2 repo — verdict must mirror this."""
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_PASS_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["verdict"]["tier_1_count"] == 1
        assert result["verdict"]["tier_2_count"] == 1

    def test_verdict_file_written_on_fail(self, tmp_path):
        """Verdict file must be written even when gate=FAIL."""
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_FAIL_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="dead1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["verdict_path"] is not None
        assert Path(result["verdict_path"]).exists()


# ---------------------------------------------------------------------------
# 5. Strict mode plumbing
# ---------------------------------------------------------------------------

class TestStrictModePlumbing:

    def test_strict_flag_passed_through_to_certify_baseline(self, tmp_path):
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        captured_kwargs: dict = {}

        def fake_certify(**kwargs):
            captured_kwargs.update(kwargs)
            return _PASS_CERTIFY_RESULT

        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            side_effect=fake_certify,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=True,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert captured_kwargs.get("strict") is True

    def test_strict_false_passed_through(self, tmp_path):
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        captured_kwargs: dict = {}

        def fake_certify(**kwargs):
            captured_kwargs.update(kwargs)
            return _PASS_CERTIFY_RESULT

        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            side_effect=fake_certify,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert captured_kwargs.get("strict") is False

    def test_strict_reflected_in_verdict(self, tmp_path):
        _make_manifest(tmp_path)
        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_PASS_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            result = run_release_gate(
                eco_root=tmp_path,
                baseline_arg="",
                strict=True,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["verdict"]["strict"] is True


# ---------------------------------------------------------------------------
# 6. Explicit baseline path overrides auto-discovery
# ---------------------------------------------------------------------------

class TestExplicitBaselinePath:

    def test_explicit_json_path_used_not_autodiscovered(self, tmp_path):
        """Pass --baseline pointing directly to a manifest JSON.
        No .baseline_v* dir structure required — path is explicit."""
        # Build a second, distinct manifest at a custom location.
        custom_dir = tmp_path / "custom_bl"
        custom_dir.mkdir()
        repos = [
            {
                "name": "CustomRepo",
                "path": str(tmp_path / "CustomRepo"),
                "tier": "TIER_1",
                "probe": "PASS",
                "doctor": "PASS",
                "configure": "PASS",
                "build": "PASS",
            }
        ]
        (tmp_path / "CustomRepo").mkdir()
        custom_manifest = custom_dir / "repo_manifest.json"
        custom_manifest.write_text(
            json.dumps(
                {
                    "baseline_name": "CustomBaseline",
                    "certified_repos": repos,
                    "summary": {},
                }
            ),
            encoding="utf-8",
        )

        pf = tmp_path / "pf"
        captured_manifest: dict = {}

        def fake_certify(**kwargs):
            captured_manifest["path"] = kwargs.get("manifest_path")
            return _PASS_CERTIFY_RESULT

        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            side_effect=fake_certify,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            result = run_release_gate(
                eco_root=None,
                baseline_arg=str(custom_manifest),
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["gate"] == "PASS"
        assert captured_manifest["path"].resolve() == custom_manifest.resolve()

    def test_explicit_directory_path_resolves_manifest(self, tmp_path):
        """Pass a directory as --baseline; it must resolve to repo_manifest.json inside."""
        custom_dir = tmp_path / "explicit_bl_dir"
        custom_dir.mkdir()
        repos = [
            {
                "name": "DirRepo",
                "path": str(tmp_path / "DirRepo"),
                "tier": "TIER_2",
                "probe": "PASS",
                "doctor": "PASS",
                "configure": "N/A",
                "build": "N/A",
            }
        ]
        (tmp_path / "DirRepo").mkdir()
        (custom_dir / "repo_manifest.json").write_text(
            json.dumps(
                {
                    "baseline_name": "DirBaseline",
                    "certified_repos": repos,
                    "summary": {},
                }
            ),
            encoding="utf-8",
        )

        pf = tmp_path / "pf"
        with patch(
            "ngksdevfabric.ngk_fabric.release_gate.run_certify_baseline",
            return_value=_PASS_CERTIFY_RESULT,
        ), patch(
            "ngksdevfabric.ngk_fabric.release_gate.subprocess.check_output",
            return_value="abc1234\n",
        ):
            result = run_release_gate(
                eco_root=None,
                baseline_arg=str(custom_dir),
                strict=False,
                no_build=True,
                build_mode="release",
                pf=pf,
            )
        assert result["gate"] == "PASS"
        assert result["error"] is None
