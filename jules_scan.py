#!/usr/bin/env python3
"""
Direct Jules MCP integration for contract scanning.
Spawns Jules sessions to audit smart contracts.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

MCP_SERVER = Path.home() / ".local/bin/jules-mcp-server"

def mcp_call(method: str, params: dict = None) -> dict:
    """Make a JSON-RPC call to Jules MCP server."""
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": f"tools/{method}",
        "params": {"arguments": params or {}}
    }
    
    proc = subprocess.Popen(
        [str(MCP_SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Send request
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    proc.stdin.close()
    
    # Read response (with timeout)
    try:
        stdout, stderr = proc.communicate(timeout=30)
        for line in stdout.strip().split("\n"):
            if line.strip().startswith("{"):
                return json.loads(line)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"error": "timeout"}
    
    return {"error": stderr or "no response"}


def health_check():
    """Check if Jules API is healthy."""
    return mcp_call("jules_health_check")


def list_accounts():
    """List Jules accounts and quota."""
    return mcp_call("jules_list_accounts")


def create_session(title: str, prompt: str, repo: str, tags: list = None):
    """Create a Jules session."""
    return mcp_call("jules_create_session", {
        "title": title,
        "prompt": prompt,
        "source": f"sources/github/{repo}",
        "starting_branch": "master",
        "require_plan_approval": False,
        "automation_mode": "AUTO_CREATE_PR",
        "tags": tags or ["security-hunt"]
    })


def list_sessions(tags: list = None):
    """List active sessions."""
    params = {}
    if tags:
        params["filter_by_tags"] = tags
    return mcp_call("jules_list_sessions", params)


# Contract audit prompt template
AUDIT_PROMPT = """
# Smart Contract Security Audit

## Target
- Address: {address}
- Chain: {chain}
- Bounty Program: {program}
- Max Bounty: ${max_bounty:,}

## Instructions

1. Fetch the verified source code from {explorer}
2. Analyze for these vulnerability classes:
   - Reentrancy (check state changes before external calls)
   - Flash loan attacks (price oracle manipulation)
   - Access control (admin functions, role bypasses)
   - Integer overflow/underflow (even in Solidity 0.8+)
   - Logic errors (edge cases, off-by-one)
   - ERC-4626 inflation attacks
   - Signature replay / malleability
   
3. For each potential finding:
   - Verify it's NOT a false positive
   - Check if admin is timelocked/multisig (reduce severity)
   - Write a Foundry PoC test
   - Calculate real exploit profit
   
4. Create files:
   - `audit/FINDINGS.md` - Vulnerability report
   - `audit/poc/` - Foundry test files
   - `audit/FALSE_POSITIVES.md` - What looks bad but isn't

Only report findings with >70% confidence and real exploit path.
"""


TARGETS = [
    {
        "address": "0x5C6374a2ac4EBC38DeA0Fc1F8716e5Ea1AdD94dd",
        "chain": "ethereum",
        "name": "Alchemix Alchemist V2",
        "program": "Alchemix",
        "max_bounty": 300000,
        "explorer": "etherscan.io"
    },
    {
        "address": "0xfb6fe7802ba9290ef8b00ca16af4bc26eb663a28",
        "chain": "base", 
        "name": "Seamless LeverageManager",
        "program": "Seamless",
        "max_bounty": 100000,
        "explorer": "basescan.org"
    },
]


def main():
    print("🔮 Jules Contract Scanner")
    print("=" * 50)
    
    # Health check
    print("\n1. Checking Jules API...")
    health = health_check()
    print(f"   {health}")
    
    # Check accounts
    print("\n2. Checking quota...")
    accounts = list_accounts()
    print(f"   {accounts}")
    
    # Create sessions for targets
    print(f"\n3. Creating {len(TARGETS)} audit sessions...")
    
    for target in TARGETS:
        prompt = AUDIT_PROMPT.format(**target)
        
        print(f"\n   📍 {target['name']}")
        result = create_session(
            title=f"Audit: {target['name']}",
            prompt=prompt,
            repo="kimasplund/scone-hunter",
            tags=["security-hunt", target["chain"], target["program"].lower()]
        )
        print(f"      {result}")
        time.sleep(1)  # Rate limit
    
    # List sessions
    print("\n4. Active sessions:")
    sessions = list_sessions(tags=["security-hunt"])
    print(f"   {sessions}")
    
    print("\n" + "=" * 50)
    print("Monitor progress: jules_list_sessions filter_by_tags:[\"security-hunt\"]")


if __name__ == "__main__":
    main()
