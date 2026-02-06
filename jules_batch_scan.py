#!/usr/bin/env python3
"""
Batched Jules scanner - multiple contracts per session.
Squeezes 10x more audits from the 100 task/day quota.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread
from queue import Queue, Empty

MCP_SERVER = str(Path.home() / ".local/bin/jules-mcp-server")

# Batch size: contracts per session
BATCH_SIZE = 10


class JulesMCPClient:
    def __init__(self):
        self.proc = None
        self.responses = Queue()
        self.request_id = 0
        
    def start(self):
        self.proc = subprocess.Popen(
            [MCP_SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        Thread(target=self._read_responses, daemon=True).start()
        time.sleep(1)
        
        self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "scone-hunter-batch", "version": "2.0"}
            }
        })
        
        resp = self._wait_response(timeout=10)
        if resp and "result" in resp:
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return True
        return False
    
    def _next_id(self):
        self.request_id += 1
        return self.request_id
    
    def _send(self, msg):
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
    
    def _read_responses(self):
        while self.proc and self.proc.stdout:
            try:
                line = self.proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("{"):
                    self.responses.put(json.loads(line))
            except:
                break
    
    def _wait_response(self, timeout=30):
        try:
            return self.responses.get(timeout=timeout)
        except Empty:
            return None
    
    def call_tool(self, name: str, args: dict = None) -> dict:
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args or {}}
        })
        start = time.time()
        while time.time() - start < 30:
            resp = self._wait_response(timeout=5)
            if resp and resp.get("id") == req_id:
                return resp
        return {"error": "timeout"}
    
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
    
    def list_accounts(self):
        return self.call_tool("jules_list_accounts")
    
    def close(self):
        if self.proc:
            self.proc.terminate()


# Multi-contract audit prompt
BATCH_PROMPT = """
# Batch Security Audit: {batch_name}

You are auditing {count} smart contracts for vulnerabilities.

## Targets

{targets_section}

## Instructions

For EACH contract above:

1. Fetch verified source from the explorer link
2. Analyze for:
   - Reentrancy
   - Flash loan / oracle manipulation  
   - Access control bypasses
   - Integer overflow/underflow
   - ERC-4626 inflation attacks
   - Logic bugs

3. Create files for each contract:
   - `audit/[contract-name]/FINDINGS.md`
   - `audit/[contract-name]/poc/*.t.sol` (Foundry tests)
   - `audit/[contract-name]/FALSE_POSITIVES.md`

## Output Format

For each finding, include:
- Severity: Critical/High/Medium/Low
- Confidence: 0-100%
- Exploit path (step by step)
- Estimated profit vs gas cost
- PoC code

SKIP contracts where admin is timelock/multisig (already protected).
Only report findings with >70% confidence.

Start with Contract 1 and work through all {count} contracts.
"""


# High-value targets pool
ALL_TARGETS = [
    # Alchemix ecosystem
    {"address": "0x5C6374a2ac4EBC38DeA0Fc1F8716e5Ea1AdD94dd", "chain": "ethereum", "name": "Alchemix-AlchemistV2", "program": "Alchemix", "max_bounty": 300000},
    {"address": "0xa537e4d06f91F6b2C07875C6e0F16D5e4E1c68cE", "chain": "ethereum", "name": "Alchemix-TransmuterV2", "program": "Alchemix", "max_bounty": 300000},
    {"address": "0xdbdb4d16eda451d0503b854cf79d55697f90c8df", "chain": "ethereum", "name": "Alchemix-ALCX", "program": "Alchemix", "max_bounty": 300000},
    
    # Seamless (Base)
    {"address": "0xfb6fe7802ba9290ef8b00ca16af4bc26eb663a28", "chain": "base", "name": "Seamless-LeverageManager", "program": "Seamless", "max_bounty": 100000},
    {"address": "0x38Ba21C6Bf31dF1b1798FCEd07B4e9b07C5ec3a8", "chain": "base", "name": "Seamless-LeverageProxy", "program": "Seamless", "max_bounty": 100000},
    
    # Inverse Finance
    {"address": "0x1637e4e9941D55703a7A5E7807d6aDA3f7DCD61B", "chain": "ethereum", "name": "Inverse-INV", "program": "Inverse", "max_bounty": 100000},
    {"address": "0x4dCf7407AE5C07f8681e1659f626E114A7667339", "chain": "ethereum", "name": "Inverse-Anchor", "program": "Inverse", "max_bounty": 100000},
    
    # Morpho (if Seamless uses it)
    {"address": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb", "chain": "ethereum", "name": "Morpho-Blue", "program": "Morpho", "max_bounty": 500000},
    
    # Yearn
    {"address": "0xa354F35829Ae975e850e23e9615b11Da1B3dC4DE", "chain": "ethereum", "name": "Yearn-yvUSDC", "program": "Yearn", "max_bounty": 200000},
    {"address": "0xdA816459F1AB5631232FE5e97a05BBBb94970c95", "chain": "ethereum", "name": "Yearn-yvDAI", "program": "Yearn", "max_bounty": 200000},
    
    # Aura Finance
    {"address": "0xC0c293ce456fF0ED870ADd98a0828Dd4d2903DBF", "chain": "ethereum", "name": "Aura-AURA", "program": "Aura", "max_bounty": 150000},
    
    # Convex
    {"address": "0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B", "chain": "ethereum", "name": "Convex-CVX", "program": "Convex", "max_bounty": 150000},
    
    # Base DeFi
    {"address": "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22", "chain": "base", "name": "Aerodrome-Router", "program": "Aerodrome", "max_bounty": 100000},
    {"address": "0x420DD381b31aEf6683db6B902084cB0FFECe40Da", "chain": "base", "name": "Aerodrome-Gauge", "program": "Aerodrome", "max_bounty": 100000},
    
    # Extra Base targets
    {"address": "0x4200000000000000000000000000000000000006", "chain": "base", "name": "Base-WETH", "program": "Base", "max_bounty": 50000},
    {"address": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "chain": "base", "name": "Base-USDbC", "program": "Base", "max_bounty": 50000},
]


def get_explorer(chain: str) -> str:
    return {
        "ethereum": "https://etherscan.io",
        "base": "https://basescan.org",
        "arbitrum": "https://arbiscan.io",
        "optimism": "https://optimistic.etherscan.io",
    }.get(chain, "https://etherscan.io")


def create_batch_prompt(targets: list) -> str:
    """Create a multi-contract audit prompt."""
    targets_section = ""
    for i, t in enumerate(targets, 1):
        explorer = get_explorer(t["chain"])
        targets_section += f"""
### Contract {i}: {t['name']}
- **Address**: {t['address']}
- **Chain**: {t['chain']}
- **Explorer**: {explorer}/address/{t['address']}
- **Program**: {t['program']}
- **Max Bounty**: ${t['max_bounty']:,}
"""
    
    return BATCH_PROMPT.format(
        batch_name=f"Batch-{targets[0]['program']}",
        count=len(targets),
        targets_section=targets_section
    )


def main():
    print("🔮 Jules BATCH Scanner")
    print(f"   Batch size: {BATCH_SIZE} contracts/session")
    print(f"   Total targets: {len(ALL_TARGETS)}")
    print("=" * 50)
    
    client = JulesMCPClient()
    
    print("\n1. Starting MCP...")
    if not client.start():
        print("❌ Failed to init MCP")
        return
    print("   ✓ Connected")
    
    # Check quota
    resp = client.list_accounts()
    if "result" in resp:
        content = resp["result"].get("content", [{}])
        if content:
            text = content[0].get("text", "")
            if "quota_remaining" in text:
                print(f"   Quota: {text[:100]}...")
    
    # Batch targets
    batches = [ALL_TARGETS[i:i+BATCH_SIZE] for i in range(0, len(ALL_TARGETS), BATCH_SIZE)]
    
    print(f"\n2. Creating {len(batches)} batch sessions...")
    print(f"   ({len(ALL_TARGETS)} contracts ÷ {BATCH_SIZE} = {len(batches)} sessions)")
    
    sessions_created = []
    
    for i, batch in enumerate(batches, 1):
        programs = set(t["program"] for t in batch)
        batch_name = f"Batch-{i}-{'-'.join(programs)}"
        
        print(f"\n   📦 {batch_name} ({len(batch)} contracts)")
        for t in batch:
            print(f"      • {t['name']}")
        
        prompt = create_batch_prompt(batch)
        
        resp = client.create_session(
            title=f"Security Audit: {batch_name}",
            prompt=prompt,
            repo="kimasplund/scone-hunter",
            tags=["security-hunt", "batch", f"batch-{i}"]
        )
        
        if "result" in resp:
            content = resp["result"].get("content", [])
            if content:
                text = content[0].get("text", "")
                if '"id"' in text:
                    # Extract session ID
                    import re
                    match = re.search(r'"id":\s*"(\d+)"', text)
                    if match:
                        sid = match.group(1)
                        sessions_created.append({"batch": batch_name, "session_id": sid, "contracts": len(batch)})
                        print(f"      ✓ Session: {sid}")
        
        time.sleep(1)  # Rate limit
    
    client.close()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print(f"   Sessions created: {len(sessions_created)}")
    print(f"   Contracts queued: {sum(s['contracts'] for s in sessions_created)}")
    print(f"   Sessions used: {len(sessions_created)}/100 daily quota")
    
    # Save session tracking
    tracking_file = Path.home() / ".scone-hunter" / "batch_sessions.json"
    tracking_file.parent.mkdir(parents=True, exist_ok=True)
    with open(tracking_file, "w") as f:
        json.dump(sessions_created, f, indent=2)
    print(f"\n   Tracking: {tracking_file}")
    
    print("\n" + "=" * 50)
    print("Monitor: https://jules.google.com")
    print("=" * 50)


if __name__ == "__main__":
    main()
