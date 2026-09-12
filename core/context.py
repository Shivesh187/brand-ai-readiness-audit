import threading
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class AuditContext:
    target_url: str
    raw_html: str = ""
    status_code: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    archetype: str = "GENERAL_CONTENT"
    robots_txt: str = ""
    parsed_json_ld: List[Dict[str, Any]] = field(default_factory=list)
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add_finding(
        self,
        finding_id: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        evidence: str,
        confidence: float = 1.0,
        recommendation: Optional[str] = None,
        **extra
    ) -> Dict[str, Any]:
        finding = {
            "id": finding_id,
            "category": category,
            "severity": severity.lower(),
            "title": title,
            "message": message,
            "evidence": evidence,
            "confidence": confidence,
            "recommendation": recommendation or message,
            **extra
        }
        with self._lock:
            # Avoid duplicate finding IDs
            if not any(f["id"] == finding_id for f in self.findings):
                self.findings.append(finding)
        return finding

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "target_url": self.target_url,
                "status_code": self.status_code,
                "archetype": self.archetype,
                "headers": self.headers,
                "parsed_json_ld_count": len(self.parsed_json_ld),
                "extracted_entities": self.extracted_entities,
                "findings": list(self.findings),
                "metadata": self.metadata
            }
