import urllib.request
import json
import sys
import re
from html.parser import HTMLParser

class SemanticParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_json_ld = False
        self.json_ld_contents = []
        self.raw_text_segments = []
        self.images = []
        self.canvases = []
        self.js_framework_signatures = []
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        # Check for JSON-LD script blocks
        if tag == "script" and attrs_dict.get("type") == "application/ld+json":
            self.in_json_ld = True
            
        # Check for client-side framework scripts / hydration indicators
        if tag == "script" and attrs_dict.get("src"):
            src = attrs_dict.get("src", "")
            if any(sig in src.lower() for sig in ["next/static", "react-dom", "vue.js", "angular", "nuxt", "chunk.js"]):
                self.js_framework_signatures.append(src)
                
        if tag == "div" and attrs_dict.get("id") in ["__next", "root", "app"]:
            self.js_framework_signatures.append(f"div#{attrs_dict.get('id')}")
            
        elif tag == "img":
            self.images.append({
                "src": attrs_dict.get("src", ""),
                "alt": attrs_dict.get("alt", "")
            })
            
        elif tag == "canvas":
            self.canvases.append(attrs_dict.get("id", "unlabeled"))

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_json_ld = False

    def handle_data(self, data):
        cleaned = data.strip()
        if self.in_json_ld:
            self.json_ld_contents.append(data)
        elif cleaned:
            self.raw_text_segments.append(cleaned)

def check_json_ld(blocks):
    schemas = []
    issues = []
    
    for idx, block in enumerate(blocks):
        try:
            data = json.loads(block.strip())
            items = data if isinstance(data, list) else [data]
            for item in items:
                schema_type = item.get("@type")
                if schema_type:
                    schemas.append((schema_type, item))
                else:
                    issues.append({
                        "error": "Missing '@type' property in JSON-LD",
                        "block_index": idx
                    })
        except Exception as e:
            issues.append({
                "error": f"JSON parse error: {str(e)}",
                "block_index": idx
            })
            
    return schemas, issues

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No domain or URL provided"}))
        sys.exit(1)
        
    target = sys.argv[1]
    url = target if target.startswith("http") else f"https://{target}"
    findings = []
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5.0) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        findings.append({
            "id": "semantics-fetch-failed",
            "title": "Failed to fetch page HTML for semantic analysis",
            "severity": "critical",
            "evidence": str(e),
            "suggested_action": {
                "summary": "Check domain connectivity and confirm target is serving HTML content.",
                "priority": 1
            }
        })
        print(json.dumps(findings, indent=2))
        sys.exit(0)
        
    parser = SemanticParser()
    parser.feed(html)
    
    schemas, parse_issues = check_json_ld(parser.json_ld_contents)
    
    # 1. Report JSON-LD Syntax errors
    for issue in parse_issues:
        findings.append({
            "id": f"semantics-jsonld-syntax-error-{issue['block_index']}",
            "title": "Malformed Schema JSON-LD Block",
            "severity": "critical",
            "evidence": issue["error"],
            "suggested_action": {
                "summary": "Validate and fix schema structures using JSON validators.",
                "priority": 1
            }
        })
        
    # 2. Check for missing core schemas (Product, Organization, FAQPage)
    found_types = [s[0] for s in schemas]
    for core_type in ["Organization", "Product", "FAQPage"]:
        if core_type not in found_types:
            findings.append({
                "id": f"semantics-schema-missing-{core_type.lower()}",
                "title": f"Missing Schema.org Type: {core_type}",
                "severity": "high" if core_type == "Organization" else "medium",
                "evidence": f"Found schemas: {', '.join(found_types) if found_types else 'None'}",
                "suggested_action": {
                    "summary": f"Inject a valid <script type='application/ld+json'> block for type '{core_type}' on relevant pages.",
                    "priority": 2
                }
            })
            
    # 3. Detect client-side JS rendering gaps (Hydration / Blank raw HTML)
    total_raw_text = " ".join(parser.raw_text_segments)
    is_client_rendered = len(parser.js_framework_signatures) > 0
    
    if is_client_rendered and len(total_raw_text) < 400:
        findings.append({
            "id": "semantics-js-hydration-gap",
            "title": "Severe client-side JS rendering gap detected",
            "severity": "critical",
            "evidence": f"Client-side signatures found: {parser.js_framework_signatures}. Raw HTML text body is only {len(total_raw_text)} chars.",
            "suggested_action": {
                "summary": "Implement Server-Side Rendering (SSR) or Static Site Generation (SSG) to ensure static crawlers can read the body.",
                "priority": 1
            }
        })
        
    # 4. Detect text locked inside canvas or image tags without alt
    for idx, img in enumerate(parser.images):
        if not img["alt"]:
            findings.append({
                "id": f"semantics-image-missing-alt-{idx}",
                "title": f"Image missing alt attribute: {img['src'][:60]}",
                "severity": "medium",
                "evidence": f"Image source: {img['src']}",
                "suggested_action": {
                    "summary": "Provide descriptive 'alt' tags to allow AI crawlers and vision APIs to index image text/context.",
                    "priority": 3
                }
            })
            
    for idx, canvas_id in enumerate(parser.canvases):
        findings.append({
            "id": f"semantics-canvas-locked-text-{idx}",
            "title": f"Render canvas element detected: id={canvas_id}",
            "severity": "high",
            "evidence": "HTML5 <canvas> elements are invisible to structural crawlers",
            "suggested_action": {
                "summary": "Ensure any text or critical labels inside the canvas are mirrored as structured text in screen-reader fallback tags.",
                "priority": 2
            }
        })
        
    print(json.dumps(findings, indent=2))

if __name__ == "__main__":
    main()
