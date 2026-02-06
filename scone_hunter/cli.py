"""CLI interface for SCONE Hunter."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .scanner import Scanner
from .analyzer import Analyzer
from .config import Config

app = typer.Typer(
    name="scone-hunter",
    help="AI-powered smart contract vulnerability scanner",
)
console = Console()


@app.command()
def scan(
    chain: str = typer.Option("ethereum", help="Chain to scan (ethereum, bsc, base)"),
    mode: str = typer.Option("monitor", help="Scan mode (monitor, hunt)"),
    min_tvl: int = typer.Option(10000, help="Minimum TVL in USD to consider"),
    max_tvl: Optional[int] = typer.Option(None, help="Maximum TVL in USD"),
    limit: int = typer.Option(100, help="Max contracts to scan"),
):
    """Scan for vulnerable contracts."""
    console.print(f"[bold green]🛡️ SCONE Hunter[/bold green]")
    console.print(f"Chain: {chain} | Mode: {mode} | Min TVL: ${min_tvl:,}")
    
    config = Config()
    scanner = Scanner(config)
    
    asyncio.run(scanner.run(
        chain=chain,
        mode=mode,
        min_tvl=min_tvl,
        max_tvl=max_tvl,
        limit=limit,
    ))


@app.command()
def analyze(
    address: str = typer.Argument(..., help="Contract address to analyze"),
    chain: str = typer.Option("ethereum", help="Chain (ethereum, bsc, base)"),
    depth: str = typer.Option("standard", help="Analysis depth (quick, standard, deep)"),
):
    """Analyze a specific contract for vulnerabilities."""
    console.print(f"[bold green]🔍 Analyzing contract[/bold green]")
    console.print(f"Address: {address}")
    console.print(f"Chain: {chain} | Depth: {depth}")
    
    config = Config()
    analyzer = Analyzer(config)
    
    result = asyncio.run(analyzer.analyze_contract(
        address=address,
        chain=chain,
        depth=depth,
    ))
    
    # Display results
    if result.vulnerabilities:
        console.print(f"\n[bold red]⚠️ Found {len(result.vulnerabilities)} potential vulnerabilities:[/bold red]\n")
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Severity")
        table.add_column("Type")
        table.add_column("Description")
        table.add_column("Est. Impact")
        
        for vuln in result.vulnerabilities:
            severity_color = {
                "critical": "red",
                "high": "orange3",
                "medium": "yellow",
                "low": "blue",
            }.get(vuln.severity, "white")
            
            table.add_row(
                f"[{severity_color}]{vuln.severity.upper()}[/{severity_color}]",
                vuln.vuln_type,
                vuln.description[:60] + "..." if len(vuln.description) > 60 else vuln.description,
                f"${vuln.estimated_impact:,.0f}" if vuln.estimated_impact else "Unknown",
            )
        
        console.print(table)
    else:
        console.print("\n[bold green]✅ No vulnerabilities detected[/bold green]")
    
    console.print(f"\nConfidence: {result.confidence:.0%}")
    console.print(f"Analysis time: {result.analysis_time:.1f}s")


@app.command()
def watch(
    chain: str = typer.Option("ethereum", help="Chain to watch"),
    webhook: Optional[str] = typer.Option(None, help="Discord/Slack webhook for alerts"),
):
    """Watch for new contract deployments in real-time."""
    console.print(f"[bold green]👁️ Watching {chain} for new deployments...[/bold green]")
    console.print("Press Ctrl+C to stop\n")
    
    config = Config()
    scanner = Scanner(config)
    
    try:
        asyncio.run(scanner.watch_deployments(chain=chain, webhook=webhook))
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching.[/yellow]")


@app.command()
def report(
    address: str = typer.Argument(..., help="Contract address"),
    platform: str = typer.Option("immunefi", help="Platform (immunefi, code4rena)"),
    dry_run: bool = typer.Option(True, help="Don't actually submit"),
):
    """Submit a vulnerability report to bug bounty platform."""
    console.print(f"[bold green]📝 Preparing report for {platform}[/bold green]")
    console.print(f"Contract: {address}")
    console.print(f"Dry run: {dry_run}")
    
    # TODO: Implement report submission
    console.print("\n[yellow]Report submission not yet implemented.[/yellow]")


if __name__ == "__main__":
    app()
