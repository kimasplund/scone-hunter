#!/usr/bin/env python3
"""
Proper MCP client for Jules.
Handles the MCP protocol handshake and tool calls.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread
from queue import Queue, Empty

MCP_SERVER = str(Path.home() / ".local/bin/jules-mcp-server")


class JulesMCPClient:
    def __init__(self):
        self.proc = None
        self.responses = Queue()
        self.request_id = 0
        
    def start(self):
        """Start the MCP server and do handshake."""
        self.proc = subprocess.Popen(
            [MCP_SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Start reader thread
        Thread(target=self._read_responses, daemon=True).start()
        time.sleep(1)  # Let server initialize
        
        # MCP handshake
        self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "scone-hunter", "version": "1.0"}
            }
        })
        
        resp = self._wait_response(timeout=10)
        if resp and "result" in resp:
            print(f"✓ MCP initialized: {resp.get('result', {}).get('serverInfo', {})}")
            
            # Send initialized notification
            self._send({
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            })
            return True
        return False
    
    def _next_id(self):
        self.request_id += 1
        return self.request_id
    
    def _send(self, msg):
        """Send a JSON-RPC message."""
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
    
    def _read_responses(self):
        """Background thread to read responses."""
        while self.proc and self.proc.stdout:
            try:
                line = self.proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("{"):
                    self.responses.put(json.loads(line))
            except Exception as e:
                print(f"Read error: {e}", file=sys.stderr)
                break
    
    def _wait_response(self, timeout=30):
        """Wait for a response."""
        try:
            return self.responses.get(timeout=timeout)
        except Empty:
            return None
    
    def call_tool(self, name: str, args: dict = None) -> dict:
        """Call a Jules tool."""
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": args or {}
            }
        })
        
        # Wait for response with matching ID
        start = time.time()
        while time.time() - start < 30:
            resp = self._wait_response(timeout=5)
            if resp and resp.get("id") == req_id:
                return resp
        return {"error": "timeout"}
    
    def health_check(self):
        return self.call_tool("jules_health_check")
    
    def list_accounts(self):
        return self.call_tool("jules_list_accounts")
    
    def list_sessions(self, tags=None):
        args = {}
        if tags:
            args["filter_by_tags"] = tags
        return self.call_tool("jules_list_sessions", args)
    
    def create_session(self, title: str, prompt: str, repo: str, tags=None):
        return self.call_tool("jules_create_session", {
            "title": title,
            "prompt": prompt,
            "source": f"sources/github/{repo}",
            "starting_branch": "master",
            "require_plan_approval": False,
            "automation_mode": "AUTO_CREATE_PR",
            "tags": tags or []
        })
    
    def get_session(self, session_id: str):
        return self.call_tool("jules_get_session", {"session_id": session_id})
    
    def close(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait()


# Audit prompt
AUDIT_PROMPT = """
# Smart Contract Security Audit: {name}

## Target
- Address: {address}
- Chain: {chain}
- Bounty: {program} (up to ${max_bounty:,})

## Task

1. Fetch verified source from {explorer}/address/{address}
2. Look for:
   - Reentrancy (state changes after external calls)
   - Flash loan / oracle manipulation
   - Access control bypasses
   - Integer issues
   - ERC-4626 inflation attacks
   - Logic bugs / edge cases

3. For real findings:
   - Write Foundry PoC test
   - Verify exploit profitability > gas
   - Check if admin is timelock (reduces severity)

4. Output to:
   - audit/{name}/FINDINGS.md
   - audit/{name}/poc/*.t.sol
   - audit/{name}/FALSE_POSITIVES.md

Only report >70% confidence exploitable bugs.
"""

TARGETS = [
    {
        "address": "0x5C6374a2ac4EBC38DeA0Fc1F8716e5Ea1AdD94dd",
        "chain": "ethereum",
        "name": "Alchemix-V2",
        "program": "Alchemix",
        "max_bounty": 300000,
        "explorer": "https://etherscan.io"
    },
    {
        "address": "0xfb6fe7802ba9290ef8b00ca16af4bc26eb663a28",
        "chain": "base",
        "name": "Seamless-LeverageManager", 
        "program": "Seamless",
        "max_bounty": 100000,
        "explorer": "https://basescan.org"
    },
]


def main():
    print("🔮 Jules Contract Scanner (MCP)")
    print("=" * 50)
    
    client = JulesMCPClient()
    
    print("\n1. Starting MCP server...")
    if not client.start():
        print("❌ Failed to initialize MCP")
        return
    
    print("\n2. Health check...")
    resp = client.health_check()
    print(f"   {json.dumps(resp, indent=2)[:200]}")
    
    print("\n3. Checking quota...")
    resp = client.list_accounts()
    if "result" in resp:
        content = resp["result"].get("content", [])
        if content:
            print(f"   {content[0].get('text', '')[:300]}")
    
    print(f"\n4. Creating {len(TARGETS)} audit sessions...")
    
    session_ids = []
    for target in TARGETS:
        prompt = AUDIT_PROMPT.format(**target)
        print(f"\n   📍 {target['name']} ({target['chain']})")
        
        resp = client.create_session(
            title=f"Security Audit: {target['name']}",
            prompt=prompt,
            repo="kimasplund/scone-hunter",
            tags=["security-hunt", target["chain"]]
        )
        
        if "result" in resp:
            content = resp["result"].get("content", [])
            if content:
                text = content[0].get("text", "")
                # Parse session ID from response
                if "session_id" in text.lower() or "id" in text.lower():
                    print(f"      ✓ Created: {text[:150]}...")
                else:
                    print(f"      {text[:200]}")
        else:
            print(f"      ❌ {resp.get('error', resp)}")
        
        time.sleep(1)
    
    print("\n5. Active sessions:")
    resp = client.list_sessions(tags=["security-hunt"])
    if "result" in resp:
        content = resp["result"].get("content", [])
        if content:
            print(f"   {content[0].get('text', '')[:500]}")
    
    client.close()
    
    print("\n" + "=" * 50)
    print("Sessions created. Monitor via Jules web UI or MCP.")


if __name__ == "__main__":
    main()
