import sys
import os
import json
import time
import unittest
from unittest.mock import patch, MagicMock

# Dynamically locate workspace root
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from common.models import AuditState, Finding, AuditReport, EvidenceStatus, SuggestedAction
import importlib.util

def load_script_module(relative_path: str, module_name: str):
    full_path = os.path.join(workspace_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, full_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

check_corroboration = load_script_module(os.path.join("skills", "freshness-corroboration", "scripts", "check_corroboration.py"), "check_corroboration")
run_audit_mod = load_script_module(os.path.join("skills", "audit-orchestrator", "scripts", "run_audit.py"), "run_audit_mod")

class TestKnowledgeGraphCorroboration(unittest.TestCase):

    def setUp(self):
        check_corroboration.clear_entity_cache()

    # 1. Wikidata Success
    @patch.object(check_corroboration, 'fetch_url')
    def test_01_wikidata_success(self, mock_fetch):
        mock_fetch.side_effect = [
            # Wikidata response
            {"success": True, "content": json.dumps({"search": [{"id": "Q166453", "label": "Stripe", "description": "Financial software company", "concepturi": "https://www.wikidata.org/wiki/Q166453"}]}), "error": None},
            # Wikipedia response
            {"success": True, "content": json.dumps({"type": "standard", "title": "Stripe, Inc.", "extract": "Stripe is a financial infrastructure platform.", "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Stripe,_Inc."}}}), "error": None}
        ]

        state = AuditState(target_url="stripe.com", normalized_domain="stripe.com", brand="Stripe")
        findings = check_corroboration.run_corroboration_check(state)

        obs = state.corroboration_observations
        self.assertEqual(obs.get("wikidata_status"), "SUCCESS")
        self.assertEqual(obs.get("wikipedia_status"), "SUCCESS")
        self.assertEqual(obs.get("final_status"), "VERIFIED")
        self.assertIsNotNone(obs.get("wikidata_entity"))
        self.assertEqual(obs.get("wikidata_entity").get("id"), "Q166453")

    # 2. Wikidata Timeout
    @patch.object(check_corroboration, 'fetch_url')
    def test_02_wikidata_timeout(self, mock_fetch):
        mock_fetch.side_effect = [
            # Wikidata timeout
            {"success": False, "content": None, "error": "Connection timed out"},
            # Wikipedia success
            {"success": True, "content": json.dumps({"type": "standard", "title": "Stripe", "extract": "Stripe page."}), "error": None}
        ]

        state = AuditState(target_url="stripe.com", normalized_domain="stripe.com", brand="Stripe")
        check_corroboration.run_corroboration_check(state)

        obs = state.corroboration_observations
        self.assertEqual(obs.get("wikidata_status"), "TIMEOUT")
        self.assertEqual(obs.get("final_status"), "VERIFIED")
        self.assertTrue(obs.get("fallback_used"))

    # 3. Wikidata HTTP Error
    @patch.object(check_corroboration, 'fetch_url')
    def test_03_wikidata_http_error(self, mock_fetch):
        mock_fetch.side_effect = [
            # Wikidata HTTP 503
            {"success": False, "content": None, "error": "HTTP 503 Service Unavailable"},
            # Wikipedia error
            {"success": False, "content": None, "error": "HTTP 500"}
        ]

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        check_corroboration.run_corroboration_check(state)

        obs = state.corroboration_observations
        self.assertEqual(obs.get("wikidata_status"), "ERROR")
        self.assertEqual(obs.get("wikipedia_status"), "ERROR")
        self.assertEqual(obs.get("final_status"), "UNAVAILABLE")

    # 4. Wikidata Malformed Response
    @patch.object(check_corroboration, 'fetch_url')
    def test_04_wikidata_malformed_response(self, mock_fetch):
        mock_fetch.side_effect = [
            # Malformed JSON
            {"success": True, "content": "<html>502 Bad Gateway</html>", "error": None},
            # Wikipedia fail
            {"success": False, "content": None, "error": "Error"}
        ]

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        check_corroboration.run_corroboration_check(state)

        obs = state.corroboration_observations
        self.assertEqual(obs.get("wikidata_status"), "ERROR")

    # 5. Wikipedia Fallback
    @patch.object(check_corroboration, 'fetch_url')
    def test_05_wikipedia_fallback(self, mock_fetch):
        mock_fetch.side_effect = [
            # Wikidata error
            {"success": False, "content": None, "error": "HTTP 503"},
            # Wikipedia success
            {"success": True, "content": json.dumps({"type": "standard", "title": "Example Corp", "extract": "Example Corp software."}), "error": None}
        ]

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        check_corroboration.run_corroboration_check(state)

        obs = state.corroboration_observations
        self.assertEqual(obs.get("wikidata_status"), "ERROR")
        self.assertEqual(obs.get("wikipedia_status"), "SUCCESS")
        self.assertEqual(obs.get("final_status"), "VERIFIED")

    # 6. Both External Providers Unavailable
    @patch.object(check_corroboration, 'fetch_url')
    def test_06_both_external_providers_unavailable(self, mock_fetch):
        mock_fetch.return_value = {"success": False, "content": None, "error": "Timeout"}

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        check_corroboration.run_corroboration_check(state)

        obs = state.corroboration_observations
        self.assertEqual(obs.get("final_status"), "UNAVAILABLE")
        # Ensure UNAVAILABLE evidence item created
        unavail_ev = [e for e in state.evidence_records if e.status == EvidenceStatus.UNAVAILABLE]
        self.assertTrue(len(unavail_ev) > 0)

    # 7. Cache Hit
    @patch.object(check_corroboration, 'fetch_url')
    def test_07_cache_hit(self, mock_fetch):
        mock_fetch.side_effect = [
            {"success": True, "content": json.dumps({"search": [{"id": "Q12345", "label": "Acme", "description": "Acme software company"}]}), "error": None},
            {"success": True, "content": json.dumps({"type": "standard", "title": "Acme Corp", "extract": "Extract"}), "error": None}
        ]

        state1 = AuditState(target_url="acme.com", normalized_domain="acme.com", brand="Acme")
        check_corroboration.run_corroboration_check(state1)
        self.assertEqual(mock_fetch.call_count, 2)

        # Second audit for same brand uses process-local cache
        state2 = AuditState(target_url="acme.com", normalized_domain="acme.com", brand="Acme")
        check_corroboration.run_corroboration_check(state2)
        # Call count remains 2!
        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual(state2.corroboration_observations.get("wikidata_entity").get("id"), "Q12345")

    # 8. Cache Expiration & Transient Failures Not Cached
    @patch.object(check_corroboration, 'fetch_url')
    def test_08_cache_expiration_and_transient_failures(self, mock_fetch):
        mock_fetch.return_value = {"success": False, "content": None, "error": "Timeout"}

        state1 = AuditState(target_url="fail.com", normalized_domain="fail.com", brand="Fail")
        check_corroboration.run_corroboration_check(state1)

        # Transient failures must NOT be cached
        state2 = AuditState(target_url="fail.com", normalized_domain="fail.com", brand="Fail")
        check_corroboration.run_corroboration_check(state2)
        self.assertEqual(mock_fetch.call_count, 4) # Retried network call!

    # 9. False Common-Name Entity Mismatch Prevention
    @patch.object(check_corroboration, 'fetch_url')
    def test_09_false_common_name_entity_mismatch(self, mock_fetch):
        mock_fetch.side_effect = [
            # Common noun "Stripe" returning a pattern/textile entry
            {"success": True, "content": json.dumps({"search": [{"id": "Q1000", "label": "stripe", "description": "line or band that differs in color"}]}), "error": None},
            {"success": False, "content": None, "error": "None"}
        ]

        state = AuditState(target_url="stripe.com", normalized_domain="stripe.com", brand="Stripe")
        check_corroboration.run_corroboration_check(state)

        # Must reject textile stripe entity for Stripe brand!
        self.assertIsNone(state.corroboration_observations.get("wikidata_entity"))

    # 10. Verified sameAs Entity Matching
    @patch.object(check_corroboration, 'fetch_url')
    def test_10_verified_same_as_entity(self, mock_fetch):
        mock_fetch.side_effect = [
            # Returns entity Q166453 matching explicit sameAs link
            {"success": True, "content": json.dumps({"search": [{"id": "Q166453", "label": "Stripe", "description": "some description"}]}), "error": None},
            {"success": False, "content": None, "error": "None"}
        ]

        state = AuditState(target_url="stripe.com", normalized_domain="stripe.com", brand="Stripe")
        state.extracted_content["same_as_links"] = ["https://www.wikidata.org/wiki/Q166453"]
        check_corroboration.run_corroboration_check(state)

        self.assertIsNotNone(state.corroboration_observations.get("wikidata_entity"))
        self.assertEqual(state.corroboration_observations.get("wikidata_entity").get("id"), "Q166453")

    # 11. UNAVAILABLE Does Not Reduce Readiness Score
    def test_11_unavailable_does_not_reduce_readiness_score(self):
        f_unavail = Finding(
            id="F-TELEMETRY-UNAVAIL",
            title="External Telemetry Unavailable",
            severity="critical",
            category="corroboration",
            evidence="Wikidata service timed out.",
            evidence_origin=EvidenceStatus.UNAVAILABLE,
            suggested_action=SuggestedAction(summary="Retry audit later.")
        )

        f_obs = Finding(
            id="F-ROBOTS-MISSING",
            title="Robots txt missing",
            severity="high",
            category="discoverability",
            evidence="404 on robots.txt",
            evidence_origin=EvidenceStatus.LIVE_OBSERVED,
            suggested_action=SuggestedAction(summary="Create robots.txt")
        )

        report = AuditReport(
            site="example.com",
            brand="Example",
            collection={"http_fetch_success": True},
            findings=[f_unavail, f_obs]
        )
        report.compute_scores_and_summary()

        # Score must be 94 (100 - 10 * 0.60 for high severity f_obs under 60/30/10 model), ignoring critical f_unavail!
        self.assertEqual(report.readiness_score, 94)

    # 12. UNAVAILABLE Reduces Audit Confidence Appropriately
    def test_12_unavailable_reduces_audit_confidence_appropriately(self):
        report_full = AuditReport(
            site="example.com",
            brand="Example",
            collection={
                "http_fetch_success": True,
                "playwright_used": True,
                "robots_checked": True,
                "sitemap_checked": True,
                "sitemap_status": "VERIFIED_PRESENT",
                "entity_corroboration_status": "VERIFIED"
            },
            findings=[]
        )
        report_full.compute_scores_and_summary()
        self.assertEqual(report_full.audit_confidence, 100)

        report_unavail = AuditReport(
            site="example.com",
            brand="Example",
            collection={
                "http_fetch_success": True,
                "playwright_used": False,
                "playwright_status": "UNAVAILABLE",
                "robots_checked": True,
                "sitemap_checked": False,
                "sitemap_status": "UNAVAILABLE",
                "entity_corroboration_status": "UNAVAILABLE"
            },
            findings=[]
        )
        report_unavail.compute_scores_and_summary()
        # Audit confidence drops when telemetry items are UNAVAILABLE
        self.assertTrue(report_unavail.audit_confidence < 100)
        # Readiness score remains 100!
        self.assertEqual(report_unavail.readiness_score, 100)

    # 13. Audit Pipeline Completes Safely When All Corroboration Providers Fail
    @patch.object(check_corroboration, 'fetch_url')
    @patch.object(run_audit_mod.corroboration_module, 'fetch_url')
    @patch('common.crawler.EnhancedCrawler.fetch_url_with_redirects')
    def test_13_audit_completes_safely_when_all_corroboration_providers_fail(self, mock_crawl, mock_corr_fetch2, mock_corr_fetch1):
        mock_crawl.return_value = {
            "url": "https://example.com",
            "final_url": "https://example.com",
            "status_code": 200,
            "content": "<html><head><title>Example</title></head><body><h1>Example Domain</h1><p>Text</p></body></html>",
            "headers": {"Content-Type": "text/html"},
            "success": True,
            "redirect_chain": []
        }
        mock_corr_fetch1.return_value = {"success": False, "content": None, "error": "HTTP 503"}
        mock_corr_fetch2.return_value = {"success": False, "content": None, "error": "HTTP 503"}

        report = run_audit_mod.execute_audit_pipeline("example.com", "Example", enable_llm=False)
        self.assertIsNotNone(report)
        self.assertEqual(report.site, "example.com")
        self.assertEqual(report.collection.get("entity_corroboration_status"), "UNAVAILABLE")

if __name__ == "__main__":
    unittest.main()
