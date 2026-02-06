#!/usr/bin/env python3
"""
Discover and prioritize smart contract targets for scanning.
Run daily to keep target pool fresh.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from scone_hunter.discovery import TargetAggregator


def main():
    print(f"🔍 SCONE HUNTER - TARGET DISCOVERY")
    print(f"   Time: {datetime.now().isoformat()}")
    print("=" * 50)
    
    agg = TargetAggregator()
    
    # Refresh from all sources
    print("\n📡 Refreshing target sources...")
    results = agg.refresh_all()
    
    print(f"\n   Immunefi: +{results['immunefi']} new")
    print(f"   DeFiLlama: +{results['defillama']} new")
    print(f"   Total pool: {results['total_targets']} targets")
    
    # Get stats
    stats = agg.get_stats()
    
    print("\n📊 Pool Statistics:")
    print(f"   With bounty program: {stats['with_bounty_program']}")
    print(f"   Total bounty value: ${stats['total_bounty_value']:,}")
    print(f"   Total TVL tracked: ${stats['total_tvl']/1e9:.1f}B")
    print(f"   Already scanned: {stats['scanned_count']}")
    
    print("\n   By Chain:")
    for chain, count in sorted(stats['by_chain'].items(), key=lambda x: -x[1]):
        print(f"      {chain}: {count}")
    
    # Show top unscanned
    print("\n🎯 Top 10 Priority Targets (unscanned):")
    targets = agg.get_unscanned(limit=10)
    
    for i, t in enumerate(targets, 1):
        bounty = f"${t.max_bounty:,}" if t.max_bounty else "No bounty"
        tvl = f"${t.tvl/1e6:.0f}M" if t.tvl else ""
        program = f"[{t.program}]" if t.program else ""
        
        print(f"\n   {i}. {t.name} ({t.chain}) {program}")
        print(f"      Score: {t.priority_score} | {bounty} | {tvl}")
        print(f"      {t.address}")
    
    # Generate batch for immediate scanning
    batch = agg.get_batch_for_jules(batch_size=20)
    
    # Save batch for the scanner
    batch_file = Path.home() / ".scone-hunter" / "next_batch.json"
    with open(batch_file, "w") as f:
        json.dump(batch, f, indent=2)
    
    print(f"\n✅ Next batch ({len(batch)} targets) saved to: {batch_file}")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()
