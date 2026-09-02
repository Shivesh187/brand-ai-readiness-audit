# Brand AI Readiness Audit — Skill Marketplace

This repository hosts a multi-agent skill marketplace compliant with the [agentskills.io](https://agentskills.io) specification. The marketplace performs comprehensive, non-invasive diagnostic audits evaluating how visible, crawlable, structured, corroborated, and frequently cited a brand is within Generative AI Search Engines and Large Language Model (LLM) RAG indexes.

*Note: This audit system is recommendation-only and performs passive diagnostic checks; it never modifies live websites.*

---

## 🏗️ Marketplace Skills

The marketplace is structured into five specialized skills:

1. **`audit-orchestrator` (Marketplace Entrypoint)**
   * **Role**: Central pipeline coordinator and synthesis engine.
   * **Mechanism**: Initializes shared in-memory `AuditState`, composes the four domain audit skills, handles Playwright rendering decisions, executes optional Gemini 3.7 Flash reasoning, applies Python safety guardrails, and outputs the final score and report.

2. **`crawl-render-audit` (`skills/crawl-render-audit`)**
   * **Role**: Technical crawler permissions, network metrics, and DOM rendering.
   * **Mechanism**: Inspects `robots.txt` access rules for AI bots (`GPTBot`, `ClaudeBot`, `PerplexityBot`), validates SSL certificates, executes Playwright headless browser rendering for client-side hydrated web apps, and measures raw vs rendered DOM differences.

3. **`semantic-readiness` (`skills/semantic-readiness`)**
   * **Role**: Metadata, structured data, and semantic hierarchy evaluation.
   * **Mechanism**: Evaluates Schema.org JSON-LD definitions (`Organization`, `Product`, `FAQPage`), heading hierarchies (`H1`-`H6`), locked image/canvas text risks, and context chunkability for LLM context windows.

4. **`freshness-corroboration` (`skills/freshness-corroboration`)**
   * **Role**: Fact consistency and external entity resolution.
   * **Mechanism**: Queries authoritative knowledge graphs (Wikidata, Wikipedia) to verify entity identity, checks `sameAs` schema links, and categorizes claims into `CORROBORATED`, `CONTRADICTED`, or `UNKNOWN` states.

5. **`engagement-audit` (`skills/engagement-audit`)**
   * **Role**: Layout density, summarization readiness, and preview card optimization.
   * **Mechanism**: Evaluates text-to-code ratios, hero section value propositions, meta descriptions, and preview card readiness for Generative Search engine result snippets.

---

## ⚙️ Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Playwright Browsers (Optional for Client-Side JS Rendering)
```bash
python3 -m playwright install chromium
```

### 3. Configure Environment Variables (Optional)
Copy `.env.example` to `.env` or set environment variables in your shell:

```bash
export GEMINI_API_KEY="your_api_key_here"
export GEMINI_MODEL="gemini-3.7-flash"
```

*Note: `GEMINI_API_KEY` is completely optional. If missing or invalid, the audit engine gracefully falls back to deterministic candidate audit findings.*

---

## 🌐 Web Application Interface

Launch the interactive local web server:

```bash
python3 server.py
```

Then open your browser and navigate to:
```text
http://localhost:8080
```

---

## 🚀 Running via Command Line (CLI)

### Basic Execution Command
```bash
python3 skills/audit-orchestrator/scripts/run_audit.py --url example.com --brand Example
```

### Deterministic-Only Mode (Bypass AI Engine)
```bash
python3 skills/audit-orchestrator/scripts/run_audit.py --url react.dev --brand React --no-llm
```

### Live Gemini Smoke Test Script
```bash
python3 scripts/test_gemini_live.py
```

### Run Automated Unit Test Suite
```bash
python3 -m unittest discover -s tests
```

---

## 📂 Directory Structure

```text
.
├── marketplace.json                # Catalog manifest for agentskills.io standard
├── README.md                       # Architecture & execution guide
├── requirements.txt                # Dependency manifest
├── server.py                       # Python Web Application Server (POST /api/audit, GET /api/health)
├── .env.example                    # Environment variable configuration template
├── .gitignore                      # Git exclusion rules
├── common/                         # Shared infrastructure
│   ├── __init__.py
│   ├── models.py                   # AuditState, Finding, Evidence, & AuditReport dataclasses
│   ├── http_client.py              # Resilient IPv4 curl/HTTP fetcher with decompression
│   └── llm_client.py               # GeminiReasoningEngine & Python safety guardrails
├── web/                            # Adobe Spectrum-styled Web UI
│   ├── index.html                  # Main Web UI template
│   ├── styles.css                  # Modern UI design system & responsive layout
│   └── app.js                      # Interactive frontend logic & API client
├── scripts/
│   └── test_gemini_live.py         # Live Gemini API verification script
├── skills/                         # Marketplace skills
│   ├── audit-orchestrator/         # ENTRYPOINT: Orchestration & pipeline coordination
│   ├── crawl-render-audit/         # AI crawler permissions & Playwright rendering
│   ├── semantic-readiness/         # Schema.org & semantic HTML structure checks
│   ├── freshness-corroboration/    # Wikidata & Wikipedia entity resolution
│   └── engagement-audit/           # Text density & preview card readiness checks
└── tests/
    ├── test_audit.py               # Automated audit pipeline unit test suite
    └── test_server.py              # Web API server unit test suite
```
