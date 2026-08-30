---
name: offsite-corroboration
description: Audits fact consistency, entity resolution, and public sentiment alignment across third-party sources (Wikipedia, reviews, directory networks).
version: 1.0.0
---

# Offsite Corroboration Diagnostics

This skill performs factual alignment verification, ensuring that the brand's core data assertions match authority graphs (Wikidata, Wikipedia, Crunchbase). It also analyzes the brand name's lexical structure to calculate semantic collision/ambiguity risks in vector indexes.

## Reference Configurations
- Authoritative Indices Registry: [authority_sources.json](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/offsite-corroboration/references/authority_sources.json)

## Execution Logic

To evaluate offsite consensus and identify data discrepancies, run the local Python corroboration script. This parses entity dictionaries and evaluates brand name overlaps.

### Diagnostic Command
Run the following script command from the workspace root:
```powershell
python ./skills/offsite-corroboration/scripts/check_corroboration.py "<brand_name>" '<claims_json>'
```
*Example:*
```powershell
python ./skills/offsite-corroboration/scripts/check_corroboration.py "Example Corp" '{"founded": "2015", "headquarters": "Oakland, California", "ceo": "Jane Doe"}'
```

### Steps for the AI Agent:

1. **Verify Brand Name Ambiguity**:
   - Inspect the script's `ambiguityAnalysis` output.
   - If the brand name overlaps with common dictionary nouns (as logged in [authority_sources.json](file:///c:/Users/sunil/OneDrive/Desktop/Projects/Adobe/skills/offsite-corroboration/references/authority_sources.json)), flag a **Critical Ambiguity Risk**. For example, a company named "Stripe" or "Slack" requires significant context-hinting or schema grounding to prevent LLM retrieval mix-ups.
2. **Triangulate Factual Claims**:
   - Compare on-site facts (e.g. founding date, CEO, services) against off-site authority nodes.
   - For any "Conflict" status returned, log it as a mismatch. If the brand's primary site contradicts Wikipedia or Crunchbase, LLM retrievers may discard the website's factual claims as untrusted.
3. **Verify Uncorroborated Claims**:
   - Flag any claims marked as "Uncorroborated". Highlight to the user that these claims are only hosted on their primary domain and lack external validation signals, which lowers search engine authority.
4. **Output Compilation**: Extract the corroboration confidence score and forward it to the orchestrator.
