import sys
import os
import json
import time
import unittest
import urllib.request
import urllib.error
import socket
import importlib.util
from unittest.mock import patch, MagicMock

# Dynamically locate workspace root
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from common.models import Finding, SuggestedAction, AuditReport, AuditState, Evidence, EvidenceStatus
from common.http_client import fetch_url, check_ssl_certificate
from common.browser_renderer import (
    RenderingResult,
    evaluate_rendering_decision,
    compare_raw_vs_rendered,
    render_page
)
from common.llm_client import (
    GeminiReasoningEngine,
    CircuitBreaker,
    build_evidence_packet,
    sanitize_evidence_packet,
    compute_packet_hash,
    apply_gemini_reasoning_and_guardrails,
    PROMPT_VERSION,
    _RESPONSE_CACHE
)

def load_script_module(relative_path: str, module_name: str):
    full_path = os.path.join(workspace_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, full_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

check_access = load_script_module(os.path.join("skills", "crawl-render-audit", "scripts", "check_access.py"), "check_access")
check_semantics = load_script_module(os.path.join("skills", "semantic-readiness", "scripts", "check_semantics.py"), "check_semantics")
check_corroboration = load_script_module(os.path.join("skills", "freshness-corroboration", "scripts", "check_corroboration.py"), "check_corroboration")
check_engagement = load_script_module(os.path.join("skills", "engagement-audit", "scripts", "check_engagement.py"), "check_engagement")
run_audit = load_script_module(os.path.join("skills", "audit-orchestrator", "scripts", "run_audit.py"), "run_audit")

class TestBrandAIReadinessAuditPhase4(unittest.TestCase):

    def setUp(self):
        _RESPONSE_CACHE.clear()

    # 1. Missing API Key
    def test_01_missing_api_key(self):
        cb = CircuitBreaker()
        engine = GeminiReasoningEngine(api_key="", circuit_breaker=cb)
        self.assertFalse(engine.is_available())
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "UNAVAILABLE")
        self.assertIsNone(res)

    # 2. GEMINI_ENABLED=false
    def test_02_gemini_enabled_false(self):
        cb = CircuitBreaker()
        engine = GeminiReasoningEngine(api_key="key", enabled=False, circuit_breaker=cb)
        self.assertFalse(engine.is_available())
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "DISABLED")

    # 3. Successful Gemini Response
    @patch('urllib.request.urlopen')
    def test_03_successful_gemini_response(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [{
                                "finding_id": "F-001",
                                "decision": "VALID",
                                "confidence": 0.95,
                                "severity": "high",
                                "reasoning_summary": "Evidence verified."
                            }]
                        })
                    }]
                }
            }]
        }
        mock_response.read.return_value = json.dumps(payload).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.add_finding(Finding(id="F-001", title="Title", severity="high", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix")))

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        validated = apply_gemini_reasoning_and_guardrails(state, engine)
        self.assertEqual(len(validated), 1)
        self.assertEqual(state.llm_observations["status"], "SUCCESS")
        self.assertFalse(state.llm_observations["fallback_used"])

    # 4. HTTP 429 Rate Limiting
    @patch('urllib.request.urlopen')
    def test_04_http_429_rate_limiting(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=1)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "RATE_LIMITED")
        self.assertIsNone(res)

    # 5. HTTP 500
    @patch('urllib.request.urlopen')
    def test_05_http_500(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=1)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "PROVIDER_UNAVAILABLE")

    # 6. HTTP 502
    @patch('urllib.request.urlopen')
    def test_06_http_502(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 502, "Bad Gateway", {}, None)

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "PROVIDER_UNAVAILABLE")

    # 7. HTTP 503 Capacity Outage
    @patch('urllib.request.urlopen')
    def test_07_http_503_outage(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "PROVIDER_UNAVAILABLE")

    # 8. HTTP 504
    @patch('urllib.request.urlopen')
    def test_08_http_504(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 504, "Gateway Timeout", {}, None)

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "PROVIDER_UNAVAILABLE")

    # 9. Timeout Handling
    @patch('urllib.request.urlopen')
    def test_09_timeout_handling(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_urlopen.side_effect = socket.timeout("timed out")

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "TIMEOUT")

    # 10. Connection Failure
    @patch('urllib.request.urlopen')
    def test_10_connection_failure(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "FAILED")

    # 11. Malformed JSON Response
    @patch('urllib.request.urlopen')
    def test_11_malformed_json(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "Broken text"}]}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "MALFORMED_RESPONSE")

    # 12. Malformed Schema (Missing results array)
    @patch('urllib.request.urlopen')
    def test_12_malformed_schema(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"wrong_key\\": 123}"}]}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "MALFORMED_RESPONSE")

    # 13. Unknown Finding ID Filtering
    @patch('urllib.request.urlopen')
    def test_13_unknown_finding_id_filtering(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [{
                                "finding_id": "F-UNKNOWN-999",
                                "decision": "VALID"
                            }]
                        })
                    }]
                }
            }]
        }
        mock_response.read.return_value = json.dumps(payload).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.add_finding(Finding(id="F-001", title="Real Finding", severity="high", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix")))

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb)
        validated = apply_gemini_reasoning_and_guardrails(state, engine)
        self.assertEqual(len(validated), 1)
        self.assertEqual(validated[0].id, "F-001")

    # 14. Invalid Decision Vocabulary Fallback
    @patch('urllib.request.urlopen')
    def test_14_invalid_decision_vocabulary(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [{
                                "finding_id": "F-001",
                                "decision": "INVALID_DECISION_STRING",
                                "confidence": 0.90
                            }]
                        })
                    }]
                }
            }]
        }
        mock_response.read.return_value = json.dumps(payload).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.add_finding(Finding(id="F-001", title="Title", severity="high", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix")))

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb)
        validated = apply_gemini_reasoning_and_guardrails(state, engine)
        # Invalid decision falls back to QUESTIONABLE, capping confidence at 0.50
        self.assertEqual(validated[0].confidence, 0.50)

    # 15. Invalid Severity Fallback
    @patch('urllib.request.urlopen')
    def test_15_invalid_severity_fallback(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [{
                                "finding_id": "F-001",
                                "decision": "VALID",
                                "confidence": 0.90,
                                "severity": "EXTREME_DANGER"
                            }]
                        })
                    }]
                }
            }]
        }
        mock_response.read.return_value = json.dumps(payload).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.add_finding(Finding(id="F-001", title="Title", severity="medium", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix")))

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb)
        validated = apply_gemini_reasoning_and_guardrails(state, engine)
        self.assertEqual(validated[0].severity, "medium")

    # 16. Confidence Clamping
    @patch('urllib.request.urlopen')
    def test_16_confidence_clamping(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [{
                                "finding_id": "F-001",
                                "decision": "VALID",
                                "confidence": 12.5  # Clamped to 1.0
                            }]
                        })
                    }]
                }
            }]
        }
        mock_response.read.return_value = json.dumps(payload).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.add_finding(Finding(id="F-001", title="Title", severity="medium", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix")))

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb)
        validated = apply_gemini_reasoning_and_guardrails(state, engine)
        self.assertEqual(validated[0].confidence, 1.0)

    # 17. Questionable Decision Confidence Cap (0.50)
    @patch('urllib.request.urlopen')
    def test_17_questionable_confidence_cap(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [{
                                "finding_id": "F-001",
                                "decision": "QUESTIONABLE",
                                "confidence": 0.95
                            }]
                        })
                    }]
                }
            }]
        }
        mock_response.read.return_value = json.dumps(payload).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.add_finding(Finding(id="F-001", title="Title", severity="medium", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix")))

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb)
        validated = apply_gemini_reasoning_and_guardrails(state, engine)
        self.assertEqual(validated[0].confidence, 0.50)

    # 18. Severity Guardrail for Low Confidence
    @patch('urllib.request.urlopen')
    def test_18_severity_guardrail_for_low_confidence(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "results": [{
                                "finding_id": "F-001",
                                "decision": "VALID",
                                "confidence": 0.20,
                                "severity": "CRITICAL"
                            }]
                        })
                    }]
                }
            }]
        }
        mock_response.read.return_value = json.dumps(payload).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.add_finding(Finding(id="F-001", title="Title", severity="low", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix")))

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb)
        validated = apply_gemini_reasoning_and_guardrails(state, engine)
        self.assertEqual(validated[0].severity, "medium")

    # 19. Deterministic Fallback After Provider Failure
    @patch('urllib.request.urlopen')
    def test_19_deterministic_fallback_after_failure(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)

        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        f = Finding(id="F-001", title="Deterministic Candidate", severity="high", category="semantics", evidence="Ev", suggested_action=SuggestedAction("Fix"))
        state.add_finding(f)

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        validated = apply_gemini_reasoning_and_guardrails(state, engine)

        # Candidate finding must remain intact
        self.assertEqual(len(validated), 1)
        self.assertEqual(validated[0].id, "F-001")
        self.assertTrue(state.llm_observations["fallback_used"])
        self.assertEqual(state.llm_observations["status"], "PROVIDER_UNAVAILABLE")

    # 20. Circuit Breaker Opens After Repeated Failures
    @patch('urllib.request.urlopen')
    def test_20_circuit_breaker_opens_after_failures(self, mock_urlopen):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 503, "Unavailable", {}, None)

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)

        # Failures 1, 2, 3
        engine.evaluate_evidence_packet({})
        engine.evaluate_evidence_packet({})
        engine.evaluate_evidence_packet({})

        self.assertEqual(cb.state, "OPEN")

        # Attempt 4 should fail immediately with CIRCUIT_OPEN without calling network
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "CIRCUIT_OPEN")

    # 21. Circuit Breaker Cooldown & Half-Open Transition
    def test_21_circuit_breaker_cooldown_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, "OPEN")

        # Wait for cooldown to expire
        time.sleep(0.15)
        self.assertTrue(cb.allow_request())
        self.assertEqual(cb.state, "HALF_OPEN")

    # 22. Successful Recovery After Outage (Half-Open -> Closed)
    @patch('urllib.request.urlopen')
    def test_22_successful_recovery_after_outage(self, mock_urlopen):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.01)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, "OPEN")
        time.sleep(0.02)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"results\\": []}"}]}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb, max_retries=0)
        status, res, hit = engine.evaluate_evidence_packet({})
        self.assertEqual(status, "SUCCESS")
        self.assertEqual(cb.state, "CLOSED")

    # 23. Cache Hit Behavior
    @patch('urllib.request.urlopen')
    def test_23_cache_hit_behavior(self, mock_urlopen):
        cb = CircuitBreaker()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"results\\": []}"}]}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = GeminiReasoningEngine(api_key="mock_key", circuit_breaker=cb)
        packet = {"test": "data_unique_23"}

        status1, res1, hit1 = engine.evaluate_evidence_packet(packet)
        self.assertFalse(hit1)

        status2, res2, hit2 = engine.evaluate_evidence_packet(packet)
        self.assertTrue(hit2)
        self.assertEqual(mock_urlopen.call_count, 1)

    # 24. Cache Invalidation on Model Change
    def test_24_cache_invalidation_on_model_change(self):
        packet = {"test": "data"}
        hash1 = compute_packet_hash(packet, "gemini-3.7-flash", provider="gemini", prompt_version=PROMPT_VERSION)
        hash2 = compute_packet_hash(packet, "gemini-2.0-flash", provider="gemini", prompt_version=PROMPT_VERSION)
        self.assertNotEqual(hash1, hash2)

    # 25. Cache Invalidation on Prompt Version Change
    def test_25_cache_invalidation_on_prompt_version_change(self):
        packet = {"test": "data"}
        hash1 = compute_packet_hash(packet, "gemini-3.7-flash", provider="gemini", prompt_version="v1.0")
        hash2 = compute_packet_hash(packet, "gemini-3.7-flash", provider="gemini", prompt_version="v2.0")
        self.assertNotEqual(hash1, hash2)

    # 26. Secret Redaction
    def test_26_secret_redaction(self):
        secret_packet = {
            "api_key": "AIzaSySecretKey123456789012345678901",
            "bearer_token": "Bearer xyz123",
            "safe_data": "Public evidence"
        }
        redacted = sanitize_evidence_packet(secret_packet)
        self.assertEqual(redacted["api_key"], "[REDACTED_SECRET]")
        self.assertEqual(redacted["bearer_token"], "[REDACTED_SECRET]")
        self.assertEqual(redacted["safe_data"], "Public evidence")

    # 27. --no-llm Flag Execution
    def test_27_no_llm_flag_execution(self):
        report = run_audit.execute_audit_pipeline("google.com", "Google", enable_llm=False)
        self.assertEqual(report.llm_observations["status"], "DISABLED")
        self.assertTrue(report.llm_observations["fallback_used"])

    # 28. Complete Audit Execution with No API Key
    def test_28_complete_audit_no_api_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            report = run_audit.execute_audit_pipeline("example.com", "Example", enable_llm=True)
            self.assertEqual(report.site, "example.com")
            self.assertEqual(report.llm_observations["status"], "UNAVAILABLE")
            self.assertTrue(report.llm_observations["fallback_used"])
            self.assertGreater(len(report.findings), 0)

    # 29. Complete Audit Execution with Simulated HTTP 503
    @patch('urllib.request.urlopen')
    def test_29_complete_audit_simulated_503(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock_key", "GEMINI_MAX_RETRIES": "0"}):
            report = run_audit.execute_audit_pipeline("example.com", "Example", enable_llm=True)
            self.assertEqual(report.site, "example.com")
            self.assertEqual(report.llm_observations["status"], "PROVIDER_UNAVAILABLE")
            self.assertTrue(report.llm_observations["fallback_used"])
            self.assertGreater(len(report.findings), 0)

    # 30. Complete Audit Execution with Simulated Timeout
    @patch('urllib.request.urlopen')
    def test_30_complete_audit_simulated_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("timed out")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock_key", "GEMINI_MAX_RETRIES": "0"}):
            report = run_audit.execute_audit_pipeline("example.com", "Example", enable_llm=True)
            self.assertEqual(report.site, "example.com")
            self.assertEqual(report.llm_observations["status"], "TIMEOUT")
            self.assertTrue(report.llm_observations["fallback_used"])
            self.assertGreater(len(report.findings), 0)

class TestTelemetryAndEvidencePipeline(unittest.TestCase):

    # 1. Playwright ready but target render fails
    @patch('common.browser_renderer.render_page')
    def test_01_playwright_ready_target_render_failure(self, mock_render):
        mock_render.return_value = RenderingResult(
            attempted=True,
            successful=False,
            error="Browser page load timed out after 8000ms"
        )
        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.raw_html["example.com"] = "<html><body><div id='root'></div><script src='app.js'></script></body></html>"
        
        with patch('skills.audit-orchestrator.scripts.run_audit.PLAYWRIGHT_AVAILABLE', True):
            # Evaluate rendering pipeline logic
            should_render, _, _, _ = evaluate_rendering_decision(state.raw_html["example.com"], state.extracted_content)
            self.assertTrue(should_render)
            
            res = mock_render("example.com", timeout_ms=8000)
            self.assertFalse(res.successful)

    # 2. Playwright ready and target render succeeds
    @patch('common.browser_renderer.render_page')
    def test_02_playwright_ready_target_render_success(self, mock_render):
        mock_render.return_value = RenderingResult(
            attempted=True,
            successful=True,
            rendered_html="<html><body><h1>Hydrated Title</h1><p>Full content text.</p></body></html>",
            visible_text="Hydrated Title Full content text.",
            h1_headers=["Hydrated Title"]
        )
        res = mock_render("example.com")
        self.assertTrue(res.successful)
        self.assertEqual(res.h1_headers, ["Hydrated Title"])

    # 3. Playwright unavailable globally
    def test_03_playwright_unavailable_globally(self):
        res = render_page("example.com")
        from common.browser_renderer import PLAYWRIGHT_AVAILABLE as PW_AVAIL
        if not PW_AVAIL:
            self.assertFalse(res.successful)
            self.assertFalse(res.browser_available)

    # 4. JS rendering not required
    def test_04_js_rendering_not_required(self):
        html_content = "<html><body><h1>Static Title</h1>" + "<p>Static paragraph text with high information density.</p>" * 50 + "</body></html>"
        should_render, reason, _, _ = evaluate_rendering_decision(html_content, {})
        self.assertFalse(should_render)
        self.assertIn("sufficient", reason.lower())

    # 5. Sitemap verified present
    @patch.object(check_access, 'fetch_url')
    def test_05_sitemap_verified_present(self, mock_fetch):
        mock_fetch.side_effect = [
            # robots.txt
            {"success": True, "content": "User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml", "latency_ms": 50},
            # sitemap.xml
            {"success": True, "content": "<?xml version='1.0'?><urlset><url><loc>https://example.com/</loc></url></urlset>", "latency_ms": 50}
        ]
        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.http_responses["example.com"] = {"success": True, "content": "<html></html>", "latency_ms": 100, "headers": {}, "redirect_chain": [], "redirect_count": 0, "final_url": "https://example.com"}
        check_access.run_discoverability_check(state)
        self.assertEqual(state.crawl_metadata.get("sitemap_status"), "VERIFIED_PRESENT")

    # 6. Sitemap verified absent
    @patch.object(check_access, 'fetch_url')
    def test_06_sitemap_verified_absent(self, mock_fetch):
        mock_fetch.side_effect = [
            # robots.txt
            {"success": True, "content": "User-agent: *\nAllow: /", "latency_ms": 50},
            # sitemap.xml 404
            {"success": False, "content": None, "error": "HTTP 404 Not Found", "latency_ms": 50}
        ]
        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.http_responses["example.com"] = {"success": True, "content": "<html></html>", "latency_ms": 100, "headers": {}, "redirect_chain": [], "redirect_count": 0, "final_url": "https://example.com"}
        check_access.run_discoverability_check(state)
        self.assertEqual(state.crawl_metadata.get("sitemap_status"), "VERIFIED_ABSENT")

    # 7. Sitemap unavailable
    @patch.object(check_access, 'fetch_url')
    def test_07_sitemap_unavailable(self, mock_fetch):
        mock_fetch.side_effect = [
            # robots.txt
            {"success": True, "content": "User-agent: *\nAllow: /", "latency_ms": 50},
            # sitemap.xml 503 Timeout
            {"success": False, "content": None, "error": "HTTP 503 Connection Timeout", "latency_ms": 50}
        ]
        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.http_responses["example.com"] = {"success": True, "content": "<html></html>", "latency_ms": 100, "headers": {}, "redirect_chain": [], "redirect_count": 0, "final_url": "https://example.com"}
        check_access.run_discoverability_check(state)
        self.assertEqual(state.crawl_metadata.get("sitemap_status"), "UNAVAILABLE")

    # 8. UNAVAILABLE does not reduce readiness score
    def test_08_unavailable_does_not_reduce_readiness_score(self):
        f_unavail = Finding(
            id="F-UNAVAIL",
            title="Telemetry Unavailable",
            severity="critical",
            category="discoverability",
            evidence="Timeout",
            evidence_origin=EvidenceStatus.UNAVAILABLE,
            suggested_action=SuggestedAction("Fix")
        )
        report = AuditReport(site="example.com", brand="Example", collection={"http_fetch_success": True}, findings=[f_unavail])
        report.compute_scores_and_summary()
        self.assertEqual(report.readiness_score, 100)

    # 9. UNAVAILABLE reduces audit confidence
    def test_09_unavailable_reduces_audit_confidence(self):
        report = AuditReport(
            site="example.com",
            brand="Example",
            collection={
                "http_fetch_success": True,
                "playwright_status": "UNAVAILABLE",
                "sitemap_status": "UNAVAILABLE",
                "entity_corroboration_status": "UNAVAILABLE"
            },
            findings=[]
        )
        report.compute_scores_and_summary()
        self.assertLess(report.audit_confidence, 100)
        self.assertEqual(report.readiness_score, 100)

    # 10. NOT_APPLICABLE does not reduce readiness score or audit confidence
    def test_10_not_applicable_scoring(self):
        f_na = Finding(
            id="F-NA",
            title="Check Not Applicable",
            severity="high",
            category="semantics",
            evidence="N/A",
            evidence_origin=EvidenceStatus.NOT_APPLICABLE,
            suggested_action=SuggestedAction("N/A")
        )
        report = AuditReport(
            site="example.com",
            brand="Example",
            collection={
                "http_fetch_success": True,
                "playwright_status": "NOT_REQUIRED",
                "sitemap_status": "VERIFIED_PRESENT",
                "entity_corroboration_status": "VERIFIED"
            },
            findings=[f_na]
        )
        report.compute_scores_and_summary()
        self.assertEqual(report.readiness_score, 100)
        self.assertEqual(report.audit_confidence, 100)

    # 11. Gemini cannot overwrite evidence provenance
    def test_11_gemini_cannot_overwrite_unavailable_provenance(self):
        f_unavail = Finding(
            id="F-UNAVAIL-TEST",
            title="Sitemap Timeout",
            severity="medium",
            category="discoverability",
            evidence="Sitemap fetch timed out.",
            evidence_origin=EvidenceStatus.UNAVAILABLE,
            suggested_action=SuggestedAction("Retry")
        )
        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.candidate_findings = [f_unavail]
        
        mock_engine = MagicMock()
        mock_engine.evaluate_evidence_packet.return_value = ("SUCCESS", {
            "results": [{
                "finding_id": "F-UNAVAIL-TEST",
                "decision": "VALID",
                "confidence": 0.9,
                "severity": "medium",
                "reasoning_summary": "Valid timeout observation."
            }]
        }, False)

        final_findings = apply_gemini_reasoning_and_guardrails(state, mock_engine)
        
        updated = final_findings[0]
        # Origin MUST remain UNAVAILABLE!
        self.assertEqual(updated.evidence_origin, EvidenceStatus.UNAVAILABLE)

    # 12. End-to-end audit preserves telemetry contract
    def test_12_end_to_end_telemetry_preservation(self):
        report = run_audit.execute_audit_pipeline("example.com", "Example", enable_llm=False)
        col = report.collection
        self.assertIn(col.get("playwright_status"), ["SUCCESS", "NOT_REQUIRED", "UNAVAILABLE", "ATTEMPTED"])
        self.assertIn(col.get("sitemap_status"), ["VERIFIED_PRESENT", "VERIFIED_ABSENT", "UNAVAILABLE"])
        self.assertIn(col.get("entity_corroboration_status"), ["VERIFIED", "INFERRED", "UNAVAILABLE"])
        
        report_dict = report.to_dict()
        self.assertIn("collection", report_dict)
        self.assertIn("audit_confidence", report_dict)
        self.assertIn("readiness_score", report_dict)

class TestThreeDimensionScoringAndBlockerPrioritization(unittest.TestCase):
    """
    Regression test suite verifying 3 top-level dimension scoring (60% AI Discoverability, 30% Engagement, 10% Tech Health)
    and weighted Top Blocker prioritization (SSL expiration never blocks major AI discoverability issues).
    """
    def test_01_ssl_expiration_never_blocks_major_ai_issues(self):
        f_ssl = Finding(
            id="access-ssl-expiring",
            title="SSL certificate expires within 20 days",
            severity="high",
            category="discoverability",
            evidence="SSL certificate expires in 20 days.",
            suggested_action=SuggestedAction(summary="Renew SSL certificate.")
        )
        f_entity = Finding(
            id="corroboration-weak-identity",
            title="Weak Organization Entity Grounding",
            severity="high",
            category="corroboration",
            evidence="No Wikidata entity link or sameAs identity signals found.",
            suggested_action=SuggestedAction(summary="Add sameAs schema links.")
        )
        f_valprop = Finding(
            id="engagement-value-prop-weak",
            title="Unclear Hero Value Proposition",
            severity="high",
            category="engagement",
            evidence="Page lacks clear business positioning statement.",
            suggested_action=SuggestedAction(summary="Add clear H1 value proposition.")
        )

        report = AuditReport(
            site="example.com",
            brand="Example",
            findings=[f_ssl, f_entity, f_valprop]
        )
        report.compute_scores_and_summary()

        top_titles = [b["title"] for b in report.top_blockers]
        # SSL warning MUST be listed below entity identity and value proposition!
        self.assertIn("Weak Organization Entity Grounding", top_titles)
        self.assertIn("Unclear Hero Value Proposition", top_titles)
        self.assertNotEqual(top_titles[0], "SSL certificate expires within 20 days")

    def test_02_three_dimension_weighted_score_calculation(self):
        # AI Discoverability issue (-10 pts -> 90/100)
        f_ai = Finding(
            id="semantics-schema-missing",
            title="Organization Schema Missing",
            severity="high",
            category="semantics",
            evidence="No JSON-LD schema found.",
            suggested_action=SuggestedAction(summary="Add JSON-LD")
        )
        report = AuditReport(
            site="example.com",
            brand="Example",
            findings=[f_ai]
        )
        report.compute_scores_and_summary()

        self.assertEqual(report.ai_discoverability_score, 90)
        self.assertEqual(report.onsite_engagement_score, 100)
        self.assertEqual(report.technical_health_score, 100)
        # Readiness score: 90 * 0.60 + 100 * 0.30 + 100 * 0.10 = 54 + 30 + 10 = 94
        self.assertEqual(report.readiness_score, 94)

    def test_03_case_b_conversion_friction_outranks_minor_ai_metadata(self):
        f_friction = Finding(
            id="engagement-cta-missing",
            title="Missing primary action CTA",
            severity="high",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="CTA_VISIBILITY",
            finding_type="BLOCKER",
            business_impact="high",
            evidence="No clear conversion CTA button.",
            suggested_action=SuggestedAction(summary="Add CTA button.")
        )
        f_meta = Finding(
            id="engagement-meta-description-length",
            title="Suboptimal meta description length",
            severity="low",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="AI_REFERRAL_CONTEXT",
            finding_type="TECHNICAL_NOTICE",
            business_impact="low",
            evidence="Meta description length is 180 chars.",
            suggested_action=SuggestedAction(summary="Shorten meta description.")
        )
        report = AuditReport(site="example.com", brand="Example", findings=[f_friction, f_meta])
        report.compute_scores_and_summary()
        top_ids = [b["id"] for b in report.top_blockers]
        self.assertEqual(top_ids[0], "engagement-cta-missing")

    def test_04_case_c_high_confidence_outranks_low_confidence_speculation(self):
        f_confident = Finding(
            id="access-robots-ai-blocked",
            title="GPTBot blocked in robots.txt",
            severity="high",
            category="discoverability",
            confidence=1.0,
            evidence="Disallow: / for GPTBot",
            suggested_action=SuggestedAction(summary="Allow GPTBot")
        )
        f_speculative = Finding(
            id="semantics-speculative-missing",
            title="Possible missing niche microdata",
            severity="high",
            category="semantics",
            confidence=0.3,
            evidence="Inferred missing microdata",
            suggested_action=SuggestedAction(summary="Add microdata")
        )
        report = AuditReport(site="example.com", brand="Example", findings=[f_confident, f_speculative])
        report.compute_scores_and_summary()
        top_ids = [b["id"] for b in report.top_blockers]
        self.assertEqual(top_ids[0], "access-robots-ai-blocked")

    def test_05_case_d_sitemap_absent_alone_never_top_blocker(self):
        f_sitemap = Finding(
            id="access-sitemap-missing",
            title="Sitemap file missing or unlisted",
            severity="medium",
            category="discoverability",
            primary_dimension="technical_health",
            mechanism="SITEMAP_INFRASTRUCTURE",
            finding_type="TECHNICAL_NOTICE",
            business_impact="low",
            evidence="No sitemap declaration found.",
            suggested_action=SuggestedAction(summary="Create sitemap.xml")
        )
        f_h1 = Finding(
            id="engagement-h1-missing",
            title="Missing H1 value proposition heading",
            severity="high",
            category="engagement",
            primary_dimension="onsite_engagement",
            mechanism="VALUE_PROPOSITION",
            finding_type="BLOCKER",
            business_impact="high",
            evidence="No H1 tag present.",
            suggested_action=SuggestedAction(summary="Add H1 value proposition.")
        )
        report = AuditReport(site="example.com", brand="Example", findings=[f_sitemap, f_h1])
        report.compute_scores_and_summary()
        top_ids = [b["id"] for b in report.top_blockers]
        self.assertEqual(top_ids[0], "engagement-h1-missing")
        self.assertNotEqual(top_ids[0], "access-sitemap-missing")

    def test_06_case_e_critical_technical_access_blocker_can_rank_high(self):
        f_access = Finding(
            id="access-http-connection-failed",
            title="Failed to connect to primary brand homepage",
            severity="critical",
            category="discoverability",
            primary_dimension="ai_discoverability",
            mechanism="HTTP_HEALTH",
            finding_type="BLOCKER",
            business_impact="critical",
            evidence="HTTP 500 Connection Refused.",
            suggested_action=SuggestedAction(summary="Fix web server.")
        )
        report = AuditReport(site="example.com", brand="Example", findings=[f_access])
        report.compute_scores_and_summary()
        top_ids = [b["id"] for b in report.top_blockers]
        self.assertEqual(top_ids[0], "access-http-connection-failed")

class TestRound3AccuracyFixes(unittest.TestCase):
    def test_robots_txt_rfc9309_inline_comments_and_case(self):
        from common.crawler import EnhancedCrawler
        robots_content = """
        # Robots.txt rule file
        USER-AGENT: gptbot # inline comment
        DISALLOW: / # block root

        user-agent: * # fallback rule
        allow: /
        disallow: /private/
        """
        res = EnhancedCrawler.parse_robots_txt(robots_content)
        self.assertIn("GPTBot", res["disallowed_bots"])
        self.assertIn("ClaudeBot", res["allowed_bots"])

    def test_robots_txt_script_check_access_gptbot_and_google_extended(self):
        robots_content = """
        User-agent: GPTBot
        Disallow: /

        User-agent: Google-Extended
        Disallow: /
        """
        findings, _ = check_access.parse_robots_txt(robots_content, "example.com")
        gptbot_f = next(f for f in findings if "gptbot" in f.id)
        google_ext_f = next(f for f in findings if "google-extended" in f.id)

        self.assertIn("Pre-training Crawler", gptbot_f.title)
        self.assertIn("foundational model pre-training", gptbot_f.mechanism_impact)
        self.assertEqual(google_ext_f.severity, "low")
        self.assertEqual(google_ext_f.finding_type, "TECHNICAL_NOTICE")
        self.assertIn("does NOT block", google_ext_f.mechanism_impact)

    def test_jsonld_syntax_error_reporting(self):
        bad_html = """
        <html>
        <head>
          <script type="application/ld+json">
            { "@context": "https://schema.org", "@type": "Organization", "name": "Test Brand",
          </script>
        </head>
        <body><h1>Welcome</h1></body>
        </html>
        """
        state = AuditState(target_url="example.com", normalized_domain="example.com", brand="Example")
        state.http_responses["example.com"] = {"success": True, "content": bad_html}
        findings = check_semantics.run_semantics_check(state)
        syntax_f = next((f for f in findings if "jsonld-syntax-error" in f.id), None)
        self.assertIsNotNone(syntax_f)
        self.assertIn("JSONLD_SYNTAX_ERROR", syntax_f.title)
        self.assertEqual(syntax_f.severity, "critical")

    def test_non_commercial_documentation_page_exemptions(self):
        doc_html = "<html><head><title>API Documentation</title></head><body><h1>API Developer Reference</h1><p>Welcome to developer portal documentation.</p></body></html>"
        state = AuditState(target_url="docs.example.com", normalized_domain="docs.example.com", brand="Example")
        state.http_responses["docs.example.com"] = {"success": True, "content": doc_html}

        sem_findings = check_semantics.run_semantics_check(state)
        org_f = next((f for f in sem_findings if "missing-organization" in f.id), None)
        self.assertIsNone(org_f) # Exempted for doc portal

        eng_findings = check_engagement.run_engagement_check(state)
        cta_f = next((f for f in eng_findings if "cta-missing" in f.id), None)
        self.assertIsNone(cta_f) # Exempted for doc portal

    def test_multilingual_cta_detection(self):
        french_html = "<html><body><h1>Notre Service</h1><button>Découvrir</button></body></html>"
        state = AuditState(target_url="example.fr", normalized_domain="example.fr", brand="Example")
        state.http_responses["example.fr"] = {"success": True, "content": french_html}

        findings = check_engagement.run_engagement_check(state)
        cta_missing = next((f for f in findings if "cta-missing" in f.id), None)
        cta_generic = next((f for f in findings if "cta-generic" in f.id), None)
        self.assertIsNone(cta_missing)
        self.assertIsNone(cta_generic)

    @patch.object(check_corroboration, "query_wikidata_entity")
    @patch.object(check_corroboration, "query_wikipedia_summary")
    def test_corroboration_external_unavailable_neutral_scoring(self, mock_wp, mock_wd):
        mock_wd.return_value = (None, "SUCCESS", 10.0)
        mock_wp.return_value = (None, "SUCCESS", 10.0)
        state = AuditState(target_url="startup.io", normalized_domain="startup.io", brand="StartupApp")
        findings = check_corroboration.run_corroboration_check(state)

        wikidata_f = next((f for f in findings if "wikidata-missing" in f.id), None)
        self.assertIsNotNone(wikidata_f)
        self.assertEqual(wikidata_f.severity, "low")
        self.assertEqual(wikidata_f.finding_type, "TECHNICAL_NOTICE")
        self.assertIn("EXTERNAL_CORROBORATION_UNAVAILABLE", wikidata_f.title)

    def test_single_probe_latency_telemetry_reclassification(self):
        state = AuditState(target_url="slowsite.com", normalized_domain="slowsite.com", brand="Slowsite")
        state.http_responses["slowsite.com"] = {"success": True, "content": "<html></html>", "latency_ms": 2500, "redirect_count": 0}

        findings = check_access.run_discoverability_check(state)
        lat_f = next((f for f in findings if "latency-slow" in f.id), None)
        self.assertIsNotNone(lat_f)
        self.assertEqual(lat_f.severity, "low")
        self.assertEqual(lat_f.finding_type, "TECHNICAL_NOTICE")

if __name__ == "__main__":
    unittest.main()

