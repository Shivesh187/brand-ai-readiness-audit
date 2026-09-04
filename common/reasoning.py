import sys
import os
import re
from typing import Dict, Any, List, Optional, Tuple

from common.models import Finding, SuggestedAction, AuditState, EvidenceStatus

class DeterministicReasoningEngine:
    """
    Deterministic Reasoning Framework for Brand AI Readiness Audit.
    Evaluates evidence-backed observations, calculates calibrated confidence, enforces mechanism-based
    priority & severity safety rules, and generates non-generic technical recommendations.
    """

    @staticmethod
    def calculate_priority(severity: str, confidence: float) -> str:
        sev = severity.lower()
        if sev == "critical":
            return "P0" if confidence >= 0.70 else "P2"
        elif sev == "high":
            return "P1" if confidence >= 0.50 else "P2"
        elif sev == "medium":
            return "P2"
        else:
            return "P3"

    @staticmethod
    def apply_false_positive_rules(finding: Finding, state: AuditState) -> Tuple[Finding, str]:
        """
        Cross-validates candidate findings against multi-skill evidence to eliminate false positives.
        Returns: (updated_finding, status) where status is 'VALID', 'QUESTIONABLE', or 'REJECT'
        """
        domain = state.normalized_domain
        fid = finding.id.lower()
        title_lower = finding.title.lower()
        rendering_meta = state.rendering_metadata.get("comparison", {})

        # Rule 1: Raw H1 Missing vs Rendered DOM H1
        if "h1" in fid or "heading" in title_lower or "h1" in title_lower:
            if rendering_meta.get("h1_revealed_via_js"):
                finding.severity = "low"
                finding.confidence = 0.50
                finding.priority = "P3"
                finding.title = f"H1 heading tag requires JavaScript client-side rendering on {domain}"
                finding.evidence += " [Cross-Validation: H1 heading tag is instantiated dynamically post-JS hydration.]"
                finding.why_it_matters = "Non-JS crawlers and static RAG parsers may fail to extract the primary document title if H1 is client-side rendered."
                finding.mechanism_impact = "Client-side H1 rendering creates latency dependencies for static HTML vector chunkers."
                finding.suggested_action.summary = f"Pre-render the primary <h1> hero heading in server-rendered HTML for {domain}."
                finding.suggested_action.priority = "low"
                return finding, "QUESTIONABLE"

        # Rule 2: Raw Links vs Rendered DOM Links
        if "link" in fid or "navigation" in title_lower or "link" in title_lower:
            new_links = rendering_meta.get("new_links_count", 0)
            if new_links > 5:
                finding.severity = "medium"
                finding.confidence = 0.75
                finding.priority = "P2"
                finding.why_it_matters = f"Discovered {new_links} critical navigation links only after client-side JavaScript execution."
                finding.mechanism_impact = "Static AI spiders cannot discover client-side rendered subpages without crawling rendered DOM trees."
                finding.suggested_action.summary = f"Expose primary navigation links in server-rendered HTML tags on {domain}."
                return finding, "VALID"

        # Rule 3: Organization Schema vs Wikidata/Wikipedia Entity Resolution
        if "organization" in fid or "schema" in fid or "org" in fid or "organization" in title_lower or "schema" in title_lower:
            wiki_entity = state.entity_observations.get("wikidata_entity") or state.corroboration_observations.get("wikidata_entity")
            qid = wiki_entity.get("id") if wiki_entity else None
            qid_str = f" pointing to https://www.wikidata.org/wiki/{qid}" if qid else ""
            same_as = [f"https://www.wikidata.org/wiki/{qid}"] if qid else []
            import json
            dynamic_jsonld = json.dumps({
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": state.brand,
                "url": f"https://{domain}",
                "sameAs": same_as
            }, indent=2)
            finding.confidence = 0.85
            finding.why_it_matters = f"Brand '{state.brand}' lacks explicit Schema.org Organization markup on target homepage."
            finding.mechanism_impact = "Missing Organization JSON-LD prevents AI search engines from mapping local domain URLs directly to universal knowledge graph entity IDs."
            finding.suggested_action.summary = f"Inject Organization JSON-LD script containing sameAs link{qid_str} for '{state.brand}' on {domain}."
            finding.suggested_action.recommendation = f'<script type="application/ld+json">\n{dynamic_jsonld}\n</script>'
            return finding, "VALID"

        # Default: Valid direct observation
        return finding, "VALID"

    @classmethod
    def enrich_and_validate_findings(cls, state: AuditState) -> List[Finding]:
        """
        Enriches candidate findings with non-generic technical recommendations, mechanism impacts,
        and enforces Python safety guardrails and false positive control.
        """
        raw_candidates = state.candidate_findings
        validated_findings = []

        for candidate in raw_candidates:
            # 1. False Positive Cross-Validation
            finding, decision = cls.apply_false_positive_rules(candidate, state)

            if decision == "REJECT":
                continue

            # 2. Python Safety & Severity Guardrails
            if finding.confidence < 0.40 and finding.severity in ["critical", "high"]:
                finding.severity = "medium"

            if finding.confidence < 0.60 and finding.severity == "critical":
                finding.severity = "high"

            # 3. Priority Derivation
            finding.priority = cls.calculate_priority(finding.severity, finding.confidence)
            finding.reasoning_source = "deterministic"

            # 4. Ensure Non-Generic Recommended Action & Why It Matters
            if not finding.why_it_matters or finding.why_it_matters.startswith("Impacts AI"):
                finding.why_it_matters = (
                    f"Directly impacts how Generative Search engines (SearchGPT, Perplexity, Google SGE) "
                    f"index and corroborate {state.brand}'s primary domain ({state.normalized_domain})."
                )

            validated_findings.append(finding)

        state.candidate_findings = validated_findings
        return state.validate_and_deduplicate_findings()
