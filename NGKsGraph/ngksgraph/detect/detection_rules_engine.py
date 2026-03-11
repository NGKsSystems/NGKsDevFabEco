from __future__ import annotations

import json
from pathlib import Path


def _rules_file() -> Path:
    return Path(__file__).resolve().parents[1] / "rules" / "detection_rules.json"


def _load_rules() -> list[dict[str, object]]:
    try:
        payload = json.loads(_rules_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_rules = payload.get("rules", []) if isinstance(payload, dict) else []
    return [item for item in raw_rules if isinstance(item, dict)]


def _expand_brace_glob(pattern: str) -> list[str]:
    left = pattern.find("{")
    right = pattern.find("}")
    if left == -1 or right == -1 or right < left:
        return [pattern]
    prefix = pattern[:left]
    suffix = pattern[right + 1 :]
    options = [item.strip() for item in pattern[left + 1 : right].split(",") if item.strip()]
    if not options:
        return [pattern]
    return [f"{prefix}{opt}{suffix}" for opt in options]


def evaluate_detection_rules(repo_root: Path) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for rule in _load_rules():
        rule_id = str(rule.get("id", "")).strip()
        if not rule_id:
            continue
        rule_type = str(rule.get("type", "")).strip().lower()
        pattern = str(rule.get("pattern", ""))

        if rule_type == "has_file":
            file_name = str(rule.get("file", "")).strip()
            if not file_name:
                continue
            if (repo_root / file_name).exists():
                hits.append({"id": rule_id, "type": "has_file", "matched_by": [file_name]})
            continue

        if rule_type == "contains_text":
            file_name = str(rule.get("file", "")).strip()
            if file_name:
                candidate = repo_root / file_name
                if candidate.exists() and candidate.is_file():
                    text = candidate.read_text(encoding="utf-8", errors="ignore")
                    if pattern and pattern in text:
                        hits.append({"id": rule_id, "type": "contains_text", "matched_by": [file_name]})
                continue

            file_glob = str(rule.get("file_glob", "")).strip()
            if not file_glob:
                continue

            matched_paths: list[str] = []
            for expanded in _expand_brace_glob(file_glob):
                for path in repo_root.glob(expanded):
                    if not path.exists() or not path.is_file():
                        continue
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    if pattern and pattern in text:
                        matched_paths.append(path.resolve().relative_to(repo_root.resolve()).as_posix())
                        if len(matched_paths) >= 8:
                            break
                if len(matched_paths) >= 8:
                    break

            if matched_paths:
                hits.append({"id": rule_id, "type": "contains_text", "matched_by": sorted(set(matched_paths))})

    return hits
