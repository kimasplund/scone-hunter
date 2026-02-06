"""Notification handlers for SCONE Hunter alerts."""

import json
import subprocess
from typing import Optional

from .config import Config
from .models import AnalysisResult, Severity


class Notifier:
    """Send alerts when vulnerabilities are found."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def should_alert(self, result: AnalysisResult) -> bool:
        """Determine if this result warrants an alert."""
        if not result.vulnerabilities:
            return False
        
        # Alert on high/critical vulnerabilities with decent confidence
        for vuln in result.vulnerabilities:
            if vuln.severity in (Severity.CRITICAL, Severity.HIGH) and vuln.confidence >= 0.6:
                return True
        
        return False
    
    def format_alert(self, result: AnalysisResult) -> str:
        """Format an alert message."""
        contract = result.contract
        vulns = result.vulnerabilities
        
        lines = [
            f"🚨 *SCONE Hunter Alert*",
            f"",
            f"*Contract:* `{contract.address[:10]}...{contract.address[-6:]}`",
            f"*Chain:* {contract.chain.value}",
            f"*Risk:* {self._severity_emoji(vulns[0].severity)} {vulns[0].severity.value.upper()}",
            f"*Confidence:* {result.confidence:.0%}",
            f"",
            f"*Vulnerabilities Found:* {len(vulns)}",
        ]
        
        for i, vuln in enumerate(vulns[:3], 1):  # Top 3
            lines.append(f"")
            lines.append(f"{i}. *{vuln.vuln_type.value}* ({vuln.severity.value})")
            lines.append(f"   {vuln.description[:100]}...")
            if vuln.estimated_impact:
                lines.append(f"   💰 Est. impact: ${vuln.estimated_impact:,.0f}")
        
        if len(vulns) > 3:
            lines.append(f"")
            lines.append(f"_...and {len(vulns) - 3} more_")
        
        lines.append(f"")
        lines.append(f"🔗 https://basescan.org/address/{contract.address}" if contract.chain.value == "base" else f"🔗 https://etherscan.io/address/{contract.address}")
        
        return "\n".join(lines)
    
    def _severity_emoji(self, severity: Severity) -> str:
        return {
            Severity.CRITICAL: "🔴",
            Severity.HIGH: "🟠",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🟢",
        }.get(severity, "⚪")
    
    async def send_whatsapp(self, result: AnalysisResult) -> bool:
        """Send alert via Clawdbot WhatsApp."""
        if not self.config.whatsapp_alert_number:
            return False
        
        message = self.format_alert(result)
        
        try:
            # Use clawdbot CLI to send message
            cmd = [
                "clawdbot", "send",
                "--channel", "whatsapp",
                "--to", self.config.whatsapp_alert_number,
                "--message", message
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
            
        except Exception as e:
            print(f"WhatsApp alert failed: {e}")
            return False
    
    async def send_all(self, result: AnalysisResult) -> dict[str, bool]:
        """Send alerts to all configured channels."""
        results = {}
        
        if self.config.whatsapp_alert_number:
            results["whatsapp"] = await self.send_whatsapp(result)
        
        # TODO: Add Discord, Telegram, Slack
        
        return results
