"""
NGKsGraph Target Drift Detector (Simplified)

Scans repository structure for common test/lib patterns,
detects undeclared but discoverable targets.
"""

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Set


@dataclass
class DiscoveredTarget:
    """A target detected by filesystem scanning."""
    name: str
    type: str
    src_globs: List[str]
    confidence: float
    reason: str
    location: str


class TargetDriftDetector:
    """Detects drift between discovered and declared targets."""

    def __init__(self, config: dict, repo_root: Path):
        self.config = config or {}
        self.repo_root = Path(repo_root)
        self.discovered: List[DiscoveredTarget] = []
        self.declared_names: Set[str] = set()

    def scan_discovered_targets(self) -> List[DiscoveredTarget]:
        """Scan repo for discoverable targets - simplified."""
        self.discovered = []

        # Extract declared target names
        targets_list = self.config.get("targets", [])
        if targets_list and isinstance(targets_list, list):
            for t in targets_list:
                if isinstance(t, dict):
                    name = t.get("name", "")
                    if name:
                        self.declared_names.add(name)

        # Scan common test/lib dirs (non-recursive for speed)
        self._scan_test_directories()
        self._scan_lib_directories()

        return self.discovered

    def _scan_test_directories(self):
        """Find test executables in common test directories."""
        test_patterns = ["tests", "test", "QtTests", "unit_tests", "unittests"]
        
        for pattern in test_patterns:
            test_dir = self.repo_root / pattern
            if test_dir.is_dir():
                cpps = list(test_dir.glob("*.cpp")) + list(test_dir.glob("*.cc"))
                if cpps:
                    target_name = pattern + "_exe"
                    if target_name not in self.declared_names:
                        self.discovered.append(
                            DiscoveredTarget(
                                name=target_name,
                                type="test_exe",
                                src_globs=[f"{pattern}/*.cpp"],
                                confidence=0.8,
                                reason=f"Test dir '{pattern}' with {len(cpps)} file(s)",
                                location=str(test_dir.relative_to(self.repo_root)),
                            )
                        )

    def _scan_lib_directories(self):
        """Find library candidates in common lib directories."""
        lib_patterns = ["lib", "libs"]
        
        for pattern in lib_patterns:
            lib_dir = self.repo_root / pattern
            if lib_dir.is_dir():
                cpps = list(lib_dir.glob("*.cpp")) + list(lib_dir.glob("*.cc"))
                if len(cpps) > 1:
                    target_name = pattern
                    if target_name not in self.declared_names:
                        self.discovered.append(
                            DiscoveredTarget(
                                name=target_name,
                                type="staticlib",
                                src_globs=[f"{pattern}/*.cpp"],
                                confidence=0.6,
                                reason=f"Lib dir '{pattern}' with {len(cpps)} file(s)",
                                location=str(lib_dir.relative_to(self.repo_root)),
                            )
                        )

    def compare(self) -> Dict:
        """Compare discovered vs declared targets."""
        if not self.discovered:
            self.scan_discovered_targets()

        entries = []
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
