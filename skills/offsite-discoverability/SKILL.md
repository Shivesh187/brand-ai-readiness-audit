---
name: offsite-discoverability
description: Evaluates a brand's technical and crawlers discoverability across AI search engines, public datasets, and API endpoints.
version: 1.0.0
---

# Offsite Discoverability Diagnostics

This skill performs low-level web discoverability checks, verifying if AI crawler agents are allowed to ingest content, checking network response metrics, and confirming SSL certificate validity.

## Reference Configurations
- AI Bot Registry and Thresholds: [crawler_list.json](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/offsite-discoverability/references/crawler_list.json)

## Execution Logic

To run this diagnostic, you must invoke the local Python agent script. This offloads deterministic network parsing, SSL handshakes, and response time calculations from the model to code.

### Diagnostic Command
Run the following script command from the workspace root:
```powershell
python ./skills/offsite-discoverability/scripts/check_access.py <target_domain>
```

### Steps for the AI Agent:

1. **Invoke Crawler Audit Script**: Execute the script command above with the target domain.
2. **Evaluate Robots.txt Rules**:
   - Compare the output's robots.txt access map against [crawler_list.json](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/offsite-discoverability/references/crawler_list.json).
   - Verify if critical bots (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `OAI-SearchBot`) are explicitly blocked or allowed.
3. **Verify HTTP Status & Performance**:
   - Ensure the home page returns an acceptable status code (typically `200` or safe redirections).
   - Check if response latency exceeds the maximum limit specified in references (`1500ms`). Slow sites are de-prioritized by active RAG search engines.
4. **Check SSL Certificates**:
   - Verify the SSL certificate is valid and is not expiring within the next `30 days`.
5. **Output Compilation**: Extract the JSON output from the script and format it into a diagnostic summary for the orchestrator.
