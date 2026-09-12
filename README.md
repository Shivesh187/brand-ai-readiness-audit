# Brand AI Readiness Audit — Agent Skills Marketplace

An enterprise-grade, multi-agent diagnostic marketplace compliant with the **[agentskills.io](https://agentskills.io)** specification.

This engine performs deep, non-invasive technical audits evaluating how crawlable, structured, corroborated, and citation-ready a brand is across Generative AI Search Engines (Perplexity, SearchGPT, Google AI Overviews) and LLM Retrieval-Augmented Generation (RAG) pipelines.

> **Operational Guardrail**: Passive and recommendation-only. It inspects observable telemetry over the wire and in-memory without altering or modifying live systems.

---

## 📑 Table of Contents

* [Architecture Overview](https://www.google.com/search?q=%23-architecture-overview)
* [Marketplace Skills](https://www.google.com/search?q=%23-marketplace-skills)
* [Multi-Tiered Reliability & Resilience](https://www.google.com/search?q=%23-multi-tiered-reliability--resilience)
* [Quick Start](https://www.google.com/search?q=%23-quick-start)
* [Running Audits](https://www.google.com/search?q=%23-running-audits)
* [Web Interface](https://www.google.com/search?q=%23-web-interface)
* [Automated Testing & Compliance](https://www.google.com/search?q=%23-automated-testing--compliance)
* [Directory Layout](https://www.google.com/search?q=%23-directory-layout)
* [Security & Safe Execution](https://www.google.com/search?q=%23-security--safe-execution)

---

## 🏗️ Architecture Overview

The marketplace coordinates five specialized domain skills via an in-memory blackboard architecture:

```
                      ┌─────────────────────────────────────────┐
                      │        Target URL & Brand Input         │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │    skills/audit-orchestrator (Entry)   │
                      │  Initializes AuditState & Telemetry Bus │
                      └───────┬─────────────────────────┬───────┘
                              │                         │
            ┌─────────────────┴────────┐       ┌────────┴─────────────────┐
            ▼                          ▼       ▼                          ▼
 ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
 │  crawl-render-audit  │   │  semantic-readiness  │   │ freshness-corrobor.  │
 │  • RFC 9309 Rules    │   │  • Schema.org JSONLD │   │  • Wikidata SPARQL   │
 │  • Headless Browser  │   │  • Heading Tree      │   │  • Entity Grounding  │
 │  • Latency / SSL     │   │  • Content Chunking  │   │  • Fact Consistency  │
 └──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
            │                          │                          │
            └─────────────────┬────────┴──────────────────────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │   engagement-audit   │
                   │ • Hero / CTA Checks  │
                   │ • Extraction Density │
                   │ • AI Preview Cards   │
                   └──────────┬───────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Synthesis & Calibration Gate                      │
│                                                                        │
│   ┌──────────────────────────────┐    ┌────────────────────────────┐   │
│   │ Gemini Reasoning Engine      │    │ Deterministic Engine       │   │
│   │ (Confidence, Nuance, Impact) │ or │ (Zero-LLM Offline Fallback)│   │
│   └──────────────┬───────────────┘    └─────────────┬──────────────┘   │
│                  │                                  │                  │
│                  └────────────────┬─────────────────┘                  │
│                                   ▼                                    │
│                     Strict Calibration Filters                         │
│             (Deduplication • Bounds Check • JSON Schema)               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │   Final Audit Report (0-100 Scorecard, Roadmaps, JSON)  │
       └─────────────────────────────────────────────────────────┘

```

---

## 🧩 Marketplace Skills

Every skill implements self-contained execution logic and standardized dataclass models:

| Skill | Directory | Primary Responsibilities |
| --- | --- | --- |
| **`audit-orchestrator`** *(Entrypoint)* | `skills/audit-orchestrator` | Central coordination, state lifecycle, Playwright render gating, Gemini reasoning integration, and JSON synthesis. |
| **`crawl-render-audit`** | `skills/crawl-render-audit` | Evaluates crawler directives (`GPTBot`, `ClaudeBot`, `PerplexityBot`), SSL lifecycle, redirect hops, and selective Playwright DOM hydration. |
| **`semantic-readiness`** | `skills/semantic-readiness` | In-depth Schema.org JSON-LD extraction (`Organization`, `Product`, `FAQPage`), header hierarchy validation, and semantic container chunking. |
| **`freshness-corroboration`** | `skills/freshness-corroboration` | Entity resolution via Wikidata SPARQL and Wikipedia APIs, validating `sameAs` references and identifying entity ambiguity. |
| **`engagement-audit`** | `skills/engagement-audit` | Inspects text-to-code ratios, viewport value propositions, high-contrast action triggers, and snippet preview cards. |

---

## 🛡️ Multi-Tiered Reliability & Resilience

The pipeline runs reliably across offline, rate-limited, or production environments:

* **Three-State Circuit Breaker (`CLOSED` ➔ `OPEN` ➔ `HALF-OPEN`)**: Automatically isolates external LLM service failures without halting the audit cycle.
* **Deterministic Fallback Engine**: If Gemini is disabled, unreachable, or credentials are omitted, audits execute via a rule-based fallback system.
* **Strict Evidence Provenance**: Findings are attributed to observable evidentiary states:
* `LIVE_OBSERVED` — Directly detected in wire response or DOM.
* `AI_VALIDATED` — Corroborated with multi-skill context.
* `UNAVAILABLE` — Endpoint timed out or blocked; scored neutrally to prevent false deductions.
* `CONTRADICTED` — Explicit structural mismatch detected.


* **Zero Shell Injections**: Subprocess tasks utilize structured array arguments (`shell=False`) with input normalization.

---

## ⚡ Quick Start

### 1. Prerequisites

* Python 3.9+ installed
* Google Gemini API Key *(Optional, deterministic fallback active by default)*

### 2. Installation

Clone the repository and install dependencies in a virtual environment:

```bash
git clone https://github.com/Shivesh187/brand-ai-readiness-audit.git
cd brand-ai-readiness-audit

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

```

### 3. Optional Headless Browser Setup

For JavaScript-heavy single-page applications (SPAs):

```bash
python3 -m playwright install chromium

```

### 4. Configuration (Optional)

Copy the environment template:

```bash
cp .env.example .env

```

Set credentials inside `.env`:

```env
GEMINI_API_KEY="AIzaSy..."
GEMINI_MODEL="gemini-3-flash-preview"
GEMINI_TIMEOUT_SECONDS="25.0"
GEMINI_MAX_RETRIES="1"

```

---

## 🚀 Running Audits

### CLI Mode

**Standard Multi-Skill Audit (with AI Reasoning)**

```bash
python3 skills/audit-orchestrator/scripts/run_audit.py --url "adobe.com" --brand "Adobe"

```

**Deterministic Offline Audit (Bypass LLM completely)**

```bash
python3 skills/audit-orchestrator/scripts/run_audit.py --url "adobe.com" --brand "Adobe" --no-llm

```

**Save Structured Report to File**

```bash
python3 skills/audit-orchestrator/scripts/run_audit.py --url "stripe.com" --brand "Stripe" > audit_report.json

```

---

## 🌐 Web Interface

The system includes a glassmorphic dashboard built using modern UI design principles.

### Start Web Server

```bash
python3 server.py

```

Open **`http://localhost:8080`** in your browser.

### Key Features

* **Three-Phase Layout**: Minimalist hero landing form (Phase 1), animated multi-agent orbital progress pipeline (Phase 2), and comprehensive executive scorecard (Phase 3).
* **Live Provenance Pills**: Granular indicators reflecting verification states for HTTP access, robots.txt, XML sitemaps, DOM rendering, schema extraction, and knowledge graph grounding.
* **Dynamic Findings Filter**: Real-time filtering across severity levels (`Critical`, `High`, `Medium`, `Low`) and audit modules (`Discoverability`, `Semantics`, `Corroboration`, `Engagement`).
* **Instant JSON Export**: Direct export of full audit records for reporting or downstream systems.

---

## 🧪 Automated Testing & Compliance

The codebase maintains full test coverage with strict regression enforcement:

```bash
# Run complete test suite (114 tests)
pytest -v

# Run agentskills.io marketplace compliance verification
python3 scripts/validate_marketplace.py

```

Expected compliance output:

```text
=== AGENTSKILLS.IO MARKETPLACE HYGIENE VALIDATOR ===
RESULT: SUCCESS — Marketplace is 100% compliant with agentskills.io standard!

```

---

## 📂 Directory Layout

```text
.
├── marketplace.json                    # agentskills.io catalog registry manifest
├── README.md                           # Project documentation & architecture manual
├── requirements.txt                    # Production dependencies
├── server.py                           # Application web server (REST endpoints)
├── .env.example                        # Sanitized configuration template
│
├── common/                             # Shared foundation runtime
│   ├── models.py                       # AuditState, Finding, EvidenceStatus dataclasses
│   ├── http_client.py                  # Resilient HTTP fetcher with redirect tracking
│   ├── crawler.py                      # Heuristic text-to-code crawler & DOM inspector
│   ├── reasoning.py                    # Gemini client & DeterministicReasoningEngine
│   └── llm_client.py                   # Unified reasoning exports & circuit breakers
│
├── skills/                             # Decoupled Domain Skills
│   ├── audit-orchestrator/             # Pipeline coordinator & scoring synthesis
│   │   ├── SKILL.md                    # agentskills.io skill manifest
│   │   └── scripts/run_audit.py        # CLI execution entrypoint
│   ├── crawl-render-audit/             # Crawler matrix, SSL, & Playwright renderer
│   │   ├── SKILL.md
│   │   └── scripts/check_access.py
│   ├── semantic-readiness/             # Schema.org JSON-LD & DOM heading parser
│   │   ├── SKILL.md
│   │   └── scripts/check_semantics.py
│   ├── freshness-corroboration/        # Wikidata SPARQL & entity corroboration
│   │   ├── SKILL.md
│   │   └── scripts/corroborate_facts.py
│   └── engagement-audit/               # Value proposition & preview card auditor
│       ├── SKILL.md
│       └── scripts/audit_engagement.py
│
├── web/                                # Glassmorphic UI dashboard
│   ├── index.html                      # Semantic 3-phase DOM template
│   ├── styles.css                      # Modern responsive design system
│   └── app.js                          # UI client & state management
│
├── scripts/                            # Operational utility tools
│   ├── validate_marketplace.py         # agentskills.io specification validator
│   └── test_gemini_live.py             # Live Gemini API endpoint probe
│
└── tests/                              # Automated test harness
    ├── test_audit.py                   # Core orchestrator & telemetry pipeline tests
    ├── test_reasoning.py               # Deterministic fallback & AI engine validation
    └── test_server.py                  # HTTP API endpoint tests

```

---

## 🔒 Security & Safe Execution

* **No Dynamic Injections**: All subprocess executions use explicit parameter lists (`shell=False`), eliminating remote code execution vectors.
* **Credential Redaction**: API keys and environment values are stripped and redacted from stdout/stderr, runtime logs, and serialized JSON reports.
* **Bounded Resource Usage**: Live HTTP queries enforce a 5-second socket timeout, and Playwright executions run within sandboxed, short-lived headless contexts.
* **Lightweight Archive Packaging**: The complete production submission package builds at **< 200 KB** by excluding developer artifacts (`.venv`, `__pycache__`, `.git`, `.env`).

---