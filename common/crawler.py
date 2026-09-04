import sys
import os
import re
import gzip
import zlib
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple, Set

# Attempt importing Playwright dynamically
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

REALISTIC_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
AI_USER_AGENTS = ["GPTBot", "ClaudeBot", "PerplexityBot", "CCBot", "Google-Extended", "Bytespider"]

HIGH_VALUE_KEYWORDS = [
    "about", "company", "product", "products", "service", "services", 
    "pricing", "doc", "docs", "documentation", "blog", "faq", "support", 
    "contact", "terms", "privacy"
]

class EnhancedCrawler:
    """
    Production-Grade Web Crawler & Site Discovery Engine.
    Handles raw HTTP transport, headless Playwright DOM hydration,
    robots.txt directives, and sitemap index traversal.
    """

    @staticmethod
    def is_playwright_ready() -> bool:
        return PLAYWRIGHT_AVAILABLE

    @staticmethod
    def fetch_url_with_redirects(url: str, timeout: float = 6.0) -> Dict[str, Any]:
        target = url if url.startswith(('http://', 'https://')) else f"https://{url}"
        
        headers = {
            "User-Agent": REALISTIC_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        redirect_chain = [target]
        final_url = target

        class RedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                redirect_chain.append(newurl)
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        opener = urllib.request.build_opener(RedirectHandler)
        req = urllib.request.Request(target, headers=headers, method="GET")

        try:
            with opener.open(req, timeout=timeout) as resp:
                final_url = resp.geturl()
                if final_url not in redirect_chain:
                    redirect_chain.append(final_url)
                
                content_bytes = resp.read()
                encoding = resp.info().get('Content-Encoding', '').lower()

                if encoding == 'gzip':
                    try:
                        content_bytes = gzip.decompress(content_bytes)
                    except Exception:
                        pass
                elif encoding == 'deflate':
                    try:
                        content_bytes = zlib.decompress(content_bytes)
                    except Exception:
                        pass

                html_text = content_bytes.decode('utf-8', errors='replace')
                return {
                    "success": True,
                    "status": resp.status,
                    "initial_url": target,
                    "final_url": final_url,
                    "redirect_chain": redirect_chain,
                    "redirect_count": len(redirect_chain) - 1,
                    "content": html_text,
                    "headers": dict(resp.headers)
                }

        except urllib.error.HTTPError as e:
            return {
                "success": False,
                "status": e.code,
                "initial_url": target,
                "final_url": e.url if hasattr(e, 'url') else target,
                "redirect_chain": redirect_chain,
                "redirect_count": max(0, len(redirect_chain) - 1),
                "content": "",
                "error": str(e)
            }
        except Exception as ex:
            return {
                "success": False,
                "status": 0,
                "initial_url": target,
                "final_url": target,
                "redirect_chain": redirect_chain,
                "redirect_count": 0,
                "content": "",
                "error": str(ex)
            }

    @staticmethod
    def render_with_playwright(url: str, timeout_ms: int = 15000) -> Dict[str, Any]:
        """
        Executes a real headless Chromium instance to capture the fully-hydrated DOM
        and verify client-side vs server-side rendering disparities.
        Uses bounded hybrid hydration:
        1. Navigate with wait_until='domcontentloaded' (timeout max 10,000ms).
        2. Await root app selectors or networkidle with a 2,000ms ceiling.
        3. Enforce a hard 15,000ms total timeout.
        Operations remain strictly read-only (no click, fill, or mutations).
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "success": False,
                "error": "Playwright module not installed in Python environment",
                "html": "",
                "title": "",
                "rendered_text_len": 0
            }

        target = url if url.startswith(('http://', 'https://')) else f"https://{url}"
        total_timeout = min(timeout_ms, 15000)
        nav_timeout = min(total_timeout, 10000)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=REALISTIC_USER_AGENT)
                page = context.new_page()
                
                # Bounded hybrid hydration: Step 1 domcontentloaded
                page.goto(target, timeout=nav_timeout, wait_until="domcontentloaded")
                
                # Step 2: Bounded await for SPA root selector or networkidle (max 2,000ms)
                try:
                    page.wait_for_selector("#root, #app, main, article", timeout=2000)
                except Exception:
                    try:
                        page.wait_for_load_state("networkidle", timeout=2000)
                    except Exception:
                        pass

                rendered_html = page.content()
                page_title = page.title()
                rendered_text = page.inner_text("body") if page.query_selector("body") else ""
                browser.close()

                return {
                    "success": True,
                    "html": rendered_html,
                    "title": page_title,
                    "rendered_text_len": len(rendered_text.strip()),
                    "error": None
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "html": "",
                "title": "",
                "rendered_text_len": 0
            }

    @staticmethod
    def parse_robots_txt(robots_content: str) -> Dict[str, Any]:
        sitemaps = []
        disallowed_bots = []
        allowed_bots = []

        if not robots_content:
            return {"sitemaps": [], "disallowed_bots": [], "allowed_bots": []}

        clean_lines = []
        for line in robots_content.splitlines():
            # Strip inline comments
            line_no_comment = line.split('#', 1)[0].strip()
            if line_no_comment:
                clean_lines.append(line_no_comment)
                if ":" in line_no_comment:
                    k, v = line_no_comment.split(":", 1)
                    if k.strip().lower() == "sitemap":
                        sm_val = v.strip()
                        if sm_val and sm_val not in sitemaps:
                            sitemaps.append(sm_val)

        import urllib.robotparser
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(clean_lines)

        for bot in AI_USER_AGENTS:
            # can_fetch evaluates exact bot agent matching with wildcard fallback according to RFC 9309
            if not parser.can_fetch(bot, "/"):
                if bot not in disallowed_bots:
                    disallowed_bots.append(bot)
            else:
                if bot not in allowed_bots:
                    allowed_bots.append(bot)

        return {
            "sitemaps": sitemaps,
            "disallowed_bots": disallowed_bots,
            "allowed_bots": allowed_bots
        }

    @classmethod
    def discover_sitemaps(cls, domain: str, robots_sitemaps: List[str]) -> List[str]:
        candidates = list(robots_sitemaps)
        clean_domain = domain.replace("https://", "").replace("http://", "").strip("/")

        default_paths = [
            f"https://{clean_domain}/sitemap.xml",
            f"https://{clean_domain}/sitemap_index.xml"
        ]

        for p in default_paths:
            if p not in candidates:
                candidates.append(p)

        discovered = []
        for s_url in candidates:
            res = cls.fetch_url_with_redirects(s_url, timeout=4.0)
            if res["success"] and ("xml" in res.get("headers", {}).get("Content-Type", "").lower() or res["content"].strip().startswith("<?xml")):
                discovered.append(s_url)
                try:
                    root = ET.fromstring(res["content"])
                    for loc in root.findall(".//{*}loc"):
                        if loc.text and "sitemap" in loc.text and loc.text not in discovered:
                            discovered.append(loc.text.strip())
                except Exception:
                    pass

        return discovered

    @classmethod
    def sample_high_value_pages(cls, homepage_html: str, domain: str, max_samples: int = 10) -> List[str]:
        clean_domain = domain.replace("https://", "").replace("http://", "").strip("/")
        base_origin = f"https://{clean_domain}"

        found_links: Set[str] = set()
        if homepage_html:
            hrefs = re.findall(r'href=["\']([^"\']+)["\']', homepage_html, flags=re.IGNORECASE)
            for href in hrefs:
                if href.startswith('#') or href.startswith('javascript:'):
                    continue
                full_url = urllib.parse.urljoin(base_origin, href)
                parsed = urllib.parse.urlparse(full_url)
                if parsed.netloc and clean_domain in parsed.netloc:
                    path = parsed.path.lower()
                    if any(kw in path for kw in HIGH_VALUE_KEYWORDS):
                        found_links.add(full_url.split('#')[0].split('?')[0])

        sampled = list(found_links)[:max_samples]
        if not sampled:
            sampled = [base_origin]
        return sampled