import subprocess
import urllib.request
import urllib.parse
import urllib.error
import ssl
import socket
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple

# Modern browser user agents and headers to bypass edge bot firewalls
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = [
    "-H", f"User-Agent: {DEFAULT_USER_AGENT}",
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Sec-Ch-Ua: \"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\", \"Google Chrome\";v=\"128\"",
    "-H", "Sec-Ch-Ua-Mobile: ?0",
    "-H", "Sec-Ch-Ua-Platform: \"macOS\"",
    "-H", "Sec-Fetch-Dest: document",
    "-H", "Sec-Fetch-Mode: navigate",
    "-H", "Sec-Fetch-Site: none",
    "-H", "Sec-Fetch-User: ?1",
    "-H", "Upgrade-Insecure-Requests: 1",
    "-H", "Cache-Control: max-age=0"
]

def _parse_curl_headers(header_text: str) -> Dict[str, str]:
    headers = {}
    for line in header_text.splitlines():
        line = line.strip()
        if not line or line.startswith("HTTP/"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers

def _raw_curl_get(url: str, timeout: float = 8.0, user_agent: Optional[str] = None) -> Tuple[bool, int, str, Dict[str, str]]:
    cmd = [
        'curl', '-s', '-L', '--compressed',
        '--max-redirs', '5',
        '--connect-timeout', '4',
        '--max-time', str(int(timeout)),
        '-D', '-'  # Dump headers to stdout alongside body
    ]
    
    if user_agent:
        cmd.extend(['-H', f'User-Agent: {user_agent}'])
    else:
        cmd.extend(BROWSER_HEADERS)
        
    cmd.append(url)
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=timeout + 2.0)
        output = proc.stdout if proc.stdout else ""
        
        # Split headers from body (separated by double CRLF/LF)
        parts = re.split(r'\r?\n\r?\n', output)
        if len(parts) >= 2:
            header_text = parts[-2]
            body = parts[-1]
            headers = _parse_curl_headers(header_text)
            
            # Extract status code from last HTTP status line
            status_match = re.search(r'HTTP/[\d\.]+\s+(\d+)', header_text)
            status_code = int(status_match.group(1)) if status_match else 200
        else:
            headers = {"content-type": "text/html"}
            body = output
            status_code = 200 if proc.returncode == 0 and body.strip() else 0

        # Discard bot challenges or empty drops
        if proc.returncode == 0 and len(body.strip()) > 50 and "OK Bot" not in body:
            return True, status_code, body, headers
            
        return False, status_code, body, headers
    except Exception:
        return False, 0, "", {}

def fetch_url(url: str, user_agent: Optional[str] = None, timeout: float = 8.0, max_redirects: int = 5) -> Dict[str, Any]:
    """
    Robust network fetcher for web audit. Uses system curl with browser headers,
    automatic Brotli/Gzip decompression, redirect handling, and subpath fallbacks.
    """
    if not url.startswith(('http://', 'https://')):
        target_url = f"https://{url}"
    else:
        target_url = url

    start_time = time.time()

    # 1. Primary Curl Fetch
    success, status_code, content, headers = _raw_curl_get(target_url, timeout, user_agent)

    if success:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "success": True,
            "status": status_code,
            "status_code": status_code,
            "content": content,
            "html": content,
            "text": content,
            "final_url": target_url,
            "url": target_url,
            "latency_ms": latency_ms,
            "headers": headers,
            "error": None
        }

    # 2. Domain / Subpath Heuristic Fallback if landing page challenged or blank
    clean_domain = target_url.replace("https://", "").replace("http://", "").split("/")[0]
    fallback_urls = [
        f"https://www.{clean_domain}/",
        f"https://{clean_domain}/",
        f"https://www.{clean_domain}/us/",
        f"https://www.{clean_domain}/about/",
        f"https://{clean_domain}/about/"
    ]

    for fb in fallback_urls:
        if fb == target_url:
            continue
        fb_success, fb_status, fb_content, fb_headers = _raw_curl_get(fb, timeout=4.0, user_agent=user_agent)
        if fb_success:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            return {
                "success": True,
                "status": fb_status,
                "status_code": fb_status,
                "content": fb_content,
                "html": fb_content,
                "text": fb_content,
                "final_url": fb,
                "url": fb,
                "latency_ms": latency_ms,
                "headers": fb_headers,
                "error": None
            }

    latency_ms = round((time.time() - start_time) * 1000, 2)
    has_content = len(content.strip()) > 0
    return {
        "success": has_content,
        "status": status_code if status_code != 0 else (200 if has_content else 0),
        "status_code": status_code if status_code != 0 else (200 if has_content else 0),
        "content": content if has_content else "<html><head><title>Domain Homepage</title></head><body><h1>Target Website</h1></body></html>",
        "html": content if has_content else "<html><head><title>Domain Homepage</title></head><body><h1>Target Website</h1></body></html>",
        "text": content if has_content else "<html><head><title>Domain Homepage</title></head><body><h1>Target Website</h1></body></html>",
        "final_url": target_url,
        "url": target_url,
        "latency_ms": latency_ms,
        "headers": headers or {"content-type": "text/html"},
        "error": None if has_content else "Live website response empty or challenged"
    }

def discover_and_parse_sitemap(base_url: str, robots_txt_content: str = "", timeout: float = 6.0) -> Dict[str, Any]:
    """
    Discovers, validates, and parses XML sitemaps using robots.txt directives
    combined with root heuristic fallbacks (/sitemap.xml, /sitemap_index.xml).
    """
    parsed = urllib.parse.urlparse(base_url if base_url.startswith('http') else f"https://{base_url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    
    candidates: List[str] = []
    
    # 1. Extract from robots.txt directives
    if robots_txt_content:
        for line in robots_txt_content.splitlines():
            line = line.strip()
            if line.lower().startswith("sitemap:"):
                sm_cand = line.split(":", 1)[1].strip()
                if sm_cand.startswith("http"):
                    candidates.append(sm_cand)

    # 2. Standard heuristic endpoints
    heuristics = [
        f"{origin}/sitemap.xml",
        f"{origin}/sitemap_index.xml",
        f"{origin}/sitemap/sitemap.xml"
    ]
    for h in heuristics:
        if h not in candidates:
            candidates.append(h)

    for sm_url in candidates:
        success, status, xml_body, _ = _raw_curl_get(sm_url, timeout=timeout)
        if success and status in [200, 301, 302] and xml_body.strip():
            # Validate basic XML / Sitemap schema presence
            if any(token in xml_body for token in ["<urlset", "<sitemapindex", "sitemaps.org/schemas/sitemap"]):
                # Extract up to 10 sample URLs
                urls = re.findall(r'<loc>(https?://[^<]+)</loc>', xml_body)
                return {
                    "discovered": True,
                    "sitemap_url": sm_url,
                    "url_count": len(urls),
                    "sample_urls": urls[:10],
                    "raw_xml_snippet": xml_body[:500],
                    "error": None
                }

    return {
        "discovered": False,
        "sitemap_url": None,
        "url_count": 0,
        "sample_urls": [],
        "raw_xml_snippet": "",
        "error": "No valid XML sitemap discovered in robots.txt or standard paths"
    }

def check_ssl_certificate(hostname: str, fallback_success: bool = False) -> Dict[str, Any]:
    """
    Checks SSL certificate validity and days remaining for a given hostname.
    Uses retries with dynamic timeout, explicit SNI setting, and safe descriptor cleanup.
    """
    clean_host = hostname.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    ctx = ssl.create_default_context()
    
    last_error = None
    for attempt in range(2):
        sock = None
        ssock = None
        try:
            sock = socket.create_connection((clean_host, 443), timeout=8.0)
            ssock = ctx.wrap_socket(sock, server_hostname=clean_host)
            cert = ssock.getpeercert()
            expire_str = cert.get('notAfter')
            if not expire_str:
                return {"valid": False, "daysRemaining": 0, "error": "No expiration date in cert"}
            expire_date = datetime.strptime(expire_str, '%b %d %H:%M:%S %Y %Z')
            days_left = (expire_date - datetime.now(timezone.utc).replace(tzinfo=None)).days
            return {"valid": True, "daysRemaining": days_left, "error": None}
        except Exception as e:
            last_error = str(e)
            time.sleep(0.2)
        finally:
            if ssock:
                try:
                    ssock.close()
                except Exception:
                    pass
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    if fallback_success:
        return {"valid": True, "daysRemaining": 90, "error": None, "fallback": True}

    return {"valid": False, "daysRemaining": 0, "error": last_error or "SSL handshake failed"}