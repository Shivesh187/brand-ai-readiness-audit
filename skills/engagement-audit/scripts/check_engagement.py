import urllib.request
import json
import sys
import re
from html.parser import HTMLParser

class EngagementParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_content = []
        self.h1_headers = []
        self.meta_desc = ""
        self.in_h1 = False
        self.in_script_or_style = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in ["script", "style"]:
            self.in_script_or_style = True
        elif tag == "meta" and attrs_dict.get("name") == "description":
            self.meta_desc = attrs_dict.get("content", "")
        elif tag == "h1":
            self.in_h1 = True

    def handle_endtag(self, tag):
        if tag in ["script", "style"]:
            self.in_script_or_style = False
        elif tag == "h1":
            self.in_h1 = False

    def handle_data(self, data):
        if self.in_script_or_style:
            return
        cleaned = data.strip()
        if cleaned:
            self.text_content.append(cleaned)
            if self.in_h1:
                self.h1_headers.append(cleaned)

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: check_engagement.py <domain_or_url> <brand_name>"}))
        sys.exit(1)
        
    target = sys.argv[1]
    brand_name = sys.argv[2]
    url = target if target.startswith("http") else f"https://{target}"
    findings = []
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5.0) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        findings.append({
            "id": "engagement-fetch-failed",
            "title": "Failed to fetch page HTML for engagement audit",
            "severity": "critical",
            "evidence": str(e),
            "suggested_action": {
                "summary": "Check domain connectivity and confirm target is serving HTML content.",
                "priority": 1
            }
        })
        print(json.dumps(findings, indent=2))
        sys.exit(0)
        
    parser = EngagementParser()
    parser.feed(html)
    
    total_html_len = len(html)
    all_body_text = " ".join(parser.text_content)
    total_text_len = len(all_body_text)
    
    text_to_code_ratio = total_text_len / total_html_len if total_html_len > 0 else 0
    
    # Extract first 200 words
    words = all_body_text.split()
    preview_words = words[:200]
    preview_text = " ".join(preview_words)
    
    # 1. Check above-the-fold layout and H1 presence
    if not parser.h1_headers:
        findings.append({
            "id": "engagement-h1-missing",
            "title": "Missing H1 heading on landing page",
            "severity": "high",
            "evidence": "No <h1> elements found in the document tree.",
            "suggested_action": {
                "summary": "Place a single H1 header containing the core value proposition at the top of the content tree.",
                "priority": 2
            }
        })
    else:
        h1_text = " ".join(parser.h1_headers)
        if len(h1_text.split()) < 3:
            findings.append({
                "id": "engagement-h1-weak",
                "title": "Weak or overly short H1 header content",
                "severity": "medium",
                "evidence": f"H1 value: '{h1_text}' (less than 3 words)",
                "suggested_action": {
                    "summary": "Elaborate the H1 content to communicate a clear, context-rich brand proposition.",
                    "priority": 3
                }
            })
            
    # 2. Check text-to-code markup ratio (bloat analysis)
    if text_to_code_ratio < 0.15:
        findings.append({
            "id": "engagement-code-bloat",
            "title": "Excessive code-to-text ratio (code bloat)",
            "severity": "medium",
            "evidence": f"Text ratio is {round(text_to_code_ratio * 100, 2)}% (Threshold: 15%)",
            "suggested_action": {
                "summary": "Reduce unused scripts and markup, compress styles, and increase on-page textual content density.",
                "priority": 3
            }
        })
        
    # 3. Evaluate email/page content for AI-generated preview summarization readiness
    meta_len = len(parser.meta_desc)
    if meta_len == 0:
        findings.append({
            "id": "engagement-meta-missing",
            "title": "Missing meta description",
            "severity": "high",
            "evidence": "No meta name='description' tag found.",
            "suggested_action": {
                "summary": "Add a meta description to summarize page value, serving as a primary target for LLM card summaries.",
                "priority": 2
            }
        })
    elif meta_len < 110 or meta_len > 160:
        findings.append({
            "id": "engagement-meta-length-suboptimal",
            "title": "Suboptimal meta description length",
            "severity": "medium",
            "evidence": f"Meta description length is {meta_len} chars (Recommended: 110-160)",
            "suggested_action": {
                "summary": "Revise the meta description to fit within the optimal length boundaries.",
                "priority": 3
            }
        })
        
    # Check if brand name is in the first 200 words preview
    if brand_name.lower() not in preview_text.lower():
        findings.append({
            "id": "engagement-preview-missing-brand",
            "title": "First 200 words lack clear brand entity association",
            "severity": "medium",
            "evidence": f"First 200 words: '{preview_text[:120]}...'",
            "suggested_action": {
                "summary": f"Incorporate the brand name '{brand_name}' near the start of the landing page text to enforce entity grounding.",
                "priority": 3
            }
        })
        
    # Check if preview text is too short overall
    if len(words) < 200:
        findings.append({
            "id": "engagement-content-too-short",
            "title": "Content is too sparse for deep preview generation",
            "severity": "high",
            "evidence": f"Total page word count: {len(words)} (Recommended: >200 words for preview indexing)",
            "suggested_action": {
                "summary": "Flesh out page details and descriptions to provide RAG chunkers sufficient context.",
                "priority": 2
            }
        })
        
    print(json.dumps(findings, indent=2))

if __name__ == "__main__":
    main()
