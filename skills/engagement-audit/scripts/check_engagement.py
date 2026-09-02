import sys
import os
import json
import re
from typing import List
from html.parser import HTMLParser

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

class EngagementDOMParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_segments = []
        self.h1_headers = []
        self.h2_headers = []
        self.cta_buttons = []
        self.meta_description = ""
        self.meta_title = ""
        self.in_h1 = False
        self.in_h2 = False
        self.in_title = False
        self.in_button_or_a = False
        self.current_tag_attrs = {}
        self.in_script_or_style = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in ["script", "style", "noscript"]:
            self.in_script_or_style = True
        elif tag == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.meta_description = attrs_dict.get("content", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "h1":
            self.in_h1 = True
        elif tag == "h2":
            self.in_h2 = True
        elif tag in ["button", "a"]:
            is_cta = tag == "button" or "btn" in attrs_dict.get("class", "").lower() or "cta" in attrs_dict.get("class", "").lower() or attrs_dict.get("role") == "button"
            if is_cta:
                self.in_button_or_a = True
                self.current_tag_attrs = attrs_dict

    def handle_endtag(self, tag):
        if tag in ["script", "style", "noscript"]:
            self.in_script_or_style = False
        elif tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.in_h1 = False
        elif tag == "h2":
            self.in_h2 = False
        elif tag in ["button", "a"]:
            self.in_button_or_a = False

    def handle_data(self, data):
        if self.in_script_or_style:
            return
        cleaned = data.strip()
        if cleaned:
            self.text_segments.append(cleaned)
            if self.in_title:
                self.meta_title += data
            elif self.in_h1:
                self.h1_headers.append(cleaned)
            elif self.in_h2:
                self.h2_headers.append(cleaned)
            elif self.in_button_or_a:
                self.cta_buttons.append(cleaned)

def run_engagement_check(state: AuditState) -> List[Finding]:
    domain = state.normalized_domain
    brand_name = state.brand or domain.capitalize()
    url = f"https://{domain}"
    findings = []

    # Re-use pre-fetched HTML from state if available
    if domain in state.http_responses and state.http_responses[domain].get("content"):
        html_content = state.http_responses[domain]["content"]
    elif domain in state.raw_html:
        html_content = state.raw_html[domain]
    else:
        res = fetch_url(url, timeout=7.0)
        state.http_responses[domain] = res
        if res["success"]:
            html_content = res["content"]
            state.raw_html[domain] = html_content
        else:
            html_content = ""

    if not html_content:
        f = Finding(
            id="engagement-fetch-failed",
            title="Failed to fetch landing page HTML for engagement audit",
            severity="critical",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="INFORMATION_FINDABILITY",
            finding_type="BLOCKER",
            business_impact="critical",
            evidence=f"Could not retrieve HTML content for target '{url}'.",
            suggested_action=SuggestedAction(
                summary="Ensure target domain is online and serving HTML.",
                priority="critical"
            ),
            mechanism_impact="Engagement audit requires HTML content to evaluate text-to-code density and preview card readiness.",
            source_skill="engagement-audit",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)
        return findings

    parser = EngagementDOMParser()
    parser.feed(html_content)

    total_html_bytes = len(html_content)
    all_body_text = " ".join(parser.text_segments)

    comparison = state.rendering_metadata.get("comparison", {})
    if comparison.get("meaningful_content_revealed"):
        rendered_text_len = comparison.get("rendered_text_length", len(all_body_text))
        text_to_code_ratio = rendered_text_len / total_html_bytes if total_html_bytes > 0 else 0.0
        words_count = max(len(all_body_text.split()), int(rendered_text_len / 6))
    else:
        text_to_code_ratio = len(all_body_text) / total_html_bytes if total_html_bytes > 0 else 0.0
        words_count = len(all_body_text.split())

    state.engagement_observations["text_to_code_ratio"] = text_to_code_ratio
    state.engagement_observations["word_count"] = words_count

    preview_words = all_body_text.split()[:200]
    preview_text = " ".join(preview_words)

    # 1. Above-The-Fold H1 Value Proposition Verification
    h1_headers = parser.h1_headers
    h1_rendered = state.extracted_content.get("h1_headers_rendered", [])
    if h1_rendered and not h1_headers:
        h1_headers = h1_rendered

    if not h1_headers:
        state.add_evidence(
            url=url,
            page_context="H1 Header Inspection",
            observation="No <h1> tag present in DOM tree.",
            status=EvidenceStatus.OBSERVED,
            source_type="raw_html",
            source_skill="engagement-audit"
        )
        f = Finding(
            id="engagement-h1-missing",
            title="Missing H1 value proposition heading on primary landing page",
            severity="high",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="VALUE_PROPOSITION",
            finding_type="BLOCKER",
            business_impact="high",
            evidence="No <h1> elements found in the document object model.",
            suggested_action=SuggestedAction(
                summary="Add a single prominent H1 header containing the core value proposition at the top of the content tree.",
                priority="high"
            ),
            mechanism_impact="H1 headers communicate the primary offering to visitors and AI referral engines.",
            source_skill="engagement-audit",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)
    else:
        h1_text = " ".join(h1_headers)
        h1_word_count = len(h1_text.split())
        if comparison.get("h1_revealed_via_js"):
            f = Finding(
                id="engagement-h1-client-rendered",
                title=f"H1 header ('{h1_text}') requires client-side JavaScript rendering",
                severity="low",
                category="engagement",
                primary_dimension="onsite_engagement",
                mechanism="VALUE_PROPOSITION",
                finding_type="TECHNICAL_NOTICE",
                business_impact="low",
                evidence=f"H1 header is rendered dynamically via JavaScript. Search bots without JS engines cannot extract the main title from raw HTML.",
                suggested_action=SuggestedAction(
                    summary="Consider pre-rendering the H1 heading in static server-side HTML.",
                    priority="low"
                ),
                mechanism_impact="Pre-rendered HTML headings ensure instant indexing by lightweight scrapers.",
                source_skill="engagement-audit",
                affected_urls=[url]
            )
            findings.append(f)
            state.add_finding(f)

        elif h1_word_count < 3:
            f = Finding(
                id="engagement-h1-weak",
                title=f"Weak H1 value proposition header ('{h1_text}')",
                severity="medium",
                category="engagement",
                primary_dimension="onsite_engagement",
                mechanism="VALUE_PROPOSITION",
                finding_type="ISSUE",
                business_impact="medium",
                evidence=f"H1 contains only {h1_word_count} word(s). Short H1 headers fail to communicate distinct brand positioning.",
                suggested_action=SuggestedAction(
                    summary="Elaborate H1 heading to explicitly state the brand's core offering and target outcome.",
                    priority="medium"
                ),
                mechanism_impact="Short H1 headers lack sufficient context for visitor understanding.",
                source_skill="engagement-audit",
                affected_urls=[url]
            )
            findings.append(f)
            state.add_finding(f)

    # 2. Call-To-Action (CTA) Clarity & Visibility Analysis
    cta_texts = [c.lower() for c in parser.cta_buttons]
    action_keywords = ["start", "get", "sign", "try", "buy", "order", "demo", "contact", "download", "subscribe", "book", "apply"]
    has_action_cta = any(any(kw in t for kw in action_keywords) for t in cta_texts)
    has_generic_cta = any("learn more" in t or "read more" in t for t in cta_texts)

    if not cta_texts:
        f = Finding(
            id="engagement-cta-missing",
            title="Missing clear action-oriented Call-to-Action (CTA)",
            severity="high",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="CTA_VISIBILITY",
            finding_type="BLOCKER",
            business_impact="high",
            evidence="No clear button or link CTA detected on landing page.",
            suggested_action=SuggestedAction(
                summary="Add an explicit, high-visibility CTA button (e.g. 'Get Started', 'Request Demo').",
                priority="high"
            ),
            mechanism_impact="Visitors arriving from AI search answers require an immediate next action path.",
            source_skill="engagement-audit",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)
    elif not has_action_cta and has_generic_cta:
        f = Finding(
            id="engagement-cta-generic",
            title="Primary CTA relies on generic text ('Learn More')",
            severity="medium",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="CTA_CLARITY",
            finding_type="GROWTH_OPPORTUNITY",
            business_impact="medium",
            evidence="CTA buttons use passive language ('Learn More') rather than specific outcome-driven copy.",
            suggested_action=SuggestedAction(
                summary="Upgrade CTA copy to communicate clear outcome (e.g. 'Start Free Trial', 'Explore Products').",
                priority="medium"
            ),
            mechanism_impact="Action-oriented CTAs increase conversion rate for AI-referred traffic.",
            source_skill="engagement-audit",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    # 3. Text-to-Code Content Density Ratio
    if text_to_code_ratio < 0.10:
        f = Finding(
            id="engagement-code-bloat",
            title="Low text-to-code ratio (Excessive markup bloat)",
            severity="medium",
            category="engagement",
            primary_dimension="ai_discoverability",
            mechanism="CONTENT_EXTRACTION",
            finding_type="ISSUE",
            business_impact="medium",
            evidence=f"Text content ratio is {round(text_to_code_ratio * 100, 2)}% (Recommended: >15%). Heavy markup bloat penalizes automated scraper extraction speed.",
            suggested_action=SuggestedAction(
                summary="De-bloat DOM structures, inline CSS/JS scripts, and increase body text density.",
                priority="medium"
            ),
            mechanism_impact="Heavy DOM bloat dilutes textual content density in RAG vector chunking.",
            source_skill="engagement-audit",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    # 4. Meta Description & AI Referral Context
    meta_desc = parser.meta_description.strip()
    meta_len = len(meta_desc)

    if meta_len == 0:
        f = Finding(
            id="engagement-meta-description-missing",
            title="Missing meta description tag for AI referral context",
            severity="high",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="AI_REFERRAL_CONTEXT",
            finding_type="ISSUE",
            business_impact="medium",
            evidence="No <meta name='description'> tag found in page head.",
            suggested_action=SuggestedAction(
                summary="Add a concise meta description tag (110-160 chars) summarizing brand value.",
                priority="high"
            ),
            mechanism_impact="AI search engines rely on meta descriptions to render fallback response cards.",
            source_skill="engagement-audit",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    # 5. Brand Entity Association in Lead Text
    if brand_name.lower() not in preview_text.lower():
        f = Finding(
            id="engagement-preview-missing-brand",
            title=f"First 200 words lack clear brand entity association ('{brand_name}')",
            severity="medium",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="AI_REFERRAL_CONTEXT",
            finding_type="GROWTH_OPPORTUNITY",
            business_impact="medium",
            evidence=f"Brand name '{brand_name}' does not appear in the lead 200 words of body text.",
            suggested_action=SuggestedAction(
                summary=f"Mention the brand name '{brand_name}' in the hero paragraph to reinforce entity resolution.",
                priority="medium"
            ),
            mechanism_impact="Hero paragraphs set the initial vector context for LLM snippet summarizers.",
            source_skill="engagement-audit",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    return findings

    # 5. Overall Body Content Depth Check
    if words_count < 150:
        f = Finding(
            id="engagement-content-sparse",
            title="Landing page textual content is sparse (<150 words)",
            severity="high",
            category="engagement",
            evidence=f"Total word count is {words_count} words. Sparse content limits LLM RAG chunking efficiency.",
            suggested_action=SuggestedAction(
                summary="Expand landing page body text to provide rich context vectors for Generative AI engines.",
                priority="high"
            ),
            mechanism_impact="Sparse text produces low-dimensional embeddings that perform poorly in vector similarity search.",
            source_skill="engagement-audit",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    return findings

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: check_engagement.py <domain_or_url> <brand_name>"}))
        sys.exit(1)

    target = sys.argv[1]
    brand_name = sys.argv[2]
    domain = target.replace("https://", "").replace("http://", "").split("/")[0]

    state = AuditState(target_url=target, normalized_domain=domain, brand=brand_name)
    findings = run_engagement_check(state)

    output = [f.to_dict() for f in findings]
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
