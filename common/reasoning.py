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

class DeterministicReasoningEngine:
    """
    Deterministic Reasoning Framework for Brand AI Readiness Audit.
    Evaluates evidence-backed observations, calculates calibrated confidence, enforces mechanism-based
    priority & severity safety rules, and generates non-generic technical recommendations.
    """

    @staticmethod
    def calculate_priority(severity: str, confidence: float) -> str:
        sev = severity.lower()
        if sev == "critical":
            return "P0" if confidence >= 0.70 else "P2"
        elif sev == "high":
            return "P1" if confidence >= 0.50 else "P2"
        elif sev == "medium":
            return "P2"
        else:
            return "P3"

    @staticmethod
    def apply_false_positive_rules(finding: Finding, state: AuditState) -> Tuple[Finding, str]:
        """
        Cross-validates candidate findings against multi-skill evidence to eliminate false positives.
        Returns: (updated_finding, status) where status is 'VALID', 'QUESTIONABLE', or 'REJECT'
        """
        domain = state.normalized_domain
        fid = finding.id.lower()
        title_lower = finding.title.lower()
        rendering_meta = state.rendering_metadata.get("comparison", {})

        # Rule 1: Raw H1 Missing vs Rendered DOM H1
        if "h1" in fid or "heading" in title_lower or "h1" in title_lower:
            if rendering_meta.get("h1_revealed_via_js"):
                finding.severity = "low"
                finding.confidence = 0.50
                finding.priority = "P3"
                finding.title = f"H1 heading tag requires JavaScript client-side rendering on {domain}"
                finding.evidence += " [Cross-Validation: H1 heading tag is instantiated dynamically post-JS hydration.]"
                finding.why_it_matters = "Non-JS crawlers and static RAG parsers may fail to extract the primary document title if H1 is client-side rendered."
                finding.mechanism_impact = "Client-side H1 rendering creates latency dependencies for static HTML vector chunkers."
                finding.suggested_action.summary = f"Pre-render the primary <h1> hero heading in server-rendered HTML for {domain}."
                finding.suggested_action.priority = "low"
                return finding, "QUESTIONABLE"

        # Rule 2: Raw Links vs Rendered DOM Links
        if "link" in fid or "navigation" in title_lower or "link" in title_lower:
            new_links = rendering_meta.get("new_links_count", 0)
            if new_links > 5:
                finding.severity = "medium"
                finding.confidence = 0.75
                finding.priority = "P2"
                finding.why_it_matters = f"Discovered {new_links} critical navigation links only after client-side JavaScript execution."
                finding.mechanism_impact = "Static AI spiders cannot discover client-side rendered subpages without crawling rendered DOM trees."
                finding.suggested_action.summary = f"Expose primary navigation links in server-rendered HTML tags on {domain}."
                return finding, "VALID"

        # Rule 3: Organization Schema vs Wikidata/Wikipedia Entity Resolution
        if "organization" in fid or "schema" in fid or "org" in fid or "organization" in title_lower or "schema" in title_lower:
            wiki_entity = state.entity_observations.get("wikidata_entity") or state.corroboration_observations.get("wikidata_entity")
            qid = wiki_entity.get("id") if wiki_entity else None
            qid_str = f" pointing to https://www.wikidata.org/wiki/{qid}" if qid else ""
            same_as = [f"https://www.wikidata.org/wiki/{qid}"] if qid else []
            dynamic_jsonld = json.dumps({
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": state.brand,
                "url": f"https://{domain}",
                "sameAs": same_as
            }, indent=2)
            finding.confidence = 0.85
            finding.why_it_matters = f"Brand '{state.brand}' lacks explicit Schema.org Organization markup on target homepage."
            finding.mechanism_impact = "Missing Organization JSON-LD prevents AI search engines from mapping local domain URLs directly to universal knowledge graph entity IDs."
            finding.suggested_action.summary = f"Inject Organization JSON-LD script containing sameAs link{qid_str} for '{state.brand}' on {domain}."
            finding.suggested_action.recommendation = f'<script type="application/ld+json">\n{dynamic_jsonld}\n</script>'
            return finding, "VALID"

        # Default: Valid direct observation
        return finding, "VALID"

    @classmethod
    def enrich_and_validate_findings(cls, state: AuditState) -> List[Finding]:
        raw_candidates = state.candidate_findings
        validated_findings = []

        for candidate in raw_candidates:
            finding, decision = cls.apply_false_positive_rules(candidate, state)

            if decision == "REJECT":
                continue

            if finding.confidence < 0.40 and finding.severity in ["critical", "high"]:
                finding.severity = "medium"

            if finding.confidence < 0.60 and finding.severity == "critical":
                finding.severity = "high"

            finding.priority = cls.calculate_priority(finding.severity, finding.confidence)
            finding.reasoning_source = "deterministic"

            if not finding.why_it_matters or finding.why_it_matters.startswith("Impacts AI"):
                finding.why_it_matters = (
                    f"Directly impacts how Generative Search engines (SearchGPT, Perplexity, Google SGE) "
                    f"index and corroborate {state.brand}'s primary domain ({state.normalized_domain})."
                )

            validated_findings.append(finding)

        state.candidate_findings = validated_findings
        return state.validate_and_deduplicate_findings()


def _load_env_file(force: bool = False):
    if not force and "GEMINI_API_KEY" in os.environ and os.environ["GEMINI_API_KEY"].strip():
        return

    candidate_dirs = [
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    ]

    checked_dirs = set()
    for start_dir in candidate_dirs:
        cur = start_dir
        while cur and cur not in checked_dirs:
            checked_dirs.add(cur)
            env_path = os.path.join(cur, ".env")
            if os.path.exists(env_path) and os.path.isfile(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for raw_line in f:
                            line = raw_line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if line.lower().startswith("export ") or line.lower().startswith("export\t"):
                                line = line[6:].strip()
                            if "=" in line:
                                k, v = line.split("=", 1)
                                k = k.strip()
                                v = v.strip()
                                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                                    v = v[1:-1]
                                else:
                                    if " #" in v:
                                        v = v.split(" #", 1)[0].strip()
                                    elif "\t#" in v:
                                        v = v.split("\t#", 1)[0].strip()
                                    v = v.strip("'\"")
                                if k and v:
                                    if force or k not in os.environ:
                                        os.environ[k] = v
                except Exception as e:
                    print(f"[Environment Loader Warning] Failed to read {env_path}: {e}")
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent

    if not os.environ.get("GEMINI_API_KEY", "").strip() and os.environ.get("GOOGLE_API_KEY", "").strip():
        os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"].strip()

_load_env_file()

def reload_env():
    _load_env_file(force=True)

PROMPT_VERSION = "phase5-v2"

# Robust Defaults — Extended 25s timeout and 1 retry
DEFAULT_ENABLED = os.environ.get("GEMINI_ENABLED", "true").lower() in ["true", "1", "yes"]
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_TIMEOUT_SEC = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "25.0"))
DEFAULT_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "1"))

GEMINI_REST_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}

class CircuitBreaker:
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

GLOBAL_CIRCUIT_BREAKER = CircuitBreaker()

def sanitize_evidence_packet(data: Any) -> Any:
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
    packet_str = json.dumps(packet, sort_keys=True)
    combined = f"{prompt_version}:{provider}:{model}:{packet_str}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

def build_evidence_packet(state: AuditState) -> Dict[str, Any]:
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

        _load_env_file()
        env_enabled_str = os.environ.get("GEMINI_ENABLED", "true").lower()
        self.enabled = enabled if enabled is not None else (env_enabled_str in ["true", "1", "yes"])
        resolved_key = api_key if api_key is not None else (os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip())
        self.api_key = resolved_key.strip()
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_SEC
        self.max_retries = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES
        self.circuit_breaker = circuit_breaker or GLOBAL_CIRCUIT_BREAKER

        if self.api_key:
            print(f"[AI Engine] GEMINI_API_KEY detected (redacted). Model: {self.model}. Gemini reasoning engine ready.")
        else:
            print(f"[AI Engine] No GEMINI_API_KEY detected. Operating in deterministic fallback mode.")

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
        if not self.enabled:
            return "DISABLED", None, False

        if not self.api_key:
            return "NOT_CONFIGURED", None, False

        if not self.circuit_breaker.allow_request():
            print(f"[AI Engine Warning] Circuit breaker is OPEN. Fallback engine active.")
            return "CIRCUIT_OPEN", None, False

        packet_hash = compute_packet_hash(packet, self.model, provider="gemini", prompt_version=PROMPT_VERSION)

        if packet_hash in _RESPONSE_CACHE:
            print(f"[AI Engine Cache] Cache hit for packet hash: {packet_hash[:16]}...")
            return "SUCCESS", _RESPONSE_CACHE[packet_hash], True

        prompt_text = self.generate_reasoning_prompt(packet)
        endpoint_url = GEMINI_REST_ENDPOINT.format(model=self.model)
        timeout = timeout_sec if timeout_sec is not None else self.timeout_seconds

        gen_config: Dict[str, Any] = {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }

        if any(v in self.model for v in ["3.7", "2.5"]):
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

        print(f"[AI Engine Request] Model: {self.model} | Endpoint: {endpoint_url} | Timeout: {timeout}s | MaxRetries: {self.max_retries} | Payload: {len(body_bytes)} bytes")

        last_status = "FAILED"
        total_attempts = max(1, self.max_retries + 1)

        for attempt in range(1, total_attempts + 1):
            attempt_start = time.time()
            print(f"[AI Engine Attempt] {attempt}/{total_attempts} — Sending request to {self.model}...")
            try:
                req = urllib.request.Request(endpoint_url, data=body_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    resp_body = resp.read().decode('utf-8')
                    elapsed = time.time() - attempt_start
                    print(f"[AI Engine Response] HTTP {resp.status} in {elapsed:.2f}s | ResponseLen: {len(resp_body)} chars")
                    
                    if resp.status == 200:
                        try:
                            data = json.loads(resp_body)
                            candidates = data.get("candidates", [])
                            if not candidates:
                                self.circuit_breaker.record_failure()
                                return "MALFORMED_RESPONSE", None, False

                            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            clean_text = raw_text.strip()
                            if clean_text.startswith("```json"):
                                clean_text = clean_text[7:]
                            if clean_text.startswith("```"):
                                clean_text = clean_text[3:]
                            if clean_text.endswith("```"):
                                clean_text = clean_text[:-3]

                            parsed_json = json.loads(clean_text.strip())
                            if "results" not in parsed_json or not isinstance(parsed_json["results"], list):
                                self.circuit_breaker.record_failure()
                                return "MALFORMED_RESPONSE", None, False

                            self.circuit_breaker.record_success()
                            _RESPONSE_CACHE[packet_hash] = parsed_json
                            print(f"[AI Engine Success] Request completed in {elapsed:.2f}s with {len(parsed_json.get('results', []))} results")
                            return "SUCCESS", parsed_json, False

                        except Exception as parse_err:
                            print(f"[AI Engine Parse Error] Could not parse model response: {parse_err}")
                            self.circuit_breaker.record_failure()
                            return "MALFORMED_RESPONSE", None, False
                    else:
                        last_status = "FAILED"

            except urllib.error.HTTPError as e:
                elapsed = time.time() - attempt_start
                code = e.code
                error_body = ""
                try:
                    error_body = e.read().decode('utf-8')
                except Exception:
                    pass
                
                print(f"[AI Engine HTTPError] HTTP {code} in {elapsed:.2f}s | Body: {error_body[:300]}")

                if code == 429:
                    last_status = "RATE_LIMITED"
                    if attempt < total_attempts:
                        time.sleep(2.0 * attempt)
                        continue
                    else:
                        self.circuit_breaker.record_failure()
                        return last_status, None, False
                elif code in [500, 502, 503, 504]:
                    last_status = "PROVIDER_UNAVAILABLE"
                    if attempt < total_attempts:
                        time.sleep(1.0 * attempt)
                        continue
                    else:
                        self.circuit_breaker.record_failure()
                        return last_status, None, False
                elif code in [401, 403]:
                    self.circuit_breaker.record_failure()
                    return "INVALID_KEY", None, False
                else:
                    last_status = "FAILED"
                    self.circuit_breaker.record_failure()
                    return last_status, None, False

            except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
                elapsed = time.time() - attempt_start
                is_timeout = isinstance(e, socket.timeout) or "timed out" in str(e).lower()
                print(f"[AI Engine Network Error] {'Socket Timeout' if is_timeout else 'URLError'} in {elapsed:.2f}s: {e}")
                last_status = "TIMEOUT" if is_timeout else "FAILED"

                if attempt < total_attempts:
                    time.sleep(1.0 * attempt)
                    continue
                else:
                    self.circuit_breaker.record_failure()
                    return last_status, None, False

            except Exception as e:
                self.circuit_breaker.record_failure()
                return "FAILED", None, False

        self.circuit_breaker.record_failure()
        return last_status, None, False

def apply_gemini_reasoning_and_guardrails(state: AuditState, llm_engine: ReasoningEngine) -> List[Finding]:
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
        "call_count": 0 if (cache_hit or status in ["DISABLED", "NOT_CONFIGURED", "INVALID_KEY", "CIRCUIT_OPEN"]) else 1,
        "latency_ms": latency_ms,
        "cache_hit": cache_hit,
        "packet_hash": compute_packet_hash(packet, model_name, provider="gemini", prompt_version=PROMPT_VERSION),
        "engine_type": "gemini" if is_enabled else "deterministic",
        "error_details": None if status == "SUCCESS" else {
            "DISABLED": "AI reasoning disabled by configuration",
            "NOT_CONFIGURED": "No API key configured",
            "UNAVAILABLE": "API key not available or missing",
            "INVALID_KEY": "Invalid API key (HTTP 401/403)",
            "CIRCUIT_OPEN": "Circuit breaker open after repeated failures",
            "RATE_LIMITED": "API rate limit exceeded (HTTP 429)",
            "PROVIDER_UNAVAILABLE": "Provider service unavailable (HTTP 5xx)",
            "TIMEOUT": "Request timeout",
            "MALFORMED_RESPONSE": "Malformed API response",
            "FAILED": "General request failure"
        }.get(status, status)
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