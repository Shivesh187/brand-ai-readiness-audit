import sys
import os
import json
import re
import hashlib
import time
import urllib.request
import urllib.error
import socket
from typing import Dict, Any, List, Optional, Tuple

from common.models import Finding, SuggestedAction, AuditState, EvidenceStatus

# Auto-load .env file if GEMINI_API_KEY is not set in environment
def _load_env_file():
    if "GEMINI_API_KEY" in os.environ and os.environ["GEMINI_API_KEY"].strip():
        return
    cur = os.path.abspath(__file__)
    while cur != os.path.dirname(cur):
        env_path = os.path.join(cur, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k and v and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass
            break
        cur = os.path.dirname(cur)

_load_env_file()

PROMPT_VERSION = "phase5-v2"

# Environment Variable Configuration & Defaults
DEFAULT_ENABLED = os.environ.get("GEMINI_ENABLED", "true").lower() in ["true", "1", "yes"]
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
# Raised default timeout to 35s to eliminate false socket drops on the initial request
DEFAULT_TIMEOUT_SEC = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "35"))
DEFAULT_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "1"))

GEMINI_REST_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Process-Local Cache for Evidence Packet Hashes
_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}

class CircuitBreaker:
    """
    Process-local Circuit Breaker to prevent cascading delays during provider outages.
    States: CLOSED (normal), OPEN (tripped/failing), HALF_OPEN (probing recovery).
    """
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = "CLOSED"
        self.consecutive_failures = 0
        self.last_state_change = time.time()

    def allow_request(self) -> bool:
        now = time.time()
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if now - self.last_state_change >= self.cooldown_seconds:
                self.state = "HALF_OPEN"
                self.last_state_change = now
                return True
            return False
        elif self.state == "HALF_OPEN":
            return True
        return True

    def record_success(self):
        self.consecutive_failures = 0
        self.state = "CLOSED"
        self.last_state_change = time.time()

    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.state = "OPEN"
            self.last_state_change = time.time()

    def reset(self):
        self.state = "CLOSED"
        self.consecutive_failures = 0
        self.last_state_change = time.time()

# Global process-local circuit breaker instance
GLOBAL_CIRCUIT_BREAKER = CircuitBreaker()

def sanitize_evidence_packet(data: Any) -> Any:
    """
    Recursively redacts sensitive API keys, tokens, auth headers, and cookies before LLM transmission.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ["key", "token", "auth", "secret", "password", "cookie", "bearer"]):
                sanitized[k] = "[REDACTED_SECRET]"
            else:
                sanitized[k] = sanitize_evidence_packet(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_evidence_packet(item) for item in data]
    elif isinstance(data, str):
        if re.search(r'AIzaSy[A-Za-z0-9_-]{33}', data):
            return re.sub(r'AIzaSy[A-Za-z0-9_-]{33}', '[REDACTED_API_KEY]', data)
        return data
    else:
        return data

def compute_packet_hash(packet: Dict[str, Any], model: str, provider: str = "gemini", prompt_version: str = PROMPT_VERSION) -> str:
    """
    Computes a deterministic SHA256 hash combining prompt version, provider, model, and evidence packet.
    """
    packet_str = json.dumps(packet, sort_keys=True)
    combined = f"{prompt_version}:{provider}:{model}:{packet_str}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

def build_evidence_packet(state: AuditState) -> Dict[str, Any]:
    """
    Constructs a compact, bounded evidence packet containing multi-skill observations.
    """
    candidate_findings = []
    for f in state.candidate_findings:
        candidate_findings.append({
            "finding_id": f.id,
            "title": f.title,
            "severity": f.severity,
            "category": f.category,
            "primary_dimension": getattr(f, "primary_dimension", "ai_discoverability"),
            "business_impact": getattr(f, "business_impact", "medium"),
            "evidence": f.evidence,
            "confidence": f.confidence,
            "source_skill": f.source_skill or f.category,
            "affected_urls": f.affected_urls,
            "evidence_details": f.evidence_details
        })

    packet = {
        "audit_context": {
            "site": state.normalized_domain,
            "brand": state.brand,
            "target_url": state.target_url
        },
        "observations": {
            "discoverability": {
                "latency_ms": state.crawl_metadata.get("latency_ms"),
                "ssl_valid": state.crawl_metadata.get("ssl_valid"),
                "ssl_days": state.crawl_metadata.get("ssl_days"),
                "sitemaps": state.crawl_metadata.get("sitemaps", [])
            },
            "semantics": {
                "title": state.extracted_content.get("title"),
                "found_schemas": state.structured_data.get("found_schemas", []),
                "sameAs_links": state.structured_data.get("sameAs_links", []),
                "h1_headers": state.extracted_content.get("h1_headers", []),
                "raw_text_len": len(" ".join(state.extracted_content.get("raw_text_segments", [])))
            },
            "rendering": state.rendering_metadata.get("decision", {}),
            "corroboration": state.corroboration_observations,
            "engagement": state.engagement_observations
        },
        "candidate_findings": candidate_findings
    }

    return sanitize_evidence_packet(packet)

class ReasoningEngine:
    """
    Provider-Independent Abstract Base Class for Audit Reasoning Providers.
    """
    def is_available(self) -> bool:
        raise NotImplementedError

    def evaluate_evidence_packet(self, packet: Dict[str, Any], timeout_sec: Optional[float] = None) -> Tuple[str, Optional[Dict[str, Any]], bool]:
        raise NotImplementedError

class GeminiReasoningEngine(ReasoningEngine):
    def __init__(self,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 enabled: Optional[bool] = None,
                 timeout_seconds: Optional[float] = None,
                 max_retries: Optional[int] = None,
                 circuit_breaker: Optional[CircuitBreaker] = None):
        
        env_enabled_str = os.environ.get("GEMINI_ENABLED", "true").lower()
        self.enabled = enabled if enabled is not None else (env_enabled_str in ["true", "1", "yes"])
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "").strip()
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_SEC
        self.max_retries = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES
        self.circuit_breaker = circuit_breaker or GLOBAL_CIRCUIT_BREAKER

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_key)

    def generate_reasoning_prompt(self, packet: Dict[str, Any]) -> str:
        prompt = f"""You are the Lead Reasoning & Validation Engine for a Brand AI Discoverability & On-Site Engagement Intelligence Audit.
Evaluate candidate diagnostic findings against multi-skill evidence.

IMPORTANT PRODUCT POSITIONING:
This is NOT traditional technical SEO or infrastructure health scoring.
Your primary objectives are to evaluate:
1. AI DISCOVERABILITY: Can AI engines (SearchGPT, Perplexity, Claude, Google SGE) discover, parse, trust, and retrieve the brand correctly?
2. ON-SITE ENGAGEMENT: When an AI-referred visitor lands on the site, does the page clearly communicate the value proposition and provide obvious next actions (CTAs)?
3. TECHNICAL HEALTH: Infrastructure checks (SSL, latency, redirects, sitemaps) serve ONLY as supporting diagnostics.

EVIDENCE PACKET:
{json.dumps(packet, indent=2)}

REASONING GUIDELINES:
1. Classify every candidate finding into its primary dimension: 'ai_discoverability', 'onsite_engagement', or 'technical_health'.
2. Infrastructure issues (SSL expiration warning, slow response latency, missing sitemap) MUST receive lower business priority than AI discoverability or value proposition gaps unless they physically block crawling or rendering.
3. If raw HTML lacks an H1 header but Playwright rendering captured a valid H1 post-hydration, evaluate whether client-side rendering creates a real RAG indexing trap.
4. Combine multi-skill evidence: if Organization schema matches a verified Wikidata entity (Q-ID), entity identity is strongly corroborated.
5. Allowed 'decision' vocabulary: ONLY 'VALID', 'QUESTIONABLE', or 'REJECT'.
   - 'VALID': Evidence strongly supports the finding.
   - 'QUESTIONABLE': Evidence is weak, ambiguous, or finding is rendered post-JS.
   - 'REJECT': Evidence contradicts the candidate or finding is a false positive.
6. You MUST NOT invent new finding IDs. Every 'finding_id' in output MUST exist in candidate_findings.

STRICT JSON OUTPUT FORMAT:
{{
  "results": [
    {{
      "finding_id": "F-001",
      "decision": "VALID",
      "confidence": 0.92,
      "severity": "high",
      "primary_dimension": "ai_discoverability",
      "business_impact": "high",
      "reasoning_summary": "...",
      "mechanism_impact": "...",
      "recommended_action": "...",
      "evidence_used": ["rendered_dom", "semantics"]
    }}
  ]
}}
"""
        return prompt

    def evaluate_evidence_packet(self, packet: Dict[str, Any], timeout_sec: Optional[float] = None) -> Tuple[str, Optional[Dict[str, Any]], bool]:
        """
        Executes Gemini reasoning with transient retries, circuit breaker protection, and SHA-256 hash caching.
        Returns: (status, llm_response_dict, cache_hit)
        """
        if not self.enabled:
            return "DISABLED", None, False

        if not self.api_key:
            return "UNAVAILABLE", None, False

        if not self.circuit_breaker.allow_request():
            return "CIRCUIT_OPEN", None, False

        packet_hash = compute_packet_hash(packet, self.model, provider="gemini", prompt_version=PROMPT_VERSION)

        if packet_hash in _RESPONSE_CACHE:
            return "SUCCESS", _RESPONSE_CACHE[packet_hash], True

        prompt_text = self.generate_reasoning_prompt(packet)
        endpoint_url = GEMINI_REST_ENDPOINT.format(model=self.model)
        timeout = timeout_sec if timeout_sec is not None else self.timeout_seconds

        # Base generation configuration compatible with all models
        gen_config: Dict[str, Any] = {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }

        # thinkingBudget=256 bounds thinking models (3.6 / 3.7) to avoid prolonged thinking stalls
        if any(v in self.model for v in ["3.6", "3.7", "2.5"]):
            gen_config["thinkingConfig"] = {
                "thinkingBudget": 256
            }

        request_body = {
            "contents": [{
                "parts": [{"text": prompt_text}]
            }],
            "generationConfig": gen_config
        }
        body_bytes = json.dumps(request_body).encode('utf-8')
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        last_status = "FAILED"
        total_attempts = max(1, self.max_retries + 1)

        for attempt in range(1, total_attempts + 1):
            try:
                req = urllib.request.Request(endpoint_url, data=body_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        resp_body = resp.read().decode('utf-8')
                        try:
                            data = json.loads(resp_body)
                            candidates = data.get("candidates", [])
                            if not candidates:
                                print(f"[Gemini Error] No candidates returned: {data}")
                                self.circuit_breaker.record_failure()
                                return "MALFORMED_RESPONSE", None, False

                            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if not raw_text:
                                print(f"[Gemini Error] Empty text in candidate parts: {candidates[0]}")
                                self.circuit_breaker.record_failure()
                                return "MALFORMED_RESPONSE", None, False

                            # Strip markdown fences if present
                            clean_text = raw_text.strip()
                            if clean_text.startswith("```json"):
                                clean_text = clean_text[7:]
                            if clean_text.startswith("```"):
                                clean_text = clean_text[3:]
                            if clean_text.endswith("```"):
                                clean_text = clean_text[:-3]

                            parsed_json = json.loads(clean_text.strip())
                            if "results" not in parsed_json or not isinstance(parsed_json["results"], list):
                                print(f"[Gemini Error] 'results' array missing from parsed response: {parsed_json}")
                                self.circuit_breaker.record_failure()
                                return "MALFORMED_RESPONSE", None, False

                            self.circuit_breaker.record_success()
                            _RESPONSE_CACHE[packet_hash] = parsed_json
                            return "SUCCESS", parsed_json, False

                        except Exception as parse_err:
                            print(f"[Gemini Parse Error] Could not parse model response: {parse_err}")
                            self.circuit_breaker.record_failure()
                            return "MALFORMED_RESPONSE", None, False
                    else:
                        last_status = "FAILED"

            except urllib.error.HTTPError as e:
                code = e.code
                error_body = ""
                try:
                    error_body = e.read().decode('utf-8')
                except Exception:
                    pass
                print(f"[Gemini HTTPError] HTTP {code}: {error_body}")

                if code == 429:
                    last_status = "RATE_LIMITED"
                elif code in [500, 502, 503, 504]:
                    last_status = "PROVIDER_UNAVAILABLE"
                elif code in [400, 404]:
                    last_status = "PROVIDER_UNAVAILABLE"
                    self.circuit_breaker.record_failure()
                    return last_status, None, False
                elif code in [401, 403]:
                    self.circuit_breaker.record_failure()
                    return "UNAVAILABLE", None, False
                else:
                    last_status = "FAILED"

                if code in [429, 500, 502, 503, 504] and attempt < total_attempts:
                    time.sleep(1.0 * (2 ** (attempt - 1)))
                    continue
                else:
                    self.circuit_breaker.record_failure()
                    return last_status, None, False

            except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
                is_timeout = isinstance(e, socket.timeout) or "timed out" in str(e).lower()
                print(f"[Gemini Network Error] {'Socket Timeout' if is_timeout else 'URLError'}: {e}")
                last_status = "TIMEOUT" if is_timeout else "FAILED"

                if attempt < total_attempts:
                    time.sleep(1.0 * (2 ** (attempt - 1)))
                    continue
                else:
                    self.circuit_breaker.record_failure()
                    return last_status, None, False

            except Exception as e:
                print(f"[Gemini Unexpected Exception] {type(e).__name__}: {e}")
                self.circuit_breaker.record_failure()
                return "FAILED", None, False

        self.circuit_breaker.record_failure()
        return last_status, None, False

def apply_gemini_reasoning_and_guardrails(state: AuditState, llm_engine: ReasoningEngine) -> List[Finding]:
    """
    Applies Gemini reasoning decisions to AuditState candidate findings with strict Python safety guardrails.
    """
    packet = build_evidence_packet(state)

    t0 = time.time()
    status, llm_response, cache_hit = llm_engine.evaluate_evidence_packet(packet)
    t1 = time.time()
    latency_ms = int(round((t1 - t0) * 1000))
    model_name = getattr(llm_engine, "model", DEFAULT_MODEL)
    is_enabled = getattr(llm_engine, "enabled", True)
    has_api_key = bool(getattr(llm_engine, "api_key", "").strip()) or status == "SUCCESS"

    if not is_enabled:
        status = "DISABLED"

    state.llm_observations = {
        "enabled": is_enabled,
        "provider": "gemini",
        "model": model_name,
        "configured": has_api_key,
        "attempted": is_enabled and has_api_key,
        "used": status == "SUCCESS",
        "status": status,
        "fallback_used": status != "SUCCESS",
        "call_count": 0 if (cache_hit or status in ["DISABLED", "NOT_CONFIGURED", "UNAVAILABLE", "CIRCUIT_OPEN"]) else 1,
        "latency_ms": latency_ms,
        "cache_hit": cache_hit,
        "packet_hash": compute_packet_hash(packet, model_name, provider="gemini", prompt_version=PROMPT_VERSION)
    }

    if status != "SUCCESS" or not llm_response:
        return state.validate_and_deduplicate_findings()

    valid_candidate_ids = set(f.id for f in state.candidate_findings)
    candidate_map = {f.id: f for f in state.candidate_findings}

    results = llm_response.get("results", [])
    validated_findings = []
    summary_counts = {"valid": 0, "questionable": 0, "rejected": 0}

    for item in results:
        if not isinstance(item, dict):
            continue

        fid = item.get("finding_id")
        if fid not in valid_candidate_ids:
            continue

        decision = str(item.get("decision", "")).upper()
        if decision not in ["VALID", "QUESTIONABLE", "REJECT"]:
            decision = "QUESTIONABLE"

        finding = candidate_map[fid]

        try:
            raw_conf = float(item.get("confidence", 0.8))
        except (ValueError, TypeError):
            raw_conf = 0.8
        calibrated_conf = min(1.0, max(0.0, raw_conf))

        rec_severity = str(item.get("severity", finding.severity)).lower()
        if rec_severity not in ["critical", "high", "medium", "low"]:
            rec_severity = finding.severity

        if calibrated_conf < 0.40 and rec_severity in ["critical", "high"]:
            rec_severity = "medium"

        if decision == "REJECT":
            summary_counts["rejected"] += 1
            state.add_evidence(
                url=finding.affected_urls[0] if finding.affected_urls else f"https://{state.normalized_domain}",
                page_context=f"Gemini Validation: '{finding.title}'",
                observation=f"Finding REJECTED by Gemini reasoning engine: {item.get('reasoning_summary')}",
                status=EvidenceStatus.CONTRADICTED,
                source_type="metadata",
                confidence=calibrated_conf,
                source_skill="gemini-engine"
            )

        elif decision == "QUESTIONABLE":
            summary_counts["questionable"] += 1
            final_sev = "low" if rec_severity in ["low", "medium"] else "medium"
            final_conf = min(0.50, calibrated_conf)

            finding.severity = final_sev
            finding.confidence = final_conf
            if item.get("reasoning_summary"):
                finding.evidence += f" [AI Interpretation: {item.get('reasoning_summary')}]"
            if item.get("mechanism_impact"):
                finding.mechanism_impact = item.get("mechanism_impact")
            if item.get("recommended_action"):
                finding.suggested_action.summary = item.get("recommended_action")

            validated_findings.append(finding)

        elif decision == "VALID":
            summary_counts["valid"] += 1
            finding.severity = rec_severity
            finding.confidence = calibrated_conf
            if item.get("primary_dimension"):
                finding.primary_dimension = str(item.get("primary_dimension")).lower()
            if item.get("business_impact"):
                finding.business_impact = str(item.get("business_impact")).lower()
            
            # Guardrail: Preserve UNAVAILABLE origin if original finding was UNAVAILABLE
            if finding.evidence_origin != EvidenceStatus.UNAVAILABLE:
                finding.reasoning_source = "gemini"
                finding.evidence_origin = EvidenceStatus.AI_VALIDATED
                
            if item.get("reasoning_summary"):
                finding.evidence += f" [AI Interpretation: {item.get('reasoning_summary')}]"
            if item.get("mechanism_impact"):
                finding.mechanism_impact = item.get("mechanism_impact")
            if item.get("recommended_action"):
                finding.suggested_action.summary = item.get("recommended_action")

            validated_findings.append(finding)

    state.llm_observations["summary"] = summary_counts

    evaluated_ids = set(item.get("finding_id") for item in results if isinstance(item, dict))
    for fid, f in candidate_map.items():
        if fid not in evaluated_ids and f not in validated_findings:
            validated_findings.append(f)

    state.candidate_findings = validated_findings
    return state.validate_and_deduplicate_findings()