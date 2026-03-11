from __future__ import annotations

from enum import StrEnum


class PreflightStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL_CLOSED = "FAIL_CLOSED"


class EvidenceType(StrEnum):
    SOURCE = "source"
    MANIFEST = "manifest"
    FOREIGN_AUTHORED_CONFIG = "foreign_authored_config"
    FOREIGN_GENERATED = "foreign_generated"
    RUNTIME_ARTIFACT = "runtime_artifact"
    CACHE = "cache"
    VENDOR = "vendor"
    SAMPLE = "sample"
    TEST = "test"
    DOCS = "docs"


class TrustClass(StrEnum):
    NATIVE_AUTHORITATIVE = "native_authoritative"
    FIRST_PARTY_AUTHORED = "first_party_authored"
    FIRST_PARTY_SOURCE_REALITY = "first_party_source_reality"
    FOREIGN_AUTHORED_HINT = "foreign_authored_hint"
    FOREIGN_GENERATED_HINT = "foreign_generated_hint"
    RUNTIME_ARTIFACT = "runtime_artifact"
    BLOCKED_STALE_RISK = "blocked_stale_risk"
