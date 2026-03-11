from __future__ import annotations

from ngksgraph.core.enums import EvidenceType, TrustClass


def trust_for_evidence(evidence_type: EvidenceType, ownership: str) -> TrustClass:
    if evidence_type == EvidenceType.MANIFEST:
        return TrustClass.FIRST_PARTY_AUTHORED
    if evidence_type == EvidenceType.SOURCE:
        return TrustClass.FIRST_PARTY_SOURCE_REALITY
    if evidence_type == EvidenceType.FOREIGN_AUTHORED_CONFIG:
        return TrustClass.FOREIGN_AUTHORED_HINT
    if evidence_type == EvidenceType.FOREIGN_GENERATED:
        return TrustClass.FOREIGN_GENERATED_HINT
    if evidence_type in {EvidenceType.CACHE, EvidenceType.VENDOR}:
        return TrustClass.BLOCKED_STALE_RISK
    if ownership == "third_party":
        return TrustClass.BLOCKED_STALE_RISK
    return TrustClass.RUNTIME_ARTIFACT
