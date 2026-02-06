#!/usr/bin/env python3
"""
Aggregate and prioritize targets from multiple sources.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .immunefi import ImmunefiFetcher, BountyTarget
from .defillama import DefiLlamaFetcher, ProtocolTarget


@dataclass
class ScanTarget:
    """A prioritized scan target."""
    address: str
    chain: str
    name: str
    program: Optional[str]  # Bug bounty program if any
    max_bounty: int
    tvl: float  # TVL in USD
    priority_score: float  # Higher = scan first
    source: str  # "immunefi", "defillama", "manual"
    category: str
    url: Optional[str] = None
    last_scanned: Optional[str] = None


class TargetAggregator:
    """Aggregate targets from multiple sources and prioritize."""
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path.home() / ".scone-hunter"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.targets_file = self.data_dir / "targets.json"
        self.scanned_file = self.data_dir / "scanned.json"
        
        self.immunefi = ImmunefiFetcher(cache_dir=self.data_dir / "cache")
        self.defillama = DefiLlamaFetcher(cache_dir=self.data_dir / "cache")
        
        self._load_state()
    
    def _load_state(self):
        """Load existing targets and scan history."""
        self.targets = {}
        self.scanned = {}
        
        if self.targets_file.exists():
            with open(self.targets_file) as f:
                data = json.load(f)
                for t in data:
                    key = f"{t['chain']}:{t['address'].lower()}"
                    self.targets[key] = ScanTarget(**t)
        
        if self.scanned_file.exists():
            with open(self.scanned_file) as f:
                self.scanned = json.load(f)
    
    def _save_state(self):
        """Save targets and scan history."""
        targets_list = [asdict(t) for t in self.targets.values()]
        with open(self.targets_file, "w") as f:
            json.dump(targets_list, f, indent=2)
        
        with open(self.scanned_file, "w") as f:
            json.dump(self.scanned, f, indent=2)
    
    def _calculate_priority(
        self,
        max_bounty: int,
        tvl: float,
        has_bounty: bool,
        chain: str,
    ) -> float:
        """Calculate priority score for a target."""
        score = 0.0
        
        # Bounty value (up to 40 points)
        if max_bounty > 0:
            # Log scale: $10k=10, $100k=20, $1M=30, $10M=40
            import math
            score += min(40, 10 * math.log10(max_bounty / 1000 + 1))
        
        # TVL (up to 30 points)
        if tvl > 0:
            # Log scale: $1M=10, $10M=15, $100M=20, $1B=25, $10B=30
            import math
            score += min(30, 5 * math.log10(tvl / 100_000 + 1))
        
        # Bug bounty bonus (20 points)
        if has_bounty:
            score += 20
        
        # Chain preference (up to 10 points)
        chain_scores = {
            "ethereum": 10,
            "base": 9,  # Newer, potentially less audited
            "arbitrum": 8,
            "optimism": 7,
            "polygon": 6,
            "bsc": 5,
        }
        score += chain_scores.get(chain, 3)
        
        return round(score, 2)
    
    def refresh_immunefi(self, min_bounty: int = 25000) -> int:
        """Refresh targets from Immunefi."""
        print("Fetching Immunefi targets...")
        targets = self.immunefi.get_targets(min_bounty=min_bounty)
        
        added = 0
        for t in targets:
            key = f"{t.chain}:{t.address.lower()}"
            
            if key in self.targets:
                # Update bounty info
                self.targets[key].max_bounty = max(self.targets[key].max_bounty, t.max_bounty)
                self.targets[key].program = t.program
            else:
                # New target
                self.targets[key] = ScanTarget(
                    address=t.address,
                    chain=t.chain,
                    name=t.name,
                    program=t.program,
                    max_bounty=t.max_bounty,
                    tvl=0,  # Will be enriched from DeFiLlama
                    priority_score=self._calculate_priority(
                        t.max_bounty, 0, True, t.chain
                    ),
                    source="immunefi",
                    category=t.category,
                    url=t.url,
                )
                added += 1
        
        print(f"  Added {added} new targets from Immunefi")
        return added
    
    def refresh_defillama(
        self,
        chains: list = None,
        min_tvl: int = 10_000_000,
        limit: int = 100,
    ) -> int:
        """Refresh targets from DeFiLlama."""
        print("Fetching DeFiLlama targets...")
        chains = chains or ["ethereum", "base", "arbitrum", "optimism"]
        
        targets = self.defillama.get_top_overall(limit=limit, chains=chains)
        
        added = 0
        for t in targets:
            if not t.address:
                continue
            
            if t.tvl < min_tvl:
                continue
            
            key = f"{t.chain}:{t.address.lower()}"
            
            if key in self.targets:
                # Update TVL
                self.targets[key].tvl = t.tvl
                # Recalculate priority
                self.targets[key].priority_score = self._calculate_priority(
                    self.targets[key].max_bounty,
                    t.tvl,
                    bool(self.targets[key].program),
                    t.chain,
                )
            else:
                # New target (no bounty program known)
                self.targets[key] = ScanTarget(
                    address=t.address,
                    chain=t.chain,
                    name=t.name,
                    program=None,
                    max_bounty=0,
                    tvl=t.tvl,
                    priority_score=self._calculate_priority(
                        0, t.tvl, False, t.chain
                    ),
                    source="defillama",
                    category=t.category,
                    url=t.url,
                )
                added += 1
        
        print(f"  Added {added} new targets from DeFiLlama")
        return added
    
    def refresh_all(self) -> dict:
        """Refresh from all sources."""
        results = {
            "immunefi": self.refresh_immunefi(),
            "defillama": self.refresh_defillama(),
            "total_targets": len(self.targets),
        }
        
        self._save_state()
        return results
    
    def add_manual_target(
        self,
        address: str,
        chain: str,
        name: str,
        program: str = None,
        max_bounty: int = 0,
    ):
        """Add a manual target."""
        key = f"{chain}:{address.lower()}"
        
        self.targets[key] = ScanTarget(
            address=address,
            chain=chain,
            name=name,
            program=program,
            max_bounty=max_bounty,
            tvl=0,
            priority_score=self._calculate_priority(max_bounty, 0, bool(program), chain),
            source="manual",
            category="manual",
        )
        
        self._save_state()
    
    def mark_scanned(self, address: str, chain: str, session_id: str = None):
        """Mark a target as scanned."""
        key = f"{chain}:{address.lower()}"
        
        self.scanned[key] = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
        }
        
        if key in self.targets:
            self.targets[key].last_scanned = datetime.now().isoformat()
        
        self._save_state()
    
    def get_unscanned(self, limit: int = 100, days_since_scan: int = 7) -> list[ScanTarget]:
        """Get unscanned targets, prioritized."""
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(days=days_since_scan)
        
        unscanned = []
        for key, target in self.targets.items():
            # Check if recently scanned
            if key in self.scanned:
                scan_time = datetime.fromisoformat(self.scanned[key]["timestamp"])
                if scan_time > cutoff:
                    continue
            
            unscanned.append(target)
        
        # Sort by priority
        unscanned.sort(key=lambda t: t.priority_score, reverse=True)
        
        return unscanned[:limit]
    
    def get_batch_for_jules(self, batch_size: int = 10) -> list[dict]:
        """Get a batch of targets formatted for Jules scanner."""
        targets = self.get_unscanned(limit=batch_size)
        
        return [
            {
                "address": t.address,
                "chain": t.chain,
                "name": t.name,
                "program": t.program or "Unknown",
                "max_bounty": t.max_bounty or 50000,  # Default bounty estimate
            }
            for t in targets
        ]
    
    def get_stats(self) -> dict:
        """Get aggregator statistics."""
        by_chain = {}
        by_source = {}
        with_bounty = 0
        total_bounty_value = 0
        total_tvl = 0
        
        for t in self.targets.values():
            by_chain[t.chain] = by_chain.get(t.chain, 0) + 1
            by_source[t.source] = by_source.get(t.source, 0) + 1
            
            if t.program:
                with_bounty += 1
            
            total_bounty_value += t.max_bounty
            total_tvl += t.tvl
        
        return {
            "total_targets": len(self.targets),
            "scanned_count": len(self.scanned),
            "with_bounty_program": with_bounty,
            "total_bounty_value": total_bounty_value,
            "total_tvl": total_tvl,
            "by_chain": by_chain,
            "by_source": by_source,
        }


def main():
    """Test the aggregator."""
    print("🎯 TARGET AGGREGATOR")
    print("=" * 50)
    
    agg = TargetAggregator()
    
    print("\nRefreshing all sources...")
    results = agg.refresh_all()
    print(f"\nResults: {results}")
    
    print("\nStats:")
    stats = agg.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    print("\nTop 10 unscanned targets:")
    targets = agg.get_unscanned(limit=10)
    
    for i, t in enumerate(targets, 1):
        bounty = f"${t.max_bounty:,}" if t.max_bounty else "No bounty"
        tvl = f"${t.tvl/1e6:.1f}M TVL" if t.tvl else ""
        print(f"\n{i}. {t.name} ({t.chain})")
        print(f"   Priority: {t.priority_score}")
        print(f"   {bounty} | {tvl}")
        print(f"   Address: {t.address}")
    
    print("\n" + "=" * 50)
    print("\nBatch for Jules:")
    batch = agg.get_batch_for_jules(batch_size=5)
    for t in batch:
        print(f"  • {t['name']} ({t['chain']}) - {t['program']}")


if __name__ == "__main__":
    main()
