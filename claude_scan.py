#!/usr/bin/env python3
"""
Smart contract scanner using Claude subagents instead of Jules.
Spawns parallel analysis sessions for each contract.
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from scone_hunter.discovery import TargetAggregator


def fetch_contract_source(address: str, chain: str) -> str:
    """Fetch verified source code from block explorer."""
    explorers = {
        "ethereum": "https://api.etherscan.io/api",
        "base": "https://api.basescan.org/api",
        "arbitrum": "https://api.arbiscan.io/api",
        "optimism": "https://api-optimistic.etherscan.io/api",
        "polygon": "https://api.polygonscan.com/api",
    }
    
    api_url = explorers.get(chain, explorers["ethereum"])
    
    # Try to fetch source (requires API key for some explorers)
    import requests
    try:
        resp = requests.get(
            api_url,
            params={
                "module": "contract",
                "action": "getsourcecode",
                "address": address,
            },
            timeout=30
        )
        data = resp.json()
        if data.get("status") == "1" and data.get("result"):
            result = data["result"][0]
            source = result.get("SourceCode", "")
            name = result.get("ContractName", "Unknown")
            return source, name
    except Exception as e:
        print(f"      Failed to fetch source: {e}")
    
    return None, None


def create_audit_task(target: dict) -> str:
    """Create the audit task prompt for a Claude subagent."""
    return f"""
## Smart Contract Security Audit

**Target:** {target['name']}
**Address:** {target['address']}
**Chain:** {target['chain']}
**Bounty Program:** {target.get('program', 'Unknown')}
**Max Bounty:** ${target.get('max_bounty', 50000):,}

### Instructions

1. Fetch the verified source code from the block explorer:
   - Ethereum: https://etherscan.io/address/{target['address']}#code
   - Base: https://basescan.org/address/{target['address']}#code
   
2. Analyze the contract for these vulnerability classes:
   - **Reentrancy:** External calls before state changes
   - **Access Control:** Unprotected admin functions, missing modifiers
   - **Flash Loan Attacks:** Price oracle manipulation, single-tx exploits
   - **Integer Issues:** Overflow/underflow (especially pre-0.8.0)
   - **Logic Bugs:** Edge cases, rounding errors, off-by-one
   - **Centralization Risks:** Admin can rug (unless timelock protected)

3. For each potential finding, assess:
   - Is it actually exploitable?
   - What's the confidence level (0-100%)?
   - What's the estimated profit vs gas cost?
   - Is admin protected by timelock/multisig? (if yes, skip)

4. Report format:
   ```
   ## Finding: [Title]
   - Severity: Critical/High/Medium/Low
   - Confidence: X%
   - Location: Contract.sol line X
   - Description: What's wrong
   - Exploit: Step-by-step attack
   - Impact: Estimated loss/profit
   ```

### Rules
- Only report findings with >70% confidence
- Skip theoretical issues that aren't practically exploitable
- Skip if admin is timelock/multisig protected
- Focus on REAL bugs that could win bounties

### Output
Provide a complete security assessment. If no vulnerabilities found, explain why the contract appears secure.
"""


def spawn_audit(target: dict) -> dict:
    """Spawn a Claude subagent to audit a contract."""
    task = create_audit_task(target)
    
    # Use clawdbot CLI to spawn
    result = subprocess.run(
        [
            "clawdbot", "session", "spawn",
            "--task", task,
            "--label", f"audit-{target['chain']}-{target['address'][:10]}",
            "--timeout", "300",  # 5 min per contract
        ],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    return {
        "target": target,
        "spawned": result.returncode == 0,
        "output": result.stdout[:500] if result.stdout else result.stderr[:500]
    }


def main():
    print(f"🔍 CLAUDE SUBAGENT SCANNER")
    print(f"   Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    agg = TargetAggregator()
    
    # Refresh targets
    print("\n1️⃣ REFRESHING TARGETS")
    results = agg.refresh_all()
    print(f"   Pool: {results['total_targets']} targets")
    
    # Get top unscanned targets
    print("\n2️⃣ SELECTING TARGETS")
    targets = agg.get_batch_for_jules(batch_size=5)  # Start with 5
    print(f"   Selected: {len(targets)} contracts")
    
    if not targets:
        print("   No targets available!")
        return
    
    # Spawn subagents
    print("\n3️⃣ SPAWNING AUDITS")
    print("-" * 40)
    
    spawned = []
    for t in targets:
        print(f"\n   📍 {t['name']} ({t['chain']})")
        print(f"      Address: {t['address'][:20]}...")
        print(f"      Bounty: ${t.get('max_bounty', 0):,}")
        
        result = spawn_audit(t)
        spawned.append(result)
        
        if result["spawned"]:
            print(f"      ✓ Subagent spawned")
        else:
            print(f"      ✗ Failed: {result['output'][:100]}")
        
        # Mark as scanned
        agg.mark_scanned(t['address'], t['chain'])
    
    # Summary
    success = sum(1 for s in spawned if s["spawned"])
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print(f"   Targets selected: {len(targets)}")
    print(f"   Audits spawned: {success}")
    print(f"   Failed: {len(targets) - success}")
    print("=" * 60)
    
    print("\n⏰ Subagents will report back when complete (~5 min each)")
    print("   Check main session for results")


if __name__ == "__main__":
    main()
