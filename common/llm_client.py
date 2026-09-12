"""
LLM Client Interface & Re-Export Module.
Provides backwards-compatible interface linking to the active GeminiReasoningEngine
and DeterministicReasoningEngine in common.reasoning.
"""

from common.reasoning import (
    GeminiReasoningEngine,
    apply_gemini_reasoning_and_guardrails,
    _load_env_file,
    reload_env,
    compute_packet_hash,
    sanitize_evidence_packet,
    build_evidence_packet,
    CircuitBreaker,
    GLOBAL_CIRCUIT_BREAKER,
    ReasoningEngine,
    DeterministicReasoningEngine,
    DEFAULT_ENABLED,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SEC,
    DEFAULT_MAX_RETRIES,
    PROMPT_VERSION,
    _RESPONSE_CACHE,
)

__all__ = [
    "GeminiReasoningEngine",
    "apply_gemini_reasoning_and_guardrails",
    "_load_env_file",
    "reload_env",
    "compute_packet_hash",
    "sanitize_evidence_packet",
    "build_evidence_packet",
    "CircuitBreaker",
    "GLOBAL_CIRCUIT_BREAKER",
    "ReasoningEngine",
    "DeterministicReasoningEngine",
    "DEFAULT_ENABLED",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SEC",
    "DEFAULT_MAX_RETRIES",
    "PROMPT_VERSION",
    "_RESPONSE_CACHE",
]