from __future__ import annotations

import hashlib
import json
import os
import smtplib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from .delivery_reconciliation import append_acknowledgments_history
from .delivery_reconciliation import build_acknowledgment_record
from .delivery_reconciliation import extract_issue_context
from .delivery_reconciliation import find_reconciliation_match
from .delivery_reconciliation import load_acknowledgment_history
from .delivery_reconciliation import write_reconciliation_artifacts
from .external_status_sync import run_external_status_sync_and_closure_reconciliation
from .issue_update_policy import run_bidirectional_issue_update_policy

_ALLOWED_MODES = {"DRY_RUN", "LIVE"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _normalize_mode(value: object) -> str:
    mode = str(value or "DRY_RUN").strip().upper()
    if mode not in _ALLOWED_MODES:
        return "DRY_RUN"
    return mode


def _as_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _default_config() -> dict[str, Any]:
    return {
        "mode": "DRY_RUN",
        "github": {
            "enabled": True,
            "repo_owner": "",
            "repo_name": "",
            "token_env_var": "GITHUB_TOKEN",
        },
        "jira": {
            "enabled": True,
            "base_url": "",
            "project_key": "",
            "token_env_var": "JIRA_TOKEN",
        },
        "email": {
            "enabled": True,
            "smtp_host": "",
            "port": 587,
            "sender": "devfabeco@example.com",
        },
        "webhook": {
            "enabled": True,
            "endpoint_env_var": "DEVFABECO_WEBHOOK_URL",
        },
    }


def load_connector_transport_config(*, project_root: Path) -> dict[str, Any]:
    config_path = (project_root / "connector_transport.json").resolve()
    defaults = _default_config()
    loaded = _read_json(config_path)

    config = {
        "mode": _normalize_mode(loaded.get("mode", defaults["mode"])),
        "github": dict(defaults["github"]),
        "jira": dict(defaults["jira"]),
        "email": dict(defaults["email"]),
        "webhook": dict(defaults["webhook"]),
        "config_path": str(config_path),
        "config_found": config_path.is_file(),
    }

    for target in ("github", "jira", "email", "webhook"):
        incoming = loaded.get(target, {})
        if isinstance(incoming, dict):
            config[target].update(incoming)
        config[target]["enabled"] = _as_bool(config[target].get("enabled", True), default=True)

    return config


def _payload_items(payload: dict[str, Any], target: str) -> list[dict[str, Any]]:
    if target == "email":
        rows = payload.get("messages", [])
    else:
        rows = payload.get("requests", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _load_transport_payloads(*, pf: Path) -> dict[str, list[dict[str, Any]]]:
    hot = pf / "hotspots"
    github_payload = _read_json(hot / "29_github_delivery_payload.json")
    jira_payload = _read_json(hot / "30_jira_delivery_payload.json")
    email_payload = _read_json(hot / "31_email_delivery_payload.json")
    webhook_payload = _read_json(hot / "32_webhook_delivery_payload.json")

    return {
        "github": _payload_items(github_payload, "github"),
        "jira": _payload_items(jira_payload, "jira"),
        "email": _payload_items(email_payload, "email"),
        "webhook": _payload_items(webhook_payload, "webhook"),
    }


def _request_identifier(target: str, index: int, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256((target + "|" + str(index) + "|" + body).encode("utf-8")).hexdigest()
    return f"{target}:{index:04d}:{digest[:12]}"


def _headers_from_payload(payload_headers: object) -> dict[str, str]:
    if not isinstance(payload_headers, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in payload_headers.items():
        key = str(k).strip()
        if not key:
            continue
        out[key] = str(v)
    return out


def _http_send_json(*, url: str, method: str, headers: dict[str, str], body: dict[str, Any], timeout: float = 10.0) -> tuple[bool, str]:
    encoded = json.dumps(body).encode("utf-8")
    wire_headers = dict(headers)
    wire_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url=url, method=method.upper(), headers=wire_headers, data=encoded)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            return True, f"http_status={int(status)}"
    except urllib.error.HTTPError as exc:
        return False, f"http_error={int(exc.code)}"
    except urllib.error.URLError as exc:
        return False, f"network_error={exc.reason}"
    except Exception as exc:
        return False, f"transport_error={exc}"


def _validate_connector_live_config(target: str, connector_cfg: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if target == "github":
        if not str(connector_cfg.get("repo_owner", "")).strip():
            missing.append("repo_owner")
        if not str(connector_cfg.get("repo_name", "")).strip():
            missing.append("repo_name")
        token_env = str(connector_cfg.get("token_env_var", "")).strip()
        if not token_env:
            missing.append("token_env_var")
        elif not str(os.environ.get(token_env, "")).strip():
            missing.append("token_env_value")
    elif target == "jira":
        if not str(connector_cfg.get("base_url", "")).strip():
            missing.append("base_url")
        if not str(connector_cfg.get("project_key", "")).strip():
            missing.append("project_key")
        token_env = str(connector_cfg.get("token_env_var", "")).strip()
        if not token_env:
            missing.append("token_env_var")
        elif not str(os.environ.get(token_env, "")).strip():
            missing.append("token_env_value")
    elif target == "email":
        if not str(connector_cfg.get("smtp_host", "")).strip():
            missing.append("smtp_host")
        if not str(connector_cfg.get("sender", "")).strip():
            missing.append("sender")
    elif target == "webhook":
        endpoint_env = str(connector_cfg.get("endpoint_env_var", "")).strip()
        if not endpoint_env:
            missing.append("endpoint_env_var")
        elif not str(os.environ.get(endpoint_env, "")).strip():
            missing.append("endpoint_env_value")
    return missing


def _live_send(target: str, payload: dict[str, Any], connector_cfg: dict[str, Any]) -> tuple[bool, str]:
    if target == "github":
        endpoint = str(payload.get("endpoint_template", "")).strip()
        if not endpoint:
            return False, "missing_endpoint_template"
        repo_owner = str(connector_cfg.get("repo_owner", "")).strip()
        repo_name = str(connector_cfg.get("repo_name", "")).strip()
        token = str(os.environ.get(str(connector_cfg.get("token_env_var", "")), "")).strip()
        url = "https://api.github.com" + endpoint.format(owner=repo_owner, repo=repo_name)
        headers = _headers_from_payload(payload.get("headers", {}))
        headers["Authorization"] = "Bearer " + token
        body = payload.get("body", {}) if isinstance(payload.get("body", {}), dict) else {}
        return _http_send_json(url=url, method=str(payload.get("method", "POST")), headers=headers, body=body)

    if target == "jira":
        endpoint = str(payload.get("endpoint_template", "")).strip()
        if not endpoint:
            return False, "missing_endpoint_template"
        base_url = str(connector_cfg.get("base_url", "")).rstrip("/")
        token = str(os.environ.get(str(connector_cfg.get("token_env_var", "")), "")).strip()
        url = base_url + endpoint
        headers = _headers_from_payload(payload.get("headers", {}))
        headers["Authorization"] = "Bearer " + token
        body = payload.get("body", {}) if isinstance(payload.get("body", {}), dict) else {}
        fields = body.get("fields", {}) if isinstance(body.get("fields", {}), dict) else {}
        if "project" not in fields:
            fields["project"] = {"key": str(connector_cfg.get("project_key", "")).strip()}
            body["fields"] = fields
        return _http_send_json(url=url, method=str(payload.get("method", "POST")), headers=headers, body=body)

    if target == "webhook":
        endpoint_url = str(os.environ.get(str(connector_cfg.get("endpoint_env_var", "")), "")).strip()
        if not endpoint_url:
            return False, "missing_webhook_endpoint"
        headers = _headers_from_payload(payload.get("headers", {}))
        body = payload.get("body", {}) if isinstance(payload.get("body", {}), dict) else {}
        return _http_send_json(url=endpoint_url, method=str(payload.get("method", "POST")), headers=headers, body=body)

    if target == "email":
        host = str(connector_cfg.get("smtp_host", "")).strip()
        port = int(connector_cfg.get("port", 587) or 587)
        sender = str(connector_cfg.get("sender", "")).strip()

        recipients_raw = payload.get("recipients", payload.get("recipients_placeholder", []))
        recipients = [str(r).strip() for r in recipients_raw if str(r).strip()] if isinstance(recipients_raw, list) else []
        if not recipients:
            return False, "missing_recipients"

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = str(payload.get("subject", "DevFabEco notification"))
        msg.set_content(str(payload.get("body_text", "")))

        try:
            with smtplib.SMTP(host=host, port=port, timeout=10) as smtp:
                try:
                    smtp.starttls()
                except Exception:
                    # STARTTLS is optional for local/test SMTP relays.
                    pass
                smtp.send_message(msg)
            return True, "smtp_sent"
        except Exception as exc:
            return False, f"smtp_error={exc}"

    return False, "unsupported_target"


def run_connector_transport(*, project_root: Path, pf: Path, mode_override: str | None = None) -> dict[str, Any]:
    config = load_connector_transport_config(project_root=project_root)
    mode = _normalize_mode(mode_override) if mode_override else _normalize_mode(config.get("mode", "DRY_RUN"))
    dry_run = mode == "DRY_RUN"
    payloads = _load_transport_payloads(pf=pf)

    requests_out: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    acknowledgments: list[dict[str, Any]] = []
    reconciliation_matches: list[dict[str, Any]] = []
    reconciliation_decisions: list[dict[str, Any]] = []
    history_rows = load_acknowledgment_history(project_root=project_root)

    run_timestamp = _iso_now()

    for target in ("github", "jira", "email", "webhook"):
        connector_cfg = config.get(target, {}) if isinstance(config.get(target, {}), dict) else {}
        enabled = _as_bool(connector_cfg.get("enabled", True), default=True)
        items = payloads.get(target, [])

        if not enabled:
            skipped_receipt = {
                "transport_target": target,
                "mode": mode,
                "request_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "skipped_count": 1,
                "timestamp": run_timestamp,
                "request_identifier": f"{target}:connector_disabled",
                "dry_run_boolean": dry_run,
                "response_summary_or_placeholder": "connector_disabled",
            }
            receipts.append(skipped_receipt)
            continue

        live_config_missing = _validate_connector_live_config(target, connector_cfg) if not dry_run else []
        if live_config_missing:
            if not items:
                failed_receipt = {
                    "transport_target": target,
                    "mode": mode,
                    "request_count": 0,
                    "success_count": 0,
                    "failure_count": 1,
                    "skipped_count": 0,
                    "timestamp": run_timestamp,
                    "request_identifier": f"{target}:live_config_missing",
                    "dry_run_boolean": dry_run,
                    "response_summary_or_placeholder": "missing_live_config:" + ",".join(live_config_missing),
                }
                receipts.append(failed_receipt)
            for index, payload in enumerate(items, start=1):
                req_id = _request_identifier(target, index, payload)
                issue_ctx = extract_issue_context(pf=pf, target=target, payload=payload)
                issue_id = str(issue_ctx.get("issue_id", "")).strip()
                rec_key = str(issue_ctx.get("reconciliation_key", "")).strip()
                receipts.append(
                    {
                        "transport_target": target,
                        "mode": mode,
                        "request_count": 1,
                        "success_count": 0,
                        "failure_count": 1,
                        "skipped_count": 0,
                        "timestamp": run_timestamp,
                        "request_identifier": req_id,
                        "dry_run_boolean": dry_run,
                        "response_summary_or_placeholder": "missing_live_config:" + ",".join(live_config_missing),
                    }
                )
                acknowledgments.append(
                    build_acknowledgment_record(
                        delivery_target=target,
                        issue_id=issue_id,
                        connector_name=target,
                        mode=mode,
                        transport_status="FAILED",
                        external_id="",
                        external_url="",
                        request_identifier=req_id,
                        reconciliation_key=rec_key,
                        timestamp=run_timestamp,
                    )
                )
                reconciliation_decisions.append(
                    {
                        "connector_name": target,
                        "issue_id": issue_id,
                        "request_identifier": req_id,
                        "reconciliation_key": rec_key,
                        "decision": "FAIL_MISSING_LIVE_CONFIG",
                    }
                )
            continue

        if not items:
            receipts.append(
                {
                    "transport_target": target,
                    "mode": mode,
                    "request_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "skipped_count": 0,
                    "timestamp": run_timestamp,
                    "request_identifier": f"{target}:no_requests",
                    "dry_run_boolean": dry_run,
                    "response_summary_or_placeholder": "no_requests",
                }
            )
            continue

        for index, payload in enumerate(items, start=1):
            req_id = _request_identifier(target, index, payload)
            issue_ctx = extract_issue_context(pf=pf, target=target, payload=payload)
            issue_id = str(issue_ctx.get("issue_id", "")).strip()
            rec_key = str(issue_ctx.get("reconciliation_key", "")).strip()

            match = None
            if issue_id and rec_key:
                match = find_reconciliation_match(
                    history_rows=history_rows,
                    connector_name=target,
                    reconciliation_key=rec_key,
                )

            requests_out.append(
                {
                    "transport_target": target,
                    "mode": mode,
                    "request_identifier": req_id,
                    "dry_run_boolean": dry_run,
                    "sequence": index,
                }
            )

            if match is not None:
                response = "reconciliation_hit_existing_external_issue"
                receipts.append(
                    {
                        "transport_target": target,
                        "mode": mode,
                        "request_count": 1,
                        "success_count": 0,
                        "failure_count": 0,
                        "skipped_count": 1,
                        "timestamp": run_timestamp,
                        "request_identifier": req_id,
                        "dry_run_boolean": dry_run,
                        "response_summary_or_placeholder": response,
                    }
                )
                reconciliation_matches.append(
                    {
                        "connector_name": target,
                        "issue_id": issue_id,
                        "request_identifier": req_id,
                        "reconciliation_key": rec_key,
                        "matched_external_id": str(match.get("external_id", "")),
                        "matched_external_url": str(match.get("external_url", "")),
                    }
                )
                reconciliation_decisions.append(
                    {
                        "connector_name": target,
                        "issue_id": issue_id,
                        "request_identifier": req_id,
                        "reconciliation_key": rec_key,
                        "decision": "SKIP_RECONCILIATION_HIT",
                    }
                )
                acknowledgments.append(
                    build_acknowledgment_record(
                        delivery_target=target,
                        issue_id=issue_id,
                        connector_name=target,
                        mode=mode,
                        transport_status="RECONCILIATION_HIT",
                        external_id=str(match.get("external_id", "")),
                        external_url=str(match.get("external_url", "")),
                        request_identifier=req_id,
                        reconciliation_key=rec_key,
                        timestamp=run_timestamp,
                    )
                )
                continue

            if dry_run:
                success = True
                response = "dry_run_simulated"
            else:
                success, response = _live_send(target, payload, connector_cfg)

            receipts.append(
                {
                    "transport_target": target,
                    "mode": mode,
                    "request_count": 1,
                    "success_count": 1 if success else 0,
                    "failure_count": 0 if success else 1,
                    "skipped_count": 0,
                    "timestamp": run_timestamp,
                    "request_identifier": req_id,
                    "dry_run_boolean": dry_run,
                    "response_summary_or_placeholder": response,
                }
            )

            transport_status = "SIMULATED" if dry_run else ("DELIVERED" if success else "FAILED")
            external_id = ""
            external_url = ""
            if transport_status == "SIMULATED":
                external_id = "simulated::" + req_id
            elif transport_status == "DELIVERED":
                external_id = "pending::" + req_id

            acknowledgments.append(
                build_acknowledgment_record(
                    delivery_target=target,
                    issue_id=issue_id,
                    connector_name=target,
                    mode=mode,
                    transport_status=transport_status,
                    external_id=external_id,
                    external_url=external_url,
                    request_identifier=req_id,
                    reconciliation_key=rec_key,
                    timestamp=run_timestamp,
                )
            )
            reconciliation_decisions.append(
                {
                    "connector_name": target,
                    "issue_id": issue_id,
                    "request_identifier": req_id,
                    "reconciliation_key": rec_key,
                    "decision": "CREATE_NEW" if success or dry_run else "ATTEMPT_FAILED",
                }
            )

    failures = [
        row
        for row in receipts
        if isinstance(row, dict) and int(row.get("failure_count", 0) or 0) > 0
    ]

    by_target: dict[str, dict[str, int]] = {}
    for target in ("github", "jira", "email", "webhook"):
        by_target[target] = {
            "request_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "skipped_count": 0,
        }
    for row in receipts:
        target = str(row.get("transport_target", "")).strip()
        if target not in by_target:
            continue
        by_target[target]["request_count"] += int(row.get("request_count", 0) or 0)
        by_target[target]["success_count"] += int(row.get("success_count", 0) or 0)
        by_target[target]["failure_count"] += int(row.get("failure_count", 0) or 0)
        by_target[target]["skipped_count"] += int(row.get("skipped_count", 0) or 0)

    total_requests = sum(entry["request_count"] for entry in by_target.values())
    total_success = sum(entry["success_count"] for entry in by_target.values())
    total_failure = sum(entry["failure_count"] for entry in by_target.values())
    total_skipped = sum(entry["skipped_count"] for entry in by_target.values())

    out_dir = pf / "transport"
    _write_json(
        out_dir / "90_transport_requests.json",
        {
            "mode": mode,
            "dry_run_boolean": dry_run,
            "requests": requests_out,
        },
    )
    _write_json(
        out_dir / "91_transport_receipts.json",
        {
            "mode": mode,
            "dry_run_boolean": dry_run,
            "receipts": receipts,
        },
    )
    _write_json(
        out_dir / "92_transport_failures.json",
        {
            "mode": mode,
            "dry_run_boolean": dry_run,
            "failures": failures,
        },
    )

    summary_lines = [
        "# Connector Transport Summary",
        "",
        f"- mode: {mode}",
        f"- dry_run_boolean: {str(dry_run).lower()}",
        f"- total_request_count: {total_requests}",
        f"- total_success_count: {total_success}",
        f"- total_failure_count: {total_failure}",
        f"- total_skipped_count: {total_skipped}",
        "",
        "## Per Target",
    ]
    for target in ("github", "jira", "email", "webhook"):
        row = by_target[target]
        summary_lines.append(
            "- target="
            + target
            + " request_count="
            + str(row["request_count"])
            + " success_count="
            + str(row["success_count"])
            + " failure_count="
            + str(row["failure_count"])
            + " skipped_count="
            + str(row["skipped_count"])
        )

    _write_text(out_dir / "93_transport_summary.md", "\n".join(summary_lines) + "\n")

    reconciliation_artifacts = write_reconciliation_artifacts(
        pf=pf,
        acknowledgments=acknowledgments,
        matches=reconciliation_matches,
        decisions=reconciliation_decisions,
    )
    append_acknowledgments_history(project_root=project_root, acknowledgments=acknowledgments)
    status_sync = run_external_status_sync_and_closure_reconciliation(
        project_root=project_root,
        pf=pf,
        acknowledgments=acknowledgments,
    )
    status_sync_summary = status_sync.get("summary", {}) if isinstance(status_sync.get("summary", {}), dict) else {}
    status_sync_artifacts = status_sync.get("artifacts", []) if isinstance(status_sync.get("artifacts", []), list) else []
    update_policy = run_bidirectional_issue_update_policy(
        project_root=project_root,
        pf=pf,
        mode=mode,
    )
    update_summary = update_policy.get("summary", {}) if isinstance(update_policy.get("summary", {}), dict) else {}
    update_artifacts = update_policy.get("artifacts", []) if isinstance(update_policy.get("artifacts", []), list) else []

    return {
        "summary": {
            "mode": mode,
            "dry_run_boolean": dry_run,
            "total_request_count": total_requests,
            "total_success_count": total_success,
            "total_failure_count": total_failure,
            "total_skipped_count": total_skipped,
            "per_target": by_target,
            "config_found": bool(config.get("config_found", False)),
            "config_path": str(config.get("config_path", "")),
            "acknowledgment_count": len(acknowledgments),
            "reconciliation_match_count": len(reconciliation_matches),
            "external_status_tracked_issue_count": int(status_sync_summary.get("tracked_issue_count", 0) or 0),
            "external_status_mismatch_count": int(status_sync_summary.get("mismatch_count", 0) or 0),
            "update_policy_tracked_issue_count": int(update_summary.get("tracked_issue_count", 0) or 0),
            "update_policy_simulated_update_count": int(update_summary.get("simulated_update_count", 0) or 0),
            "update_policy_live_update_attempt_count": int(update_summary.get("live_update_attempt_count", 0) or 0),
        },
        "artifacts": [
            "transport/90_transport_requests.json",
            "transport/91_transport_receipts.json",
            "transport/92_transport_failures.json",
            "transport/93_transport_summary.md",
            *reconciliation_artifacts,
            *status_sync_artifacts,
            *update_artifacts,
        ],
    }
