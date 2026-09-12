#!/usr/bin/env python3
"""
Brand AI Readiness Audit - Unified Entrypoint
Usage:
  python audit.py https://google.com
  python audit.py https://stripe.com --brand Stripe --no-llm
"""

import sys
import os
import argparse
import json
import importlib.util

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.abspath(__file__))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

# Dynamically load run_audit from skills/audit-orchestrator/scripts/run_audit.py
orchestrator_path = os.path.join(workspace_root, "skills", "audit-orchestrator", "scripts", "run_audit.py")
spec = importlib.util.spec_from_file_location("run_audit", orchestrator_path)
run_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_audit)

execute_audit_pipeline = run_audit.execute_audit_pipeline

def render_markdown_summary(report_dict: dict) -> str:
    lines = []
    lines.append(f"# Brand AI Readiness Audit Report: {report_dict.get('brand')} ({report_dict.get('site')})")
    lines.append(f"**Audited At**: {report_dict.get('audited_at')} | **Audit Confidence**: {report_dict.get('audit_confidence')}%")
    lines.append(f"**Overall Readiness Score**: **{report_dict.get('readiness_score')}/100**")
    lines.append("")
    
    scores = report_dict.get("scores", {})
    lines.append("## Dimension Scores")
    lines.append(f"- **AI Discoverability Score**: {scores.get('ai_discoverability')}/100 (Weight: 60%)")
    lines.append(f"- **On-Site Engagement Score**: {scores.get('onsite_engagement')}/100 (Weight: 30%)")
    lines.append(f"- **Technical Health Score**: {scores.get('technical_health')}/100 (Weight: 10%)")
    lines.append("")
    
    lines.append(f"## Executive Summary")
    lines.append(f"> {report_dict.get('executive_summary')}")
    lines.append("")
    
    col = report_dict.get("collection", {})
    if col.get("archetype"):
        lines.append(f"**Site Archetype**: `{col.get('archetype')}`")
        lines.append("")

    lines.append("## Prioritized Findings Summary")
    summary = report_dict.get("summary", {})
    lines.append(f"- **Total Findings**: {summary.get('total_findings')}")
    lines.append(f"- **Critical**: {summary.get('critical')} | **High**: {summary.get('high')} | **Medium**: {summary.get('medium')} | **Low**: {summary.get('low')}")
    lines.append("")

    blockers = report_dict.get("top_blockers", [])
    if blockers:
        lines.append("## Top Priority Action Items")
        for idx, b in enumerate(blockers, 1):
            action = b.get("suggested_action", {})
            how = action.get("how") or action.get("summary") or ""
            lines.append(f"{idx}. **[{b.get('severity').upper()}] {b.get('title')}**")
            lines.append(f"   - **Issue**: {b.get('issue')}")
            lines.append(f"   - **Remediation**: {how}")
            lines.append("")
            
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Brand AI Readiness Audit Engine")
    parser.add_argument("target_url", nargs="?", help="Target URL or domain to audit (e.g., https://google.com)")
    parser.add_argument("--url", help="Target URL or domain to audit")
    parser.add_argument("--brand", help="Brand name (optional, inferred if not provided)")
    parser.add_argument("--claims", help="JSON string of corporate claims to corroborate (optional)")
    parser.add_argument("--no-llm", action="store_true", help="Disable Gemini LLM reasoning (deterministic pass)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON only")
    args = parser.parse_args()

    url = args.target_url or args.url
    if not url:
        print("Error: Target URL or domain is required.", file=sys.stderr)
        print("Usage: python audit.py https://google.com", file=sys.stderr)
        sys.exit(1)

    claims_dict = {}
    if args.claims:
        try:
            claims_dict = json.loads(args.claims)
        except Exception:
            claims_dict = {}

    enable_llm = not args.no_llm
    report = execute_audit_pipeline(url, args.brand, claims_dict, enable_llm=enable_llm)
    report_dict = report.to_dict()

    if args.json:
        print(json.dumps(report_dict, indent=2))
    else:
        print(render_markdown_summary(report_dict))
        print("\n--- Raw JSON Payload ---")
        print(json.dumps(report_dict, indent=2))

if __name__ == "__main__":
    main()
