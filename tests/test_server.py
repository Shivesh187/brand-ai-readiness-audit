import sys
import os
import json
import unittest
import urllib.request
import urllib.error
import threading
import time

# Dynamically locate workspace root
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from server import ThreadedHTTPServer, AuditRequestHandler

class TestBrandAIReadinessServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8899
        cls.server_address = ("127.0.0.1", cls.port)
        cls.httpd = ThreadedHTTPServer(cls.server_address, AuditRequestHandler)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        time.sleep(0.2)  # Allow server thread to initialize

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_01_health_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/api/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("service"), "brand-ai-readiness-audit")
            self.assertIn("playwright_available", data)

    def test_02_post_audit_valid(self):
        url = f"http://127.0.0.1:{self.port}/api/audit"
        payload = json.dumps({"url": "example.com", "brand": "Example", "no_llm": True}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertEqual(data.get("site"), "example.com")
            self.assertIn("readiness_score", data)
            self.assertIn("summary", data)

    def test_03_post_audit_missing_url(self):
        url = f"http://127.0.0.1:{self.port}/api/audit"
        payload = json.dumps({"url": "", "brand": "Example"}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Should have raised HTTP 400 Error")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            data = json.loads(e.read().decode('utf-8'))
            self.assertIn("error", data)

    def test_04_post_audit_oversized_url(self):
        url = f"http://127.0.0.1:{self.port}/api/audit"
        long_url = "a" * 300 + ".com"
        payload = json.dumps({"url": long_url, "brand": "Example"}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Should have raised HTTP 400 Error")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

if __name__ == "__main__":
    unittest.main()
