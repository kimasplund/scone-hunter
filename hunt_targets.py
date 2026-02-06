#!/usr/bin/env python3
"""Hunt high-value bug bounty targets."""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from scone_hunter.config import Config
from scone_hunter.deep_hunter import DeepHunter

# High-value targets with known contract addresses
TARGETS = [
    # Alchemix - $300k max, has paid $205k
    {
        "program": "Alchemix",
        "max_bounty": 300000,
        "chain": "ethereum",
        "contracts": [
            "0xdbdb4d16eda451d0503b854cf79d55697f90c8df",  # ALCX token
            "0x5C6374a2ac4EBC38DeA0Fc1F8716e5Ea1AdD94dd",  # Alchemist V2
            "0xa537e4d06f91F6b2C07875C6e0F16D5e4E1c68cE",  # Transmuter V2
        ]
    },
    # Inverse Finance - $100k max
    {
        "program": "Inverse Finance", 
        "max_bounty": 100000,
        "chain": "ethereum",
        "contracts": [
            "0x1637e4e9941D55703a7A5E7807d6aDA3f7DCD61B",  # INV token
            "0x4dCf7407AE5C07f8681e1659f626E114A7667339",  # Anchor
        ]
    },
    # Base chain targets - newer, potentially less audited
    {
        "program": "Base Ecosystem",
        "max_bounty": 50000,
        "chain": "base",
        "contracts": [
            "0x4200000000000000000000000000000000000006",  # WETH on Base
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
        ]
    },
]


async def hunt_all():
    """Hunt all targets and save results."""
    config = Config()
    hunter = DeepHunter(config)
    
    results = []
    findings_dir = Path.home() / ".scone-hunter" / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"🎯 SCONE HUNTER - DEEP HUNT MODE")
    print(f"Target: €25,000 by next week")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    total_contracts = sum(len(t["contracts"]) for t in TARGETS)
    scanned = 0
    
    for target in TARGETS:
        print(f"\n📍 {target['program']} (${target['max_bounty']:,} max)")
        print(f"   Chain: {target['chain']}")
        
        for addr in target["contracts"]:
            scanned += 1
            print(f"\n   [{scanned}/{total_contracts}] Hunting {addr[:10]}...")
            
            try:
                result = await hunter.hunt(
                    address=addr,
                    chain=target["chain"],
                    bounty_program=target["program"],
                    max_bounty=target["max_bounty"],
                )
                
                findings = {
                    "address": addr,
                    "chain": target["chain"],
                    "program": target["program"],
                    "max_bounty": target["max_bounty"],
                    "attacks": result.high_confidence_attacks,
                    "consensus": result.confirmed_vulns,
                    "time": result.analysis_time,
                    "timestamp": datetime.now().isoformat(),
                }
                
                results.append(findings)
                
                if result.high_confidence_attacks:
                    print(f"   ⚠️  {len(result.high_confidence_attacks)} ATTACKS FOUND!")
                    for atk in result.high_confidence_attacks[:2]:
                        print(f"      → {atk.get('name')}: {atk.get('confidence_percent')}% conf")
                else:
                    print(f"   ✓ Clean ({result.analysis_time:.1f}s)")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = findings_dir / f"hunt_{timestamp}.json"
    
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Hunt complete! Results saved to: {results_file}")
    
    # Summary
    total_attacks = sum(len(r["attacks"]) for r in results)
    if total_attacks > 0:
        print(f"\n🎯 FINDINGS SUMMARY:")
        for r in results:
            if r["attacks"]:
                print(f"   {r['program']} ({r['address'][:10]}...)")
                print(f"      {len(r['attacks'])} attacks, bounty up to ${r['max_bounty']:,}")
    else:
        print(f"\n😔 No high-confidence attacks found in this batch.")
        print(f"   Consider: expanding targets, deeper analysis, or manual review")
    
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(hunt_all())
