import sys
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Tuple
from html.parser import HTMLParser

# Check optional Playwright runtime availability
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

@dataclass
class RenderingResult:
    attempted: bool = False
    successful: bool = False
    final_url: str = ""
    status_code: int = 0
    rendered_html: str = ""
    page_title: str = ""
    visible_text: str = ""
    h1_headers: List[str] = field(default_factory=list)
    headings_count: int = 0
    links: List[str] = field(default_factory=list)
    scripts_count: int = 0
    console_error_count: int = 0
    load_time_ms: float = 0.0
    error: Optional[str] = None
    browser_available: bool = PLAYWRIGHT_AVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Omit full HTML text from default summary dictionary to keep state bounded
        d["rendered_html_bytes"] = len(self.rendered_html)
        d.pop("rendered_html", None)
        return d

def evaluate_rendering_decision(raw_html: str, extracted_content: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any], float]:
    """
    Deterministic decision engine evaluating whether headless browser rendering is warranted.
    """
    if not raw_html:
        return False, "Raw HTML empty", {}, 0.0

    raw_text = " ".join(extracted_content.get("raw_text_segments", [])).strip()
    raw_text_len = len(raw_text)
    total_html_len = len(raw_html)
    text_to_code = raw_text_len / total_html_len if total_html_len > 0 else 0.0

    js_framework_signatures = extracted_content.get("js_framework_signatures", [])
    has_spa_container = bool(re.search(r'<(div|main|section)[^>]*id=["\'](__next|root|app)["\'][^>]*>\s*</\1>', raw_html, re.I))
    has_h1 = len(extracted_content.get("h1_headers", [])) > 0 or bool(re.search(r'<h1[^>]*>', raw_html, re.I))

    signals = {
        "raw_text_length": raw_text_len,
        "text_to_code_ratio": round(text_to_code, 4),
        "has_spa_container": has_spa_container,
        "js_framework_signatures_count": len(js_framework_signatures),
        "has_h1": has_h1
    }

    # High Priority Trigger 1: Empty SPA root container or extremely low raw text (<300 chars) with JS signatures
    if (has_spa_container or js_framework_signatures) and raw_text_len < 300:
        return True, "SPA root container detected with minimal raw HTML text", signals, 0.95

    # High Priority Trigger 2: Low text-to-code ratio (< 0.05) with framework signatures
    if text_to_code < 0.05 and js_framework_signatures:
        return True, "Low text-to-code ratio with client-side framework signatures", signals, 0.90

    # Medium Priority Trigger 3: Missing H1 and sparse content (<400 chars)
    if not has_h1 and raw_text_len < 400:
        return True, "Missing H1 header and sparse raw text content", signals, 0.75

    return False, "Raw HTML content density sufficient; browser rendering not required", signals, 0.10

def render_page(url: str, timeout_ms: int = 8000) -> RenderingResult:
    """
    Executes headless Playwright browser rendering on-demand.
    Returns RenderingResult with browser_available=False if Playwright package is absent.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return RenderingResult(
            attempted=False,
            successful=False,
            browser_available=False,
            error="Playwright library unavailable in Python runtime environment"
        )

    if not url.startswith(("http://", "https://")):
        target_url = f"https://{url}"
    else:
        target_url = url

    start_time = time.time()
    console_errors = 0

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
            page = context.new_page()

            def handle_console(msg):
                nonlocal console_errors
                if msg.type in ["error", "warning"]:
                    console_errors += 1

            page.on("console", handle_console)

            # Bounded hybrid hydration: Step 1 domcontentloaded (max 10,000ms)
            nav_timeout = min(timeout_ms, 10000)
            response = page.goto(target_url, wait_until="domcontentloaded", timeout=nav_timeout)
            
            # Step 2: Bounded await for SPA root selector or networkidle (max 2,000ms)
            try:
                page.wait_for_selector("#root, #app, main, article", timeout=2000)
            except Exception:
                try:
                    page.wait_for_load_state("networkidle", timeout=2000)
                except Exception:
                    pass

            status_code = response.status if response else 200
            final_url = page.url

            rendered_html = page.content()
            page_title = page.title()
            visible_text = page.inner_text("body") if page.query_selector("body") else ""

            # Extract rendered H1 headers
            h1_elements = page.query_selector_all("h1")
            h1_headers = [h.inner_text().strip() for h in h1_elements if h.inner_text().strip()]

            # Extract headings & links counts
            all_headings = page.query_selector_all("h1, h2, h3, h4, h5, h6")
            all_links = page.query_selector_all("a[href]")
            link_hrefs = [l.get_attribute("href") for l in all_links if l.get_attribute("href")]

            scripts = page.query_selector_all("script")

            load_time_ms = round((time.time() - start_time) * 1000, 2)
            browser.close()

            return RenderingResult(
                attempted=True,
                successful=True,
                final_url=final_url,
                status_code=status_code,
                rendered_html=rendered_html,
                page_title=page_title,
                visible_text=visible_text,
                h1_headers=h1_headers,
                headings_count=len(all_headings),
                links=link_hrefs,
                scripts_count=len(scripts),
                console_error_count=console_errors,
                load_time_ms=load_time_ms,
                error=None,
                browser_available=True
            )

    except Exception as err:
        load_time_ms = round((time.time() - start_time) * 1000, 2)
        return RenderingResult(
            attempted=True,
            successful=False,
            final_url=target_url,
            load_time_ms=load_time_ms,
            error=str(err),
            browser_available=True
        )

def compare_raw_vs_rendered(raw_html: str, raw_extracted: Dict[str, Any], rendered: RenderingResult) -> Dict[str, Any]:
    """
    Computes structural and text content differences between raw HTML and post-JS rendered representation.
    """
    if not rendered.successful:
        return {"comparison_executed": False}

    raw_text = " ".join(raw_extracted.get("raw_text_segments", [])).strip()
    raw_text_len = len(raw_text)
    rendered_text_len = len(rendered.visible_text)

    text_diff_pct = ((rendered_text_len - raw_text_len) / raw_text_len * 100) if raw_text_len > 0 else 100.0

    raw_h1_count = len(raw_extracted.get("h1_headers", []))
    rendered_h1_count = len(rendered.h1_headers)

    raw_links = set(re.findall(r'href=["\']([^"\']+)["\']', raw_html, re.I))
    rendered_links = set(rendered.links)
    new_links_discovered = list(rendered_links - raw_links)

    title_changed = False
    raw_title = raw_extracted.get("title", "").strip()
    if raw_title and rendered.page_title and raw_title.lower() != rendered.page_title.lower():
        title_changed = True

    return {
        "comparison_executed": True,
        "raw_text_length": raw_text_len,
        "rendered_text_length": rendered_text_len,
        "text_increase_percentage": round(text_diff_pct, 2),
        "meaningful_content_revealed": text_diff_pct > 35.0,
        "raw_h1_count": raw_h1_count,
        "rendered_h1_count": rendered_h1_count,
        "h1_revealed_via_js": raw_h1_count == 0 and rendered_h1_count > 0,
        "new_links_count": len(new_links_discovered),
        "new_links_sample": new_links_discovered[:10],
        "title_changed": title_changed,
        "raw_title": raw_title,
        "rendered_title": rendered.page_title
    }
