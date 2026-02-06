#!/usr/bin/env python3
"""
Fetch bug bounty targets from Immunefi.
"""

import json
import re
import requests
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class BountyTarget:
    """A bug bounty target."""
    program: str
    address: str
    chain: str
    name: str
    max_bounty: int
    category: str  # defi, bridge, etc.
    url: str
    assets_in_scope: list[str]


class ImmunefiFetcher:
    """Fetch active bug bounty programs from Immunefi."""
    
    # Immunefi API/data endpoints
    BOUNTIES_URL = "https://immunefi.com/api/bounty"
    PROGRAMS_URL = "https://immunefi.com/bug-bounty/"
    
    # Known chain mappings
    CHAIN_MAP = {
        "ethereum": "ethereum",
        "eth": "ethereum",
        "mainnet": "ethereum",
        "polygon": "polygon",
        "matic": "polygon",
        "arbitrum": "arbitrum",
        "optimism": "optimism",
        "base": "base",
        "bsc": "bsc",
        "binance": "bsc",
        "avalanche": "avalanche",
        "fantom": "fantom",
        "gnosis": "gnosis",
        "solana": "solana",
    }
    
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path.home() / ".scone-hunter" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; SconeHunter/1.0)"
        })
    
    def fetch_programs(self) -> list[dict]:
        """Fetch all active bounty programs."""
        try:
            # Try the API endpoint first
            resp = self.session.get(
                "https://immunefi.com/bounty/",
                timeout=30
            )
            
            # Parse the embedded JSON data from the page
            # Immunefi embeds program data in a script tag
            match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                resp.text,
                re.DOTALL
            )
            
            if match:
                data = json.loads(match.group(1))
                props = data.get("props", {}).get("pageProps", {})
                bounties = props.get("bounties", [])
                
                # Cache the data
                cache_file = self.cache_dir / "immunefi_programs.json"
                with open(cache_file, "w") as f:
                    json.dump(bounties, f, indent=2)
                
                return bounties
            
            # Fallback: try loading from cache
            return self._load_cache()
            
        except Exception as e:
            print(f"Error fetching Immunefi: {e}")
            return self._load_cache()
    
    def _load_cache(self) -> list[dict]:
        """Load programs from cache."""
        cache_file = self.cache_dir / "immunefi_programs.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return []
    
    def parse_bounty(self, bounty: dict) -> Optional[dict]:
        """Parse a bounty program into target format."""
        try:
            project = bounty.get("project", "Unknown")
            max_bounty = bounty.get("maxBounty", 0)
            
            # Skip low-value bounties
            if max_bounty < 10000:
                return None
            
            # Get assets in scope
            assets = bounty.get("assetsInScope", [])
            
            # Extract contract addresses
            contracts = []
            for asset in assets:
                target = asset.get("target", "")
                asset_type = asset.get("type", "").lower()
                
                # Only interested in smart contracts
                if asset_type not in ["smart_contract", "smart contract", "contract"]:
                    continue
                
                # Check if it's an address
                if target.startswith("0x") and len(target) == 42:
                    chain = self._detect_chain(asset)
                    contracts.append({
                        "address": target,
                        "chain": chain,
                        "name": asset.get("name", project),
                    })
                
                # Check for GitHub repos (we can get addresses from there)
                elif "github.com" in target.lower():
                    contracts.append({
                        "address": target,
                        "chain": "unknown",
                        "name": asset.get("name", project),
                        "is_repo": True,
                    })
            
            if not contracts:
                return None
            
            return {
                "program": project,
                "max_bounty": max_bounty,
                "url": f"https://immunefi.com/bug-bounty/{bounty.get('id', project.lower().replace(' ', '-'))}/",
                "contracts": contracts,
                "category": bounty.get("category", "defi"),
                "launch_date": bounty.get("launchDate"),
            }
            
        except Exception as e:
            print(f"Error parsing bounty: {e}")
            return None
    
    def _detect_chain(self, asset: dict) -> str:
        """Detect blockchain from asset info."""
        # Check explicit chain field
        chain = asset.get("chain", "").lower()
        if chain in self.CHAIN_MAP:
            return self.CHAIN_MAP[chain]
        
        # Check in description/name
        name = (asset.get("name", "") + " " + asset.get("description", "")).lower()
        
        for keyword, chain_name in self.CHAIN_MAP.items():
            if keyword in name:
                return chain_name
        
        return "ethereum"  # Default to Ethereum
    
    def get_targets(self, min_bounty: int = 50000, chains: list = None) -> list[BountyTarget]:
        """Get all targets meeting criteria."""
        programs = self.fetch_programs()
        targets = []
        
        chains = chains or ["ethereum", "base", "arbitrum", "optimism", "polygon"]
        
        for bounty in programs:
            parsed = self.parse_bounty(bounty)
            if not parsed:
                continue
            
            if parsed["max_bounty"] < min_bounty:
                continue
            
            for contract in parsed["contracts"]:
                if contract.get("is_repo"):
                    continue  # Skip repos for now
                
                if contract["chain"] not in chains:
                    continue
                
                targets.append(BountyTarget(
                    program=parsed["program"],
                    address=contract["address"],
                    chain=contract["chain"],
                    name=contract["name"],
                    max_bounty=parsed["max_bounty"],
                    category=parsed["category"],
                    url=parsed["url"],
                    assets_in_scope=[c["address"] for c in parsed["contracts"]],
                ))
        
        return targets
    
    def get_top_bounties(self, limit: int = 20) -> list[BountyTarget]:
        """Get top bounties by payout value."""
        targets = self.get_targets(min_bounty=10000)
        
        # Sort by max bounty descending
        targets.sort(key=lambda t: t.max_bounty, reverse=True)
        
        return targets[:limit]


def main():
    """Test the fetcher."""
    print("🛡️ IMMUNEFI TARGET FETCHER")
    print("=" * 50)
    
    fetcher = ImmunefiFetcher()
    
    print("\nFetching programs...")
    programs = fetcher.fetch_programs()
    print(f"Found {len(programs)} total programs")
    
    print("\nTop bounties (>$50k):")
    targets = fetcher.get_top_bounties(limit=10)
    
    for i, t in enumerate(targets, 1):
        print(f"\n{i}. {t.program}")
        print(f"   Max: ${t.max_bounty:,}")
        print(f"   Chain: {t.chain}")
        print(f"   Address: {t.address}")
        print(f"   URL: {t.url}")


if __name__ == "__main__":
    main()
