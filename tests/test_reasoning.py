import sys
import os
import json
import unittest
import importlib.util

# Dynamically locate workspace root
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from common.models import Finding, SuggestedAction, AuditState
from common.reasoning import DeterministicReasoningEngine
from scripts.validate_marketplace import validate_marketplace

# Dynamically load run_audit orchestrator module
run_audit_path = os.path.join(workspace_root, "skills", "audit-orchestrator", "scripts", "run_audit.py")
spec = importlib.util.spec_from_file_location("run_audit", run_audit_path)
run_audit_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_audit_mod)
execute_audit_pipeline = run_audit_mod.execute_audit_pipeline

class TestDeterministicReasoningFramework(unittest.TestCase):

    def setUp(self):
        self.state = AuditState(target_url="testdomain.com", normalized_domain="testdomain.com", brand="TestBrand")

    def test_01_priority_derivation_critical_high_confidence(self):
        p = DeterministicReasoningEngine.calculate_priority("critical", 0.95)
        self.assertEqual(p, "P0")

    def test_02_priority_derivation_critical_low_confidence(self):
        p = DeterministicReasoningEngine.calculate_priority("critical", 0.40)
        self.assertEqual(p, "P2")

    def test_03_priority_derivation_high_severity(self):
        p = DeterministicReasoningEngine.calculate_priority("high", 0.85)
        self.assertEqual(p, "P1")

    def test_04_priority_derivation_medium_severity(self):
        p = DeterministicReasoningEngine.calculate_priority("medium", 0.75)
        self.assertEqual(p, "P2")

    def test_05_priority_derivation_low_severity(self):
        p = DeterministicReasoningEngine.calculate_priority("low", 0.90)
        self.assertEqual(p, "P3")

    def test_06_false_positive_h1_revealed_via_js(self):
        self.state.rendering_metadata["comparison"] = {"h1_revealed_via_js": True}
        f = Finding(id="F-H1-01", title="Missing H1 Tag", severity="high", category="semantics", evidence="No H1 in raw HTML.", suggested_action=SuggestedAction("Fix H1"))
        
        updated, decision = DeterministicReasoningEngine.apply_false_positive_rules(f, self.state)
        self.assertEqual(decision, "QUESTIONABLE")
        self.assertEqual(updated.severity, "low")
        self.assertEqual(updated.priority, "P3")
        self.assertEqual(updated.confidence, 0.50)
        self.assertIn("JavaScript client-side rendering", updated.title)

    def test_07_false_positive_links_revealed_via_js(self):
        self.state.rendering_metadata["comparison"] = {"new_links_count": 12}
        f = Finding(id="F-LINK-01", title="Missing Navigation Links", severity="high", category="discoverability", evidence="Raw HTML lacks links.", suggested_action=SuggestedAction("Fix links"))
        
        updated, decision = DeterministicReasoningEngine.apply_false_positive_rules(f, self.state)
        self.assertEqual(decision, "VALID")
        self.assertEqual(updated.severity, "medium")
        self.assertEqual(updated.priority, "P2")
        self.assertIn("Discovered 12 critical navigation links", updated.why_it_matters)

    def test_08_organization_schema_with_wikidata_corroboration(self):
        self.state.entity_observations["wikidata_entity"] = {"id": "Q999", "label": "TestBrand"}
        f = Finding(id="F-ORG-SCHEMA", title="Missing Organization Schema", severity="high", category="semantics", evidence="No schema found.", suggested_action=SuggestedAction("Add schema"))
        
        updated, decision = DeterministicReasoningEngine.apply_false_positive_rules(f, self.state)
        self.assertEqual(decision, "VALID")
        self.assertEqual(updated.confidence, 0.85)
        self.assertIn("Q999", updated.suggested_action.summary)

    def test_09_confidence_guardrail_severity_downgrade(self):
        f = Finding(id="F-TEST", title="Low Confidence Bug", severity="critical", category="semantics", evidence="Weak signal", suggested_action=SuggestedAction("Fix"), confidence=0.20)
        self.state.add_finding(f)
        
        results = DeterministicReasoningEngine.enrich_and_validate_findings(self.state)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].severity, "medium")
        self.assertEqual(results[0].priority, "P2")

    def test_10_non_generic_why_it_matters_generation(self):
        f = Finding(id="F-TEST", title="Test Issue", severity="medium", category="engagement", evidence="Low text density", suggested_action=SuggestedAction("Increase text"))
        self.state.add_finding(f)
        
        results = DeterministicReasoningEngine.enrich_and_validate_findings(self.state)
        self.assertIn("TestBrand", results[0].why_it_matters)
        self.assertIn("testdomain.com", results[0].why_it_matters)

    def test_11_marketplace_validator_script_executes(self):
        valid, errors = validate_marketplace()
        self.assertTrue(valid)
        self.assertEqual(len(errors), 0)

    def test_12_finding_to_dict_schema_contains_priority_and_why_it_matters(self):
        f = Finding(id="F-001", title="Test", severity="high", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix"))
        d = f.to_dict()
        self.assertIn("priority", d)
        self.assertIn("why_it_matters", d)
        self.assertIn("reasoning_source", d)
        self.assertEqual(d["priority"], "P1")
        self.assertEqual(d["reasoning_source"], "deterministic")

    def test_13_deduplication_preserves_higher_confidence(self):
        f1 = Finding(id="F-001", title="Duplicate Title", severity="medium", category="semantics", evidence="Ev1", suggested_action=SuggestedAction("Fix1"), confidence=0.60)
        f2 = Finding(id="F-001", title="Duplicate Title", severity="medium", category="semantics", evidence="Ev2", suggested_action=SuggestedAction("Fix2"), confidence=0.95)
        self.state.add_finding(f1)
        self.state.add_finding(f2)
        
        results = DeterministicReasoningEngine.enrich_and_validate_findings(self.state)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].confidence, 0.95)

    def test_14_arbitrary_domain_generalization(self):
        report = execute_audit_pipeline("arbitrary-saas-website.io", "ArbitrarySaaS", enable_llm=False)
        self.assertEqual(report.site, "arbitrary-saas-website.io")
        self.assertGreater(len(report.findings), 0)
        for f in report.findings:
            self.assertIn(f.priority, ["P0", "P1", "P2", "P3"])

    def test_15_empty_html_response_handling(self):
        self.state.raw_html["testdomain.com"] = ""
        results = DeterministicReasoningEngine.enrich_and_validate_findings(self.state)
        self.assertIsInstance(results, list)

    def test_16_invalid_schema_jsonld_parsing(self):
        self.state.raw_html["testdomain.com"] = '<script type="application/ld+json">{invalid json}</script>'
        results = DeterministicReasoningEngine.enrich_and_validate_findings(self.state)
        self.assertIsInstance(results, list)

    def test_17_sitemap_recommendation_injection(self):
        report = execute_audit_pipeline("example.com", "Example", enable_llm=False)
        sitemap_recs = [f for f in report.findings if "sitemap" in f.id.lower() or "sitemap" in f.title.lower()]
        self.assertGreater(len(sitemap_recs), 0)
        self.assertTrue(any("sitemap" in f.suggested_action.summary.lower() for f in sitemap_recs))

    def test_18_organization_recommendation_injection(self):
        report = execute_audit_pipeline("example.com", "Example", enable_llm=False)
        org_recs = [f for f in report.findings if "sameas" in f.title.lower() or "organization" in f.title.lower() or "organization" in f.suggested_action.summary.lower()]
        self.assertGreater(len(org_recs), 0)
        self.assertTrue(any("organization" in f.suggested_action.summary.lower() or "sameas" in f.suggested_action.summary.lower() for f in org_recs))

    def test_19_adversarial_invalid_domain_fails_gracefully(self):
        report = execute_audit_pipeline("invalid-domain-xxxx-999.xyz", "InvalidDomain", enable_llm=False)
        self.assertEqual(report.site, "invalid-domain-xxxx-999.xyz")
        self.assertGreater(len(report.findings), 0)
        self.assertIn("critical", report.summary)

    def test_20_adversarial_redirecting_website(self):
        from common.crawler import EnhancedCrawler
        res = EnhancedCrawler.parse_robots_txt("User-agent: GPTBot\nDisallow: /")
        self.assertIn("GPTBot", res["disallowed_bots"])

    def test_21_adversarial_page_with_excellent_structured_data(self):
        semantics_path = os.path.join(workspace_root, "skills", "semantic-readiness", "scripts", "check_semantics.py")
        spec_sem = importlib.util.spec_from_file_location("check_semantics", semantics_path)
        sem_mod = importlib.util.module_from_spec(spec_sem)
        spec_sem.loader.exec_module(sem_mod)
        
        valid_json_ld = '''
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "ExcellentCorp",
            "url": "https://excellentcorp.com"
        }
        '''
        parser = sem_mod.SemanticDOMParser()
        parser.feed(f'<script type="application/ld+json">{valid_json_ld}</script>')
        schemas, errors = sem_mod.parse_json_ld_blocks(parser.json_ld_contents)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0][0], "Organization")

    def test_22_adversarial_image_alt_aggregation(self):
        semantics_path = os.path.join(workspace_root, "skills", "semantic-readiness", "scripts", "check_semantics.py")
        spec_sem = importlib.util.spec_from_file_location("check_semantics", semantics_path)
        sem_mod = importlib.util.module_from_spec(spec_sem)
        spec_sem.loader.exec_module(sem_mod)
        
        parser = sem_mod.SemanticDOMParser()
        html = '<div><img src="1.png"><img src="2.png" alt=""><img src="3.png" alt="Valid"></div>'
        parser.feed(html)
        self.assertEqual(len(parser.images_without_alt), 2)
        self.assertEqual(parser.total_images, 3)

    def test_23_adversarial_gemini_503_outage_fallback(self):
        from common.llm_client import GLOBAL_CIRCUIT_BREAKER
        from unittest.mock import patch
        import urllib.error
        GLOBAL_CIRCUIT_BREAKER.reset()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock_key", "GEMINI_MAX_RETRIES": "0"}):
            with patch('urllib.request.urlopen') as mock_url:
                mock_url.side_effect = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)
                report = execute_audit_pipeline("example.com", "Example", enable_llm=True)
                self.assertEqual(report.llm_observations["status"], "PROVIDER_UNAVAILABLE")
                self.assertTrue(report.llm_observations["fallback_used"])
                self.assertGreater(len(report.findings), 0)

    def test_24_adversarial_gemini_timeout_fallback(self):
        from common.llm_client import GLOBAL_CIRCUIT_BREAKER
        from unittest.mock import patch
        import socket
        GLOBAL_CIRCUIT_BREAKER.reset()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock_key", "GEMINI_MAX_RETRIES": "0"}):
            with patch('urllib.request.urlopen') as mock_url:
                mock_url.side_effect = socket.timeout("timed out")
                report = execute_audit_pipeline("example.com", "Example", enable_llm=True)
                self.assertEqual(report.llm_observations["status"], "TIMEOUT")
                self.assertTrue(report.llm_observations["fallback_used"])
                self.assertGreater(len(report.findings), 0)

    def test_25_adversarial_gemini_429_rate_limit_fallback(self):
        from common.llm_client import GLOBAL_CIRCUIT_BREAKER
        from unittest.mock import patch
        import urllib.error
        GLOBAL_CIRCUIT_BREAKER.reset()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock_key", "GEMINI_MAX_RETRIES": "0"}):
            with patch('urllib.request.urlopen') as mock_url:
                mock_url.side_effect = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
                report = execute_audit_pipeline("example.com", "Example", enable_llm=True)
                self.assertEqual(report.llm_observations["status"], "RATE_LIMITED")
                self.assertTrue(report.llm_observations["fallback_used"])

    def test_26_adversarial_malformed_html_parsing(self):
        semantics_path = os.path.join(workspace_root, "skills", "semantic-readiness", "scripts", "check_semantics.py")
        spec_sem = importlib.util.spec_from_file_location("check_semantics", semantics_path)
        sem_mod = importlib.util.module_from_spec(spec_sem)
        spec_sem.loader.exec_module(sem_mod)
        
        malformed = '<html><head><title>Test<script>unclosed<div><span>'
        parser = sem_mod.SemanticDOMParser()
        parser.feed(malformed)
        self.assertIsInstance(parser.semantic_containers, set)

    def test_27_adversarial_empty_html_handling(self):
        report = execute_audit_pipeline("emptyhtml-site.io", "EmptyHTML", enable_llm=False)
        self.assertEqual(report.site, "emptyhtml-site.io")
        self.assertIsInstance(report.readiness_score, int)

    def test_28_adversarial_score_integrity_zero_findings(self):
        from common.models import AuditReport
        state = AuditState(target_url="perfect.com", normalized_domain="perfect.com", brand="Perfect")
        report = AuditReport(site="perfect.com", brand="Perfect", findings=[])
        report.compute_scores_and_summary()
        self.assertEqual(report.readiness_score, 100)

    def test_29_adversarial_all_15_fields_present_in_finding_dict(self):
        f = Finding(
            id="F-TEST-15",
            title="Field Audit Test",
            severity="high",
            category="semantics",
            evidence="Observed 10 items",
            suggested_action=SuggestedAction("Fix", "Do X", "high"),
            confidence=0.90,
            source_skill="semantic-readiness",
            evidence_origin="LIVE_OBSERVED",
            affected_urls=["https://test.com"]
        )
        d = f.to_dict()
        required_keys = ["id", "title", "severity", "priority", "category", "evidence", "why_it_matters", "suggested_action", "confidence", "reasoning_source", "evidence_origin", "source_skill", "affected_urls"]
        for k in required_keys:
            self.assertIn(k, d)

if __name__ == "__main__":
    unittest.main()
