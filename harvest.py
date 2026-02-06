#!/usr/bin/env python3
"""
Harvest findings from Jules sessions and notify on discoveries.
Run this periodically (e.g., via cron) to check for completed scans.
"""

import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scone_hunter.aggregator.extractor import ResultsExtractor
from scone_hunter.aggregator.notifier import FindingsNotifier, NotificationConfig


def main():
    print(f"🌾 SCONE HUNTER - HARVEST")
    print(f"   Time: {datetime.now().isoformat()}")
    print("=" * 50)
    
    extractor = ResultsExtractor()
    notifier = FindingsNotifier(NotificationConfig(
        min_confidence=70,
        min_severity="Medium",
        dedupe_hours=48
    ))
    
    # Check in-progress sessions
    in_progress = extractor.get_in_progress_sessions()
    print(f"\n📊 Sessions in progress: {len(in_progress)}")
    for s in in_progress:
        sid = s.get("id", "?")
        title = s.get("title", "")[:40]
        state = s.get("state", "?")
        print(f"   • [{state}] {sid[:10]}... - {title}")
    
    # Harvest completed sessions
    completed = extractor.get_completed_sessions()
    print(f"\n✅ Completed sessions: {len(completed)}")
    
    if not completed:
        print("   No completed sessions to harvest")
        extractor.close()
        return
    
    # Process each completed session
    results = []
    for session in completed:
        session_id = session.get("id")
        if session_id:
            print(f"\n   Harvesting {session_id}...")
            result = extractor.harvest_session(session_id)
            results.append(result)
            
            print(f"      State: {result.state}")
            print(f"      Findings: {len(result.findings)}")
            if result.pr_url:
                print(f"      PR: {result.pr_url}")
    
    # Process for notifications
    to_notify = notifier.process_results(results)
    
    print(f"\n🔔 Findings to notify: {len(to_notify)}")
    
    if to_notify:
        print("\n" + "=" * 50)
        print("NOTIFICATIONS:")
        print("=" * 50)
        
        for finding, message in to_notify:
            print(message)
            print("-" * 50)
        
        # TODO: Actually send via Clawdbot message tool
        # For now, just print and save
        notifications_file = Path.home() / ".scone-hunter" / "pending_notifications.json"
        pending = []
        for finding, message in to_notify:
            pending.append({
                "contract": finding.contract_name,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "type": finding.vuln_type,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })
        
        with open(notifications_file, "w") as f:
            json.dump(pending, f, indent=2)
        
        print(f"\n📝 Saved to: {notifications_file}")
    
    # Summary
    total_findings = sum(len(r.findings) for r in results)
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print(f"   Sessions harvested: {len(results)}")
    print(f"   Total findings: {total_findings}")
    print(f"   Notifications sent: {len(to_notify)}")
    print("=" * 50)
    
    extractor.close()


if __name__ == "__main__":
    main()
