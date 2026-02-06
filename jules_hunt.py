#!/usr/bin/env python3
"""
Jules-powered contract hunting with cognitive enhancement.

Spawns parallel Jules sessions to analyze contracts using our cognitive patterns.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Cognitive-enhanced prompt template
HUNT_PROMPT_TEMPLATE = """
# Security Audit Task: {contract_name}

## Contract Details
- **Address**: {address}
- **Chain**: {chain}
- **Bounty Program**: {bounty_program}
- **Max Bounty**: ${max_bounty:,}

## Your Mission

You are a security researcher hunting for exploitable vulnerabilities.
Apply these cognitive patterns IN ORDER:

### Phase 1: HYPOTHESIS ELIMINATION
Generate 5+ hypotheses about potential vulnerabilities, then systematically test each.

### Phase 2: ADVERSARIAL REASONING  
Think like an attacker:
- "With $100M flash loan, how would I exploit this?"
- "What happens at edge cases (0, max_uint)?"
- "Can I front-run anything profitable?"

### Phase 3: VERIFICATION
For each finding:
1. Check if admin is multisig (→ probably protected)
2. Verify exploit actually works on mainnet fork
3. Calculate real profit after gas

## Deliverables

Create these files:

1. `audit/{contract_name}/FINDINGS.md` - All vulnerabilities found
2. `audit/{contract_name}/poc/` - Foundry PoC tests for each real bug
3. `audit/{contract_name}/FALSE_POSITIVES.md` - Patterns that LOOK vulnerable but aren't

## Anti-Patterns (Don't Report These)

- Multisig-protected admin functions
- Standard ERC20 patterns
- Theoretical overflows in Solidity 0.8+
- Properly timelocked governance

## Success = Bounty

Only report bugs that:
- Are exploitable without admin keys
- Have profit > gas cost
- Pass a Foundry fork test
- Score >70% confidence

Start by fetching the contract source from Etherscan and analyzing it.
"""


class JulesHunter:
    """Spawn and manage Jules sessions for contract hunting."""
    
    def __init__(self):
        self.api_key = os.environ.get("JULES_API_KEY")
        if not self.api_key:
            raise ValueError("JULES_API_KEY not set")
    
    async def spawn_hunt_session(
        self,
        address: str,
        chain: str,
        contract_name: str,
        bounty_program: str,
        max_bounty: int,
        repo: str = "kimasplund/scone-hunter",
    ) -> dict:
        """Create a Jules session for hunting a specific contract."""
        
        prompt = HUNT_PROMPT_TEMPLATE.format(
            address=address,
            chain=chain,
            contract_name=contract_name,
            bounty_program=bounty_program,
            max_bounty=max_bounty,
        )
        
        # Jules session config
        session_config = {
            "title": f"Hunt: {contract_name} ({chain})",
            "prompt": prompt,
            "source": f"sources/github/{repo}",
            "starting_branch": "master",
            "require_plan_approval": False,  # Let it run autonomously
            "automation_mode": "AUTO_CREATE_PR",
            "tags": ["security-hunt", chain, bounty_program.lower().replace(" ", "-")],
        }
        
        return session_config
    
    async def spawn_batch(self, targets: list[dict]) -> list[dict]:
        """Spawn multiple hunting sessions."""
        sessions = []
        
        for target in targets:
            config = await self.spawn_hunt_session(
                address=target["address"],
                chain=target["chain"],
                contract_name=target["name"],
                bounty_program=target["program"],
                max_bounty=target["max_bounty"],
            )
            sessions.append(config)
            print(f"✓ Prepared: {target['name']} on {target['chain']}")
        
        return sessions


# High-value targets for hunting
TARGETS = [
    # Newer protocols on Base - less audited
    {
        "address": "0x2ae3f1ec7f1f5012cfef5f49f88ae24e24ef3f8f",
        "chain": "base",
        "name": "BaseSwap Router",
        "program": "Base Ecosystem",
        "max_bounty": 50000,
    },
    {
        "address": "0xfb6fe7802ba9290ef8b00ca16af4bc26eb663a28", 
        "chain": "base",
        "name": "Seamless Protocol",
        "program": "Seamless",
        "max_bounty": 100000,
    },
    # Fresh Ethereum deployments
    {
        "address": "0x1111111254eeb25477b68fb85ed929f73a960582",
        "chain": "ethereum",
        "name": "1inch Router v5",
        "program": "1inch",
        "max_bounty": 250000,
    },
]


async def main():
    """Main entry point."""
    print("=" * 60)
    print("🎯 JULES COGNITIVE HUNTER")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)
    
    hunter = JulesHunter()
    
    print(f"\nPreparing {len(TARGETS)} hunting sessions...\n")
    sessions = await hunter.spawn_batch(TARGETS)
    
    # Output sessions for manual creation via MCP
    output_file = Path.home() / ".scone-hunter" / "jules_sessions.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(sessions, f, indent=2)
    
    print(f"\n✅ Session configs saved to: {output_file}")
    print("\nTo spawn via MCP, use these configs with jules_create_session")
    
    # Print summary
    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("1. Start Jules MCP server: jules-mcp-server")
    print("2. Create sessions using the saved configs")
    print("3. Monitor: jules_list_sessions filter_by_tags:[\"security-hunt\"]")
    print("4. Extract PRs when COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
