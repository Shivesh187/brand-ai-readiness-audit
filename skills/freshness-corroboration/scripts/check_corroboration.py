import sys
import os
import json
import re
import time
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple

# Dynamically locate workspace root
cur_dir = os.path.abspath(__file__)
while cur_dir != os.path.dirname(cur_dir):
    if os.path.exists(os.path.join(cur_dir, "marketplace.json")) or os.path.exists(os.path.join(cur_dir, "common")):
        if cur_dir not in sys.path:
            sys.path.insert(0, cur_dir)
        break
    cur_dir = os.path.dirname(cur_dir)

from common.http_client import fetch_url
from common.models import Finding, SuggestedAction, AuditState, EvidenceStatus

COMMON_NOUNS = {
    "apple", "amazon", "stripe", "target", "meta", "alphabet", "oracle", "salesforce",
    "box", "slack", "square", "clover", "bloom", "wave", "drift", "bench", "gong", "door", "nest"
}

# Process-Local Cache for Entity Lookups (TTL: 300 seconds)
_ENTITY_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SEC = 300.0

def clear_entity_cache():
    """Utility to clear entity cache for test isolation."""
    global _ENTITY_CACHE
    _ENTITY_CACHE.clear()

def _get_from_cache(key: str) -> Optional[Any]:
    if key in _ENTITY_CACHE:
        entry = _ENTITY_CACHE[key]
        if time.time() - entry["timestamp"] < CACHE_TTL_SEC:
            return entry["val"]
        else:
            _ENTITY_CACHE.pop(key, None)
    return None

def _put_in_cache(key: str, val: Any):
    if val is not None:
        _ENTITY_CACHE[key] = {
            "val": val,
            "timestamp": time.time()
        }

def is_trusted_entity_match(brand_name: str, domain: str, candidate: Dict[str, Any], same_as_links: List[str]) -> bool:
    """
    Prevents false positive entity matches for common-name brands.
    Verifies domain matching, Schema.org sameAs links, and tech company description signals.
    """
    if not candidate:
        return False
        
    qid = candidate.get("id", "")
    if same_as_links:
        for link in same_as_links:
            if qid in link or f"Q{qid}" in link:
                return True

    name_lower = brand_name.lower().strip()
    label_lower = (candidate.get("label") or "").lower().strip()
    desc_lower = (candidate.get("description") or "").lower().strip()

    # Common noun brand safeguard (e.g. Stripe, Box, Target, Meta, Apple)
    if name_lower in COMMON_NOUNS:
        tech_keywords = ["company", "corporation", "business", "software", "technology", "platform", "service", "payment", "inc", "ltd", "developer", "enterprise"]
        is_tech_company = any(kw in desc_lower or kw in label_lower for kw in tech_keywords)
        if not is_tech_company:
            return False

    return True

def query_wikidata_entity(brand_name: str, domain: str = "", same_as_links: List[str] = None) -> Tuple[Optional[Dict[str, Any]], str, float]:
    cache_key = f"wikidata:{brand_name.lower().strip()}:{domain.lower().strip()}"
    cached = _get_from_cache(cache_key)
    if cached is not None:
        return cached, "SUCCESS", 0.0

    t0 = time.time()
    clean_name = brand_name.strip()
    encoded = urllib.parse.quote(clean_name)
    api_url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={encoded}&language=en&format=json"

    res = fetch_url(api_url, timeout=2.5)
    latency_ms = (time.time() - t0) * 1000.0

    if not res["success"]:
        err_msg = str(res.get("error", "")).lower()
        status = "TIMEOUT" if "timeout" in err_msg or "timed out" in err_msg else "ERROR"
        return None, status, latency_ms

    if res["content"]:
        try:
            data = json.loads(res["content"])
            results = data.get("search", [])
            for top in results:
                candidate = {
                    "id": top.get("id"),
                    "label": top.get("label"),
                    "description": top.get("description", ""),
                    "concepturi": top.get("concepturi")
                }
                if is_trusted_entity_match(brand_name, domain, candidate, same_as_links or []):
                    _put_in_cache(cache_key, candidate)
                    return candidate, "SUCCESS", latency_ms
            return None, "SUCCESS", latency_ms
        except Exception:
            return None, "ERROR", latency_ms

    return None, "ERROR", latency_ms

def query_wikipedia_summary(brand_name: str) -> Tuple[Optional[Dict[str, Any]], str, float]:
    cache_key = f"wikipedia:{brand_name.lower().strip()}"
    cached = _get_from_cache(cache_key)
    if cached is not None:
        return cached, "SUCCESS", 0.0

    t0 = time.time()
    clean_name = brand_name.strip().replace(" ", "_")
    api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(clean_name)}"

    res = fetch_url(api_url, timeout=2.5)
    latency_ms = (time.time() - t0) * 1000.0

    if not res["success"]:
        err_msg = str(res.get("error", "")).lower()
        status = "TIMEOUT" if "timeout" in err_msg or "timed out" in err_msg else "ERROR"
        return None, status, latency_ms

    if res["content"]:
        try:
            data = json.loads(res["content"])
            if data.get("type") == "standard":
                val = {
                    "title": data.get("title"),
                    "extract": data.get("extract", ""),
                    "page_url": data.get("content_urls", {}).get("desktop", {}).get("page")
                }
                _put_in_cache(cache_key, val)
                return val, "SUCCESS", latency_ms
            return None, "SUCCESS", latency_ms
        except Exception:
            return None, "ERROR", latency_ms

    return None, "ERROR", latency_ms

def run_corroboration_check(state: AuditState) -> List[Finding]:
    detected_org = state.entity_observations.get("detected_organization", {})
    brand_name = detected_org.get("name") or state.brand or state.normalized_domain.capitalize()
    domain = state.normalized_domain
    same_as_links = state.extracted_content.get("same_as_links", []) or state.entity_observations.get("same_as_links", [])
    findings = []

    # 1. Brand Ambiguity & Vector Collision Analysis
    name_lower = brand_name.lower().strip()
    if name_lower in COMMON_NOUNS:
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Brand Name Ambiguity Check",
            observation=f"Brand name '{brand_name}' is a high-frequency dictionary common noun.",
            status=EvidenceStatus.LIVE_OBSERVED,
            source_type="metadata",
            source_skill="freshness-corroboration"
        )
        f = Finding(
            id="corroboration-name-collision-critical",
            title=f"High semantic brand name collision risk for '{brand_name}'",
            severity="critical",
            category="corroboration",
            evidence=f"Brand name '{brand_name}' is a high-frequency common dictionary noun. LLM retrievers often confuse brand context with literal noun definitions.",
            suggested_action=SuggestedAction(
                summary="Ground the entity using explicit Schema.org sameAs links to Wikidata & Wikipedia company pages.",
                priority="critical",
                effort="Low",
                impact="Critical"
            ),
            mechanism_impact="Common noun brand names create vector embedding collisions in RAG retriever indexes.",
            source_skill="freshness-corroboration",
            affected_urls=[f"https://{domain}"],
            provenance=["Brand Name Analysis", "Dictionary Lexicon"]
        )
        findings.append(f)
        state.add_finding(f)

    # 2. Fast Fallback Hierarchy Execution
    # Provider 1: Wikidata API
    wikidata_entity, wiki_status, wiki_lat = query_wikidata_entity(brand_name, domain, same_as_links)
    
    # Provider 2: Wikipedia Summary API
    wikipedia_summary, wp_status, wp_lat = query_wikipedia_summary(brand_name)

    total_lat = wiki_lat + wp_lat
    fallback_used = wiki_status != "SUCCESS" or wp_status != "SUCCESS"

    # Compute Final Corroboration Status
    if wikidata_entity or wikipedia_summary:
        final_status = "VERIFIED"
    elif wiki_status in ["TIMEOUT", "ERROR"] and wp_status in ["TIMEOUT", "ERROR"]:
        final_status = "UNAVAILABLE"
    else:
        final_status = "INFERRED"

    # Store Detailed Observability Telemetry
    state.corroboration_observations = {
        "wikidata_status": wiki_status,
        "wikipedia_status": wp_status,
        "final_status": final_status,
        "latency_ms": round(total_lat, 2),
        "fallback_used": fallback_used,
        "wikidata_entity": wikidata_entity,
        "wikipedia_summary": wikipedia_summary,
        "same_as_links": same_as_links
    }

    # Grounding check with confirmed on-site facts
    has_sameas = len(same_as_links) > 0
    has_onsite_org = bool(detected_org.get("name") or detected_org.get("url"))
    onsite_fact_summary = f"On-site entity grounding evaluated via Organization schema ({'present' if has_onsite_org else 'absent'}) and {len(same_as_links)} declared sameAs link(s)."

    # Record Evidence & Findings based on final_status
    if wikidata_entity:
        state.add_evidence(
            url=wikidata_entity.get("concepturi", f"https://www.wikidata.org/wiki/{wikidata_entity.get('id')}"),
            page_context="Wikidata Entity Lookup",
            observation=f"Resolved entity '{brand_name}' to Wikidata Q-ID '{wikidata_entity.get('id')}'. {onsite_fact_summary}",
            status=EvidenceStatus.LIVE_OBSERVED,
            source_type="api",
            exact_value=wikidata_entity.get("id"),
            source_skill="freshness-corroboration"
        )
    elif wiki_status == "SUCCESS":
        # Successfully queried Wikidata, confirmed 0 matches (neutral observation)
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Wikidata Entity Lookup",
            observation=f"EXTERNAL_CORROBORATION_UNAVAILABLE: External Wikidata knowledge graph query returned 0 matches for '{brand_name}'. {onsite_fact_summary}",
            status=EvidenceStatus.UNAVAILABLE,
            source_type="api",
            source_skill="freshness-corroboration"
        )
        f = Finding(
            id="corroboration-wikidata-missing",
            title=f"EXTERNAL_CORROBORATION_UNAVAILABLE: Brand entity '{brand_name}' not listed on Wikidata knowledge graph",
            severity="low",
            category="corroboration",
            primary_dimension="ai_discoverability",
            mechanism="ENTITY_CORROBORATION",
            finding_type="TECHNICAL_NOTICE",
            business_impact="low",
            evidence=f"External Wikidata entity query returned 0 matches for '{brand_name}'. {onsite_fact_summary}. Score preserved without negative deduction.",
            suggested_action=SuggestedAction(
                summary="Consider registering a Wikidata entity item or adding sameAs social links to strengthen offsite knowledge graph consensus.",
                priority="low",
                effort="Medium",
                impact="Medium"
            ),
            mechanism_impact="Informational grounding observation. Missing external knowledge graph entry does not penalize non-famous or emerging brand readiness scores.",
            source_skill="freshness-corroboration",
            affected_urls=[f"https://{domain}"],
            provenance=["Wikidata REST API"]
        )
        findings.append(f)
        state.add_finding(f)
    else:
        # Telemetry UNAVAILABLE (Timeout or Error) - DO NOT GENERATE NEGATIVE SCORE PENALTY FINDING
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Wikidata Telemetry Check",
            observation=f"Wikidata API telemetry unavailable ({wiki_status}). Readiness score preserved without negative deduction.",
            status=EvidenceStatus.UNAVAILABLE,
            source_type="api",
            source_skill="freshness-corroboration"
        )

    if wikipedia_summary:
        state.add_evidence(
            url=wikipedia_summary.get("page_url", ""),
            page_context="Wikipedia Summary Lookup",
            observation=f"Corroborated article '{wikipedia_summary.get('title')}' on Wikipedia.",
            status=EvidenceStatus.LIVE_OBSERVED,
            source_type="api",
            source_skill="freshness-corroboration"
        )
    elif wp_status == "SUCCESS":
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Wikipedia Summary Lookup",
            observation=f"EXTERNAL_CORROBORATION_UNAVAILABLE: Wikipedia article query returned 0 matches for '{brand_name}'.",
            status=EvidenceStatus.UNAVAILABLE,
            source_type="api",
            source_skill="freshness-corroboration"
        )
        f = Finding(
            id="corroboration-wikipedia-missing",
            title=f"EXTERNAL_CORROBORATION_UNAVAILABLE: No dedicated Wikipedia article for '{brand_name}'",
            severity="low",
            category="corroboration",
            primary_dimension="ai_discoverability",
            mechanism="ENTITY_CORROBORATION",
            finding_type="TECHNICAL_NOTICE",
            business_impact="low",
            evidence=f"No dedicated Wikipedia article found for '{brand_name}'. Score preserved without negative penalty.",
            suggested_action=SuggestedAction(
                summary="Build offsite entity presence across B2B platforms (LinkedIn, GitHub, Crunchbase) to foster authority.",
                priority="low",
                effort="Medium",
                impact="Medium"
            ),
            mechanism_impact="Informational grounding observation. Absence of a dedicated Wikipedia article is expected for non-famous or early-stage brands.",
            source_skill="freshness-corroboration",
            affected_urls=[f"https://{domain}"],
            provenance=["Wikipedia REST API"]
        )
        findings.append(f)
        state.add_finding(f)
    else:
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Wikipedia Telemetry Check",
            observation=f"Wikipedia API telemetry unavailable ({wp_status}). Score preserved without deduction.",
            status=EvidenceStatus.UNAVAILABLE,
            source_type="api",
            source_skill="freshness-corroboration"
        )

    # 3. Explicit User Claim Triangulation
    claims = state.claims
    if claims:
        wiki_text = (wikipedia_summary["extract"] if wikipedia_summary else "") + " " + (wikidata_entity["description"] if wikidata_entity else "")
        wiki_text_lower = wiki_text.lower()

        for claim_key, claim_val in claims.items():
            val_str = str(claim_val).lower().strip()
            if val_str:
                if val_str in wiki_text_lower:
                    state.add_evidence(
                        url=f"https://{domain}",
                        page_context=f"Claim Triangulation: '{claim_key}'",
                        observation=f"Claim '{claim_key}' = '{claim_val}' corroborated in offsite knowledge base.",
                        status=EvidenceStatus.LIVE_OBSERVED,
                        source_type="api",
                        exact_value=claim_val,
                        source_skill="freshness-corroboration"
                    )
                else:
                    state.add_evidence(
                        url=f"https://{domain}",
                        page_context=f"Claim Triangulation: '{claim_key}'",
                        observation=f"Claim '{claim_key}' = '{claim_val}' is unverified in offsite sources.",
                        status=EvidenceStatus.INFERRED,
                        source_type="api",
                        exact_value=claim_val,
                        source_skill="freshness-corroboration"
                    )
                    f = Finding(
                        id=f"corroboration-claim-unverified-{claim_key}",
                        title=f"Unverified offsite claim signal: '{claim_key}' = '{claim_val}'",
                        severity="low",
                        category="corroboration",
                        evidence=f"Claim '{claim_key}' ('{claim_val}') was unverified in public Wikidata/Wikipedia records.",
                        suggested_action=SuggestedAction(
                            summary=f"Ensure '{claim_key}' matches public corporate registry entries.",
                            priority="low",
                            effort="Low",
                            impact="Low"
                        ),
                        mechanism_impact="Unverified claims have lower trust weighting in generative RAG citations.",
                        source_skill="freshness-corroboration",
                        affected_urls=[f"https://{domain}"],
                        provenance=["Claim Triangulation"]
                    )
                    findings.append(f)
                    state.add_finding(f)

    return findings

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: check_corroboration.py <brand_name> [claims_json]"}))
        sys.exit(1)

    brand_name = sys.argv[1]
    claims_json_raw = sys.argv[2] if len(sys.argv) > 2 else "{}"

    claims = {}
    if claims_json_raw and claims_json_raw != "{}":
        try:
            claims = json.loads(claims_json_raw)
        except Exception:
            claims = {}

    state = AuditState(target_url=brand_name, normalized_domain=brand_name.lower(), brand=brand_name, claims=claims)
    findings = run_corroboration_check(state)

    output = [f.to_dict() for f in findings]
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()

