#!/usr/bin/env python3
"""
Fetch high-TVL protocols from DeFiLlama.
"""

import json
import requests
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class ProtocolTarget:
    """A DeFi protocol target."""
    name: str
    slug: str
    tvl: float
    chain: str
    category: str
    address: Optional[str]
    url: str
    github: Optional[str]


class DefiLlamaFetcher:
    """Fetch top TVL protocols from DeFiLlama."""
    
    API_BASE = "https://api.llama.fi"
    
    # Chain slug mapping
    CHAIN_MAP = {
        "ethereum": "ethereum",
        "bsc": "bsc",
        "polygon": "polygon",
        "arbitrum": "arbitrum",
        "optimism": "optimism",
        "base": "base",
        "avalanche": "avalanche",
        "fantom": "fantom",
        "gnosis": "gnosis",
        "solana": "solana",
    }
    
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path.home() / ".scone-hunter" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
    
    def fetch_protocols(self) -> list[dict]:
        """Fetch all protocols from DeFiLlama."""
        try:
            resp = self.session.get(
                f"{self.API_BASE}/protocols",
                timeout=30
            )
            resp.raise_for_status()
            
            protocols = resp.json()
            
            # Cache
            cache_file = self.cache_dir / "defillama_protocols.json"
            with open(cache_file, "w") as f:
                json.dump(protocols, f, indent=2)
            
            return protocols
            
        except Exception as e:
            print(f"Error fetching DeFiLlama: {e}")
            return self._load_cache()
    
    def _load_cache(self) -> list[dict]:
        """Load from cache."""
        cache_file = self.cache_dir / "defillama_protocols.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return []
    
    def fetch_protocol_details(self, slug: str) -> Optional[dict]:
        """Fetch detailed info for a specific protocol."""
        try:
            resp = self.session.get(
                f"{self.API_BASE}/protocol/{slug}",
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Error fetching protocol {slug}: {e}")
            return None
    
    def get_top_by_chain(self, chain: str, limit: int = 20) -> list[ProtocolTarget]:
        """Get top protocols by TVL for a specific chain."""
        protocols = self.fetch_protocols()
        targets = []
        
        chain_lower = chain.lower()
        
        for p in protocols:
            # Check if protocol is on this chain
            chains = p.get("chains", [])
            chain_tvls = p.get("chainTvls", {})
            
            # Normalize chain names
            chain_match = None
            for c in chains:
                if c.lower() == chain_lower:
                    chain_match = c
                    break
            
            if not chain_match:
                continue
            
            # Get TVL for this chain
            tvl = chain_tvls.get(chain_match) or 0
            if tvl < 1_000_000:  # Skip <$1M TVL
                continue
            
            # Get address if available
            address = None
            if "address" in p:
                addr = p["address"]
                if isinstance(addr, dict):
                    address = addr.get(chain_lower) or addr.get(chain_match)
                elif isinstance(addr, str) and addr.startswith("0x"):
                    address = addr
            
            targets.append(ProtocolTarget(
                name=p.get("name", "Unknown"),
                slug=p.get("slug", ""),
                tvl=tvl,
                chain=chain_lower,
                category=p.get("category", ""),
                address=address,
                url=p.get("url", ""),
                github=p.get("github"),
            ))
        
        # Sort by TVL descending
        targets.sort(key=lambda t: t.tvl, reverse=True)
        
        return targets[:limit]
    
    def get_top_overall(self, limit: int = 50, chains: list = None) -> list[ProtocolTarget]:
        """Get top protocols overall, optionally filtered by chains."""
        protocols = self.fetch_protocols()
        targets = []
        
        chains = chains or ["ethereum", "base", "arbitrum", "optimism", "polygon"]
        chains_lower = [c.lower() for c in chains]
        
        for p in protocols:
            total_tvl = p.get("tvl") or 0
            if total_tvl < 10_000_000:  # Skip <$10M TVL
                continue
            
            # Get chains this protocol is on
            protocol_chains = [c.lower() for c in p.get("chains", [])]
            
            # Filter to our target chains
            matching_chains = [c for c in protocol_chains if c in chains_lower]
            if not matching_chains:
                continue
            
            # Get address
            address = None
            primary_chain = matching_chains[0]
            
            if "address" in p:
                addr = p["address"]
                if isinstance(addr, dict):
                    address = addr.get(primary_chain)
                elif isinstance(addr, str) and addr.startswith("0x"):
                    address = addr
            
            targets.append(ProtocolTarget(
                name=p.get("name", "Unknown"),
                slug=p.get("slug", ""),
                tvl=total_tvl,
                chain=primary_chain,
                category=p.get("category", ""),
                address=address,
                url=p.get("url", ""),
                github=p.get("github"),
            ))
        
        # Sort by TVL
        targets.sort(key=lambda t: t.tvl, reverse=True)
        
        return targets[:limit]
    
    def get_new_protocols(self, days: int = 30, min_tvl: int = 5_000_000) -> list[ProtocolTarget]:
        """Get recently launched protocols (potentially less audited)."""
        # DeFiLlama doesn't have a direct "new protocols" endpoint
        # We'd need to track protocol list changes over time
        # For now, return empty - this would be a TODO
        return []
    
    def enrich_with_contracts(self, target: ProtocolTarget) -> list[str]:
        """Try to find contract addresses for a protocol."""
        if target.address:
            return [target.address]
        
        # Fetch detailed protocol info
        details = self.fetch_protocol_details(target.slug)
        if not details:
            return []
        
        addresses = []
        
        # Check for addresses in various fields
        if "address" in details:
            addr = details["address"]
            if isinstance(addr, dict):
                for chain_addr in addr.values():
                    if isinstance(chain_addr, str) and chain_addr.startswith("0x"):
                        addresses.append(chain_addr)
            elif isinstance(addr, str) and addr.startswith("0x"):
                addresses.append(addr)
        
        # Check currentChainTvls for contract addresses
        chain_tvls = details.get("currentChainTvls", {})
        for key, value in chain_tvls.items():
            if key.startswith("0x") and len(key) == 42:
                addresses.append(key)
        
        return list(set(addresses))


def main():
    """Test the fetcher."""
    print("📊 DEFILLAMA TARGET FETCHER")
    print("=" * 50)
    
    fetcher = DefiLlamaFetcher()
    
    print("\nFetching protocols...")
    protocols = fetcher.fetch_protocols()
    print(f"Found {len(protocols)} total protocols")
    
    print("\nTop 10 on Base:")
    base_targets = fetcher.get_top_by_chain("base", limit=10)
    
    for i, t in enumerate(base_targets, 1):
        print(f"\n{i}. {t.name}")
        print(f"   TVL: ${t.tvl/1e6:.1f}M")
        print(f"   Category: {t.category}")
        print(f"   Address: {t.address or 'N/A'}")
    
    print("\n" + "=" * 50)
    print("\nTop 10 overall:")
    top_targets = fetcher.get_top_overall(limit=10)
    
    for i, t in enumerate(top_targets, 1):
        print(f"\n{i}. {t.name} ({t.chain})")
        print(f"   TVL: ${t.tvl/1e6:.1f}M")
        print(f"   Address: {t.address or 'N/A'}")


if __name__ == "__main__":
    main()
