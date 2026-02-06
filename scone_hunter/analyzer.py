"""AI-powered contract analyzer."""

import json
import time
from typing import Optional

import anthropic
import httpx

from .config import Config
from .models import (
    AnalysisResult,
    Chain,
    Contract,
    Severity,
    Vulnerability,
    VulnType,
)


ANALYSIS_PROMPT = """You are an expert smart contract security auditor. Analyze the following Solidity contract for vulnerabilities.

CONTRACT ADDRESS: {address}
CHAIN: {chain}

SOURCE CODE:
```solidity
{source_code}
```

{context}

Analyze this contract for ALL potential vulnerabilities including but not limited to:
- Reentrancy attacks
- Flash loan attacks
- Price/oracle manipulation
- Access control issues
- Integer overflow/underflow
- Rounding errors
- Logic errors
- Front-running vulnerabilities
- Unprotected functions
- Delegate call risks

For each vulnerability found, provide:
1. Type of vulnerability
2. Severity (critical/high/medium/low)
3. Exact location (function name, line if possible)
4. Detailed description of the issue
5. Potential exploit scenario
6. Estimated financial impact if exploited

Return your analysis as JSON in this exact format:
{{
    "vulnerabilities": [
        {{
            "type": "reentrancy|flash_loan|price_manipulation|access_control|integer_overflow|rounding_error|logic_error|front_running|unprotected_function|delegate_call|other",
            "severity": "critical|high|medium|low",
            "location": "function name or line",
            "description": "detailed description",
            "exploit_scenario": "how an attacker could exploit this",
            "estimated_impact_usd": 0,
            "confidence": 0.0-1.0
        }}
    ],
    "overall_risk": "critical|high|medium|low|safe",
    "summary": "brief summary of findings"
}}

Be thorough but precise. Only report vulnerabilities you are confident about. If the contract appears secure, return an empty vulnerabilities array.
"""


class Analyzer:
    """AI-powered smart contract analyzer."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.http = httpx.AsyncClient(timeout=60.0)
    
    async def analyze_contract(
        self,
        address: str,
        chain: str = "ethereum",
        depth: str = "standard",
        source_code: Optional[str] = None,
    ) -> AnalysisResult:
        """Analyze a contract for vulnerabilities."""
        start_time = time.time()
        chain_enum = Chain(chain)
        
        # Fetch contract info if not provided
        contract = Contract(address=address, chain=chain_enum)
        
        if not source_code:
            source_code = await self._fetch_source_code(address, chain)
        
        contract.source_code = source_code
        
        if not source_code:
            return AnalysisResult(
                contract=contract,
                error="Could not fetch contract source code. Is it verified?",
                analysis_time=time.time() - start_time,
            )
        
        # Get additional context
        context = await self._get_contract_context(address, chain)
        
        # Run AI analysis
        try:
            result = await self._run_analysis(contract, context, depth)
            result.analysis_time = time.time() - start_time
            return result
        except Exception as e:
            return AnalysisResult(
                contract=contract,
                error=str(e),
                analysis_time=time.time() - start_time,
            )
    
    async def _fetch_source_code(self, address: str, chain: str) -> Optional[str]:
        """Fetch contract source code from block explorer."""
        api_key = self.config.get_explorer_api_key(chain)
        
        base_urls = {
            "ethereum": "https://api.etherscan.io/api",
            "bsc": "https://api.bscscan.com/api",
            "base": "https://api.basescan.org/api",
        }
        
        base_url = base_urls.get(chain, base_urls["ethereum"])
        
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "apikey": api_key,
        }
        
        try:
            resp = await self.http.get(base_url, params=params)
            data = resp.json()
            
            if data.get("status") == "1" and data.get("result"):
                result = data["result"][0]
                source = result.get("SourceCode", "")
                
                # Handle JSON-formatted source (multiple files)
                if source.startswith("{{"):
                    try:
                        # Double-brace indicates JSON
                        source_json = json.loads(source[1:-1])
                        sources = source_json.get("sources", {})
                        # Concatenate all source files
                        source = "\n\n".join(
                            f"// File: {name}\n{info.get('content', '')}"
                            for name, info in sources.items()
                        )
                    except json.JSONDecodeError:
                        pass
                
                return source if source else None
                
        except Exception as e:
            print(f"Error fetching source code: {e}")
        
        return None
    
    async def _get_contract_context(self, address: str, chain: str) -> str:
        """Get additional context about the contract (TVL, etc)."""
        # TODO: Fetch TVL from DeFiLlama
        # TODO: Fetch token info
        # TODO: Check if it's a known protocol
        return ""
    
    async def _run_analysis(
        self,
        contract: Contract,
        context: str,
        depth: str,
    ) -> AnalysisResult:
        """Run AI analysis on the contract."""
        prompt = ANALYSIS_PROMPT.format(
            address=contract.address,
            chain=contract.chain.value,
            source_code=contract.source_code[:100000],  # Limit size
            context=context,
        )
        
        # Adjust parameters based on depth
        max_tokens = {
            "quick": 2000,
            "standard": 4000,
            "deep": 8000,
        }.get(depth, 4000)
        
        message = self.client.messages.create(
            model=self.config.ai_model,
            max_tokens=max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )
        
        response_text = message.content[0].text
        
        # Parse response
        vulnerabilities = []
        confidence = 0.0
        
        try:
            # Find JSON in response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                result_json = json.loads(response_text[json_start:json_end])
                
                for vuln_data in result_json.get("vulnerabilities", []):
                    try:
                        vuln = Vulnerability(
                            vuln_type=VulnType(vuln_data.get("type", "other")),
                            severity=Severity(vuln_data.get("severity", "medium")),
                            description=vuln_data.get("description", ""),
                            location=vuln_data.get("location"),
                            estimated_impact=vuln_data.get("estimated_impact_usd"),
                            confidence=vuln_data.get("confidence", 0.5),
                        )
                        vulnerabilities.append(vuln)
                    except (ValueError, KeyError):
                        continue
                
                # Calculate overall confidence
                if vulnerabilities:
                    confidence = sum(v.confidence for v in vulnerabilities) / len(vulnerabilities)
                else:
                    confidence = 0.9  # High confidence if no vulns found
                    
        except json.JSONDecodeError:
            pass
        
        return AnalysisResult(
            contract=contract,
            vulnerabilities=vulnerabilities,
            confidence=confidence,
            model_used=self.config.ai_model,
            tokens_used=message.usage.input_tokens + message.usage.output_tokens,
            raw_response=response_text,
        )
