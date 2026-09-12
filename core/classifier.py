import re
from html.parser import HTMLParser
from typing import Dict, Any, List, Optional


class ClassificationDOMParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tag_count = 0
        self.code_block_count = 0
        self.input_tags = []
        self.form_actions = []
        self.has_product_schema = False
        self.has_price_symbols = False
        self.has_add_to_cart = False
        self.text_tokens = []
        self.classes_and_ids = []
        self.in_script_or_style = False

    def handle_starttag(self, tag, attrs):
        self.tag_count += 1
        attrs_dict = dict(attrs)
        
        if tag in ["script", "style"]:
            self.in_script_or_style = True
            
        if tag in ["code", "pre"]:
            self.code_block_count += 1
            
        class_val = attrs_dict.get("class", "")
        id_val = attrs_dict.get("id", "")
        if class_val:
            self.classes_and_ids.append(class_val.lower())
        if id_val:
            self.classes_and_ids.append(id_val.lower())
            
        if tag == "input":
            itype = attrs_dict.get("type", "text").lower()
            iname = attrs_dict.get("name", "").lower()
            self.input_tags.append({"type": itype, "name": iname})
            
        if tag == "form":
            action = attrs_dict.get("action", "").lower()
            if action:
                self.form_actions.append(action)
                
        # E-commerce check
        combined_class_id = f"{class_val} {id_val}".lower()
        if any(k in combined_class_id for k in ["add-to-cart", "addtocart", "buy-now", "shopping-cart", "checkout"]):
            self.has_add_to_cart = True

    def handle_endtag(self, tag):
        if tag in ["script", "style"]:
            self.in_script_or_style = False

    def handle_data(self, data):
        if self.in_script_or_style:
            return
        cleaned = data.strip()
        if cleaned:
            self.text_tokens.extend(cleaned.split())
            if any(symbol in data for symbol in ["$", "€", "£", "¥"]):
                self.has_price_symbols = True

def classify_page(html: str, url: str, headers: Optional[Dict[str, str]] = None) -> str:
    """
    Classifies a webpage into an architectural archetype using fast, deterministic heuristics.
    Archetypes: UTILITY_PORTAL, DOCUMENTATION, ECOMMERCE, SAAS_MARKETING, GENERAL_CONTENT
    """
    url_lower = (url or "").lower()
    html_lower = (html or "").lower()
    
    # Fast path URL heuristics
    url_path = url_lower.replace("https://", "").replace("http://", "").split("/", 1)[-1] if "/" in url_lower else ""
    
    # 1. DOCUMENTATION detection via URL & markup
    if any(kw in url_lower for kw in ["/docs", "/doc/", "/api", "/reference", "/guide", "/manual", "readthedocs.io", "github.io"]):
        return "DOCUMENTATION"
        
    parser = ClassificationDOMParser()
    try:
        parser.feed(html[:150000])  # Sample first 150KB for speed
    except Exception:
        pass

    word_count = len(parser.text_tokens)
    text_sample = " ".join(parser.text_tokens[:300]).lower()
    
    # 2. UTILITY_PORTAL detection
    # Search engine (e.g. google.com), login/auth page, minimal app dashboard
    has_search_input = any(inp["type"] in ["search"] or inp["name"] in ["q", "query", "search", "s"] for inp in parser.input_tags)
    has_search_action = any("search" in act for act in parser.form_actions)
    has_auth_input = any(inp["type"] == "password" or inp["name"] in ["password", "pass", "pwd", "login"] for inp in parser.input_tags)
    is_root_search_engine = "google." in url_lower or "bing.com" in url_lower or "duckduckgo.com" in url_lower
    
    if is_root_search_engine or (has_search_input and (word_count < 150 or parser.tag_count < 100)) or (has_auth_input and word_count < 200 and parser.tag_count < 120):
        return "UTILITY_PORTAL"
        
    if any(kw in url_lower for kw in ["/login", "/signin", "/auth", "/app/"]):
        if word_count < 250:
            return "UTILITY_PORTAL"

    # 3. DOCUMENTATION detection via DOM
    if parser.code_block_count >= 3 or any("sidebar" in cid or "doc-content" in cid for cid in parser.classes_and_ids):
        if any(kw in text_sample for kw in ["documentation", "api reference", "getting started", "code example", "installation"]):
            return "DOCUMENTATION"

    # 4. ECOMMERCE detection
    has_product_schema = "schema.org/product" in html_lower or '"@type":"product"' in html_lower or '"@type": "product"' in html_lower
    has_cart_text = any(kw in text_sample for kw in ["add to cart", "buy now", "shopping cart", "in stock", "free shipping"])
    if has_product_schema or parser.has_add_to_cart or (has_cart_text and parser.has_price_symbols):
        return "ECOMMERCE"

    # 5. SAAS_MARKETING detection
    has_marketing_keywords = any(kw in text_sample for kw in ["get started", "free trial", "request demo", "pricing", "sign up", "features", "platform"])
    has_hero_or_cta = any("hero" in cid or "cta" in cid or "pricing" in cid for cid in parser.classes_and_ids)
    if has_marketing_keywords or has_hero_or_cta:
        return "SAAS_MARKETING"

    return "GENERAL_CONTENT"
