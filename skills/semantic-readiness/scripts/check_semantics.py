import sys
import os
import json
import re
from typing import List, Set, Tuple, Dict, Any, Optional
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
from core.classifier import classify_page

class SemanticDOMParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_json_ld = False
        self.json_ld_contents = []
        self.raw_text_segments = []
        self.images_without_alt = []
        self.total_images = 0
        self.canvases = []
        self.og_metadata = {}
        self.title_tag = ""
        self.in_title = False
        self.semantic_containers = set()
        self.js_framework_signatures = []
        self.has_microdata = False
        self.has_rdfa = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if "itemscope" in attrs_dict or "itemtype" in attrs_dict:
            self.has_microdata = True
        if "vocab" in attrs_dict or "typeof" in attrs_dict or "property" in attrs_dict:
            self.has_rdfa = True

        if tag in ["main", "article", "section", "header", "footer", "nav", "aside"]:
            self.semantic_containers.add(tag)

        if tag == "title":
            self.in_title = True

        elif tag == "script" and attrs_dict.get("type") == "application/ld+json":
            self.in_json_ld = True

        elif tag == "script" and attrs_dict.get("src"):
            src = attrs_dict.get("src", "")
            if any(sig in src.lower() for sig in ["next/static", "react-dom", "vue.js", "angular", "nuxt", "chunk.js"]):
                self.js_framework_signatures.append(src)

        elif tag == "meta":
            prop = attrs_dict.get("property") or attrs_dict.get("name", "")
            content = attrs_dict.get("content", "")
            if prop.startswith("og:") or prop.startswith("twitter:"):
                self.og_metadata[prop] = content

        elif tag == "img":
            self.total_images += 1
            src = attrs_dict.get("src", "")
            alt = attrs_dict.get("alt", "")
            if not alt or not alt.strip():
                self.images_without_alt.append(src)

        elif tag == "canvas":
            self.canvases.append(attrs_dict.get("id", "unlabeled-canvas"))

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_json_ld = False
        elif tag == "title":
            self.in_title = False

    def handle_data(self, data):
        cleaned = data.strip()
        if self.in_title:
            self.title_tag += data
        elif self.in_json_ld:
            self.json_ld_contents.append(data)
        elif cleaned:
            self.raw_text_segments.append(cleaned)

def _extract_schemas_recursive(item: Any, schemas: List[Tuple[str, Dict[str, Any]]]):
    """Recursively traverses JSON-LD objects supporting nested @graph structures."""
    if isinstance(item, list):
        for sub in item:
            _extract_schemas_recursive(sub, schemas)
    elif isinstance(item, dict):
        if "@graph" in item:
            _extract_schemas_recursive(item["@graph"], schemas)
        stype = item.get("@type")
        if stype:
            if isinstance(stype, list):
                for st in stype:
                    schemas.append((str(st), item))
            else:
                schemas.append((str(stype), item))

def parse_json_ld_blocks(blocks: List[str]) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[str]]:
    schemas = []
    syntax_errors = []
    for idx, b in enumerate(blocks):
        try:
            data = json.loads(b.strip())
            _extract_schemas_recursive(data, schemas)
        except Exception as e:
            syntax_errors.append(str(e))
    return schemas, syntax_errors

def run_semantics_check(state: AuditState) -> List[Finding]:
    domain = state.normalized_domain
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
            id="semantics-fetch-failed",
            title="Failed to fetch page HTML for semantic analysis",
            severity="critical",
            category="semantics",
            evidence=f"Could not retrieve HTML content for target '{url}'.",
            suggested_action=SuggestedAction(
                summary="Verify web server health and domain accessibility.",
                priority="critical"
            ),
            mechanism_impact="Semantic readiness audit requires HTML markup for parser inspection.",
            source_skill="semantic-readiness",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)
        return findings

    # Determine Page Archetype
    archetype = "GENERAL_CONTENT"
    if state.context and state.context.archetype:
        archetype = state.context.archetype
    else:
        headers = state.http_responses.get(domain, {}).get("headers", {})
        archetype = classify_page(html_content, url, headers)
        if state.context:
            state.context.archetype = archetype

    parser = SemanticDOMParser()
    parser.feed(html_content)

    schemas, syntax_errors = parse_json_ld_blocks(parser.json_ld_contents)
    found_types = set([s[0] for s in schemas])

    # Store in shared state for downstream skills
    state.extracted_content["title"] = parser.title_tag.strip()
    state.extracted_content["raw_text_segments"] = parser.raw_text_segments
    state.extracted_content["total_images"] = parser.total_images
    state.extracted_content["images_without_alt"] = parser.images_without_alt
    state.extracted_content["canvases"] = parser.canvases
    state.extracted_content["semantic_containers"] = list(parser.semantic_containers)
    state.extracted_content["js_framework_signatures"] = parser.js_framework_signatures

    state.structured_data["json_ld_blocks"] = parser.json_ld_contents
    state.structured_data["found_schemas"] = list(found_types)
    state.structured_data["parsed_schemas"] = schemas
    state.structured_data["og_metadata"] = parser.og_metadata
    state.structured_data["has_microdata"] = parser.has_microdata
    state.structured_data["has_rdfa"] = parser.has_rdfa
    state.rendering_metadata["js_framework_signatures"] = parser.js_framework_signatures

    if state.context:
        state.context.parsed_json_ld = [item for _, item in schemas]

    # Microdata / RDFa fallback signal recording
    if parser.has_microdata or parser.has_rdfa:
        state.add_evidence(
            url=url,
            page_context="Semantic Markup Fallback",
            observation=f"Discovered fallback semantic markup signals (Microdata: {parser.has_microdata}, RDFa: {parser.has_rdfa}).",
            status=EvidenceStatus.LIVE_OBSERVED,
            source_type="metadata",
            source_skill="semantic-readiness"
        )

    # Extract Organization Entity details for offsite corroboration skill
    org_item = None
    for stype, item in schemas:
        if stype in ["Organization", "Corporation", "Company", "EducationalOrganization", "GovOrganization"]:
            org_item = item
            break
    if org_item:
        state.entity_observations["detected_organization"] = {
            "name": org_item.get("name"),
            "url": org_item.get("url"),
            "sameAs": org_item.get("sameAs", []),
            "logo": org_item.get("logo")
        }
        if state.context:
            state.context.extracted_entities["organization"] = state.entity_observations["detected_organization"]

    full_text = " ".join(parser.raw_text_segments)
    full_text_lower = full_text.lower()

    # Detect non-commercial / documentation / utility portal
    page_path = domain.lower()
    is_non_commercial = archetype in ["DOCUMENTATION", "UTILITY_PORTAL"] or \
                        any(kw in page_path for kw in ["doc", "docs", "documentation", "blog", "dev", "developer", "api", "github.io", "github.com"]) or \
                        any(kw in full_text_lower[:500] for kw in ["documentation", "developer portal", "open-source", "open source", "api reference", "getting started guide"])
    state.entity_observations["is_non_commercial"] = is_non_commercial

    # 1. Report Explicit JSONLD_SYNTAX_ERROR Findings
    for idx, err in enumerate(syntax_errors):
        state.add_evidence(
            url=url,
            page_context=f"JSON-LD Block #{idx+1}",
            observation=f"Syntax error: {err}",
            status=EvidenceStatus.CONTRADICTED,
            source_type="metadata",
            source_skill="semantic-readiness"
        )
        f = Finding(
            id=f"semantics-jsonld-syntax-error-{idx}",
            title=f"JSONLD_SYNTAX_ERROR: Malformed JSON-LD Schema Block #{idx+1}",
            severity="critical",
            category="semantics",
            evidence=f"JSON parsing error in schema block #{idx+1}: {err}",
            suggested_action=SuggestedAction(
                summary=f"Fix JSON-LD syntax error in block #{idx+1}: {err}",
                priority="critical",
                recommendation=f"Ensure proper JSON escaping and closing syntax in block #{idx+1}. Exception: {err}"
            ),
            mechanism_impact="Syntax errors cause search engine schema parsers to reject the entire JSON-LD script block.",
            source_skill="semantic-readiness",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    # 2. Contextual Organization Entity Verification
    # Restrict Organization schema expectation to root homepages / about pages, and exempt UTILITY_PORTAL & DOCUMENTATION
    has_org_schema = any(st in found_types for st in ["Organization", "Corporation", "Company", "EducationalOrganization", "GovOrganization"])
    is_root_or_about = url.count("/") <= 3 or "/about" in url.lower() or "homepage" in url.lower()

    if not has_org_schema:
        if is_non_commercial or not is_root_or_about or archetype in ["UTILITY_PORTAL", "DOCUMENTATION"]:
            state.add_evidence(
                url=url,
                page_context="Schema.org Audit",
                observation=f"No Organization schema found, but page is classified as {archetype} or non-homepage. Expectation suppressed.",
                status=EvidenceStatus.NOT_APPLICABLE,
                source_type="metadata",
                source_skill="semantic-readiness"
            )
        else:
            state.add_evidence(
                url=url,
                page_context="Schema.org Audit",
                observation="No Organization schema found in page head/body.",
                status=EvidenceStatus.OBSERVED,
                source_type="metadata",
                source_skill="semantic-readiness"
            )
            brand_name = state.brand or domain.capitalize()
            dynamic_jsonld = json.dumps({
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": brand_name,
                "url": f"https://{domain}",
                "sameAs": []
            }, indent=2)

            f = Finding(
                id="semantics-schema-missing-organization",
                title="Missing Schema.org 'Organization' entity definition",
                severity="high",
                category="semantics",
                evidence="No 'Organization' or 'Corporation' JSON-LD schema found on primary landing page.",
                suggested_action=SuggestedAction(
                    summary=f"Inject a structured Organization JSON-LD script for '{brand_name}' on {domain}.",
                    priority="high",
                    recommendation=f'<script type="application/ld+json">\n{dynamic_jsonld}\n</script>'
                ),
                mechanism_impact="Without an Organization schema, LLMs cannot unambiguously map the brand entity to its official domain.",
                source_skill="semantic-readiness",
                affected_urls=[url]
            )
            findings.append(f)
            state.add_finding(f)

    # 3. Schema.org Ontology Validation (Verify required properties on declared types)
    for stype, item in schemas:
        missing_fields = []
        if stype in ["WebPage", "Article", "TechArticle"]:
            if not item.get("name") and not item.get("headline"):
                missing_fields.append("name/headline")
        elif stype == "FAQPage":
            if not item.get("mainEntity"):
                missing_fields.append("mainEntity (Question/Answer array)")
        elif stype == "SoftwareApplication":
            if not item.get("name") or not item.get("operatingSystem"):
                missing_fields.append("name/operatingSystem")

        if missing_fields:
            f = Finding(
                id=f"semantics-schema-incomplete-{stype.lower()}",
                title=f"Incomplete Schema.org '{stype}' structure (Missing {', '.join(missing_fields)})",
                severity="medium",
                category="semantics",
                evidence=f"Schema block for '{stype}' lacks essential ontology attributes: {', '.join(missing_fields)}.",
                suggested_action=SuggestedAction(
                    summary=f"Populate missing Schema.org '{stype}' attributes: {', '.join(missing_fields)}.",
                    priority="medium"
                ),
                mechanism_impact="Incomplete Schema.org structures reduce entity confidence during AI knowledge graph extraction.",
                source_skill="semantic-readiness",
                affected_urls=[url]
            )
            findings.append(f)
            state.add_finding(f)

    # 4. Contextual Product Check (ONLY if commercial purchase/cart signals exist AND not non-commercial)
    has_product_signals = bool(re.search(r'\b(add to cart|buy now|shopping cart|in stock|price:\s*\$|\$\d+\.\d{2})\b', full_text_lower, re.I))
    state.entity_observations["has_product_signals"] = has_product_signals
    if has_product_signals and not is_non_commercial and "Product" not in found_types:
        f = Finding(
            id="semantics-schema-missing-product",
            title="Missing Schema.org 'Product' markup on commercial page",
            severity="medium",
            category="semantics",
            evidence="Page contains commercial product/purchase signals, but lacks structured Product JSON-LD schema.",
            suggested_action=SuggestedAction(
                summary="Add Product JSON-LD schema with name, description, image, and offers.",
                priority="medium"
            ),
            mechanism_impact="Generative shopping engines require Product schema to display pricing and stock status in AI cards.",
            source_skill="semantic-readiness",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    # 5. Contextual FAQ Check (ONLY if FAQ content patterns exist)
    has_faq_signals = bool(re.search(r'\b(frequently asked questions|faq|faqs)\b', full_text_lower, re.I))
    state.entity_observations["has_faq_signals"] = has_faq_signals
    if has_faq_signals and "FAQPage" not in found_types:
        f = Finding(
            id="semantics-schema-missing-faqpage",
            title="Missing Schema.org 'FAQPage' markup on Q&A content section",
            severity="medium",
            category="semantics",
            evidence="Page contains FAQ or question-and-answer content, but lacks FAQPage JSON-LD markup.",
            suggested_action=SuggestedAction(
                summary="Wrap FAQ content with FAQPage and Question/Answer JSON-LD blocks to boost generative AI direct answers.",
                priority="medium"
            ),
            mechanism_impact="Structured FAQ markup provides clean Q&A pairs for direct LLM response generation.",
            source_skill="semantic-readiness",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    # 6. OpenGraph Metadata Check (Exempt UTILITY_PORTAL)
    if archetype not in ["UTILITY_PORTAL"] and not parser.og_metadata.get("og:title") and not parser.og_metadata.get("og:description"):
        f = Finding(
            id="semantics-opengraph-missing",
            title="Missing OpenGraph social metadata (og:title, og:description)",
            severity="medium",
            category="semantics",
            evidence="No OpenGraph metadata tags discovered. OpenGraph tags provide secondary metadata fallbacks for AI summarizers.",
            suggested_action=SuggestedAction(
                summary="Add <meta property='og:title'> and <meta property='og:description'> tags.",
                priority="medium"
            ),
            mechanism_impact="AI snippet engines use OpenGraph tags as fallback titles and descriptions when standard tags are absent.",
            source_skill="semantic-readiness",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    # 7. Consolidated Image Alt Finding
    if parser.images_without_alt:
        count = len(parser.images_without_alt)
        f = Finding(
            id="semantics-images-missing-alt-consolidated",
            title=f"{count} image asset(s) lack 'alt' text accessibility descriptions",
            severity="medium",
            category="semantics",
            evidence=f"Found {count} image(s) out of {parser.total_images} total without 'alt' tags. Missing alt tags hide image text & context from multimodal AI scrapers.",
            suggested_action=SuggestedAction(
                summary="Provide descriptive alt attributes for all meaningful content images and hero banners.",
                priority="medium"
            ),
            mechanism_impact="Multimodal LLM vision scrapers rely on alt text to contextualize image contents.",
            source_skill="semantic-readiness",
            affected_urls=[url],
            evidence_details={"images": parser.images_without_alt[:10]}
        )
        findings.append(f)
        state.add_finding(f)

    # 8. Locked Canvas Text Check
    if parser.canvases:
        f = Finding(
            id="semantics-canvas-locked-text",
            title=f"{len(parser.canvases)} HTML5 <canvas> element(s) detected",
            severity="high",
            category="semantics",
            evidence=f"HTML5 <canvas> elements (IDs: {', '.join(parser.canvases)}) are invisible to text parsers and LLM RAG indexers.",
            suggested_action=SuggestedAction(
                summary="Mirror any text rendered inside canvas elements into accessible semantic fallback HTML tags.",
                priority="high"
            ),
            mechanism_impact="Text inside <canvas> nodes cannot be extracted by HTML chunkers or vector indexers.",
            source_skill="semantic-readiness",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    # 9. HTML5 Semantic Structural Sectioning Check (Exempt UTILITY_PORTAL)
    missing_containers = [t for t in ["main", "article", "header"] if t not in parser.semantic_containers]
    if missing_containers and archetype not in ["UTILITY_PORTAL"]:
        f = Finding(
            id="semantics-html5-structure-weak",
            title="Weak HTML5 semantic sectioning markup",
            severity="low",
            category="semantics",
            evidence=f"Document tree is missing HTML5 semantic tags: <{', <'.join(missing_containers)}>. Clean semantic sectioning improves RAG text chunking accuracy.",
            suggested_action=SuggestedAction(
                summary="Structure page content using standard HTML5 <main>, <header>, and <article> tags.",
                priority="low"
            ),
            mechanism_impact="Semantic containers assist RAG splitters in isolating main content from navigation noise.",
            source_skill="semantic-readiness",
            affected_urls=[url]
        )
        findings.append(f)
        state.add_finding(f)

    return findings

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No domain or URL provided"}))
        sys.exit(1)

    target = sys.argv[1]
    domain = target.replace("https://", "").replace("http://", "").split("/")[0]
    state = AuditState(target_url=target, normalized_domain=domain, brand=domain.capitalize())
    findings = run_semantics_check(state)

    output = [f.to_dict() for f in findings]
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
