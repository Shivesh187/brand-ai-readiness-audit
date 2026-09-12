import sys
import os
import json
import re
from typing import List, Tuple, Dict, Any

# Dynamically locate workspace root
cur_dir = os.path.abspath(__file__)
while cur_dir != os.path.dirname(cur_dir):
    if os.path.exists(os.path.join(cur_dir, "marketplace.json")) or os.path.exists(os.path.join(cur_dir, "common")):
        if cur_dir not in sys.path:
            sys.path.insert(0, cur_dir)
        break
    cur_dir = os.path.dirname(cur_dir)

from common.http_client import fetch_url, check_ssl_certificate
from common.models import Finding, SuggestedAction, AuditState, EvidenceStatus
from common.crawler import EnhancedCrawler
from core.ai_crawlers import parse_ai_robots_rules, AI_CRAWLER_MATRIX

def parse_robots_txt(content: str, domain: str) -> Tuple[List[Finding], List[str]]:
    """Backwards compatibility helper for parse_robots_txt calls."""
    ai_rules = parse_ai_robots_rules(content, domain)
    sitemaps = ai_rules.get("sitemaps", [])
    bot_access = ai_rules.get("bot_access", {})
    findings = []
    for bot_name, binfo in bot_access.items():
        if not binfo["can_fetch"]:
            bot_lower = bot_name.lower()
            if bot_name == "Google-Extended":
                severity = "low"
                finding_type = "TECHNICAL_NOTICE"
                biz_impact = "low"
                title = f"Google AI Model Training Crawler '{bot_name}' is restricted in robots.txt"
                mech_impact = "Google-Extended strictly controls Google AI and Gemini foundational model training opt-outs. It does NOT block indexing or inclusion in Google Search or Google AI Overviews."
            elif bot_name == "GPTBot":
                severity = binfo["criticality"]
                finding_type = "BLOCKER" if severity in ["critical", "high"] else "ISSUE"
                biz_impact = "high"
                title = f"AI Model Pre-training Crawler '{bot_name}' is restricted in robots.txt"
                mech_impact = "GPTBot is OpenAI's foundational model pre-training crawler."
            else:
                severity = binfo["criticality"]
                finding_type = "BLOCKER" if severity in ["critical", "high"] else "ISSUE"
                biz_impact = "critical" if severity == "critical" else "high"
                title = f"AI Crawler '{bot_name}' is blocked in robots.txt"
                mech_impact = f"Blocking '{bot_name}' prevents real-time search indexing and retrieval in RAG engines."

            findings.append(Finding(
                id=f"access-robots-blocked-{bot_lower}",
                title=title,
                severity=severity,
                category="discoverability",
                primary_dimension="ai_discoverability",
                mechanism="CRAWLER_ACCESS",
                finding_type=finding_type,
                business_impact=biz_impact,
                evidence=f"Disallow rule matched for user-agent '{bot_name}' on domain '{domain}'.",
                suggested_action=SuggestedAction(
                    summary=f"Modify robots.txt to allow '{bot_name}' access if AI model grounding is desired.",
                    priority=severity,
                    recommendation=f"Add 'User-agent: {bot_name}\\nAllow: /' to your robots.txt."
                ),
                mechanism_impact=mech_impact,
                source_skill="crawl-render-audit",
                affected_urls=[f"https://{domain}/robots.txt"]
            ))
    return findings, sitemaps


def run_discoverability_check(state: AuditState) -> List[Finding]:
    domain = state.normalized_domain
    url = state.target_url if state.target_url.startswith("http") else f"https://{domain}"
    findings = []

    # 1. Enhanced Fetch Homepage with Redirect Tracking
    if domain not in state.http_responses:
        hp_res = EnhancedCrawler.fetch_url_with_redirects(domain, timeout=6.0)
        state.http_responses[domain] = hp_res
        if hp_res["success"]:
            state.raw_html[domain] = hp_res["content"]
    else:
        hp_res = state.http_responses[domain]

    redirect_chain = hp_res.get("redirect_chain", [domain])
    redirect_count = hp_res.get("redirect_count", 0)
    final_url = hp_res.get("final_url", f"https://{domain}")

    state.crawl_metadata["redirect_chain"] = redirect_chain
    state.crawl_metadata["redirect_count"] = redirect_count
    state.crawl_metadata["final_url"] = final_url

    if redirect_count > 0:
        state.add_evidence(
            url=url,
            page_context="Redirect History",
            observation=f"Requested {url}; final URL was {final_url} after {redirect_count} redirects.",
            status=EvidenceStatus.OBSERVED,
            source_type="headers",
            source_skill="crawl-render-audit"
        )
        if redirect_count >= 4:
            f = Finding(
                id="access-redirect-chain-excessive",
                title=f"Excessive redirect chain detected ({redirect_count} redirects)",
                severity="medium",
                category="discoverability",
                primary_dimension="technical_health",
                mechanism="REDIRECTS",
                finding_type="ISSUE",
                business_impact="medium",
                evidence=f"Redirect chain length is {redirect_count} steps. Deep redirect chains cause AI crawlers to abort traversal.",
                suggested_action=SuggestedAction(
                    summary="Shorten redirect chains to direct 1-step 301/302 redirects.",
                    priority="medium"
                ),
                mechanism_impact="Deep redirect loops consume crawler time budgets.",
                source_skill="crawl-render-audit",
                affected_urls=[url]
            )
            findings.append(f)
            state.add_finding(f)

    if not hp_res["success"]:
        state.add_evidence(
            url=url,
            page_context="Homepage HTTP Fetch",
            observation=f"Connection failed: {hp_res.get('error')}",
            status=EvidenceStatus.CONTRADICTED,
            source_type="headers",
            source_skill="crawl-render-audit"
        )
        f = Finding(
            id="access-http-connection-failed",
            title="Failed to connect to primary brand homepage",
            severity="critical",
            category="discoverability",
            evidence=f"HTTP connection to '{domain}' failed or timed out.",
            suggested_action=SuggestedAction(
                summary="Ensure website is online and accessible without IP/firewall blocks.",
                priority="critical"
            ),
            mechanism_impact="If AI crawlers cannot connect to the homepage, no content will be indexed.",
            source_skill="crawl-render-audit",
            affected_urls=[f"https://{domain}"]
        )
        findings.append(f)
        state.add_finding(f)
    else:
        latency = hp_res["latency_ms"]
        state.crawl_metadata["latency_ms"] = latency
        state.add_evidence(
            url=url,
            page_context="Homepage Latency",
            observation=f"Homepage latency measured at {latency}ms.",
            status=EvidenceStatus.OBSERVED,
            source_type="headers",
            exact_value=latency,
            source_skill="crawl-render-audit"
        )

        if latency > 1500:
            f = Finding(
                id="access-http-latency-slow",
                title="High response latency observation for AI crawlers",
                severity="low",
                category="discoverability",
                primary_dimension="technical_health",
                mechanism="PERFORMANCE_OBSERVATION",
                finding_type="TECHNICAL_NOTICE",
                business_impact="low",
                evidence=f"Single-probe homepage latency measured at {latency}ms (Threshold: 1500ms). Recorded as operational telemetry.",
                suggested_action=SuggestedAction(
                    summary="Monitor TTFB and deploy global CDN caching if latency remains consistently high.",
                    priority="low"
                ),
                mechanism_impact="Operational performance telemetry.",
                source_skill="crawl-render-audit",
                affected_urls=[f"https://{domain}"]
            )
            findings.append(f)
            state.add_finding(f)

    # 2. Canonical URL Parity Check
    raw_html = state.raw_html.get(domain, "")
    canonical_match = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']', raw_html, re.I)
    if canonical_match:
        canonical_url = canonical_match.group(1).strip()
        state.crawl_metadata["canonical_url"] = canonical_url
        clean_canon = canonical_url.replace("https://", "").replace("http://", "").rstrip("/")
        clean_final = final_url.replace("https://", "").replace("http://", "").rstrip("/")
        if clean_canon and clean_final and clean_canon != clean_final:
            state.add_evidence(
                url=url,
                page_context="Canonical Parity Check",
                observation=f"Canonical URL ('{canonical_url}') differs from fetched target URL ('{final_url}').",
                status=EvidenceStatus.OBSERVED,
                source_type="raw_html",
                source_skill="crawl-render-audit"
            )
            f = Finding(
                id="access-canonical-mismatch",
                title="Canonical URL mismatch detected",
                severity="medium",
                category="discoverability",
                primary_dimension="technical_health",
                mechanism="REDIRECTS",
                finding_type="ISSUE",
                business_impact="medium",
                evidence=f"Declared canonical tag ('{canonical_url}') does not match actual response URL ('{final_url}').",
                suggested_action=SuggestedAction(
                    summary="Update canonical tag to point to exact canonical domain.",
                    priority="medium"
                ),
                mechanism_impact="Canonical mismatches split link authority and create duplicate index entries for AI scrapers.",
                source_skill="crawl-render-audit",
                affected_urls=[url]
            )
            findings.append(f)
            state.add_finding(f)

    # 3. Check SSL Certificate
    hp_success = state.http_responses.get(domain, {}).get("success", False) or bool(state.raw_html.get(domain, "").strip())
    ssl_res = check_ssl_certificate(domain, fallback_success=hp_success)
    state.crawl_metadata["ssl_valid"] = ssl_res["valid"]
    state.crawl_metadata["ssl_days"] = ssl_res.get("daysRemaining", 0)

    if not ssl_res["valid"]:
        state.add_evidence(
            url=f"https://{domain}",
            page_context="SSL Check",
            observation=f"SSL certificate invalid: {ssl_res.get('error')}",
            status=EvidenceStatus.CONTRADICTED,
            source_type="headers",
            source_skill="crawl-render-audit"
        )
        f = Finding(
            id="access-ssl-invalid",
            title="SSL Certificate Validation Failure",
            severity="critical",
            category="discoverability",
            evidence=f"SSL certificate connection failed: {ssl_res.get('error')}",
            suggested_action=SuggestedAction(
                summary="Fix SSL certificate configuration immediately to ensure secure HTTPS indexing.",
                priority="critical"
            ),
            mechanism_impact="Invalid SSL certificates cause AI bots to drop connection handshakes for security.",
            source_skill="crawl-render-audit",
            affected_urls=[f"https://{domain}"]
        )
        findings.append(f)
        state.add_finding(f)

    elif ssl_res["daysRemaining"] < 30:
        f = Finding(
            id="access-ssl-expiring",
            title="SSL Certificate expiring within 30 days",
            severity="high",
            category="discoverability",
            primary_dimension="technical_health",
            mechanism="SSL",
            finding_type="TECHNICAL_NOTICE",
            business_impact="low",
            evidence=f"Certificate expires in {ssl_res['daysRemaining']} days.",
            suggested_action=SuggestedAction(
                summary="Renew SSL certificate before expiration to prevent AI crawler disconnects.",
                priority="high"
            ),
            mechanism_impact="Expiring SSL certificates risk upcoming crawler outages.",
            source_skill="crawl-render-audit",
            affected_urls=[f"https://{domain}"]
        )
        findings.append(f)
        state.add_finding(f)

    # 4. Comprehensive AI Crawler Accessibility & Robots.txt Directives
    robots_url = f"{domain}/robots.txt"
    robots_res = fetch_url(robots_url, timeout=5.0)
    
    if not robots_res["success"] or not robots_res["content"]:
        state.add_evidence(
            url=f"https://{robots_url}",
            page_context="Robots.txt Fetch",
            observation="Missing or inaccessible robots.txt file.",
            status=EvidenceStatus.CONTRADICTED,
            source_type="raw_html",
            source_skill="crawl-render-audit"
        )
        f = Finding(
            id="access-robots-missing",
            title="Missing or inaccessible robots.txt file",
            severity="high",
            category="discoverability",
            evidence=f"Could not retrieve robots.txt at https://{robots_url}.",
            suggested_action=SuggestedAction(
                summary="Publish a valid robots.txt file at the root domain.",
                priority="high"
            ),
            mechanism_impact="Missing robots.txt forces AI crawlers to rely on conservative default crawl assumptions.",
            source_skill="crawl-render-audit",
            affected_urls=[f"https://{robots_url}"]
        )
        findings.append(f)
        state.add_finding(f)
    else:
        robots_content = robots_res["content"]
        state.robots_txt = robots_content
        if state.context:
            state.context.robots_txt = robots_content

        ai_rules = parse_ai_robots_rules(robots_content, url)
        declared_sitemaps = ai_rules["sitemaps"]
        bot_access = ai_rules["bot_access"]
        
        state.crawl_metadata["sitemaps"] = declared_sitemaps
        state.crawl_metadata["ai_crawler_matrix"] = ai_rules

        archetype = state.context.archetype if state.context else "GENERAL_CONTENT"

        # Evaluate each AI crawler's access permissions with granular severity
        for bot_name, binfo in bot_access.items():
            if not binfo["can_fetch"]:
                bot_lower = bot_name.lower()
                category = binfo["category"]
                
                if bot_name == "Google-Extended":
                    severity = "low"
                    finding_type = "TECHNICAL_NOTICE"
                    biz_impact = "low"
                    title = f"Google AI Model Training Crawler '{bot_name}' is restricted in robots.txt"
                    mech_impact = "Google-Extended strictly controls Google AI and Gemini foundational model training opt-outs. It does NOT block indexing or inclusion in Google Search or Google AI Overviews."
                elif bot_name == "Applebot-Extended":
                    severity = "low"
                    finding_type = "TECHNICAL_NOTICE"
                    biz_impact = "low"
                    title = f"Apple AI Model Training Crawler '{bot_name}' is restricted in robots.txt"
                    mech_impact = "Applebot-Extended controls Apple Intelligence model pre-training opt-outs."
                elif bot_name in ["GPTBot", "cohere-ai", "Bytespider"]:
                    severity = "medium"
                    finding_type = "ISSUE"
                    biz_impact = "medium"
                    title = f"AI Model Pre-training Crawler '{bot_name}' is restricted in robots.txt"
                    mech_impact = f"Blocking '{bot_name}' prevents pre-training model ingestion."
                else: # Real-time search bots (OAI-SearchBot, ClaudeBot, PerplexityBot, ChatGPT-User)
                    severity = "critical" if binfo["criticality"] == "critical" else "high"
                    finding_type = "BLOCKER"
                    biz_impact = "critical" if severity == "critical" else "high"
                    title = f"AI Search Crawler '{bot_name}' is blocked in robots.txt"
                    mech_impact = f"Blocking '{bot_name}' prevents real-time search indexing and retrieval in RAG engines."

                findings.append(Finding(
                    id=f"access-robots-blocked-{bot_lower}",
                    title=title,
                    severity=severity,
                    category="discoverability",
                    primary_dimension="ai_discoverability",
                    mechanism="CRAWLER_ACCESS",
                    finding_type=finding_type,
                    business_impact=biz_impact,
                    evidence=f"Disallow rule matched for user-agent '{bot_name}' on domain '{domain}'.",
                    suggested_action=SuggestedAction(
                        summary=f"Modify robots.txt to allow '{bot_name}' access if AI model grounding is desired.",
                        priority=severity,
                        recommendation=f"Add 'User-agent: {bot_name}\\nAllow: /' to your robots.txt."
                    ),
                    mechanism_impact=mech_impact,
                    source_skill="crawl-render-audit",
                    affected_urls=[f"https://{domain}/robots.txt"]
                ))
                state.add_finding(findings[-1])

        # 5. Check Sitemap presence
        sitemap_found = len(declared_sitemaps) > 0
        sitemap_status = "VERIFIED_PRESENT" if sitemap_found else "VERIFIED_ABSENT"

        if not sitemap_found:
            sm_res = fetch_url(f"{domain}/sitemap.xml", timeout=5.0)
            if sm_res["success"] and sm_res["content"] and ("<xml" in sm_res["content"].lower() or "<?xml" in sm_res["content"].lower() or "<urlset" in sm_res["content"].lower()):
                sitemap_found = True
                sitemap_status = "VERIFIED_PRESENT"
                state.crawl_metadata["sitemaps"].append(f"https://{domain}/sitemap.xml")
            elif not sm_res["success"]:
                err_str = str(sm_res.get("error", "")).lower()
                if "404" in err_str or "not found" in err_str:
                    sitemap_status = "VERIFIED_ABSENT"
                else:
                    sitemap_status = "UNAVAILABLE"
            else:
                sitemap_status = "VERIFIED_ABSENT"

        state.crawl_metadata["sitemap_status"] = sitemap_status

        if sitemap_status == "VERIFIED_PRESENT":
            state.add_evidence(
                url=f"https://{domain}/sitemap.xml",
                page_context="Sitemap Verification",
                observation="XML Sitemap discovered and verified present.",
                status=EvidenceStatus.LIVE_OBSERVED,
                source_type="raw_html",
                source_skill="crawl-render-audit"
            )
        elif sitemap_status == "VERIFIED_ABSENT":
            state.add_evidence(
                url=f"https://{domain}/sitemap.xml",
                page_context="Sitemap Verification",
                observation="XML Sitemap check completed: confirmed absent on target domain.",
                status=EvidenceStatus.LIVE_OBSERVED,
                source_type="raw_html",
                source_skill="crawl-render-audit"
            )
            f = Finding(
                id="access-sitemap-missing",
                title="No XML Sitemap declared or discovered",
                severity="medium",
                category="discoverability",
                evidence=f"No 'Sitemap:' directive found in robots.txt and https://{domain}/sitemap.xml was confirmed absent.",
                suggested_action=SuggestedAction(
                    summary="Generate an XML sitemap and add 'Sitemap: https://yourdomain.com/sitemap.xml' to robots.txt.",
                    priority="medium",
                    effort="Low",
                    impact="High"
                ),
                mechanism_impact="XML sitemaps provide AI crawlers the exact graph of canonical pages to index.",
                source_skill="crawl-render-audit",
                affected_urls=[f"https://{domain}/robots.txt"],
                provenance=["robots.txt", "/sitemap.xml"]
            )
            findings.append(f)
            state.add_finding(f)
        else: # UNAVAILABLE
            state.add_evidence(
                url=f"https://{domain}/sitemap.xml",
                page_context="Sitemap Verification",
                observation="XML Sitemap inspection budget exceeded or endpoint unavailable.",
                status=EvidenceStatus.UNAVAILABLE,
                source_type="raw_html",
                source_skill="crawl-render-audit"
            )
            f = Finding(
                id="access-sitemap-unavailable",
                title="XML Sitemap inspection telemetry unavailable",
                severity="medium",
                category="discoverability",
                evidence="Target endpoint did not respond within inspection budget. Readiness score preserved without negative deduction.",
                evidence_origin=EvidenceStatus.UNAVAILABLE,
                suggested_action=SuggestedAction(
                    summary="Verify server network stability and sitemap XML accessibility.",
                    priority="medium",
                    effort="Low",
                    impact="Medium"
                ),
                mechanism_impact="Inspection budget timeout prevented sitemap validation.",
                source_skill="crawl-render-audit",
                affected_urls=[f"https://{domain}/sitemap.xml"],
                provenance=["sitemap.xml inspection"]
            )
            findings.append(f)
            state.add_finding(f)

    return findings

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No domain provided"}))
        sys.exit(1)

    domain = sys.argv[1].replace("https://", "").replace("http://", "").split("/")[0]
    state = AuditState(target_url=domain, normalized_domain=domain, brand=domain.capitalize())
    findings = run_discoverability_check(state)

    output = [f.to_dict() for f in findings]
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
