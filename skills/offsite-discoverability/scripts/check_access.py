import urllib.request
import ssl
import socket
import time
import json
import sys
import re
from datetime import datetime, timezone

def check_ssl(hostname):
    ctx = ssl.create_default_context()
    with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
        s.settimeout(5.0)
        try:
            s.connect((hostname, 443))
            cert = s.getpeercert()
            expire_str = cert.get('notAfter')
            expire_date = datetime.strptime(expire_str, '%b %d %H:%M:%S %Y %Z')
            days_left = (expire_date - datetime.now(timezone.utc).replace(tzinfo=None)).days
            return {"valid": True, "daysRemaining": days_left, "error": None}
        except Exception as e:
            return {"valid": False, "daysRemaining": 0, "error": str(e)}

def parse_robots_txt(domain, bots):
    url = f"https://{domain}/robots.txt"
    findings = []
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5.0) as response:
            content = response.read().decode('utf-8')
    except Exception as e:
        findings.append({
            "id": "access-robots-fetch-failed",
            "title": "Failed to fetch robots.txt",
            "severity": "high",
            "evidence": str(e),
            "suggested_action": {
                "summary": "Ensure robots.txt is published at the root domain and returns 200 OK.",
                "priority": 2
            }
        })
        return findings

    # Parse rules
    access_map = {}
    lines = content.split('\n')
    current_agents = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        agent_match = re.match(r'^user-agent:\s*(.+)$', line, re.IGNORECASE)
        if agent_match:
            agent = agent_match.group(1).strip().lower()
            current_agents.append(agent)
            continue
        disallow_match = re.match(r'^disallow:\s*(.+)$', line, re.IGNORECASE)
        if disallow_match and current_agents:
            path = disallow_match.group(1).strip()
            for agent in current_agents:
                if agent not in access_map:
                    access_map[agent] = []
                access_map[agent].append({"type": "disallow", "path": path})
        if line == "":
            current_agents = []

    for bot in bots:
        bot_lower = bot.lower()
        rules = []
        if bot_lower in access_map:
            rules = access_map[bot_lower]
        elif '*' in access_map:
            rules = access_map['*']
            
        is_blocked = any(r["type"] == "disallow" and r["path"] in ["/", "/*", ""] for r in rules)
        if is_blocked:
            findings.append({
                "id": f"access-robots-blocked-{bot_lower}",
                "title": f"AI Crawler '{bot}' is blocked in robots.txt",
                "severity": "critical" if bot in ["GPTBot", "PerplexityBot"] else "high",
                "evidence": f"Disallow rule matched for user-agent '{bot}'",
                "suggested_action": {
                    "summary": f"Modify robots.txt to permit '{bot}' access to high-value content paths.",
                    "priority": 1
                }
            })
            
    return findings

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No domain provided"}))
        sys.exit(1)
        
    domain = sys.argv[1]
    findings = []
    
    # Check HTTP GET and Latency
    start_time = time.time()
    try:
        req = urllib.request.Request(f"https://{domain}", headers={'User-Agent': 'Mozilla/5.0'}, method='GET')
        with urllib.request.urlopen(req, timeout=5.0) as response:
            status = response.getcode()
            latency = (time.time() - start_time) * 1000
            
            if status != 200:
                findings.append({
                    "id": "access-http-status-non200",
                    "title": f"Homepage returns non-200 status code ({status})",
                    "severity": "high",
                    "evidence": f"HTTP status code: {status}",
                    "suggested_action": {
                        "summary": "Ensure homepage returns a success status code (200 OK) for root crawls.",
                        "priority": 2
                    }
                })
            
            if latency > 1500:
                findings.append({
                    "id": "access-http-latency-slow",
                    "title": "High homepage response latency",
                    "severity": "medium",
                    "evidence": f"Latency: {int(latency)}ms (Threshold: 1500ms)",
                    "suggested_action": {
                        "summary": "Optimize server response times and deploy global CDN caching.",
                        "priority": 3
                    }
                })
    except Exception as e:
        findings.append({
            "id": "access-http-connection-failed",
            "title": "Could not connect to homepage",
            "severity": "critical",
            "evidence": str(e),
            "suggested_action": {
                "summary": "Check dns settings, firewall rules, and web server health.",
                "priority": 1
            }
        })
        
    # Check SSL
    ssl_result = check_ssl(domain)
    if not ssl_result["valid"]:
        findings.append({
            "id": "access-ssl-invalid",
            "title": "SSL Certificate Handshake Failed",
            "severity": "critical",
            "evidence": ssl_result["error"],
            "suggested_action": {
                "summary": "Renew or fix the SSL certificate configuration immediately.",
                "priority": 1
            }
        })
    elif ssl_result["daysRemaining"] < 30:
        findings.append({
            "id": "access-ssl-expiring",
            "title": "SSL Certificate expiring soon",
            "severity": "high",
            "evidence": f"Certificate expires in {ssl_result['daysRemaining']} days",
            "suggested_action": {
                "summary": "Renew the SSL certificate before it expires to prevent client errors.",
                "priority": 2
            }
        })

    # Check Robots
    bots_to_check = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"]
    robots_findings = parse_robots_txt(domain, bots_to_check)
    findings.extend(robots_findings)

    print(json.dumps(findings, indent=2))

if __name__ == "__main__":
    main()
