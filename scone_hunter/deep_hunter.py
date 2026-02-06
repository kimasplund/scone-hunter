"""Deep hunting mode with multi-model consensus and adversarial reasoning."""

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

from .analyzer import Analyzer, ANALYSIS_PROMPT
from .config import Config
from .models import AnalysisResult, Severity, Vulnerability, VulnType
from .notifier import Notifier


ADVERSARIAL_PROMPT = """You are an adversarial security researcher trying to BREAK this contract and steal funds.

CONTRACT: {address} on {chain}

SOURCE CODE:
```solidity
{source_code}
```

Think like an attacker. Consider:

1. **Flash Loan Attacks**: Can I borrow massive amounts and manipulate state?
2. **Sandwich Attacks**: Can I front-run/back-run user transactions?
3. **Oracle Manipulation**: Can I manipulate price feeds to my advantage?
4. **Governance Attacks**: Can I exploit voting or admin functions?
5. **Cross-Function Reentrancy**: Can I re-enter through a different function?
6. **Token Approval Exploits**: Can I drain approved tokens?
7. **Precision Loss**: Can rounding errors accumulate in my favor?
8. **Timestamp Manipulation**: Can miners influence timing-based logic?
9. **Denial of Service**: Can I brick the contract or lock funds?
10. **Access Control Bypass**: Can I call privileged functions?

For EACH potential attack vector:
- Describe the exact steps to exploit
- Estimate stolen amount potential
- Rate confidence (0-100%)

Return JSON:
{{
    "attack_vectors": [
        {{
            "name": "attack name",
            "type": "flash_loan|sandwich|oracle|governance|reentrancy|approval|precision|timestamp|dos|access_control|other",
            "steps": ["step 1", "step 2", ...],
            "exploit_code_sketch": "pseudo-solidity or description",
            "estimated_profit_usd": 0,
            "confidence_percent": 0,
            "difficulty": "trivial|easy|medium|hard|expert"
        }}
    ],
    "highest_value_attack": "name of best attack",
    "overall_exploitability": "none|low|medium|high|critical"
}}

Be creative but realistic. Only include attacks you're >50% confident about.
"""


@dataclass
class HuntResult:
    """Result from deep hunting analysis."""
    contract_address: str
    chain: str
    source_code: str
    
    # Multi-model results
    openai_result: Optional[AnalysisResult] = None
    gemini_result: Optional[str] = None
    adversarial_result: Optional[dict] = None
    
    # Consensus
    confirmed_vulns: list = field(default_factory=list)
    high_confidence_attacks: list = field(default_factory=list)
    
    # Meta
    analysis_time: float = 0.0
    bounty_program: Optional[str] = None
    max_bounty_usd: int = 0


class DeepHunter:
    """Multi-model deep analysis for bug bounties."""
    
    def __init__(self, config: Config):
        self.config = config
        self.analyzer = Analyzer(config)
        self.notifier = Notifier(config)
    
    async def hunt(
        self,
        address: str,
        chain: str = "ethereum",
        source_code: Optional[str] = None,
        bounty_program: Optional[str] = None,
        max_bounty: int = 0,
    ) -> HuntResult:
        """Run deep multi-model analysis on a contract."""
        start_time = time.time()
        
        result = HuntResult(
            contract_address=address,
            chain=chain,
            source_code=source_code or "",
            bounty_program=bounty_program,
            max_bounty_usd=max_bounty,
        )
        
        # Fetch source if not provided
        if not source_code:
            source_code = await self.analyzer._fetch_source_code(address, chain)
            result.source_code = source_code or ""
        
        if not source_code:
            return result
        
        # Run analyses in parallel
        tasks = [
            self._run_openai_analysis(address, chain, source_code),
            self._run_gemini_analysis(address, chain, source_code),
            self._run_adversarial_analysis(address, chain, source_code),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        result.openai_result = results[0] if not isinstance(results[0], Exception) else None
        result.gemini_result = results[1] if not isinstance(results[1], Exception) else None
        result.adversarial_result = results[2] if not isinstance(results[2], Exception) else None
        
        # Find consensus vulnerabilities
        result.confirmed_vulns = self._find_consensus(result)
        result.high_confidence_attacks = self._extract_attacks(result)
        
        result.analysis_time = time.time() - start_time
        
        # Alert if we found something juicy
        if result.high_confidence_attacks:
            await self._send_hunt_alert(result)
        
        return result
    
    async def _run_openai_analysis(
        self, address: str, chain: str, source_code: str
    ) -> AnalysisResult:
        """Standard OpenAI analysis."""
        return await self.analyzer.analyze_contract(
            address=address,
            chain=chain,
            depth="deep",
            source_code=source_code,
        )
    
    async def _run_gemini_analysis(
        self, address: str, chain: str, source_code: str
    ) -> str:
        """Run analysis via Gemini CLI."""
        prompt = ANALYSIS_PROMPT.format(
            address=address,
            chain=chain,
            source_code=source_code[:50000],
            context="",
        )
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "gemini", "-p", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            return stdout.decode() if proc.returncode == 0 else stderr.decode()
        except Exception as e:
            return f"Gemini error: {e}"
    
    async def _run_adversarial_analysis(
        self, address: str, chain: str, source_code: str
    ) -> dict:
        """Run adversarial attack-focused analysis."""
        import openai
        
        prompt = ADVERSARIAL_PROMPT.format(
            address=address,
            chain=chain,
            source_code=source_code[:80000],
        )
        
        client = openai.OpenAI(api_key=self.config.openai_api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        
        text = response.choices[0].message.content
        
        # Parse JSON
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except:
            pass
        
        return {"attack_vectors": [], "error": "Failed to parse"}
    
    def _find_consensus(self, result: HuntResult) -> list:
        """Find vulnerabilities confirmed by multiple models."""
        vulns = []
        
        # Get OpenAI vulns
        openai_vulns = set()
        if result.openai_result and result.openai_result.vulnerabilities:
            for v in result.openai_result.vulnerabilities:
                openai_vulns.add(v.vuln_type.value)
        
        # Check Gemini for same issues
        gemini_text = (result.gemini_result or "").lower()
        
        consensus_types = []
        for vtype in openai_vulns:
            if vtype.replace("_", " ") in gemini_text or vtype in gemini_text:
                consensus_types.append(vtype)
        
        return consensus_types
    
    def _extract_attacks(self, result: HuntResult) -> list:
        """Extract high-confidence attack vectors."""
        attacks = []
        
        if result.adversarial_result and "attack_vectors" in result.adversarial_result:
            for attack in result.adversarial_result["attack_vectors"]:
                if attack.get("confidence_percent", 0) >= 60:
                    attacks.append(attack)
        
        # Sort by potential profit
        attacks.sort(key=lambda x: x.get("estimated_profit_usd", 0), reverse=True)
        
        return attacks
    
    async def _send_hunt_alert(self, result: HuntResult):
        """Send alert for high-value findings."""
        if not self.config.whatsapp_alert_number:
            return
        
        top_attack = result.high_confidence_attacks[0]
        
        msg = f"""🎯 *DEEP HUNT ALERT*

*Contract:* `{result.contract_address[:10]}...`
*Chain:* {result.chain}
*Program:* {result.bounty_program or 'Unknown'}
*Max Bounty:* ${result.max_bounty_usd:,}

*Top Attack:* {top_attack.get('name', 'Unknown')}
*Type:* {top_attack.get('type', 'other')}
*Confidence:* {top_attack.get('confidence_percent', 0)}%
*Est. Profit:* ${top_attack.get('estimated_profit_usd', 0):,}
*Difficulty:* {top_attack.get('difficulty', 'unknown')}

*Consensus Vulns:* {', '.join(result.confirmed_vulns) or 'None'}

Analysis time: {result.analysis_time:.1f}s"""
        
        try:
            subprocess.run(
                ["clawdbot", "send", "--channel", "whatsapp",
                 "--to", self.config.whatsapp_alert_number,
                 "--message", msg],
                timeout=30,
            )
        except:
            pass


# Target programs with high bounties
HIGH_VALUE_TARGETS = [
    {"name": "Scroll", "max_bounty": 1000000, "chain": "ethereum"},
    {"name": "SSV Network", "max_bounty": 1000000, "chain": "ethereum"},
    {"name": "Alchemix", "max_bounty": 300000, "chain": "ethereum"},
    {"name": "ENS", "max_bounty": 250000, "chain": "ethereum"},
    {"name": "Lombard Finance", "max_bounty": 250000, "chain": "ethereum"},
    {"name": "Inverse Finance", "max_bounty": 100000, "chain": "ethereum"},
    {"name": "Pinto", "max_bounty": 100000, "chain": "ethereum"},
]
