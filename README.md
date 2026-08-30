# Brand AI Readiness Audit — Agent Skill Marketplace

This repository hosts a multi-agent skill marketplace compliant with the **[agentskills.io](https://agentskills.io)** specification. The marketplace is specifically engineered to perform comprehensive audits on how visible, crawlable, structured, corroborated, and frequently cited a brand is within Generative AI Search Engines (such as SearchGPT, Perplexity, Google SGE) and Large Language Models (LLMs).

---

## 🏗️ Multi-Skill Architecture

The marketplace uses a modular, hub-and-spoke multi-skill model where a single orchestrator skill serves as the central manager, delegating highly specialized tasks to four domain-specific skills. 

```mermaid
graph TD
    A([User Input / API Call]) --> B[audit-orchestrator (Entrypoint)]
    
    subgraph Domain Audit Skills
        B -->|1. Crawler Perms & APIs| C[offsite-discoverability]
        B -->|2. JSON-LD & Chunkability| D[semantic-readiness]
        B -->|3. Wiki & Entity Conflicts| E[offsite-corroboration]
        B -->|4. Share-of-Voice & Sentiment| F[engagement-audit]
    end
    
    C -->|Discoverability Report| B
    D -->|Semantic Quality Metrics| B
    E -->|Fact Consistency Audits| B
    F -->|Citation & Mentions Analytics| B
    
    B --> G[Unified AI Readiness Score & Roadmap]
```

### 1. Audit Orchestrator (`audit-orchestrator`) — **Entrypoint**
*   **Role**: Central coordination and synthesis engine.
*   **Mechanism**: Consumes the primary configuration, dynamically activates the domain-specific skills in sequence, manages intermediate JSON outputs, aggregates scores, and compiles the final executive report.

### 2. Offsite Discoverability (`offsite-discoverability`)
*   **Role**: Technical crawler check.
*   **Mechanism**: Verifies page indexability and access rules in `robots.txt` for AI spiders (e.g., `GPTBot`, `ClaudeBot`, `PerplexityBot`), sitemap structural validity, and parses API exposure levels.

### 3. Semantic Readiness (`semantic-readiness`)
*   **Role**: On-page metadata and structure evaluation.
*   **Mechanism**: Evaluates RDFa, Microdata, and JSON-LD markup against Schema.org definitions. Measures header hierarchies (`H1`-`H3`) and structural chunkability to ensure content matches LLM RAG pipelines.

### 4. Offsite Corroboration (`offsite-corroboration`)
*   **Role**: Fact checking and trust triangulation.
*   **Mechanism**: Scans authoritative registries (Wikipedia, Wikidata, Crunchbase) to verify that brand-level facts (e.g., founders, locations, key products) align, reducing the likelihood of LLM hallucinations.

### 5. Engagement Audit (`engagement-audit`)
*   **Role**: Generative Share-of-Voice (SoV) and citation auditing.
*   **Mechanism**: Runs mock inquiries through LLM endpoints to compute how often the brand is mentioned in unbranded queries, its average citation rank, and the semantic sentiment of the generated outputs.

---

## 📂 Repository Directory Structure

```text
.
├── marketplace.json                # Root marketplace manifest (catalog)
├── README.md                       # Architecture & execution guide
└── skills/                         # Folder containing agentskills.io skills
    ├── audit-orchestrator/
    │   └── SKILL.md                # Orchestration logic & workflow
    ├── offsite-discoverability/
    │   └── SKILL.md                # AI Crawler permissions checking
    ├── semantic-readiness/
    │   └── SKILL.md                # Schema & structure analysis
    ├── offsite-corroboration/
    │   └── SKILL.md                # Fact corroboration across external sites
    └── engagement-audit/
        └── SKILL.md                # LLM testing & share-of-voice checks
```

---

## ⚙️ How to Execute the Audit

Because this repository strictly follows the `agentskills.io` standard, compatible AI coding agents and CLI systems (such as Claude Code, Cursor, or Gemini CLI) can parse and run these skills automatically.

### Step 1: Install the Skill Marketplace
Add this repository to your agent's local or team marketplace:
```bash
/plugin install brand-ai-readiness-audit
```
*Or, manually configure the repository URL in your agent's config or global settings.*

### Step 2: Triggering the Audit via Agent CLI
To trigger the complete audit, run a prompt targeting the `audit-orchestrator` entrypoint:

```bash
run audit-orchestrator --domain "example.com" --brand "Example Corp" --keyProducts '["CRM Software", "Customer Service Portal"]'
```

Alternatively, you can interact with the agent in plain English:
> *"Run a complete Brand AI Readiness Audit on example.com (Example Corp). Evaluate discoverability, semantic schemas, Wiki corroboration, and test their current SoV on generative engines."*

### Step 3: View the Outputs
Once executed, the orchestrator compiles data from all modules and outputs a unified markdown report:
1.  **Readiness Scorecard**: A score from 0 to 100 indicating performance.
2.  **Module Breakdowns**: Specific lists of errors and warnings discovered (e.g., missing Schema properties, blocked AI crawlers).
3.  **Remediation Checklist**: A prioritised checklist showing exact file locations, code snippets, or configuration edits required to optimize the brand for Generative AI.
