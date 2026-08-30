---
name: engagement-audit
description: Measures brand presence, sentiment, and reference frequencies within LLM prompts, chat responses, and generative engine results.
version: 1.0.0
---

# Engagement Audit Diagnostics

This skill evaluates on-site layout signals to assess how effectively a landing page communicates its primary value proposition to AI agents, parses text-to-code ratios, and checks if site descriptions and headings are optimized for automated snippet extraction and preview generation.

## Reference Configurations
- Preview Summarization Heuristics: [preview_heuristics.json](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/engagement-audit/references/preview_heuristics.json)

## Execution Logic

To evaluate these on-site layout and summarization indexes, run the local Python engagement validator script. This script parses text weights and validates meta tags.

### Diagnostic Command
Run the following script command from the workspace root:
```powershell
python ./skills/engagement-audit/scripts/check_engagement.py <target_domain_or_url> "<brand_name>"
```
*Example:*
```powershell
python ./skills/engagement-audit/scripts/check_engagement.py "example.com" "Example Corp"
```

### Steps for the AI Agent:

1. **Audit On-Site Orientation (Above the Fold)**:
   - Verify if an `H1` header is present at the top of the document hierarchy.
   - Confirm that the hero section includes a clear value proposition containing at least `15` words but no more than `80` words (to prevent overly verbose summaries).
2. **Evaluate Text-to-Code Ratio**:
   - Inspect the `textToCodeRatio` in the script output.
   - Compare the ratio against the thresholds in [preview_heuristics.json](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/engagement-audit/references/preview_heuristics.json).
   - If the ratio is below `0.15` (15%), flag a warning. Low text ratios indicate the page is bloated with heavy HTML structures or excessive script snippets, hindering LLM scraper parsers and lowering page ranking in real-time searches.
3. **Verify Preview Summarization Readiness**:
   - Inspect `previewReadiness` metrics.
   - Verify the `metaDescription` is present and falls within the target range of `110` to `160` characters. LLMs and Search APIs use this meta tag as a fallback for displaying search result cards.
   - Confirm that the primary brand name appears within the first lead paragraph (first 200 characters) to ensure immediate entity association.
4. **Output Compilation**: Extract the validation JSON and submit the results to the orchestrator.
