#!/usr/bin/env python3
"""
Notify on significant findings via WhatsApp/Telegram.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from .extractor import Finding, SessionResult


@dataclass
class NotificationConfig:
    """Notification configuration."""
    min_confidence: int = 70
    min_severity: str = "Medium"  # Critical, High, Medium, Low
    dedupe_hours: int = 24


class FindingsNotifier:
    """Notify on significant vulnerability findings."""
    
    SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"]
    
    def __init__(self, config: NotificationConfig = None):
        self.config = config or NotificationConfig()
        self.state_dir = Path.home() / ".scone-hunter" / "notifier"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.sent_file = self.state_dir / "sent_notifications.json"
        self._load_sent()
    
    def _load_sent(self):
        """Load previously sent notifications."""
        if self.sent_file.exists():
            with open(self.sent_file) as f:
                self.sent = json.load(f)
        else:
            self.sent = {}
    
    def _save_sent(self):
        """Save sent notifications."""
        with open(self.sent_file, "w") as f:
            json.dump(self.sent, f, indent=2)
    
    def _finding_hash(self, finding: Finding) -> str:
        """Generate unique hash for a finding."""
        key = f"{finding.contract_address}:{finding.vuln_type}:{finding.severity}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
    
    def _is_duplicate(self, finding: Finding) -> bool:
        """Check if finding was already notified."""
        hash_key = self._finding_hash(finding)
        
        if hash_key in self.sent:
            sent_time = datetime.fromisoformat(self.sent[hash_key])
            hours_ago = (datetime.now() - sent_time).total_seconds() / 3600
            return hours_ago < self.config.dedupe_hours
        
        return False
    
    def _mark_sent(self, finding: Finding):
        """Mark finding as notified."""
        hash_key = self._finding_hash(finding)
        self.sent[hash_key] = datetime.now().isoformat()
        self._save_sent()
    
    def _severity_meets_threshold(self, severity: str) -> bool:
        """Check if severity meets minimum threshold."""
        try:
            finding_idx = self.SEVERITY_ORDER.index(severity)
            threshold_idx = self.SEVERITY_ORDER.index(self.config.min_severity)
            return finding_idx <= threshold_idx
        except ValueError:
            return False
    
    def should_notify(self, finding: Finding) -> bool:
        """Determine if a finding should trigger notification."""
        # Check confidence threshold
        if finding.confidence < self.config.min_confidence:
            return False
        
        # Check severity threshold
        if not self._severity_meets_threshold(finding.severity):
            return False
        
        # Check for duplicates
        if self._is_duplicate(finding):
            return False
        
        return True
    
    def format_notification(self, finding: Finding) -> str:
        """Format finding as notification message."""
        emoji = {
            "Critical": "🚨",
            "High": "⚠️",
            "Medium": "📋",
            "Low": "ℹ️"
        }.get(finding.severity, "📋")
        
        bounty_info = ""
        if finding.max_bounty:
            bounty_info = f"\n💰 Bounty: up to ${finding.max_bounty:,}"
        
        pr_info = ""
        if finding.pr_url:
            pr_info = f"\n🔗 PR: {finding.pr_url}"
        
        return f"""{emoji} **POTENTIAL VULNERABILITY FOUND**

📍 **Contract:** {finding.contract_name}
🔗 Address: `{finding.contract_address}`
⛓️ Chain: {finding.chain}

🔍 **Type:** {finding.vuln_type}
⚡ **Severity:** {finding.severity}
📊 **Confidence:** {finding.confidence}%
{bounty_info}

📝 **Description:**
{finding.description[:300]}{'...' if len(finding.description) > 300 else ''}
{pr_info}

⚡ **Action Required:** Manual review before submission"""
    
    def process_results(self, results: list[SessionResult]) -> list[tuple[Finding, str]]:
        """Process results and return findings that should be notified."""
        to_notify = []
        
        for result in results:
            for finding in result.findings:
                if self.should_notify(finding):
                    message = self.format_notification(finding)
                    to_notify.append((finding, message))
                    self._mark_sent(finding)
        
        return to_notify
    
    def notify_via_stdout(self, findings: list[tuple[Finding, str]]):
        """Print notifications to stdout (for testing)."""
        for finding, message in findings:
            print("=" * 60)
            print(message)
            print("=" * 60)
            print()
    
    def get_stats(self) -> dict:
        """Get notification statistics."""
        return {
            "total_sent": len(self.sent),
            "config": {
                "min_confidence": self.config.min_confidence,
                "min_severity": self.config.min_severity,
                "dedupe_hours": self.config.dedupe_hours,
            }
        }


def main():
    """CLI for testing notifier."""
    notifier = FindingsNotifier()
    
    # Create test finding
    test_finding = Finding(
        contract_name="Test Contract",
        contract_address="0x1234...5678",
        chain="ethereum",
        vuln_type="reentrancy",
        severity="High",
        confidence=85,
        description="Potential reentrancy vulnerability in withdraw() function. State is updated after external call.",
        max_bounty=100000,
        pr_url="https://github.com/kimasplund/scone-hunter/pull/1"
    )
    
    print("📬 NOTIFICATION TEST")
    print("=" * 50)
    
    if notifier.should_notify(test_finding):
        message = notifier.format_notification(test_finding)
        print(message)
    else:
        print("Finding does not meet notification threshold")
    
    print("\nStats:", notifier.get_stats())


if __name__ == "__main__":
    main()
