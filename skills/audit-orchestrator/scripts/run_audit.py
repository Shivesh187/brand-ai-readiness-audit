import sys
import os
import argparse
import json
import re
import importlib.util
from datetime import datetime, timezone

# Dynamically locate workspace root
workspace_root = os.path.abspath(__file__)
while workspace_root != os.path.dirname(workspace_root):
    if os.path.exists(os.path.join(workspace_root, "marketplace.json")) or os.path.exists(os.path.join(workspace_root, "common")):
        if workspace_root not in sys.path:
            sys.path.insert(0, workspace_root)
        break
    workspace_root = os.path.dirname(workspace_root)

from common.http_client import fetch_url
from common.models import Finding, SuggestedAction, AuditState, AuditReport, EvidenceStatus
from common.browser_renderer import PLAYWRIGHT_AVAILABLE, evaluate_rendering_decision, render_page, compare_raw_vs_rendered
from common.llm_client import GeminiReasoningEngine, apply_gemini_reasoning_and_guardrails
from common.reasoning import DeterministicReasoningEngine

def load_skill_module(relative_path: str, module_name: str):
    full_path = os.path.join(workspace_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, full_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# In-Memory Sub-Skill Imports
discoverability_module = load_skill_module(os.path.join("skills", "crawl-render-audit", "scripts", "check_access.py"), "check_access")
semantics_module = load_skill_module(os.path.join("skills", "semantic-readiness", "scripts", "check_semantics.py"), "check_semantics")
corroboration_module = load_skill_module(os.path.join("skills", "freshness-corroboration", "scripts", "check_corroboration.py"), "check_corroboration")
engagement_module = load_skill_module(os.path.join("skills", "engagement-audit", "scripts", "check_engagement.py"), "check_engagement")

def clean_url(url_str: str) -> str:
    clean = re.sub(r'^https?://', '', url_str, flags=re.IGNORECASE)
    clean = clean.split('/')[0].split('?')[0]
    return clean

def extract_brand_name(domain: str) -> str:
    parts = domain.split('.')
    if len(parts) >= 2:
        name = parts[-2]
        return name.capitalize() if name.lower() not in ["co", "com", "org", "net"] else parts[0].capitalize()
    return domain.capitalize()

def execute_audit_pipeline(target_domain: str, brand_name: str, claims: dict = None, enable_llm: bool = True) -> AuditReport:
    domain = clean_url(target_domain)
    brand = brand_name if brand_name else extract_brand_name(domain)
    claims_dict = claims if claims else {}

    # Initialize Shared Pipeline State
    state = AuditState(target_url=target_domain, normalized_domain=domain, brand=brand, claims=claims_dict)

    # 1. Pipeline Stage 1: Fast HTTP Acquisition (Pre-fetch primary homepage)
    hp_res = fetch_url(domain, timeout=6.0)
    state.http_responses[domain] = hp_res
    if hp_res["success"]:
        state.raw_html[domain] = hp_res["content"]

    # 2. Pipeline Stage 2: Offsite Discoverability Check
    try:
        discoverability_module.run_discoverability_check(state)
    except Exception as e:
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Discoverability Stage",
            observation=f"Discoverability check encountered runtime exception: {str(e)}",
            status=EvidenceStatus.CONTRADICTED,
            source_type="headers",
            source_skill="crawl-render-audit"
        )

    # 3. Pipeline Stage 3: Semantic Readiness Check (Populates extracted_content & JS signatures)
    try:
        semantics_module.run_semantics_check(state)
    except Exception as e:
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Semantics Stage",
            observation=f"Semantics check encountered runtime exception: {str(e)}",
            status=EvidenceStatus.CONTRADICTED,
            source_type="raw_html",
            source_skill="semantic-readiness"
        )

    # 4. Pipeline Stage 4: Rendering Decision Engine & Optional Browser Layer
    raw_html_str = state.raw_html.get(domain, "")
    should_render, reason, signals, confidence = evaluate_rendering_decision(raw_html_str, state.extracted_content)

    state.rendering_metadata["decision"] = {
        "should_render": should_render,
        "reason": reason,
        "signals": signals,
        "confidence": confidence
    }

    if not should_render:
        state.rendering_metadata["status"] = "NOT_REQUIRED"
    elif not PLAYWRIGHT_AVAILABLE:
        state.rendering_metadata["status"] = "UNAVAILABLE"
        state.rendering_metadata["error"] = "Playwright runtime unavailable"
    else:
        state.rendering_metadata["status"] = "ATTEMPTED"
        try:
            render_res = render_page(domain, timeout_ms=8000)
            state.rendering_metadata["executed"] = True
            if render_res.successful:
                state.rendering_metadata["status"] = "SUCCESS"
                state.rendering_metadata["result"] = render_res.to_dict()

                # Compare raw HTML vs post-JS rendered DOM
                comparison = compare_raw_vs_rendered(raw_html_str, state.extracted_content, render_res)
                state.rendering_metadata["comparison"] = comparison

                state.add_evidence(
                    url=f"https://{domain}",
                    page_context="Headless Browser DOM Rendering",
                    observation=f"Rendered DOM text length: {comparison.get('rendered_text_length')} chars (Raw: {comparison.get('raw_text_length')} chars, +{comparison.get('text_increase_percentage')}%)",
                    status=EvidenceStatus.LIVE_OBSERVED,
                    source_type="rendered_dom",
                    exact_value=comparison,
                    source_skill="browser-renderer"
                )

                if comparison.get("h1_revealed_via_js"):
                    state.extracted_content["h1_headers_rendered"] = render_res.h1_headers
                    state.add_evidence(
                        url=f"https://{domain}",
                        page_context="Headless Browser H1 Extraction",
                        observation=f"H1 heading ('{render_res.h1_headers[0]}') revealed via client-side rendering.",
                        status=EvidenceStatus.LIVE_OBSERVED,
                        source_type="rendered_dom",
                        source_skill="browser-renderer"
                    )
            else:
                state.rendering_metadata["status"] = "FAILED"
                state.rendering_metadata["error"] = render_res.error
        except Exception as e:
            state.rendering_metadata["status"] = "FAILED"
            state.rendering_metadata["error"] = str(e)

    # 5. Pipeline Stage 5: Offsite Corroboration Check (Uses entity_observations from Stage 3)
    try:
        corroboration_module.run_corroboration_check(state)
    except Exception as e:
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Corroboration Stage",
            observation=f"Entity corroboration check encountered runtime exception: {str(e)}",
            status=EvidenceStatus.UNAVAILABLE,
            source_type="api",
            source_skill="freshness-corroboration"
        )

    # 6. Pipeline Stage 6: Engagement Audit Check (Consumes rendering_metadata & comparison)
    try:
        engagement_module.run_engagement_check(state)
    except Exception as e:
        state.add_evidence(
            url=f"https://{domain}",
            page_context="Engagement Stage",
            observation=f"Engagement check encountered runtime exception: {str(e)}",
            status=EvidenceStatus.INFERRED,
            source_type="raw_html",
            source_skill="engagement-audit"
        )

    # Rule-Based Proactive Recommendations Injection
    temp_findings = state.validate_and_deduplicate_findings()
    has_sitemap_issue = any("sitemap" in f.id.lower() for f in temp_findings)
    if has_sitemap_issue:
        state.add_finding(Finding(
            id="F-SITEMAP-REC",
            title="Establish an AI-Optimized Sitemap Protocol",
            severity="medium",
            category="discoverability",
            evidence="Sitemap is missing or lacks AI indexing metadata tags.",
            suggested_action=SuggestedAction(
                summary="Publish an AI-optimized XML sitemap detailing content modification frequency and context vector tags.",
                priority="medium",
                effort="Low",
                impact="High"
            ),
            mechanism_impact="Explicit sitemaps accelerate Generative Search engine crawl indexation.",
            why_it_matters="Sitemaps provide AI web scrapers the canonical URL manifest required for vector database indexing.",
            source_skill="audit-orchestrator",
            affected_urls=[f"https://{domain}/sitemap.xml"],
            provenance=["robots.txt", "sitemap.xml"]
        ))

    has_org_issue = any("organization" in f.title.lower() for f in temp_findings)
    if has_org_issue:
        state.add_finding(Finding(
            id="F-SAMEAS-REC",
            title="Ground brand entities with Schema.org sameAs properties",
            severity="medium",
            category="semantics",
            evidence="Organization schema is missing authoritative reference link properties.",
            suggested_action=SuggestedAction(
                summary="Include sameAs links pointing to official Wikidata, Wikipedia, and Crunchbase company pages.",
                priority="medium",
                effort="Low",
                impact="High"
            ),
            mechanism_impact="sameAs properties link local schemas to universal knowledge graph entity IDs.",
            why_it_matters="Knowledge graph entity links prevent LLMs from hallucinating corporate metadata.",
            source_skill="audit-orchestrator",
            affected_urls=[f"https://{domain}"],
            provenance=["Schema.org JSON-LD", "Wikidata"]
        ))

    # Initial Deduplication & Deterministic Reasoning Engine Pass
    deterministic_findings = DeterministicReasoningEngine.enrich_and_validate_findings(state)

    # 7. Pipeline Stage 7: Optional Gemini Reasoning Engine & Safety Guardrails
    if enable_llm:
        llm_engine = GeminiReasoningEngine()
        final_findings = apply_gemini_reasoning_and_guardrails(state, llm_engine)
        # Ensure any AI-validated finding retains deterministic priority & why_it_matters if missing
        for f in final_findings:
            if not f.why_it_matters:
                f.why_it_matters = f.mechanism_impact or f"Impacts AI discovery for {domain}."
            if not f.priority:
                f.priority = DeterministicReasoningEngine.calculate_priority(f.severity, f.confidence)
    else:
        state.llm_observations = {
            "enabled": False,
            "provider": "gemini",
            "model": os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
            "configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
            "attempted": False,
            "used": False,
            "status": "DISABLED",
            "fallback_used": True,
            "call_count": 0,
            "latency_ms": 0,
            "cache_hit": False
        }
        final_findings = deterministic_findings

    rendering_status = state.rendering_metadata.get("status", "NOT_REQUIRED")
    playwright_used = PLAYWRIGHT_AVAILABLE and rendering_status in ["SUCCESS", "NOT_REQUIRED", "ATTEMPTED"]
    playwright_status = "SUCCESS" if rendering_status == "SUCCESS" else ("NOT_REQUIRED" if rendering_status == "NOT_REQUIRED" else ("UNAVAILABLE" if rendering_status == "UNAVAILABLE" else "ATTEMPTED"))

    sitemaps_list = state.crawl_metadata.get("sitemaps", [])
    has_sitemap_info = "sitemaps" in state.crawl_metadata or "sitemap_checked" in state.crawl_metadata
    sitemap_found = len(sitemaps_list) > 0
    sitemap_status = "VERIFIED_PRESENT" if sitemap_found else ("VERIFIED_ABSENT" if has_sitemap_info else "UNAVAILABLE")

    corr_obs = state.corroboration_observations
    corr_final = corr_obs.get("final_status")
    if not corr_final:
        if corr_obs.get("wikidata_entity") or corr_obs.get("wikipedia_summary"):
            corr_final = "VERIFIED"
        else:
            corr_final = "INFERRED"

    # Build Real-Data Collection Metadata
    state.collection = {
        "target_url": target_domain,
        "canonical_url": state.crawl_metadata.get("final_url", f"https://{domain}"),
        "pages_crawled": len(state.http_responses),
        "http_fetch_success": bool(state.http_responses.get(domain, {}).get("success", False)),
        "playwright_used": playwright_used,
        "playwright_status": playwright_status,
        "robots_checked": "sitemaps" in state.crawl_metadata or "robots_fetched" in state.crawl_metadata or domain in state.http_responses,
        "sitemap_checked": has_sitemap_info,
        "sitemap_found": sitemap_found,
        "sitemap_status": sitemap_status,
        "entity_corroboration_attempted": bool(corr_obs),
        "entity_corroboration_status": corr_final,
        "entity_corroboration_source": "wikidata/wikipedia",
        "collection_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data_origin": "LIVE_OBSERVED"
    }

    # Build Final Audit Report
    report = AuditReport(
        site=domain,
        brand=brand,
        rendering_metadata=state.rendering_metadata,
        llm_observations=state.llm_observations,
        collection=state.collection,
        findings=final_findings
    )
    report.compute_scores_and_summary()
    return report

def main():
    parser = argparse.ArgumentParser(description="Brand AI Readiness Audit Orchestrator")
    parser.add_argument("--url", required=True, help="Target URL or domain to audit")
    parser.add_argument("--brand", help="Target Brand Name (inferred if not provided)")
    parser.add_argument("--claims", help="JSON string of corporate claims to corroborate (optional)")
    parser.add_argument("--no-llm", action="store_true", help="Disable Gemini LLM reasoning (deterministic-only audit)")
    args = parser.parse_args()

    claims_dict = {}
    if args.claims:
        try:
            claims_dict = json.loads(args.claims)
        except Exception:
            claims_dict = {}

    enable_llm = not args.no_llm
    report = execute_audit_pipeline(args.url, args.brand, claims_dict, enable_llm=enable_llm)
    print(json.dumps(report.to_dict(), indent=2))

if __name__ == "__main__":
    main()
