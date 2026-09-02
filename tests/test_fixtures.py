import sys
import os
import json
import unittest
import importlib.util

workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from common.models import AuditState, Finding, SuggestedAction
from common.reasoning import DeterministicReasoningEngine

# Dynamically import check_semantics
semantics_path = os.path.join(workspace_root, "skills", "semantic-readiness", "scripts", "check_semantics.py")
spec_sem = importlib.util.spec_from_file_location("check_semantics", semantics_path)
sem_mod = importlib.util.module_from_spec(spec_sem)
spec_sem.loader.exec_module(sem_mod)

# Dynamically import run_audit orchestrator
orchestrator_path = os.path.join(workspace_root, "skills", "audit-orchestrator", "scripts", "run_audit.py")
spec_orch = importlib.util.spec_from_file_location("run_audit", orchestrator_path)
orch_mod = importlib.util.module_from_spec(spec_orch)
spec_orch.loader.exec_module(orch_mod)

class TestControlledGroundTruthFixtures(unittest.TestCase):

    def load_fixture(self, name: str) -> str:
        path = os.path.join(workspace_root, "tests", "fixtures", f"{name}.html")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_01_perfect_site_fixture_high_score(self):
        html = self.load_fixture("perfect-site")
        state = AuditState(target_url="perfectcorp.com", normalized_domain="perfectcorp.com", brand="PerfectCorp")
        state.http_responses["perfectcorp.com"] = {"success": True, "content": html, "latency_ms": 250}
        state.raw_html["perfectcorp.com"] = html
        
        findings = sem_mod.run_semantics_check(state)
        critical_or_high = [f for f in findings if f.severity in ["critical", "high"]]
        self.assertEqual(len(critical_or_high), 0)

    def test_02_missing_schema_fixture_detection(self):
        html = self.load_fixture("missing-schema-site")
        state = AuditState(target_url="missingschema.com", normalized_domain="missingschema.com", brand="MissingSchema")
        state.http_responses["missingschema.com"] = {"success": True, "content": html, "latency_ms": 300}
        state.raw_html["missingschema.com"] = html
        
        findings = sem_mod.run_semantics_check(state)
        schema_findings = [f for f in findings if "schema" in f.id.lower() or "organization" in f.title.lower()]
        self.assertGreater(len(schema_findings), 0)

    def test_03_missing_h1_fixture_detection(self):
        html = self.load_fixture("missing-h1-site")
        parser = sem_mod.SemanticDOMParser()
        parser.feed(html)
        
        eng_path = os.path.join(workspace_root, "skills", "engagement-audit", "scripts", "check_engagement.py")
        spec_eng = importlib.util.spec_from_file_location("check_engagement", eng_path)
        eng_mod = importlib.util.module_from_spec(spec_eng)
        spec_eng.loader.exec_module(eng_mod)
        
        eng_parser = eng_mod.EngagementDOMParser()
        eng_parser.feed(html)
        self.assertEqual(len(eng_parser.h1_headers), 0)

    def test_04_js_rendered_site_false_positive_control(self):
        state = AuditState(target_url="js-spa.com", normalized_domain="js-spa.com", brand="JSSPA")
        state.rendering_metadata["comparison"] = {
            "h1_revealed_via_js": True,
            "new_links_count": 6
        }
        f_h1 = Finding(
            id="engagement-h1-missing",
            title="Missing H1 heading tag on primary landing page",
            severity="high",
            category="engagement",
            evidence="No <h1> tag present in raw HTML",
            suggested_action=SuggestedAction("Fix H1")
        )
        updated, decision = DeterministicReasoningEngine.apply_false_positive_rules(f_h1, state)
        self.assertEqual(decision, "QUESTIONABLE")
        self.assertEqual(updated.severity, "low")
        self.assertEqual(updated.priority, "P3")
        self.assertIn("JavaScript client-side rendering", updated.title)

    def test_05_bad_images_fixture_consolidation(self):
        html = self.load_fixture("bad-images-site")
        parser = sem_mod.SemanticDOMParser()
        parser.feed(html)
        self.assertEqual(len(parser.images_without_alt), 10)
        
        state = AuditState(target_url="badimages.com", normalized_domain="badimages.com", brand="BadImages")
        state.raw_html["badimages.com"] = html
        findings = sem_mod.run_semantics_check(state)
        alt_findings = [f for f in findings if "alt" in f.id.lower() or "alt" in f.title.lower()]
        self.assertEqual(len(alt_findings), 1)
        self.assertIn("10 image asset(s)", alt_findings[0].title)

    def test_06_article_site_no_product_faq_penalties(self):
        html = self.load_fixture("article-site")
        state = AuditState(target_url="articledomain.com", normalized_domain="articledomain.com", brand="ArticleDomain")
        state.raw_html["articledomain.com"] = html
        findings = sem_mod.run_semantics_check(state)
        product_faq_penalties = [f for f in findings if f.id in ["semantics-schema-missing-product", "semantics-schema-missing-faqpage"]]
        self.assertEqual(len(product_faq_penalties), 0)

if __name__ == "__main__":
    unittest.main()
