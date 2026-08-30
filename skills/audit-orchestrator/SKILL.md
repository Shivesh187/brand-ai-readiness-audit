---
name: audit-orchestrator
description: Coordinative skill that orchestrates the execution flow of the Brand AI Readiness Audit, invoking domain skills sequentially, aggregating findings, and generating a unified score.
version: 1.0.0
entrypoint: true
---

# Audit Orchestrator

The `audit-orchestrator` is the central coordination node for the Brand AI Readiness Audit. It manages inputs, launches execution routines for each of the four domain-specific verification scripts, normalizes findings, and structures a unified JSON report.

## Reference Sub-Skills
- Discoverability Check: [offsite-discoverability/SKILL.md](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/offsite-discoverability/SKILL.md)
- Semantic Readiness Check: [semantic-readiness/SKILL.md](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/semantic-readiness/SKILL.md)
- Offsite Corroboration Check: [offsite-corroboration/SKILL.md](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/offsite-corroboration/SKILL.md)
- Engagement Audit Check: [engagement-audit/SKILL.md](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/engagement-audit/SKILL.md)

## Execution Logic

To trigger a complete automated audit, call the orchestration script. The script invokes all sub-skill diagnostic scripts in series, capturing their JSON stdout streams, and maps them to a normalized format.

### Diagnostic Command
From the workspace root, run:
```powershell
python ./skills/audit-orchestrator/scripts/run_audit.py --url <target_domain> [--brand "<brand_name>"] [--claims '<claims_json>']
```

*Example:*
```powershell
python ./skills/audit-orchestrator/scripts/run_audit.py --url google.com --brand "Google"
```

### Steps for the AI Agent:

1. **Invoke Orchestrator Script**: Execute the script command above with the target site URL.
2. **Collect Sub-Skill Findings**:
   - The orchestrator will sequentially trigger:
     - `check_access.py`
     - `check_semantics.py`
     - `check_engagement.py`
     - `check_corroboration.py`
3. **Compile and Summarize Severity Counts**:
   - Extract raw findings, transform IDs to the standard `F-XXX` notation, and count issues grouping by `critical`, `high`, and `medium` severity.
4. **Inject Proactive Recommendations**:
   - Add high-value optimizations that help brands exceed baseline checks (e.g. AI sitemaps, Wikidata integration).
5. **Output Results**: Print the strict JSON schema detailing the audit timestamp, site metadata, counts, and findings list.
