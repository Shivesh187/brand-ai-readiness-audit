---
name: freshness-corroboration
description: Audits fact consistency, entity resolution, Wikipedia/Wikidata corroboration, sameAs link signals, and factual freshness.
version: 1.0.0
---

# Freshness & Corroboration Skill

This skill performs factual alignment verification, ensuring that a brand's core data assertions match authoritative entity knowledge graphs (Wikidata, Wikipedia, Crunchbase). It verifies external entity resolution, `sameAs` link properties, and evaluates brand name semantic collision risks in LLM vector retrieval pipelines.

## Reference Configurations
- Authoritative Indices Registry: [authority_sources.json](./references/authority_sources.json)

## Execution Logic

This skill operates in-memory over the shared `AuditState` pipeline. When executed via CLI or script, run:

```bash
python3 ./skills/freshness-corroboration/scripts/check_corroboration.py "<brand_name>" '<claims_json>'
```

### Key Responsibilities:
1. **External Entity Resolution**: Queries Wikidata and Wikipedia APIs to locate authoritative knowledge graph entries (`Q-IDs`).
2. **SameAs Signal Triangulation**: Verifies whether on-page Organization schemas contain `sameAs` links pointing to authoritative Wikipedia/Wikidata entity pages.
3. **Brand Name Ambiguity & Collision**: Evaluates brand name lexical structure against common English dictionary nouns to measure vector index retrieval collision risks.
4. **Fact Corroboration**: Categorizes facts into `CORROBORATED`, `CONTRADICTED`, or `UNKNOWN` states.
