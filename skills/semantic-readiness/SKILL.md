---
name: semantic-readiness
description: Assesses semantic density, entity relationships, Schema.org structure, and context chunkability for LLM context windows.
version: 1.0.0
---

# Semantic Readiness Diagnostics

This skill evaluates the semantic structure of a website, verifying if schema metadata (JSON-LD) is valid and complete, analyzing the delta between raw and client-side rendered content, and detecting assets containing text locked away from semantic parsers.

## Reference Configurations
- Schema Requirements Checklist: [schema_checklists.json](./references/schema_checklists.json)

## Execution Logic

To perform this check, you must execute the semantic analyzer utility script. This ensures the parsing of HTML nodes, script extracting, and element tag validation is executed deterministically.

### Diagnostic Command
Run the following script command from the workspace root:
```powershell
python ./skills/semantic-readiness/scripts/check_semantics.py <target_domain_or_url>
```

### Steps for the AI Agent:

1. **Run DOM and Schema Scan**: Execute the Python script command above targeting the brand's primary landing page.
2. **Analyze Raw vs. Rendered DOM Delta**:
   - Inspect the script's `domComparison` output. If `hydrationRequired` is true or if the node/text size delta exceeds thresholds in [schema_checklists.json](./references/schema_checklists.json), note that a JavaScript rendering crawler (like SearchGPT/Perplexity) is required to index the full content.
3. **Verify Schema.org Validation**:
   - Review `schemasFound` and verify presence of `Organization`, `Product`, and `FAQPage` schemas against the target page type.
   - Cross-check property keys against requirements in [schema_checklists.json](./references/schema_checklists.json) (e.g., ensuring `Product` contains `offers` with pricing).
4. **Detect Locked Text Risks**:
   - Inspect `lockedTextRisk` reports.
   - For all images flagged with empty `alt` text, identify if they are hero banners or diagrammatic assets. If they contain text, recommend adding alt text.
   - Note all `<canvas>` nodes; because LLMs and semantic crawlers cannot parse canvas rendering context directly, recommend extracting canvas text into fallback HTML elements.
5. **Output Compilation**: Send the validated JSON report up to the orchestrator for indexing.
