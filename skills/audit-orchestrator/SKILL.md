---
name: audit-orchestrator
description: Coordinative skill that orchestrates the execution flow of the Brand AI Readiness Audit, invoking domain skills sequentially, aggregating findings, and generating a unified score.
version: 1.0.0
entrypoint: true
---

# Audit Orchestrator (Marketplace Entrypoint)

The `audit-orchestrator` is the central marketplace entrypoint for the Brand AI Readiness Audit. It initializes shared `AuditState`, coordinates acquisition and Playwright rendering, invokes the four specialized audit skills in sequence, shares structured evidence across skills, deduplicates candidate findings, executes the optional Gemini reasoning engine, applies strict Python safety guardrails, and computes the deterministic AI readiness score.

## Reference Sub-Skills
- Crawl & Render Audit: [crawl-render-audit/SKILL.md](../crawl-render-audit/SKILL.md)
- Semantic Readiness Check: [semantic-readiness/SKILL.md](../semantic-readiness/SKILL.md)
- Freshness & Corroboration Check: [freshness-corroboration/SKILL.md](../freshness-corroboration/SKILL.md)
- Engagement Audit Check: [engagement-audit/SKILL.md](../engagement-audit/SKILL.md)

## Execution Logic

To trigger a complete automated audit, execute the orchestrator script:

```bash
python3 ./skills/audit-orchestrator/scripts/run_audit.py --url <target_domain> [--brand "<brand_name>"] [--claims '<claims_json>'] [--no-llm]
```

### Key Responsibilities:
1. **Pipeline Initialization**: Initializes shared typed `AuditState`.
2. **HTTP Acquisition & Pre-fetching**: Fetches target domain HTML and evaluates response metrics.
3. **Specialized Skill Execution**: Sequentially runs `check_access.py` (crawl-render-audit), `check_semantics.py` (semantic-readiness), `check_corroboration.py` (freshness-corroboration), and `check_engagement.py` (engagement-audit).
4. **Hybrid Playwright Rendering**: Evaluates rendering decision metrics and executes Chromium DOM rendering for client-side hydrated web applications when required.
5. **AI Reasoning & Guardrails**: Builds compact multi-skill evidence packets for optional Gemini reasoning, enforcing strict Python confidence calibration and severity guardrails.
6. **Deterministic Scoring**: Calculates overall and sub-module readiness scores deterministically.
