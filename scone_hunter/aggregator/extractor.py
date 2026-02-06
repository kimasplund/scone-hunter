#!/usr/bin/env python3
"""
Extract findings from completed Jules sessions.
"""

import json
import subprocess
import time
import re
from pathlib import Path
from threading import Thread
from queue import Queue, Empty
from dataclasses import dataclass
from typing import Optional

MCP_SERVER = str(Path.home() / ".local/bin/jules-mcp-server")


@dataclass
class Finding:
    """A potential vulnerability finding."""
    contract_name: str
    contract_address: str
    chain: str
    vuln_type: str
    severity: str  # Critical, High, Medium, Low
    confidence: int  # 0-100
    description: str
    poc_code: Optional[str] = None
    bounty_program: Optional[str] = None
    max_bounty: Optional[int] = None
    pr_url: Optional[str] = None
    session_id: Optional[str] = None


@dataclass 
class SessionResult:
    """Results from a completed Jules session."""
    session_id: str
    state: str
    title: str
    created: str
    findings: list[Finding]
    pr_url: Optional[str] = None
    raw_output: Optional[str] = None


class JulesMCPClient:
    """Lightweight Jules MCP client for extraction."""
    
    def __init__(self):
        self.proc = None
        self.responses = Queue()
        self.req_id = 0
    
    def start(self) -> bool:
        self.proc = subprocess.Popen(
            [MCP_SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        Thread(target=self._read, daemon=True).start()
        time.sleep(1)
        
        self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "extractor", "version": "1.0"}
            }
        })
        
        resp = self._wait(10)
        if resp and "result" in resp:
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return True
        return False
    
    def _next_id(self):
        self.req_id += 1
        return self.req_id
    
    def _send(self, msg):
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
    
    def _read(self):
        while self.proc and self.proc.stdout:
            try:
                line = self.proc.stdout.readline().strip()
                if line.startswith("{"):
                    self.responses.put(json.loads(line))
            except:
                break
    
    def _wait(self, timeout=30):
        try:
            return self.responses.get(timeout=timeout)
        except Empty:
            return None
    
    def call(self, name: str, args: dict = None) -> dict:
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args or {}}
        })
        
        start = time.time()
        while time.time() - start < 30:
            resp = self._wait(5)
            if resp and resp.get("id") == req_id:
                return resp
        return {"error": "timeout"}
    
    def close(self):
        if self.proc:
            self.proc.terminate()


class ResultsExtractor:
    """Extract findings from Jules sessions."""
    
    def __init__(self):
        self.client = None
        self.findings_dir = Path.home() / ".scone-hunter" / "findings"
        self.findings_dir.mkdir(parents=True, exist_ok=True)
    
    def _ensure_client(self):
        if not self.client:
            self.client = JulesMCPClient()
            self.client.start()
    
    def list_sessions(self, tags: list = None, states: list = None) -> list[dict]:
        """List Jules sessions with optional filters."""
        self._ensure_client()
        
        args = {}
        if tags:
            args["filter_by_tags"] = tags
        if states:
            args["filter_by_states"] = states
        
        resp = self.client.call("jules_list_sessions", args)
        
        if "result" in resp:
            content = resp["result"].get("content", [])
            if content:
                data = json.loads(content[0].get("text", "{}"))
                return data.get("sessions", [])
        return []
    
    def get_completed_sessions(self) -> list[dict]:
        """Get all completed security-hunt sessions."""
        return self.list_sessions(
            tags=["security-hunt"],
            states=["COMPLETED"]
        )
    
    def get_in_progress_sessions(self) -> list[dict]:
        """Get all in-progress sessions."""
        return self.list_sessions(
            tags=["security-hunt"],
            states=["IN_PROGRESS", "PLANNING", "EXECUTING"]
        )
    
    def extract_artifacts(self, session_id: str) -> dict:
        """Extract PR and code artifacts from a session."""
        self._ensure_client()
        
        resp = self.client.call("jules_extract_artifacts", {
            "session_id": session_id
        })
        
        if "result" in resp:
            content = resp["result"].get("content", [])
            if content:
                return json.loads(content[0].get("text", "{}"))
        return {}
    
    def get_activities(self, session_id: str) -> list[dict]:
        """Get session activities (includes findings)."""
        self._ensure_client()
        
        resp = self.client.call("jules_list_activities", {
            "session_id": session_id
        })
        
        if "result" in resp:
            content = resp["result"].get("content", [])
            if content:
                data = json.loads(content[0].get("text", "{}"))
                return data.get("activities", [])
        return []
    
    def parse_findings(self, artifacts: dict, activities: list) -> list[Finding]:
        """Parse findings from session artifacts and activities."""
        findings = []
        
        # Look for findings in PR content or activities
        for activity in activities:
            # Check for any output that mentions vulnerabilities
            if "agentOutput" in activity:
                output = activity["agentOutput"].get("output", "")
                findings.extend(self._extract_from_text(output))
            
            if "codeChange" in activity:
                # Check if there are findings files
                changes = activity["codeChange"].get("changes", [])
                for change in changes:
                    path = change.get("path", "")
                    if "FINDINGS" in path.upper():
                        content = change.get("content", "")
                        findings.extend(self._extract_from_text(content))
        
        # Check artifacts for PR
        if "pullRequest" in artifacts:
            pr = artifacts["pullRequest"]
            for f in findings:
                f.pr_url = pr.get("url")
        
        return findings
    
    def _extract_from_text(self, text: str) -> list[Finding]:
        """Extract findings from text content."""
        findings = []
        
        # Pattern matching for common finding formats
        # Look for severity markers
        severity_patterns = [
            (r'(?:^|\n)#+\s*(Critical|High|Medium|Low)[:\s]*(.*?)(?=\n#+|\Z)', 'markdown'),
            (r'Severity:\s*(Critical|High|Medium|Low)', 'labeled'),
            (r'\*\*(Critical|High|Medium|Low)\*\*', 'bold'),
        ]
        
        for pattern, _ in severity_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                if isinstance(match, tuple):
                    severity, desc = match[0], match[1] if len(match) > 1 else ""
                else:
                    severity, desc = match, ""
                
                # Try to extract more details
                finding = Finding(
                    contract_name="Unknown",
                    contract_address="",
                    chain="",
                    vuln_type=self._guess_vuln_type(desc or text),
                    severity=severity.capitalize(),
                    confidence=70,  # Default confidence
                    description=desc[:500] if desc else "See PR for details"
                )
                findings.append(finding)
        
        # Also check for explicit confidence scores
        conf_match = re.search(r'confidence[:\s]*(\d+)%?', text, re.IGNORECASE)
        if conf_match and findings:
            findings[-1].confidence = int(conf_match.group(1))
        
        return findings
    
    def _guess_vuln_type(self, text: str) -> str:
        """Guess vulnerability type from text."""
        text_lower = text.lower()
        
        vuln_keywords = {
            "reentrancy": ["reentrancy", "reentrant", "re-entrancy"],
            "flash loan": ["flash loan", "flashloan", "flash-loan"],
            "oracle manipulation": ["oracle", "price manipulation"],
            "access control": ["access control", "unauthorized", "permission"],
            "integer overflow": ["overflow", "underflow", "integer"],
            "inflation attack": ["inflation", "first depositor", "donation"],
            "front-running": ["front-run", "frontrun", "mev", "sandwich"],
            "logic error": ["logic", "edge case", "off-by-one"],
        }
        
        for vuln_type, keywords in vuln_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return vuln_type
        
        return "unknown"
    
    def harvest_session(self, session_id: str) -> SessionResult:
        """Harvest all results from a session."""
        self._ensure_client()
        
        # Get session details
        resp = self.client.call("jules_get_session", {"session_id": session_id})
        session_info = {}
        if "result" in resp:
            content = resp["result"].get("content", [])
            if content:
                session_info = json.loads(content[0].get("text", "{}"))
        
        # Get artifacts
        artifacts = self.extract_artifacts(session_id)
        
        # Get activities
        activities = self.get_activities(session_id)
        
        # Parse findings
        findings = self.parse_findings(artifacts, activities)
        
        # Add session ID to all findings
        for f in findings:
            f.session_id = session_id
        
        return SessionResult(
            session_id=session_id,
            state=session_info.get("state", "UNKNOWN"),
            title=session_info.get("title", ""),
            created=session_info.get("createTime", ""),
            findings=findings,
            pr_url=artifacts.get("pullRequest", {}).get("url"),
            raw_output=json.dumps(activities, indent=2)[:5000]
        )
    
    def harvest_all_completed(self) -> list[SessionResult]:
        """Harvest all completed sessions."""
        results = []
        
        completed = self.get_completed_sessions()
        print(f"Found {len(completed)} completed sessions")
        
        for session in completed:
            session_id = session.get("id")
            if session_id:
                print(f"  Harvesting {session_id}...")
                result = self.harvest_session(session_id)
                results.append(result)
                
                # Save to file
                self._save_result(result)
        
        return results
    
    def _save_result(self, result: SessionResult):
        """Save result to findings directory."""
        filepath = self.findings_dir / f"{result.session_id}.json"
        
        data = {
            "session_id": result.session_id,
            "state": result.state,
            "title": result.title,
            "created": result.created,
            "pr_url": result.pr_url,
            "findings_count": len(result.findings),
            "findings": [
                {
                    "contract": f.contract_name,
                    "address": f.contract_address,
                    "chain": f.chain,
                    "type": f.vuln_type,
                    "severity": f.severity,
                    "confidence": f.confidence,
                    "description": f.description,
                }
                for f in result.findings
            ]
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def close(self):
        if self.client:
            self.client.close()


def main():
    """CLI for testing extraction."""
    import sys
    
    extractor = ResultsExtractor()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            # Show session status
            print("📊 SESSION STATUS")
            print("=" * 50)
            
            in_progress = extractor.get_in_progress_sessions()
            completed = extractor.get_completed_sessions()
            
            print(f"\nIn Progress: {len(in_progress)}")
            for s in in_progress:
                print(f"  • {s.get('id')} - {s.get('title', '')[:40]}...")
            
            print(f"\nCompleted: {len(completed)}")
            for s in completed:
                print(f"  • {s.get('id')} - {s.get('title', '')[:40]}...")
        
        elif sys.argv[1] == "harvest":
            # Harvest all completed
            print("🌾 HARVESTING COMPLETED SESSIONS")
            print("=" * 50)
            
            results = extractor.harvest_all_completed()
            
            total_findings = sum(len(r.findings) for r in results)
            print(f"\nTotal sessions: {len(results)}")
            print(f"Total findings: {total_findings}")
            
            for r in results:
                if r.findings:
                    print(f"\n{r.session_id}:")
                    for f in r.findings:
                        print(f"  [{f.severity}] {f.vuln_type} - {f.confidence}% confidence")
        
        elif sys.argv[1] == "session":
            if len(sys.argv) > 2:
                session_id = sys.argv[2]
                result = extractor.harvest_session(session_id)
                print(f"Session: {result.session_id}")
                print(f"State: {result.state}")
                print(f"PR: {result.pr_url or 'None'}")
                print(f"Findings: {len(result.findings)}")
                for f in result.findings:
                    print(f"  [{f.severity}] {f.vuln_type}")
    else:
        print("Usage:")
        print("  python extractor.py status   - Show session status")
        print("  python extractor.py harvest  - Harvest all completed")
        print("  python extractor.py session <id> - Harvest specific session")
    
    extractor.close()


if __name__ == "__main__":
    main()
