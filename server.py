import sys
import os
import json
import re
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

# Dynamically locate workspace root and insert into sys.path
workspace_root = os.path.abspath(os.path.dirname(__file__))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

import importlib.util

# Helper function to auto-load .env file if GEMINI_API_KEY is not set in environment or force re-read
def _load_env_file(force: bool = False):
    if not force and "GEMINI_API_KEY" in os.environ and os.environ["GEMINI_API_KEY"].strip():
        return
    cur = os.path.abspath(__file__)
    while cur != os.path.dirname(cur):
        env_path = os.path.join(cur, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k and v:
                                if force or k not in os.environ:
                                    os.environ[k] = v
            except Exception:
                pass
            break
        cur = os.path.dirname(cur)

_load_env_file()

# Dynamically load run_audit orchestrator module
run_audit_path = os.path.join(workspace_root, "skills", "audit-orchestrator", "scripts", "run_audit.py")
spec = importlib.util.spec_from_file_location("run_audit", run_audit_path)
run_audit_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_audit_mod)

execute_audit_pipeline = run_audit_mod.execute_audit_pipeline
clean_url = run_audit_mod.clean_url

from common.browser_renderer import PLAYWRIGHT_AVAILABLE

PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP Server for concurrent audit request isolation."""
    daemon_threads = True
    allow_reuse_address = True

class AuditRequestHandler(SimpleHTTPRequestHandler):
    """
    HTTP Request Handler serving API endpoints and Adobe-styled Web UI static files.
    """
    def __init__(self, *args, **kwargs):
        # Serve static assets from 'web' directory
        web_dir = os.path.join(workspace_root, "web")
        super().__init__(*args, directory=web_dir, **kwargs)

    def log_message(self, format, *args):
        # Clean logging without exposing credentials or internal tokens
        sys.stdout.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        _load_env_file(force=True)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            llm_enabled = os.environ.get("GEMINI_ENABLED", "true").lower() in ["true", "1", "yes"]
            has_api_key = bool(os.environ.get("GEMINI_API_KEY", "").strip())
            return self._send_json(200, {
                "status": "ok",
                "service": "brand-ai-readiness-audit",
                "version": "1.0.0",
                "playwright_available": PLAYWRIGHT_AVAILABLE,
                "llm_enabled": llm_enabled,
                "llm_key_configured": has_api_key
            })
        
        # Fall back to serving static web files from web/
        return super().do_GET()

    def do_POST(self):
        _load_env_file(force=True)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/audit":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length <= 0 or content_length > 65536:
                    return self._send_json(400, {"error": "Invalid request payload size."})

                raw_body = self.rfile.read(content_length).decode('utf-8')
                try:
                    payload = json.loads(raw_body)
                except json.JSONDecodeError:
                    return self._send_json(400, {"error": "Invalid JSON format."})

                raw_url = str(payload.get("url", "")).strip()
                raw_brand = str(payload.get("brand", "")).strip()
                no_llm = bool(payload.get("no_llm", False))

                # Input Validation & Sanitization
                if not raw_url:
                    return self._send_json(400, {"error": "Website URL is required."})

                if len(raw_url) > 255:
                    return self._send_json(400, {"error": "URL length exceeds limit (max 255 characters)."})

                if len(raw_brand) > 100:
                    return self._send_json(400, {"error": "Brand length exceeds limit (max 100 characters)."})

                normalized_domain = clean_url(raw_url)
                if not normalized_domain or not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', normalized_domain):
                    return self._send_json(400, {"error": "Invalid target domain or URL format."})

                enable_llm = not no_llm

                # Execute audit pipeline safely in-memory (Zero shell injection risk)
                report = execute_audit_pipeline(
                    target_domain=normalized_domain,
                    brand_name=raw_brand if raw_brand else None,
                    enable_llm=enable_llm
                )

                return self._send_json(200, report.to_dict())

            except Exception as ex:
                # Sanitized error response - Hides stack traces and API keys
                return self._send_json(500, {
                    "error": "An internal audit execution error occurred cleanly. Please check domain or network connectivity."
                })

        return self._send_json(404, {"error": "API endpoint not found."})

def run_server():
    server_address = (HOST, PORT)
    httpd = ThreadedHTTPServer(server_address, AuditRequestHandler)
    print(f"=== Brand AI Readiness Audit Web Server Running ===")
    print(f"URL: http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server gracefully...")
        httpd.shutdown()

if __name__ == "__main__":
    run_server()
