from __future__ import annotations

from pathlib import Path
from typing import Any

from .devfabeco_validation_plugins import ValidationPlugin, read_json, write_json, write_text

_WRAPPER_TYPES = {"frame", "panel", "card", "layout", "container", "wrapper", "group"}


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _slug(value: str) -> str:
    text = str(value).strip().lower()
    chars = [ch if ch.isalnum() else "_" for ch in text]
    compact = "".join(chars)
    while "__" in compact:
        compact = compact.replace("__", "_")
    return compact.strip("_") or "item"


def _bounds(node: dict[str, Any]) -> tuple[float, float]:
    top = _safe_float(node.get("rendered_top", node.get("top", node.get("y", 0.0))))
    if "rendered_bottom" in node:
        bottom = _safe_float(node.get("rendered_bottom", 0.0))
    elif "bottom" in node:
        bottom = _safe_float(node.get("bottom", 0.0))
    else:
        bottom = top + _safe_float(node.get("height", node.get("min_height", 0.0)))
    if bottom < top:
        return bottom, top
    return top, bottom


def _has_explicit_vertical_position(node: dict[str, Any]) -> bool:
    return any(key in node for key in ("rendered_top", "top", "y", "rendered_bottom", "bottom"))


def _resolved_child_bounds(
    *,
    parent: dict[str, Any],
    children: list[dict[str, Any]],
    spacing: float,
    padding_top: float,
) -> list[tuple[dict[str, Any], float, float]]:
    parent_top, _parent_bottom = _bounds(parent)
    content_top = parent_top + padding_top
    cursor = content_top
    resolved: list[tuple[dict[str, Any], float, float]] = []

    for child in children:
        margin_top = _safe_float(child.get("margin_top", 0.0))
        margin_bottom = _safe_float(child.get("margin_bottom", 0.0))
        child_height = _safe_float(child.get("min_height", child.get("height", 0.0)))

        if _has_explicit_vertical_position(child):
            top, bottom = _bounds(child)
        else:
            top = cursor + margin_top
            bottom = top + max(0.0, child_height)

        resolved.append((child, top, bottom))
        cursor = max(cursor, bottom + margin_bottom + spacing)

    return resolved


class UILayoutIntegrityValidationPlugin(ValidationPlugin):
    plugin_name = "ui_layout_integrity"
    plugin_version = "1.0.0"
    plugin_category = "UI_LAYOUT_VALIDATION"

    def load_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        self.context = dict(context)
        pf = Path(str(context.get("pf", "."))).resolve()

        payload: dict[str, Any] = {}
        if isinstance(context.get("layout_snapshot", {}), dict):
            payload = context.get("layout_snapshot", {})
        elif str(context.get("layout_snapshot_path", "")).strip():
            payload = read_json(Path(str(context.get("layout_snapshot_path", "")).strip()))
        else:
            payload = read_json(pf / "layout" / "layout_snapshot.json")

        containers = payload.get("containers", []) if isinstance(payload.get("containers", []), list) else []
        self.inputs = {
            "view_name": str(payload.get("view_name", context.get("view_name", "runtime_default_view"))),
            "root_container": str(payload.get("root_container", "root")),
            "supported_viewports": payload.get("supported_viewports", []) if isinstance(payload.get("supported_viewports", []), list) else [],
            "containers": [row for row in containers if isinstance(row, dict)],
        }
        return self.inputs

    def _build_issue(
        self,
        *,
        issue_id: str,
        severity: str,
        container_name: str,
        parent_height: float,
        required_height: float,
        overflow_amount: float,
        overlap_details: dict[str, Any] | None = None,
        nesting_depth: int = 0,
        recommended_fixes: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "issue_id": issue_id,
            "severity": severity,
            "container_name": container_name,
            "parent_height": round(parent_height, 4),
            "required_height": round(required_height, 4),
            "overflow_amount": round(max(0.0, overflow_amount), 4),
            "overlap_details": overlap_details or {},
            "nesting_depth": int(nesting_depth),
            "recommended_fixes": recommended_fixes or [],
        }

    def _fixes_for(self, issue_type: str) -> list[str]:
        table = {
            "LAYOUT_OVERFLOW": [
                "remove fixed height from inner container",
                "use stretch or flex sizing instead of hard heights",
                "reduce vertical padding and margins in stacked sections",
                "place overflow-prone region in a scroll area",
            ],
            "LAYOUT_COLLISION": [
                "replace manual y-positioning with deterministic vertical layout",
                "increase section spacing to prevent bound overlap",
                "split summary and detail controls into separate regions",
            ],
            "LAYOUT_CLIPPING_WARNING": [
                "ensure child bounds stay inside parent content region",
                "enable scrolling for clipped control groups",
                "remove duplicated wrapper layers reducing usable height",
            ],
            "WRAPPER_WASTE_WARNING": [
                "replace nested wrapper stack with direct layout",
                "remove purely decorative intermediate containers",
                "merge wrapper padding into one parent container",
            ],
            "DUPLICATE_STATUS_REGION_WARNING": [
                "merge duplicate status rows into a single status region",
                "collapse secondary status details by default",
            ],
            "VIEWPORT_FIT_FAILURE": [
                "introduce responsive collapse for secondary sections",
                "split summary and detail views for small viewport heights",
                "use viewport-aware scroll area in central panel",
            ],
        }
        return list(table.get(issue_type, ["review layout sizing strategy for this container"]))

    def run_analysis(self) -> dict[str, Any]:
        containers = self.inputs.get("containers", []) if isinstance(self.inputs.get("containers", []), list) else []
        index = {
            str(row.get("name", "")).strip(): row
            for row in containers
            if isinstance(row, dict) and str(row.get("name", "")).strip()
        }
        children_map: dict[str, list[dict[str, Any]]] = {}
        for row in containers:
            name = str(row.get("name", "")).strip()
            parent = str(row.get("parent", "")).strip()
            if name and parent:
                children_map.setdefault(parent, []).append(row)

        overflow_rows: list[dict[str, Any]] = []
        collision_rows: list[dict[str, Any]] = []
        wrapper_rows: list[dict[str, Any]] = []
        recommendation_rows: list[dict[str, Any]] = []

        for parent_name, children in children_map.items():
            parent = index.get(parent_name, {}) if isinstance(index.get(parent_name, {}), dict) else {}
            parent_height = _safe_float(parent.get("height", parent.get("min_height", 0.0)))
            padding_top = _safe_float(parent.get("padding_top", parent.get("padding", 0.0)))
            padding_bottom = _safe_float(parent.get("padding_bottom", parent.get("padding", 0.0)))
            parent_content_height = max(0.0, parent_height - padding_top - padding_bottom)
            spacing = _safe_float(parent.get("spacing", 0.0))

            required = 0.0
            for child in children:
                child_height = _safe_float(child.get("min_height", child.get("height", 0.0)))
                margin_top = _safe_float(child.get("margin_top", 0.0))
                margin_bottom = _safe_float(child.get("margin_bottom", 0.0))
                required += child_height + margin_top + margin_bottom
            if len(children) > 1:
                required += spacing * (len(children) - 1)

            overflow = required - parent_content_height
            if overflow > 0.0:
                severity = "FAIL" if overflow >= max(24.0, parent_content_height * 0.12) else "WARNING"
                issue = self._build_issue(
                    issue_id=f"LAYOUT_OVERFLOW_{_slug(parent_name)}",
                    severity=severity,
                    container_name=parent_name,
                    parent_height=parent_content_height,
                    required_height=required,
                    overflow_amount=overflow,
                    nesting_depth=0,
                    recommended_fixes=self._fixes_for("LAYOUT_OVERFLOW"),
                )
                overflow_rows.append(issue)

            resolved_children = _resolved_child_bounds(
                parent=parent,
                children=children,
                spacing=spacing,
                padding_top=padding_top,
            )
            sorted_children = sorted(resolved_children, key=lambda row: row[1])
            previous = None
            for current in sorted_children:
                current_child, cur_top, cur_bottom = current
                if previous is not None:
                    previous_child, prev_top, prev_bottom = previous
                    if prev_bottom > cur_top:
                        issue = self._build_issue(
                            issue_id=f"LAYOUT_COLLISION_{_slug(parent_name)}_{_slug(str(previous_child.get('name', 'a')))}_{_slug(str(current_child.get('name', 'b')))}",
                            severity="FAIL",
                            container_name=parent_name,
                            parent_height=parent_content_height,
                            required_height=required,
                            overflow_amount=max(0.0, prev_bottom - cur_top),
                            overlap_details={
                                "first_child": str(previous_child.get("name", "")),
                                "second_child": str(current_child.get("name", "")),
                                "first_bottom": round(prev_bottom, 4),
                                "second_top": round(cur_top, 4),
                            },
                            recommended_fixes=self._fixes_for("LAYOUT_COLLISION"),
                        )
                        collision_rows.append(issue)
                previous = current

                parent_top, _ = _bounds(parent)
                content_top = parent_top + padding_top
                content_bottom = content_top + parent_content_height
                if cur_top < content_top or cur_bottom > content_bottom:
                    issue = self._build_issue(
                        issue_id=f"LAYOUT_CLIPPING_WARNING_{_slug(parent_name)}_{_slug(str(current_child.get('name', 'child')))}",
                        severity="WARNING",
                        container_name=parent_name,
                        parent_height=parent_content_height,
                        required_height=required,
                        overflow_amount=max(0.0, cur_bottom - content_bottom),
                        overlap_details={
                            "child": str(current_child.get("name", "")),
                            "child_top": round(cur_top, 4),
                            "child_bottom": round(cur_bottom, 4),
                            "content_top": round(content_top, 4),
                            "content_bottom": round(content_bottom, 4),
                        },
                        recommended_fixes=self._fixes_for("LAYOUT_CLIPPING_WARNING"),
                    )
                    overflow_rows.append(issue)

            status_like = []
            for child in children:
                role = str(child.get("region_role", "")).strip().lower()
                name = str(child.get("name", "")).strip().lower()
                if role in {"status", "state", "info_band"} or any(token in name for token in ("status", "state", "phase")):
                    status_like.append(child)
            if len(status_like) >= 2:
                issue = self._build_issue(
                    issue_id=f"DUPLICATE_STATUS_REGION_WARNING_{_slug(parent_name)}",
                    severity="WARNING",
                    container_name=parent_name,
                    parent_height=parent_content_height,
                    required_height=required,
                    overflow_amount=0.0,
                    overlap_details={
                        "duplicate_regions": [str(row.get("name", "")) for row in status_like],
                    },
                    recommended_fixes=self._fixes_for("DUPLICATE_STATUS_REGION_WARNING"),
                )
                wrapper_rows.append(issue)

        for row in containers:
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            node_type = str(row.get("type", "container")).strip().lower()
            if node_type not in _WRAPPER_TYPES:
                continue
            depth = 1
            current = row
            while True:
                parent_name = str(current.get("parent", "")).strip()
                parent = index.get(parent_name, {}) if isinstance(index.get(parent_name, {}), dict) else {}
                if not parent:
                    break
                parent_type = str(parent.get("type", "container")).strip().lower()
                if parent_type in _WRAPPER_TYPES:
                    depth += 1
                current = parent
            if depth >= 4:
                issue = self._build_issue(
                    issue_id=f"WRAPPER_WASTE_WARNING_{_slug(name)}",
                    severity="WARNING",
                    container_name=name,
                    parent_height=_safe_float(row.get("height", row.get("min_height", 0.0))),
                    required_height=_safe_float(row.get("min_height", row.get("height", 0.0))),
                    overflow_amount=0.0,
                    nesting_depth=depth,
                    recommended_fixes=self._fixes_for("WRAPPER_WASTE_WARNING"),
                )
                wrapper_rows.append(issue)

        root_name = str(self.inputs.get("root_container", "root")).strip()
        root = index.get(root_name, {}) if isinstance(index.get(root_name, {}), dict) else {}
        root_children = children_map.get(root_name, [])
        root_spacing = _safe_float(root.get("spacing", 0.0))
        root_required = 0.0
        for child in root_children:
            root_required += _safe_float(child.get("min_height", child.get("height", 0.0)))
            root_required += _safe_float(child.get("margin_top", 0.0)) + _safe_float(child.get("margin_bottom", 0.0))
        if len(root_children) > 1:
            root_required += root_spacing * (len(root_children) - 1)

        for viewport in self.inputs.get("supported_viewports", []):
            if not isinstance(viewport, dict):
                continue
            viewport_name = str(viewport.get("name", "viewport")).strip() or "viewport"
            viewport_height = _safe_float(viewport.get("height", 0.0))
            if viewport_height <= 0.0:
                continue
            if root_required > viewport_height:
                issue = self._build_issue(
                    issue_id=f"VIEWPORT_FIT_FAILURE_{_slug(viewport_name)}",
                    severity="FAIL",
                    container_name=root_name,
                    parent_height=viewport_height,
                    required_height=root_required,
                    overflow_amount=root_required - viewport_height,
                    overlap_details={"viewport": viewport_name},
                    recommended_fixes=self._fixes_for("VIEWPORT_FIT_FAILURE"),
                )
                overflow_rows.append(issue)

        all_rows = [*overflow_rows, *collision_rows, *wrapper_rows]
        for issue in all_rows:
            recommendation_rows.append(
                {
                    "issue_id": str(issue.get("issue_id", "")),
                    "severity": str(issue.get("severity", "INFO")),
                    "container_name": str(issue.get("container_name", "")),
                    "recommended_fixes": issue.get("recommended_fixes", []),
                }
            )

        fail_count = sum(1 for row in all_rows if str(row.get("severity", "INFO")) == "FAIL")
        warning_count = sum(1 for row in all_rows if str(row.get("severity", "INFO")) == "WARNING")
        status = "PASS"
        if fail_count > 0:
            status = "FAIL"
        elif warning_count > 0:
            status = "WARNING"

        self.analysis = {
            "status": status,
            "view_name": str(self.inputs.get("view_name", "runtime_default_view")),
            "overflow_issues": overflow_rows,
            "collision_issues": collision_rows,
            "wrapper_waste_issues": wrapper_rows,
            "fix_recommendations": recommendation_rows,
            "summary": {
                "issue_count": len(all_rows),
                "fail_count": fail_count,
                "warning_count": warning_count,
                "detected_issue_types": sorted(
                    {
                        str(row.get("issue_id", "")).split("_")[0] + "_" + str(row.get("issue_id", "")).split("_")[1]
                        for row in all_rows
                        if "_" in str(row.get("issue_id", ""))
                    }
                ),
            },
        }
        return self.analysis

    def generate_artifacts(self, output_dir: Path) -> list[str]:
        layout_dir = output_dir / "layout"
        overflow = self.analysis.get("overflow_issues", []) if isinstance(self.analysis.get("overflow_issues", []), list) else []
        collisions = self.analysis.get("collision_issues", []) if isinstance(self.analysis.get("collision_issues", []), list) else []
        wrapper = self.analysis.get("wrapper_waste_issues", []) if isinstance(self.analysis.get("wrapper_waste_issues", []), list) else []
        fixes = self.analysis.get("fix_recommendations", []) if isinstance(self.analysis.get("fix_recommendations", []), list) else []
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}

        write_json(layout_dir / "210_layout_overflow.json", {"rows": overflow, "summary": summary})
        write_json(layout_dir / "211_layout_collision.json", {"rows": collisions, "summary": summary})
        write_json(layout_dir / "212_layout_wrapper_waste.json", {"rows": wrapper, "summary": summary})
        write_json(layout_dir / "213_layout_fix_recommendations.json", {"rows": fixes, "summary": summary})

        lines = [
            "# UI Layout Integrity Validation Summary",
            "",
            f"- view_name: {self.analysis.get('view_name', '')}",
            f"- plugin_status: {self.analysis.get('status', 'PASS')}",
            f"- issue_count: {summary.get('issue_count', 0)}",
            f"- fail_count: {summary.get('fail_count', 0)}",
            f"- warning_count: {summary.get('warning_count', 0)}",
            "",
            "## Primary Recommendations",
        ]
        if fixes:
            for row in fixes[:15]:
                recs = row.get("recommended_fixes", []) if isinstance(row.get("recommended_fixes", []), list) else []
                lines.append(
                    "- issue_id="
                    + str(row.get("issue_id", ""))
                    + " container="
                    + str(row.get("container_name", ""))
                    + " fixes="
                    + "; ".join(str(item) for item in recs[:2])
                )
        else:
            lines.append("- no layout integrity issues detected")

        write_text(layout_dir / "214_layout_summary.md", "\n".join(lines) + "\n")

        return [
            "validation_plugins/ui_layout/layout/210_layout_overflow.json",
            "validation_plugins/ui_layout/layout/211_layout_collision.json",
            "validation_plugins/ui_layout/layout/212_layout_wrapper_waste.json",
            "validation_plugins/ui_layout/layout/213_layout_fix_recommendations.json",
            "validation_plugins/ui_layout/layout/214_layout_summary.md",
        ]

    def generate_summary(self) -> str:
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}
        return (
            f"plugin={self.plugin_name} status={self.analysis.get('status', 'PASS')} "
            f"issues={summary.get('issue_count', 0)} fails={summary.get('fail_count', 0)} warnings={summary.get('warning_count', 0)}"
        )
