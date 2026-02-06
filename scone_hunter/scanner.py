"""Contract scanner for monitoring and hunting vulnerabilities."""

import asyncio
import time
from typing import Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.table import Table

from .analyzer import Analyzer
from .config import Config
from .models import Chain, ScanResult


console = Console()


class Scanner:
    """Smart contract vulnerability scanner."""
    
    def __init__(self, config: Config):
        self.config = config
        self.analyzer = Analyzer(config)
        self.http = httpx.AsyncClient(timeout=60.0)
    
    async def run(
        self,
        chain: str = "ethereum",
        mode: str = "monitor",
        min_tvl: int = 10000,
        max_tvl: Optional[int] = None,
        limit: int = 100,
    ) -> ScanResult:
        """Run the scanner in specified mode."""
        chain_enum = Chain(chain)
        start_time = time.time()
        
        result = ScanResult(chain=chain_enum)
        
        if mode == "monitor":
            result = await self._monitor_mode(chain, min_tvl, limit)
        elif mode == "hunt":
            result = await self._hunt_mode(chain, min_tvl, max_tvl, limit)
        else:
            console.print(f"[red]Unknown mode: {mode}[/red]")
        
        result.duration_seconds = time.time() - start_time
        
        # Print summary
        self._print_summary(result)
        
        return result
    
    async def _monitor_mode(
        self,
        chain: str,
        min_tvl: int,
        limit: int,
    ) -> ScanResult:
        """Monitor recent contract deployments."""
        console.print("[cyan]Fetching recent contract deployments...[/cyan]")
        
        contracts = await self._get_recent_deployments(chain, limit)
        
        console.print(f"Found {len(contracts)} recent contracts")
        
        return await self._scan_contracts(contracts, chain, min_tvl)
    
    async def _hunt_mode(
        self,
        chain: str,
        min_tvl: int,
        max_tvl: Optional[int],
        limit: int,
    ) -> ScanResult:
        """Hunt for vulnerabilities in existing contracts."""
        console.print("[cyan]Fetching contracts by TVL...[/cyan]")
        
        # TODO: Fetch from DeFiLlama or similar
        contracts = await self._get_contracts_by_tvl(chain, min_tvl, max_tvl, limit)
        
        console.print(f"Found {len(contracts)} contracts in TVL range")
        
        return await self._scan_contracts(contracts, chain, min_tvl)
    
    async def _scan_contracts(
        self,
        contracts: list[str],
        chain: str,
        min_tvl: int,
    ) -> ScanResult:
        """Scan a list of contract addresses."""
        result = ScanResult(chain=Chain(chain))
        
        # Create progress table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Contract")
        table.add_column("Status")
        table.add_column("Vulns")
        table.add_column("Impact")
        
        semaphore = asyncio.Semaphore(self.config.max_concurrent_scans)
        
        async def scan_one(address: str):
            async with semaphore:
                try:
                    analysis = await self.analyzer.analyze_contract(
                        address=address,
                        chain=chain,
                    )
                    return analysis
                except Exception as e:
                    console.print(f"[red]Error scanning {address}: {e}[/red]")
                    return None
        
        # Scan all contracts
        with Live(table, console=console, refresh_per_second=4):
            tasks = [scan_one(addr) for addr in contracts]
            
            for coro in asyncio.as_completed(tasks):
                analysis = await coro
                
                if analysis:
                    result.contracts_scanned += 1
                    result.results.append(analysis)
                    
                    vuln_count = len(analysis.vulnerabilities)
                    
                    if vuln_count > 0:
                        result.vulnerabilities_found += vuln_count
                        impact = sum(
                            v.estimated_impact or 0 
                            for v in analysis.vulnerabilities
                        )
                        result.total_potential_impact += impact
                        
                        status = f"[red]⚠️ {vuln_count} vulns[/red]"
                        impact_str = f"[red]${impact:,.0f}[/red]"
                    else:
                        status = "[green]✓ Clean[/green]"
                        impact_str = "-"
                    
                    table.add_row(
                        analysis.contract.address[:16] + "...",
                        status,
                        str(vuln_count),
                        impact_str,
                    )
        
        return result
    
    async def _get_recent_deployments(
        self,
        chain: str,
        limit: int,
    ) -> list[str]:
        """Get recently deployed contract addresses."""
        api_key = self.config.get_explorer_api_key(chain)
        
        base_urls = {
            "ethereum": "https://api.etherscan.io/api",
            "bsc": "https://api.bscscan.com/api",
            "base": "https://api.basescan.org/api",
        }
        
        base_url = base_urls.get(chain, base_urls["ethereum"])
        
        # Get recent verified contracts
        params = {
            "module": "contract",
            "action": "listcontracts",
            "page": 1,
            "offset": limit,
            "apikey": api_key,
        }
        
        try:
            resp = await self.http.get(base_url, params=params)
            data = resp.json()
            
            if data.get("status") == "1" and data.get("result"):
                return [c.get("Address") for c in data["result"] if c.get("Address")]
        except Exception as e:
            console.print(f"[yellow]Warning: Could not fetch recent deployments: {e}[/yellow]")
        
        return []
    
    async def _get_contracts_by_tvl(
        self,
        chain: str,
        min_tvl: int,
        max_tvl: Optional[int],
        limit: int,
    ) -> list[str]:
        """Get contracts filtered by TVL."""
        # TODO: Integrate with DeFiLlama API
        # For now, return empty list
        console.print("[yellow]TVL filtering not yet implemented. Use monitor mode.[/yellow]")
        return []
    
    async def watch_deployments(
        self,
        chain: str,
        webhook: Optional[str] = None,
    ):
        """Watch for new contract deployments in real-time."""
        rpc_url = self.config.get_rpc_url(chain)
        
        if not rpc_url:
            console.print(f"[red]No RPC URL configured for {chain}[/red]")
            return
        
        console.print(f"[cyan]Connecting to {chain}...[/cyan]")
        
        # TODO: Implement WebSocket subscription to new blocks
        # For now, poll every 12 seconds (one block)
        
        seen_contracts = set()
        
        while True:
            try:
                # Get latest block
                contracts = await self._get_recent_deployments(chain, 10)
                
                for address in contracts:
                    if address not in seen_contracts:
                        seen_contracts.add(address)
                        console.print(f"\n[cyan]New contract: {address}[/cyan]")
                        
                        # Analyze it
                        analysis = await self.analyzer.analyze_contract(
                            address=address,
                            chain=chain,
                        )
                        
                        if analysis.vulnerabilities:
                            console.print(
                                f"[bold red]⚠️ Found {len(analysis.vulnerabilities)} vulnerabilities![/bold red]"
                            )
                            
                            # Send webhook notification
                            if webhook:
                                await self._send_webhook(webhook, analysis)
                        else:
                            console.print("[green]✓ No vulnerabilities detected[/green]")
                
                await asyncio.sleep(12)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                await asyncio.sleep(12)
    
    async def _send_webhook(self, url: str, analysis):
        """Send vulnerability alert to webhook."""
        vulns = analysis.vulnerabilities
        
        payload = {
            "content": f"🚨 **Vulnerability Alert**\n\n"
                      f"Contract: `{analysis.contract.address}`\n"
                      f"Chain: {analysis.contract.chain.value}\n"
                      f"Vulnerabilities: {len(vulns)}\n"
                      f"Severity: {max(v.severity.value for v in vulns) if vulns else 'N/A'}\n"
                      f"Est. Impact: ${sum(v.estimated_impact or 0 for v in vulns):,.0f}",
        }
        
        try:
            await self.http.post(url, json=payload)
        except Exception as e:
            console.print(f"[yellow]Failed to send webhook: {e}[/yellow]")
    
    def _print_summary(self, result: ScanResult):
        """Print scan summary."""
        console.print("\n" + "=" * 50)
        console.print("[bold]Scan Summary[/bold]")
        console.print("=" * 50)
        console.print(f"Chain: {result.chain.value}")
        console.print(f"Contracts scanned: {result.contracts_scanned}")
        console.print(f"Vulnerabilities found: {result.vulnerabilities_found}")
        console.print(f"Total potential impact: ${result.total_potential_impact:,.0f}")
        console.print(f"Duration: {result.duration_seconds:.1f}s")
        console.print("=" * 50)
