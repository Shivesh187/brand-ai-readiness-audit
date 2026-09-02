---
name: crawl-render-audit
description: Evaluates technical crawler access, robots.txt directives, SSL/TLS metrics, Playwright headless rendering, and raw vs rendered DOM differences.
version: 1.0.0
---

# Crawl & Render Audit Skill

This skill performs low-level web discoverability and rendering checks: verifying if AI crawler agents are allowed to ingest content via `robots.txt`, evaluating network response metrics and SSL certificate validity, executing Playwright headless browser rendering for single-page applications, and measuring raw vs rendered DOM differences.

## Reference Configurations
- AI Bot Registry and Thresholds: [crawler_list.json](./references/crawler_list.json)

## Execution Logic

This skill operates in-memory over the shared `AuditState` pipeline. When executed via CLI or orchestrator script, run:

```bash
python3 ./skills/crawl-render-audit/scripts/check_access.py <target_domain>
```

### Key Responsibilities:
1. **Robots.txt & AI Crawler Directives**: Verifies whether critical AI scrapers (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `OAI-SearchBot`) are explicitly blocked or permitted.
2. **HTTP Acquisition & Latency**: Ensures acceptable HTTP status (`200 OK`) and checks response latency against performance thresholds.
3. **SSL Certificate Validation**: Confirms valid SSL certificates and checks expiration dates.
4. **Headless Browser Rendering**: Evaluates SPA rendering requirements and compares raw HTML vs post-JS rendered DOM to prevent false missing content penalties.
