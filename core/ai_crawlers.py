import urllib.robotparser
import urllib.parse
from typing import Dict, List, Any, Optional

AI_CRAWLER_MATRIX = [
    {
        "name": "GPTBot",
        "owner": "OpenAI",
        "category": "training",
        "criticality": "high",
        "description": "OpenAI foundational model pre-training scraper."
    },
    {
        "name": "ChatGPT-User",
        "owner": "OpenAI",
        "category": "user_browsing",
        "criticality": "high",
        "description": "Real-time user-driven browsing in ChatGPT."
    },
    {
        "name": "OAI-SearchBot",
        "owner": "OpenAI",
        "category": "search_retrieval",
        "criticality": "critical",
        "description": "OpenAI real-time search and RAG retrieval indexer."
    },
    {
        "name": "ClaudeBot",
        "owner": "Anthropic",
        "category": "search_retrieval",
        "criticality": "high",
        "description": "Anthropic AI assistant search and retrieval crawler."
    },
    {
        "name": "Claude-Web",
        "owner": "Anthropic",
        "category": "user_browsing",
        "criticality": "high",
        "description": "Real-time user fetcher in Claude web interface."
    },
    {
        "name": "PerplexityBot",
        "owner": "Perplexity AI",
        "category": "search_retrieval",
        "criticality": "critical",
        "description": "Perplexity Generative Search Engine crawler."
    },
    {
        "name": "Google-Extended",
        "owner": "Google",
        "category": "training",
        "criticality": "low",
        "description": "Controls Google Gemini/PaLM model training opt-out (does not affect Google Search indexation)."
    },
    {
        "name": "Applebot-Extended",
        "owner": "Apple",
        "category": "training",
        "criticality": "low",
        "description": "Controls Apple Intelligence foundational model training opt-out."
    },
    {
        "name": "Bytespider",
        "owner": "ByteDance",
        "category": "training",
        "criticality": "medium",
        "description": "ByteDance AI model training crawler."
    },
    {
        "name": "cohere-ai",
        "owner": "Cohere",
        "category": "training",
        "criticality": "medium",
        "description": "Cohere enterprise LLM pre-training scraper."
    }
]

def parse_ai_robots_rules(robots_txt_content: str, url: str) -> Dict[str, Any]:
    """
    Parses robots.txt content against the matrix of modern AI user-agents per RFC 9309 rules.
    Returns per-bot accessibility status, crawl-delay directives, and declared sitemap URLs.
    """
    parsed_sitemaps = []
    crawl_delays = {}
    
    if robots_txt_content:
        for line in robots_txt_content.splitlines():
            line_clean = line.split('#', 1)[0].strip()
            if not line_clean or ":" not in line_clean:
                continue
            k, v = line_clean.split(":", 1)
            k_clean = k.strip().lower()
            v_clean = v.strip()
            if k_clean == "sitemap":
                if v_clean and v_clean not in parsed_sitemaps:
                    parsed_sitemaps.append(v_clean)
            elif k_clean in ["crawl-delay", "request-rate"]:
                try:
                    crawl_delays["default"] = float(v_clean)
                except ValueError:
                    pass

    # Extract target path
    parsed_url = urllib.parse.urlparse(url if url.startswith("http") else f"https://{url}")
    target_path = parsed_url.path or "/"

    # Prepare urllib robotparser lines
    clean_lines = []
    if robots_txt_content:
        for line in robots_txt_content.splitlines():
            line_clean = line.split('#', 1)[0].strip()
            if line_clean:
                clean_lines.append(line_clean)

    parser = urllib.robotparser.RobotFileParser()
    parser.parse(clean_lines)

    bot_access = {}
    blocked_count = 0
    allowed_count = 0

    for bot in AI_CRAWLER_MATRIX:
        bot_name = bot["name"]
        can_fetch = parser.can_fetch(bot_name, target_path)
        
        if can_fetch:
            allowed_count += 1
            status_str = "ALLOWED"
        else:
            blocked_count += 1
            status_str = "DISALLOWED"

        bot_access[bot_name] = {
            "name": bot_name,
            "owner": bot["owner"],
            "category": bot["category"],
            "criticality": bot["criticality"],
            "status": status_str,
            "can_fetch": can_fetch,
            "description": bot["description"]
        }

    return {
        "target_path": target_path,
        "sitemaps": parsed_sitemaps,
        "crawl_delays": crawl_delays,
        "bot_access": bot_access,
        "summary": {
            "total_ai_bots_checked": len(AI_CRAWLER_MATRIX),
            "allowed_count": allowed_count,
            "blocked_count": blocked_count
        }
    }
