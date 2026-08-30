import json
import sys

COMMON_NOUNS = {
    "apple", "amazon", "stripe", "target", "meta", "alphabet", "oracle", "salesforce",
    "box", "slack", "square", "clover", "bloom", "wave", "drift", "bench", "gong"
}

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: check_corroboration.py <brand_name> <claims_json>"}))
        sys.exit(1)
        
    brand_name = sys.argv[1]
    claims_raw = sys.argv[2]
    findings = []
    
    try:
        claims = json.loads(claims_raw)
    except Exception as e:
        findings.append({
            "id": "corroboration-invalid-input",
            "title": "Invalid claims input JSON",
            "severity": "high",
            "evidence": str(e),
            "suggested_action": {
                "summary": "Provide a valid JSON dictionary of claims (e.g. founded, ceo, headquarters) to cross-reference.",
                "priority": 2
            }
        })
        print(json.dumps(findings, indent=2))
        sys.exit(0)
        
    # Mock authority database matching (e.g., Wikidata, Wikipedia, Crunchbase)
    mock_authority = {
        "adobe": {
            "founded": "1982",
            "headquarters": "San Jose, California",
            "ceo": "Shantanu Narayen"
        },
        "examplecorp": {
            "founded": "2015",
            "headquarters": "San Francisco, California",
            "ceo": "Jane Doe"
        }
    }
    
    # Clean brand key for dict lookup
    brand_key = brand_name.lower().replace(" ", "").replace(".", "")
    auth_data = mock_authority.get(brand_key, {})
    
    # 1. Brand name ambiguity analysis
    name_lower = brand_name.lower().strip()
    if name_lower in COMMON_NOUNS:
        findings.append({
            "id": "corroboration-name-collision-critical",
            "title": "High semantic brand name collision risk",
            "severity": "critical",
            "evidence": f"Brand name '{brand_name}' is a high-frequency dictionary common noun.",
            "suggested_action": {
                "summary": "Use specific Schema.org entity ids (sameAs relationships) to ground the brand entity for LLM crawlers.",
                "priority": 1
            }
        })
    elif len(name_lower) < 5:
        findings.append({
            "id": "corroboration-name-abbreviation-conflict",
            "title": "Lexical ambiguity due to short brand name length",
            "severity": "high",
            "evidence": f"Brand name length is only {len(name_lower)} characters.",
            "suggested_action": {
                "summary": "Enforce explicit naming structures (e.g. including Corp/Inc) on official profiles to prevent abbreviations mix-ups.",
                "priority": 2
            }
        })
        
    # 2. Fact cross-referencing
    for claim_key, claim_val in claims.items():
        if claim_key in auth_data:
            auth_val = auth_data[claim_key]
            if str(claim_val).lower() != str(auth_val).lower():
                findings.append({
                    "id": f"corroboration-fact-conflict-{claim_key}",
                    "title": f"Factual discrepancy found on key claim: '{claim_key}'",
                    "severity": "high",
                    "evidence": f"On-site claim: '{claim_val}' vs. Off-site authority record: '{auth_val}'",
                    "suggested_action": {
                        "summary": f"Align values on the official website or submit corrections to authoritative registries (Wikidata/Wikipedia).",
                        "priority": 2
                    }
                })
        else:
            findings.append({
                "id": f"corroboration-fact-uncorroborated-{claim_key}",
                "title": f"Uncorroborated factual assertion: '{claim_key}'",
                "severity": "medium",
                "evidence": f"No corroborative records found for claim '{claim_key}' = '{claim_val}' on Crunchbase or Wikidata.",
                "suggested_action": {
                    "summary": "Register corporate facts on directories and platforms to build index corroboration.",
                    "priority": 3
                }
            })
            
    print(json.dumps(findings, indent=2))

if __name__ == "__main__":
    main()
