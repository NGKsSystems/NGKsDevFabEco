"""NGKsGraph target drift detection and controlled manifest sync."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Set


@dataclass
class DiscoveredTarget:
    """A target detected by repository scanning."""
    name: str
    type: str
    src_globs: List[str]
    confidence: float
    reason: str
    location: str


class TargetDriftDetector:
    """Detect drift between discovered targets and declared targets."""

    def __init__(self, config: dict, repo_root: Path):
        self.config = config or {}
        self.repo_root = Path(repo_root)
        self.discovered: List[DiscoveredTarget] = []
        self.declared_names: Set[str] = set()

    def scan_discovered_targets(self) -> List[DiscoveredTarget]:
        """Scan repo for discoverable targets."""
        self.discovered = []

        self._collect_declared_target_names()
        self._scan_qmake_projects()
        self._scan_common_test_directories()

        return self.discovered

    def _collect_declared_target_names(self) -> None:
        targets = self.config.get("targets", [])
        if not isinstance(targets, list):
            return
        for target in targets:
            name = ""
            if isinstance(target, dict):
                name = str(target.get("name", "") or "")
            else:
                name = str(getattr(target, "name", "") or "")
            if name:
                self.declared_names.add(name)

    def _scan_qmake_projects(self) -> None:
        ignore_parts = {".git", "build", "dist", "_proof", ".venv", "venv", "node_modules"}
        by_name: Dict[str, DiscoveredTarget] = {}
        for pro_file in self.repo_root.rglob("*.pro"):
            if any(part in ignore_parts for part in pro_file.parts):
                continue

            parsed = self._parse_qmake_target(pro_file)
            if not parsed:
                continue

            target_name = parsed["name"]
            src_globs = parsed["src_globs"]
            target_type = parsed["type"]

            candidate = DiscoveredTarget(
                name=target_name,
                type=target_type,
                src_globs=src_globs,
                confidence=0.95,
                reason=f"qmake project file discovered: {pro_file.name}",
                location=str(pro_file.parent.relative_to(self.repo_root)).replace("\\", "/"),
            )

            existing = by_name.get(target_name)
            if existing is None:
                by_name[target_name] = candidate
                continue

            # Prefer explicit src-root globs over wide project globs for same target name.
            existing_glob = existing.src_globs[0] if existing.src_globs else ""
            candidate_glob = candidate.src_globs[0] if candidate.src_globs else ""
            existing_is_src = "/src/" in existing_glob
            candidate_is_src = "/src/" in candidate_glob
            if candidate_is_src and not existing_is_src:
                by_name[target_name] = candidate

        self.discovered.extend(by_name.values())

    def _parse_qmake_target(self, pro_file: Path) -> Dict[str, Any] | None:
        try:
            text = pro_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

        target_match = re.search(r"^\s*TARGET\s*=\s*([A-Za-z0-9_\-\.]+)\s*$", text, flags=re.MULTILINE)
        template_match = re.search(r"^\s*TEMPLATE\s*=\s*([A-Za-z0-9_\-\.]+)\s*$", text, flags=re.MULTILINE)
        if not target_match:
            return None

        target_name = target_match.group(1).strip()
        template = (template_match.group(1).strip().lower() if template_match else "app")
        target_type = "exe" if template == "app" else "staticlib"

        src_dir = pro_file.parent / "src"
        if src_dir.exists():
            src_globs = [str((src_dir.relative_to(self.repo_root)).as_posix() + "/**/*.cpp")]
        else:
            src_globs = [str((pro_file.parent.relative_to(self.repo_root)).as_posix() + "/**/*.cpp")]

        # Fail-closed: no source files means not a valid discovery.
        has_sources = any(self.repo_root.glob(src_globs[0]))
        if not has_sources:
            return None

        return {"name": target_name, "src_globs": src_globs, "type": target_type}

    def _scan_common_test_directories(self) -> None:
        # Secondary heuristic, lower confidence than qmake parsing.
        for test_dir in self.repo_root.glob("**/tests"):
            if not test_dir.is_dir():
                continue
            cpp_files = list(test_dir.glob("**/*.cpp"))
            if not cpp_files:
                continue
            rel = str(test_dir.relative_to(self.repo_root)).replace("\\", "/")
            name = rel.split("/")[-2] + "_tests" if "/" in rel else "tests"
            self.discovered.append(
                DiscoveredTarget(
                    name=name,
                    type="test_exe",
                    src_globs=[f"{rel}/**/*.cpp"],
                    confidence=0.7,
                    reason="tests directory with C++ sources",
                    location=rel,
                )
            )

    def compare(self) -> Dict:
        """Compare discovered vs declared targets."""
        if not self.discovered:
            self.scan_discovered_targets()

        entries: List[Dict[str, Any]] = []
        for discovered in self.discovered:
            status = "declared" if discovered.name in self.declared_names else "undeclared"
            entries.append({
                "discovered": asdict(discovered),
                "declared": discovered.name if status == "declared" else None,
                "status": status,
                "action": "none" if status == "declared" else "propose",
            })

        return {
            "total_discovered": len(self.discovered),
            "total_declared": len(self.declared_names),
            "undeclared_count": sum(1 for e in entries if e["status"] == "undeclared"),
            "entries": entries,
        }

    def emit_json_report(self, output_path: Path) -> Dict:
        """Emit drift report as JSON."""
        try:
            report = self.compare()
            report["generated_at"] = str(self.repo_root)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2, default=str))
            return report
        except Exception as e:
            return {
                "error": str(e),
                "total_discovered": 0,
                "total_declared": 0,
                "undeclared_count": 0,
                "entries": []
            }

    def build_sync_proposal(self, min_confidence: float = 0.8) -> List[Dict[str, Any]]:
        report = self.compare()
        proposals: List[Dict[str, Any]] = []
        for entry in report.get("entries", []):
            if entry.get("status") != "undeclared":
                continue
            disc = entry.get("discovered", {})
            confidence = float(disc.get("confidence", 0.0))
            if confidence < min_confidence:
                continue
            proposals.append(
                {
                    "name": disc.get("name"),
                    "type": "exe" if disc.get("type") in ("exe", "test_exe") else "staticlib",
                    "src_glob": disc.get("src_globs", []),
                    "include_dirs": [],
                    "defines": ["UNICODE", "_UNICODE"],
                    "cflags": [],
                    "libs": [],
                    "lib_dirs": [],
                    "ldflags": [],
                    "cxx_std": 20,
                    "links": [],
                    "confidence": confidence,
                    "reason": disc.get("reason", ""),
                }
            )
        return proposals

    def apply_sync_to_toml(self, config_path: Path, proposals: List[Dict[str, Any]]) -> List[str]:
        if not proposals:
            return []

        original = config_path.read_text(encoding="utf-8")
        updated = original
        added: List[str] = []

        for proposal in proposals:
            name = str(proposal.get("name", "")).strip()
            if not name:
                continue
            if f'name = "{name}"' in updated:
                continue

            src_globs = proposal.get("src_glob", []) or []
            src_glob_lines = "\n".join([f'  "{g}"' for g in src_globs])
            block = (
                "\n\n[[targets]]\n"
                f'name = "{name}"\n'
                f'type = "{proposal.get("type", "exe")}"\n'
                "src_glob = [\n"
                f"{src_glob_lines}\n"
                "]\n"
                "include_dirs = []\n"
                'defines = ["UNICODE", "_UNICODE"]\n'
                "cflags = []\n"
                "libs = []\n"
                "lib_dirs = []\n"
                "ldflags = []\n"
                "cxx_std = 20\n"
                "links = []\n"
            )
            updated += block
            added.append(name)

        if not added:
            return []

        backup = config_path.with_suffix(config_path.suffix + ".bak_drift_sync")
        backup.write_text(original, encoding="utf-8")
        config_path.write_text(updated, encoding="utf-8")
        return added
