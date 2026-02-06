"""CLI interface for SCONE Hunter."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .scanner import Scanner
from .analyzer import Analyzer
from .config import Config
from .notifier import Notifier
from .deep_hunter import DeepHunter, HIGH_VALUE_TARGETS

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
    alert: bool = typer.Option(True, help="Send alert if vulnerabilities found"),
):
    """Analyze a specific contract for vulnerabilities."""
    config = Config()
    
    # Show which AI backend is being used
    if config.use_gemini:
        backend = "Gemini CLI"
    elif config.openai_api_key:
        backend = f"OpenAI ({config.ai_model})"
    elif config.anthropic_api_key:
        backend = f"Claude ({config.ai_model})"
    else:
        backend = "Unknown"
    
    console.print(f"[bold green]🔍 Analyzing contract[/bold green]")
    console.print(f"Address: {address}")
    console.print(f"Chain: {chain} | Depth: {depth} | AI: {backend}")
    
    analyzer = Analyzer(config)
    notifier = Notifier(config)
    
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
            }.get(vuln.severity.value, "white")
            
            table.add_row(
                f"[{severity_color}]{vuln.severity.value.upper()}[/{severity_color}]",
                vuln.vuln_type.value,
                vuln.description[:60] + "..." if len(vuln.description) > 60 else vuln.description,
                f"${vuln.estimated_impact:,.0f}" if vuln.estimated_impact else "Unknown",
            )
        
        console.print(table)
        
        # Send alert if enabled and warranted
        if alert and notifier.should_alert(result):
            console.print("\n[yellow]📲 Sending alert...[/yellow]")
            alert_results = asyncio.run(notifier.send_all(result))
            for channel, success in alert_results.items():
                status = "✅" if success else "❌"
                console.print(f"  {status} {channel}")
    else:
        console.print("\n[bold green]✅ No vulnerabilities detected[/bold green]")
    
    console.print(f"\nConfidence: {result.confidence:.0%}")
    console.print(f"Model: {result.model_used}")
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
def hunt(
    address: str = typer.Argument(..., help="Contract address to deep-analyze"),
    chain: str = typer.Option("ethereum", help="Chain (ethereum, bsc, base)"),
    program: Optional[str] = typer.Option(None, help="Bug bounty program name"),
    max_bounty: int = typer.Option(100000, help="Max bounty in USD"),
):
    """Deep hunt mode: multi-model consensus + adversarial analysis."""
    console.print(f"[bold red]🎯 DEEP HUNT MODE[/bold red]")
    console.print(f"Target: {address}")
    console.print(f"Chain: {chain} | Program: {program or 'Unknown'}")
    console.print(f"Max Bounty: ${max_bounty:,}")
    console.print()
    console.print("[yellow]Running multi-model analysis...[/yellow]")
    console.print("  • OpenAI GPT-4o (standard)")
    console.print("  • Gemini (second opinion)")
    console.print("  • Adversarial mode (attack vectors)")
    console.print()
    
    config = Config()
    hunter = DeepHunter(config)
    
    result = asyncio.run(hunter.hunt(
        address=address,
        chain=chain,
        bounty_program=program,
        max_bounty=max_bounty,
    ))
    
    # Display results
    if result.high_confidence_attacks:
        console.print(f"\n[bold red]🎯 {len(result.high_confidence_attacks)} HIGH-CONFIDENCE ATTACKS FOUND:[/bold red]\n")
        
        for i, attack in enumerate(result.high_confidence_attacks, 1):
            conf = attack.get('confidence_percent', 0)
            profit = attack.get('estimated_profit_usd', 0)
            diff = attack.get('difficulty', 'unknown')
            
            color = "red" if conf >= 80 else "orange3" if conf >= 60 else "yellow"
            
            console.print(f"[{color}]#{i} {attack.get('name', 'Unknown')}[/{color}]")
            console.print(f"    Type: {attack.get('type', 'other')}")
            console.print(f"    Confidence: {conf}% | Difficulty: {diff}")
            console.print(f"    Est. Profit: ${profit:,}")
            
            if attack.get('steps'):
                console.print("    Steps:")
                for step in attack['steps'][:3]:
                    console.print(f"      → {step}")
            console.print()
    
    if result.confirmed_vulns:
        console.print(f"[green]✓ Consensus vulnerabilities: {', '.join(result.confirmed_vulns)}[/green]")
    
    if result.openai_result and result.openai_result.vulnerabilities:
        console.print(f"\nOpenAI found: {len(result.openai_result.vulnerabilities)} issues")
    
    console.print(f"\nAnalysis time: {result.analysis_time:.1f}s")
    
    if result.high_confidence_attacks:
        console.print(f"\n[bold green]💰 Potential bounty: ${max_bounty:,}[/bold green]")
        console.print("[yellow]Next: Validate with Foundry PoC before reporting![/yellow]")


@app.command()
def targets():
    """List high-value bounty program targets."""
    console.print("[bold green]🎯 HIGH-VALUE TARGETS[/bold green]\n")
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("Program")
    table.add_column("Max Bounty")
    table.add_column("Chain")
    
    for target in HIGH_VALUE_TARGETS:
        table.add_row(
            target["name"],
            f"${target['max_bounty']:,}",
            target["chain"],
        )
    
    console.print(table)
    console.print("\n[dim]Use: hunt <address> --program <name> --max-bounty <amount>[/dim]")


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
