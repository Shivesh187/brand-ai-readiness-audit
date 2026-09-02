import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

SEVERITY_LEVELS = ["critical", "high", "medium", "low"]

class EvidenceStatus:
    LIVE_OBSERVED = "LIVE_OBSERVED"
    AI_VALIDATED = "AI_VALIDATED"
    INFERRED = "INFERRED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    # Backwards compatibility aliases
    OBSERVED = "LIVE_OBSERVED"
    CORROBORATED = "LIVE_OBSERVED"
    CONTRADICTED = "INFERRED"
    UNKNOWN = "UNAVAILABLE"

@dataclass
class Evidence:
    id: str
    url: str
    page_context: str
    observation: str
    status: str = EvidenceStatus.LIVE_OBSERVED
    source_type: str = "raw_html"  # raw_html, headers, api, dom, metadata
    exact_value: Optional[Any] = None
    source_skill: str = "orchestrator"
    confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "page_context": self.page_context,
            "observation": self.observation,
            "status": self.status,
            "source_type": self.source_type,
            "exact_value": self.exact_value,
            "source_skill": self.source_skill,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }

@dataclass
class SuggestedAction:
    summary: str
    how: str = ""
    priority: str = "medium"
    recommendation: Optional[str] = None
    effort: str = "Low"  # Low, Medium, High
    impact: str = "High" # Critical, High, Medium, Low

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "summary": self.summary,
            "how": self.how or self.recommendation or "Implement recommended HTML tags or server configuration.",
            "priority": self.priority,
            "effort": self.effort,
            "impact": self.impact
        }
        if self.recommendation:
            d["recommendation"] = self.recommendation
        return d

@dataclass
class Finding:
    id: str
    title: str
    severity: str  # "critical", "high", "medium", "low"
    category: str  # "discoverability", "semantics", "corroboration", "engagement"
    evidence: str
    suggested_action: SuggestedAction
    confidence: float = 1.0
    priority: str = "P2"  # "P0", "P1", "P2", "P3"
    why_it_matters: Optional[str] = None
    mechanism_impact: Optional[str] = None
    source_skill: Optional[str] = None
    affected_urls: List[str] = field(default_factory=list)
    deduplication_key: Optional[str] = None
    evidence_records: List[Dict[str, Any]] = field(default_factory=list)
    evidence_details: Optional[Dict[str, Any]] = None
    reasoning_source: str = "deterministic"
    evidence_origin: str = EvidenceStatus.LIVE_OBSERVED  # LIVE_OBSERVED, AI_VALIDATED, INFERRED, UNAVAILABLE, NOT_APPLICABLE
    provenance: List[str] = field(default_factory=list)
    why_we_know_this: Optional[str] = None
    primary_dimension: str = "ai_discoverability"  # "ai_discoverability", "onsite_engagement", "technical_health"
    mechanism: Optional[str] = None  # Controlled taxonomy (e.g. CRAWLER_ACCESS, VALUE_PROPOSITION, SSL)
    finding_type: str = "ISSUE"  # BLOCKER, ISSUE, GROWTH_OPPORTUNITY, TECHNICAL_NOTICE
    business_impact: str = "medium"  # "critical", "high", "medium", "low"
    impact_score: int = 50

    def __post_init__(self):
        self.severity = self.severity.lower()
        if self.severity not in SEVERITY_LEVELS:
            self.severity = "medium"
        if self.severity == "critical":
            self.priority = "P0"
        elif self.severity == "high":
            self.priority = "P1"
        elif self.severity == "medium":
            self.priority = "P2"
        else:
            self.priority = "P3"

        id_lower = self.id.lower()
        title_lower = self.title.lower()

        # Controlled Mechanism & Dimension Default Assignment
        if any(k in id_lower or k in title_lower for k in ["ssl", "latency", "redirect", "http-connection", "sitemap"]):
            self.primary_dimension = "technical_health"
            self.business_impact = "low" if any(k in id_lower for k in ["expiring", "latency", "sitemap-missing", "sitemap-absent"]) else "medium"
            if not self.mechanism:
                if "ssl" in id_lower: self.mechanism = "SSL"
                elif "latency" in id_lower: self.mechanism = "LATENCY"
                elif "redirect" in id_lower: self.mechanism = "REDIRECTS"
                elif "sitemap" in id_lower: self.mechanism = "SITEMAP_INFRASTRUCTURE"
                else: self.mechanism = "HTTP_HEALTH"
            if self.finding_type == "ISSUE":
                self.finding_type = "TECHNICAL_NOTICE"

        elif self.category == "engagement" or any(k in id_lower or k in title_lower for k in ["cta", "value-prop", "word-count", "heading-content", "meta-desc"]):
            self.primary_dimension = "onsite_engagement"
            self.business_impact = "high" if any(k in id_lower for k in ["value-prop", "h1-missing", "cta-missing"]) else "medium"
            if not self.mechanism:
                if "h1" in id_lower or "value-prop" in id_lower: self.mechanism = "VALUE_PROPOSITION"
                elif "cta" in id_lower: self.mechanism = "CTA_CLARITY"
                elif "meta" in id_lower: self.mechanism = "AI_REFERRAL_CONTEXT"
                else: self.mechanism = "CONTENT_HIERARCHY"
            if self.severity in ["critical", "high"] and any(k in id_lower for k in ["h1-missing", "cta-missing"]):
                self.finding_type = "BLOCKER"

        else:
            self.primary_dimension = "ai_discoverability"
            self.business_impact = "critical" if self.severity == "critical" else ("high" if self.severity == "high" else "medium")
            if not self.mechanism:
                if "robots" in id_lower or "crawler" in id_lower: self.mechanism = "CRAWLER_ACCESS"
                elif "schema" in id_lower or "jsonld" in id_lower: self.mechanism = "SEMANTIC_UNDERSTANDING"
                elif "corroboration" in id_lower or "sameas" in id_lower: self.mechanism = "ENTITY_RESOLUTION"
                else: self.mechanism = "CONTENT_EXTRACTION"
            if self.severity in ["critical", "high"] and "robots-ai-blocked" in id_lower:
                self.finding_type = "BLOCKER"

        if not self.why_it_matters:
            self.why_it_matters = self.mechanism_impact or "Impacts AI discovery and RAG vector indexing."
        if not self.why_we_know_this:
            self.why_we_know_this = f"Directly observed via {self.source_skill or 'telemetry'} inspection during live site audit."
        if not self.deduplication_key:
            self.deduplication_key = re.sub(r'[^a-z0-9]', '', self.title.lower())
        if not self.provenance:
            self.provenance = ["homepage HTML", self.source_skill or "audit-engine"]

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "priority": self.priority,
            "category": self.category,
            "primary_dimension": self.primary_dimension,
            "mechanism": self.mechanism,
            "finding_type": self.finding_type,
            "business_impact": self.business_impact,
            "impact_score": self.impact_score,
            "evidence": self.evidence,
            "why_it_matters": self.why_it_matters,
            "suggested_action": self.suggested_action.to_dict() if isinstance(self.suggested_action, SuggestedAction) else self.suggested_action,
            "confidence": self.confidence,
            "reasoning_source": self.reasoning_source,
            "evidence_origin": self.evidence_origin,
            "provenance": self.provenance,
            "why_we_know_this": self.why_we_know_this
        }
        if self.mechanism_impact:
            res["mechanism_impact"] = self.mechanism_impact
        if self.source_skill:
            res["source_skill"] = self.source_skill
        if self.affected_urls:
            res["affected_urls"] = self.affected_urls
        if self.evidence_details:
            res["evidence_details"] = self.evidence_details
        if self.evidence_records:
            res["evidence_records"] = self.evidence_records
        return res

@dataclass
class AuditState:
    target_url: str
    normalized_domain: str
    brand: str
    claims: Dict[str, Any] = field(default_factory=dict)

    # State Storage Buckets
    crawl_metadata: Dict[str, Any] = field(default_factory=dict)
    http_responses: Dict[str, Any] = field(default_factory=dict)
    raw_html: Dict[str, str] = field(default_factory=dict)
    extracted_content: Dict[str, Any] = field(default_factory=dict)
    structured_data: Dict[str, Any] = field(default_factory=dict)
    rendering_metadata: Dict[str, Any] = field(default_factory=dict)

    entity_observations: Dict[str, Any] = field(default_factory=dict)
    corroboration_observations: Dict[str, Any] = field(default_factory=dict)
    engagement_observations: Dict[str, Any] = field(default_factory=dict)
    llm_observations: Dict[str, Any] = field(default_factory=dict)
    collection: Dict[str, Any] = field(default_factory=dict)

    evidence_records: List[Evidence] = field(default_factory=list)
    candidate_findings: List[Finding] = field(default_factory=list)
    validated_findings: List[Finding] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timing: Dict[str, float] = field(default_factory=dict)

    def add_evidence(self,
                     url: str,
                     page_context: str,
                     observation: str,
                     status: str = EvidenceStatus.LIVE_OBSERVED,
                     source_type: str = "raw_html",
                     exact_value: Any = None,
                     source_skill: str = "orchestrator",
                     confidence: float = 1.0) -> Evidence:
        ev_id = f"EV-{len(self.evidence_records)+1:03d}"
        ev = Evidence(
            id=ev_id,
            url=url,
            page_context=page_context,
            observation=observation,
            status=status,
            source_type=source_type,
            exact_value=exact_value,
            source_skill=source_skill,
            confidence=confidence
        )
        self.evidence_records.append(ev)
        return ev

    def add_finding(self, finding: Finding) -> Finding:
        self.candidate_findings.append(finding)
        return finding

    def validate_and_deduplicate_findings(self) -> List[Finding]:
        key_map = {}
        for f in self.candidate_findings:
            key = f.deduplication_key or f.title.lower()
            if key not in key_map or f.confidence > key_map[key].confidence:
                key_map[key] = f

        deduped = []
        counter = 1
        for f in key_map.values():
            f.id = f"F-{counter:03d}"
            counter += 1
            deduped.append(f)

        self.validated_findings = deduped
        return self.validated_findings

@dataclass
class AuditReport:
    site: str
    brand: str
    audited_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    readiness_score: int = 100
    ai_discoverability_score: int = 100
    onsite_engagement_score: int = 100
    technical_health_score: int = 100
    audit_confidence: int = 100
    executive_summary: str = ""
    score_drivers: Dict[str, List[str]] = field(default_factory=lambda: {"positive": [], "negative": []})
    summary: Dict[str, int] = field(default_factory=lambda: {"total_findings": 0, "critical": 0, "high": 0, "medium": 0, "low": 0})
    module_breakdowns: Dict[str, Any] = field(default_factory=dict)
    rendering_metadata: Dict[str, Any] = field(default_factory=dict)
    llm_observations: Dict[str, Any] = field(default_factory=dict)
    collection: Dict[str, Any] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    top_blockers: List[Dict[str, Any]] = field(default_factory=list)
    remediation_roadmap: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    transparency_notice: Dict[str, Any] = field(default_factory=dict)

    def compute_scores_and_summary(self):
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        module_counts: Dict[str, Dict[str, int]] = {
            "discoverability": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total_checks": 4, "observed_checks": 4, "unavailable_checks": 0},
            "semantics": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total_checks": 4, "observed_checks": 4, "unavailable_checks": 0},
            "corroboration": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total_checks": 3, "observed_checks": 3, "unavailable_checks": 0},
            "engagement": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total_checks": 3, "observed_checks": 3, "unavailable_checks": 0}
        }

        penalized_findings = []
        dim_penalties = {
            "ai_discoverability": 0.0,
            "onsite_engagement": 0.0,
            "technical_health": 0.0
        }
        mod_penalties = {
            "discoverability": 0.0,
            "semantics": 0.0,
            "corroboration": 0.0,
            "engagement": 0.0
        }

        pos_drivers = []
        neg_drivers = []

        col = self.collection or {}
        if col.get("http_fetch_success"):
            pos_drivers.append("Live server HTTP response verified")
        if col.get("sitemap_status") == "VERIFIED_PRESENT":
            pos_drivers.append("Sitemap verified present and discoverable")
        if col.get("entity_corroboration_status") in ["VERIFIED", "SUCCESS"]:
            pos_drivers.append("Brand entity grounded via external knowledge graph")

        for f in self.findings:
            if f.evidence_origin in [EvidenceStatus.UNAVAILABLE, EvidenceStatus.NOT_APPLICABLE]:
                continue

            penalized_findings.append(f)
            sev = f.severity if f.severity in SEVERITY_LEVELS else "medium"
            conf = f.confidence if isinstance(f.confidence, (int, float)) else 1.0

            counts[sev] += 1
            cat = f.category if f.category in module_counts else "discoverability"
            module_counts[cat][sev] += 1

            base_p = 20.0 if sev == "critical" else (10.0 if sev == "high" else (5.0 if sev == "medium" else 2.0))
            mod_base_p = 25.0 if sev == "critical" else (12.0 if sev == "high" else (5.0 if sev == "medium" else 2.0))

            dim = f.primary_dimension if f.primary_dimension in dim_penalties else "ai_discoverability"
            dim_penalties[dim] += (base_p * conf)
            mod_penalties[cat] += (mod_base_p * conf)

            if sev in ["critical", "high"]:
                neg_drivers.append(f"{f.title} ({f.mechanism or 'General'})")

        if not neg_drivers:
            pos_drivers.append("No critical or high discoverability defects detected")

        self.score_drivers = {
            "positive": pos_drivers[:4],
            "negative": neg_drivers[:4]
        }

        self.summary = {
            "total_findings": len(self.findings),
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"]
        }

        self.ai_discoverability_score = max(0, min(100, int(round(100.0 - dim_penalties["ai_discoverability"]))))
        self.onsite_engagement_score = max(0, min(100, int(round(100.0 - dim_penalties["onsite_engagement"]))))
        self.technical_health_score = max(0, min(100, int(round(100.0 - dim_penalties["technical_health"]))))

        weighted_val = (self.ai_discoverability_score * 0.60) + (self.onsite_engagement_score * 0.30) + (self.technical_health_score * 0.10)
        self.readiness_score = max(0, min(100, int(round(weighted_val))))

        if self.readiness_score >= 85:
            self.executive_summary = f"Brand '{self.brand}' demonstrates excellent AI Discoverability ({self.ai_discoverability_score}/100) and strong On-Site Engagement ({self.onsite_engagement_score}/100) for Generative Engines."
        elif self.ai_discoverability_score < 70:
            self.executive_summary = f"Infrastructure is accessible ({self.technical_health_score}/100), but brand '{self.brand}' has significant AI Discoverability gaps ({self.ai_discoverability_score}/100) preventing AI engines from reliably finding and grounding brand identity."
        elif self.onsite_engagement_score < 70:
            self.executive_summary = f"Brand '{self.brand}' is discoverable by AI engines ({self.ai_discoverability_score}/100), but has notable On-Site Engagement gaps ({self.onsite_engagement_score}/100) that reduce visitor conversion and value proposition clarity."
        else:
            self.executive_summary = f"Brand '{self.brand}' has a balanced AI Readiness profile ({self.readiness_score}/100) with minor optimization opportunities across discoverability and engagement."

        total_checks = 14
        observed_checks = 14
        unavailable_checks = 0

        if col.get("http_fetch_success") is False:
            observed_checks -= 2
            unavailable_checks += 2
        if col.get("sitemap_status") == "TIMEOUT" or col.get("sitemap_status") == "UNAVAILABLE":
            observed_checks -= 1
            unavailable_checks += 1
        if col.get("playwright_status") == "TIMEOUT" or col.get("playwright_status") == "FAILED":
            observed_checks -= 1
            unavailable_checks += 1
        if col.get("entity_corroboration_status") == "UNAVAILABLE":
            observed_checks -= 1
            unavailable_checks += 1

        self.audit_confidence = max(50, min(100, int(round((observed_checks / total_checks) * 100))))

        for mod, mod_c in module_counts.items():
            mod_score = max(0, min(100, int(round(100.0 - mod_penalties[mod]))))
            self.module_breakdowns[mod] = {
                "score": mod_score,
                "total_checks": mod_c["total_checks"],
                "observed_checks": mod_c["observed_checks"],
                "unavailable_checks": mod_c["unavailable_checks"],
                "critical": mod_c["critical"],
                "high": mod_c["high"],
                "medium": mod_c["medium"],
                "low": mod_c["low"],
                "explanation": f"Score {mod_score}/100 based on observed technical signals and RAG indexing readiness."
            }

        # Multi-Factor Refined Prioritization Formula
        def calculate_blocker_score(f: Finding) -> float:
            sev_scores = {"critical": 100.0, "high": 75.0, "medium": 45.0, "low": 20.0}
            sev_base = sev_scores.get(f.severity.lower(), 45.0)
            
            type_mult = 1.2 if f.finding_type == "BLOCKER" else (1.0 if f.finding_type == "ISSUE" else (0.8 if f.finding_type == "GROWTH_OPPORTUNITY" else 0.5))

            biz_scores = {"critical": 100.0, "high": 75.0, "medium": 50.0, "low": 25.0}
            biz_score = biz_scores.get(getattr(f, "business_impact", "medium").lower(), 50.0)

            dim_scores = {"ai_discoverability": 100.0, "onsite_engagement": 85.0, "technical_health": 30.0}
            dim_score = dim_scores.get(getattr(f, "primary_dimension", "ai_discoverability").lower(), 100.0)

            conf = (f.confidence if isinstance(f.confidence, (int, float)) else 1.0)
            
            id_title_lower = (f.id + " " + f.title).lower()
            is_minor_infra = any(k in id_title_lower for k in ["ssl-expiring", "sitemap-missing", "sitemap-absent", "http-latency"]) and getattr(f, "primary_dimension", "") == "technical_health"

            score = (dim_score * 0.30) + (biz_score * 0.35) + (sev_base * type_mult * 0.25) + (conf * 100.0 * 0.10)

            # Minor infrastructure items (SSL expiry warning, sitemap missing alone) are capped at 55.0 so they never block major AI issues
            if is_minor_infra:
                score = min(score, 55.0)

            return score

        sorted_blockers = sorted(
            [f for f in self.findings if f.evidence_origin not in [EvidenceStatus.UNAVAILABLE, EvidenceStatus.NOT_APPLICABLE]],
            key=lambda x: calculate_blocker_score(x),
            reverse=True
        )
        self.top_blockers = [
            {
                "id": b.id,
                "title": b.title,
                "severity": b.severity,
                "priority": b.priority,
                "primary_dimension": b.primary_dimension,
                "mechanism": b.mechanism,
                "finding_type": b.finding_type,
                "business_impact": b.business_impact,
                "confidence": b.confidence,
                "issue": b.evidence,
                "why_it_matters": b.why_it_matters,
                "suggested_action": b.suggested_action.to_dict() if isinstance(b.suggested_action, SuggestedAction) else b.suggested_action
            }
            for b in sorted_blockers[:5]
        ]

        roadmap_today = []
        roadmap_week = []
        roadmap_month = []

        for f in self.findings:
            action_dict = f.suggested_action.to_dict() if isinstance(f.suggested_action, SuggestedAction) else f.suggested_action
            item = {
                "id": f.id,
                "title": f.title,
                "priority": f.priority,
                "severity": f.severity,
                "category": f.category,
                "primary_dimension": f.primary_dimension,
                "mechanism": f.mechanism,
                "finding_type": f.finding_type,
                "business_impact": f.business_impact,
                "issue": f.evidence,
                "why_it_matters": f.why_it_matters,
                "summary": action_dict.get("summary", ""),
                "how": action_dict.get("how", ""),
                "effort": action_dict.get("effort", "Medium"),
                "impact": action_dict.get("impact", "High"),
                "affected_urls": f.affected_urls
            }

            if f.primary_dimension in ["ai_discoverability", "onsite_engagement"] and (f.severity in ["critical", "high"] or f.priority in ["P0", "P1"]):
                roadmap_today.append(item)
            elif f.severity in ["critical", "high"] or f.priority in ["P0", "P1"]:
                roadmap_week.append(item)
            else:
                roadmap_month.append(item)

        self.remediation_roadmap = {
            "TODAY": roadmap_today,
            "THIS_WEEK": roadmap_week,
            "THIS_MONTH": roadmap_month
        }

        self.transparency_notice = {
            "disclaimer": "This audit evaluates observable technical signals influencing Generative Engine Discoverability & RAG retrieval. It does not claim to directly reproduce proprietary closed-source AI ranking algorithms.",
            "observed_signals": 14 - unavailable_checks,
            "unavailable_signals": unavailable_checks,
            "audit_confidence": self.audit_confidence,
            "ai_reasoning_mode": self.llm_observations.get("status", "DETERMINISTIC")
        }

    def to_dict(self) -> Dict[str, Any]:
        self.compute_scores_and_summary()
        res = {
            "site": self.site,
            "brand": self.brand,
            "audited_at": self.audited_at,
            "readiness_score": self.readiness_score,
            "ai_discoverability_score": self.ai_discoverability_score,
            "onsite_engagement_score": self.onsite_engagement_score,
            "technical_health_score": self.technical_health_score,
            "audit_confidence": self.audit_confidence,
            "executive_summary": self.executive_summary,
            "score_drivers": self.score_drivers,
            "scores": {
                "overall": self.readiness_score,
                "ai_discoverability": self.ai_discoverability_score,
                "onsite_engagement": self.onsite_engagement_score,
                "technical_health": self.technical_health_score
            },
            "summary": self.summary,
            "module_breakdowns": self.module_breakdowns,
            "top_blockers": self.top_blockers,
            "remediation_roadmap": self.remediation_roadmap,
            "transparency_notice": self.transparency_notice,
            "findings": [f.to_dict() for f in self.findings]
        }
        if self.collection:
            res["collection"] = self.collection
        if self.rendering_metadata:
            res["rendering_metadata"] = self.rendering_metadata
        if self.llm_observations:
            res["llm_observations"] = self.llm_observations
        return res
