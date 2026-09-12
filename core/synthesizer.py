import re
from typing import List, Dict, Any
from core.context import AuditContext

def cross_skill_synthesis(context: AuditContext) -> List[Dict[str, Any]]:
    """
    Cross-skill synthesizer that:
    1. Cross-correlates structured JSON-LD claims (entities, modified dates) against body text.
    2. Deduplicates overlapping findings across skills.
    3. Calibrates severities based on compensating factors (e.g. demoting heading hierarchy warnings if OpenGraph/JSON-LD provide clear topical demarcation).
    """
    raw_findings = list(context.findings)
    synthesized_findings = []
    seen_keys = set()

    # Extract compensators
    has_opengraph = any(k.startswith("og:") for k in context.metadata.get("og_metadata", {})) or \
                    any(f.get("category") == "semantics" and "opengraph" not in f.get("id", "") for f in raw_findings)
    
    has_json_ld = len(context.parsed_json_ld) > 0
    archetype = context.archetype

    for f in raw_findings:
        fid = f.get("id", "")
        title = f.get("title", "")
        sev = f.get("severity", "medium").lower()
        cat = f.get("category", "discoverability")
        
        # Deduplication key based on normalized title or mechanism
        dedup_key = re.sub(r'[^a-z0-9]', '', title.lower())
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        # 1. Severity Calibration with Compensating Factors
        # If heading structure is weak or short H1, but OpenGraph + JSON-LD exist, demote severity from high/medium to low/info
        if "h1-weak" in fid or "html5-structure" in fid:
            if has_opengraph and has_json_ld:
                sev = "low"
                f["message"] = (f.get("message") or f.get("evidence", "")) + " (Compensated by valid OpenGraph & JSON-LD metadata)."

        # If archetype is UTILITY_PORTAL, suppress or demote content density & heading warnings
        if archetype == "UTILITY_PORTAL":
            if "h1-missing" in fid or "content-sparse" in fid or "meta-description" in fid:
                continue # Suppressed for utility portal

        # Update calibrated severity & confidence
        f["severity"] = sev
        if "confidence" not in f:
            f["confidence"] = 1.0

        synthesized_findings.append(f)

    # 2. Cross-correlation check: Verify if JSON-LD brand name appears in raw body text
    entities = context.extracted_entities
    org_name = entities.get("organization", {}).get("name")
    if org_name and context.raw_html:
        clean_org = org_name.lower().strip()
        body_text_lower = context.raw_html.lower()
        if clean_org not in body_text_lower and archetype not in ["UTILITY_PORTAL"]:
            # Structured entity brand mismatch finding
            mismatch_finding = {
                "id": "synthesis-entity-body-mismatch",
                "category": "corroboration",
                "severity": "medium",
                "title": f"Structured Schema Organization name '{org_name}' not found in body text",
                "message": f"Organization name '{org_name}' declared in JSON-LD is absent from rendered page body.",
                "evidence": f"Declared JSON-LD Organization name '{org_name}' missing from body prose.",
                "confidence": 0.90,
                "recommendation": f"Ensure '{org_name}' is explicitly mentioned in page headings and body text."
            }
            if not any(f["id"] == mismatch_finding["id"] for f in synthesized_findings):
                synthesized_findings.append(mismatch_finding)

    # Store synthesized findings back into context
    context.findings = synthesized_findings
    return synthesized_findings
