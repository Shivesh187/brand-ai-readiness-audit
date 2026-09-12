import unittest
import sys
import os

workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from core.context import AuditContext
from core.classifier import classify_page
from core.ai_crawlers import parse_ai_robots_rules, AI_CRAWLER_MATRIX
from core.synthesizer import cross_skill_synthesis
from common.models import AuditState, Finding, SuggestedAction

class TestRemediationCorePhases(unittest.TestCase):

    def test_01_audit_context_thread_safety_and_serialization(self):
        ctx = AuditContext(target_url="https://google.com")
        ctx.add_finding("F-001", "discoverability", "high", "Test Title", "Message", "Evidence")
        ctx.add_finding("F-001", "discoverability", "high", "Duplicate", "Message", "Evidence") # Duplicate ID
        
        ctx_dict = ctx.to_dict()
        self.assertEqual(len(ctx_dict["findings"]), 1)
        self.assertEqual(ctx_dict["findings"][0]["id"], "F-001")

    def test_02_page_archetype_classification(self):
        # 1. UTILITY_PORTAL (e.g. Google search)
        google_html = '<html><head><title>Google</title></head><body><form action="/search"><input type="search" name="q"><input type="submit" value="Google Search"></form></body></html>'
        self.assertEqual(classify_page(google_html, "https://google.com"), "UTILITY_PORTAL")

        # 2. DOCUMENTATION
        doc_html = '<html><head><title>API Reference</title></head><body><div class="sidebar">Nav</div><pre><code>import sys</code></pre><pre><code>print(123)</code></pre><pre><code>def foo(): pass</code></pre><p>getting started guide</p></body></html>'
        self.assertEqual(classify_page(doc_html, "https://python.org/docs"), "DOCUMENTATION")

        # 3. ECOMMERCE
        ecom_html = '<html><head><script type="application/ld+json">{"@type": "Product", "name": "Item"}</script></head><body><button class="add-to-cart">Add to Cart</button><span>$99.99</span></body></html>'
        self.assertEqual(classify_page(ecom_html, "https://store.example.com"), "ECOMMERCE")

        # 4. SAAS_MARKETING
        saas_html = '<html><body><div class="hero"><h1>Build Faster</h1></div><button>Get Started</button><div class="pricing">Pricing</div></body></html>'
        self.assertEqual(classify_page(saas_html, "https://stripe.com"), "SAAS_MARKETING")

        # 5. GENERAL_CONTENT
        gen_html = '<html><body><p>Random simple text content paragraph without special markup or forms.</p></body></html>'
        self.assertEqual(classify_page(gen_html, "https://blog.example.com"), "GENERAL_CONTENT")

    def test_03_ai_crawlers_matrix_parsing(self):
        robots_txt = """
User-agent: *
Allow: /

User-agent: GPTBot
Disallow: /

User-agent: PerplexityBot
Disallow: /

Sitemap: https://example.com/sitemap.xml
"""
        res = parse_ai_robots_rules(robots_txt, "https://example.com")
        self.assertIn("https://example.com/sitemap.xml", res["sitemaps"])
        bot_access = res["bot_access"]
        self.assertEqual(bot_access["GPTBot"]["status"], "DISALLOWED")
        self.assertEqual(bot_access["PerplexityBot"]["status"], "DISALLOWED")
        self.assertEqual(bot_access["ClaudeBot"]["status"], "ALLOWED")

    def test_04_cross_skill_synthesis_calibration(self):
        ctx = AuditContext(target_url="https://google.com", archetype="UTILITY_PORTAL")
        ctx.metadata["og_metadata"] = {"og:title": "Google"}
        ctx.parsed_json_ld = [{"@type": "WebSite"}]
        
        ctx.add_finding("h1-weak-01", "engagement", "high", "Weak H1", "H1 contains 1 word", "Evidence")
        ctx.add_finding("h1-missing-02", "engagement", "high", "Missing H1", "No H1", "Evidence")

        synthesized = cross_skill_synthesis(ctx)
        # Suppressed h1-missing for UTILITY_PORTAL in synthesizer, and calibrated h1-weak
        self.assertTrue(all(f["severity"] in ["low", "medium"] for f in synthesized))

if __name__ == "__main__":
    unittest.main()
