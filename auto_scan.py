#!/usr/bin/env python3
"""
Automated scanning pipeline:
1. Discover new targets
2. Create Jules batch sessions
3. Harvest completed sessions

Run this as the daily cron job.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from scone_hunter.discovery import TargetAggregator


# Import Jules batch scanning logic
def create_jules_sessions(targets: list, batch_size: int = 10) -> list[str]:
    """Create Jules sessions for targets."""
    import subprocess
    from threading import Thread
    from queue import Queue, Empty
    
    MCP_SERVER = str(Path.home() / ".local/bin/jules-mcp-server")
    
    class JulesClient:
        def __init__(self):
            self.proc = None
            self.responses = Queue()
            self.req_id = 0
        
        def start(self):
            self.proc = subprocess.Popen(
                [MCP_SERVER],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            Thread(target=self._read, daemon=True).start()
            time.sleep(1)
            self._send({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"auto-scan","version":"1.0"}}})
            self._wait(10)
            self._send({"jsonrpc":"2.0","method":"notifications/initialized"})
            return True
        
        def _send(self, msg):
            self.proc.stdin.write(json.dumps(msg)+"\n")
            self.proc.stdin.flush()
        
        def _read(self):
            while self.proc and self.proc.stdout:
                line = self.proc.stdout.readline().strip()
                if line.startswith("{"): self.responses.put(json.loads(line))
        
        def _wait(self, timeout=30):
            try: return self.responses.get(timeout=timeout)
            except Empty: return None
        
        def call(self, name, args=None):
            self.req_id += 1
            self._send({"jsonrpc":"2.0","id":self.req_id,"method":"tools/call","params":{"name":name,"arguments":args or {}}})
            start = time.time()
            while time.time()-start < 30:
                r = self._wait(5)
                if r and r.get("id") == self.req_id: return r
            return {"error":"timeout"}
        
        def close(self):
            if self.proc: self.proc.terminate()
    
    # Batch prompt template - STATIC ANALYSIS ONLY
    BATCH_PROMPT = """
# Static Security Audit: {batch_name}

**IMPORTANT: STATIC ANALYSIS ONLY. Do NOT install tools or run tests.**

Reviewing {count} smart contracts using SOURCE CODE ANALYSIS.

## Targets

{targets_section}

## Instructions

For EACH contract:
1. Fetch verified source from the explorer (view source only)
2. Read and analyze the Solidity code manually
3. Look for: reentrancy, access control, oracle manipulation, flash loans, logic bugs
4. Create: `audit/[contract]/FINDINGS.md` with severity, confidence %, location, exploit path

## Rules
- NO tool installation (no Foundry, no npm)
- NO test execution
- Just READ the source code and find bugs
- Only report >70% confidence exploitable bugs
- Skip timelocked/multisig admins
"""
    
    def get_explorer(chain):
        return {"ethereum":"https://etherscan.io","base":"https://basescan.org","arbitrum":"https://arbiscan.io","optimism":"https://optimistic.etherscan.io"}.get(chain,"https://etherscan.io")
    
    def create_batch_prompt(batch):
        targets_section = ""
        for i, t in enumerate(batch, 1):
            targets_section += f"\n### Contract {i}: {t['name']}\n- Address: {t['address']}\n- Chain: {t['chain']}\n- Explorer: {get_explorer(t['chain'])}/address/{t['address']}\n- Program: {t.get('program','Unknown')}\n- Max Bounty: ${t.get('max_bounty',50000):,}\n"
        return BATCH_PROMPT.format(batch_name=f"Batch-{datetime.now().strftime('%Y%m%d')}", count=len(batch), targets_section=targets_section)
    
    # Create batches
    batches = [targets[i:i+batch_size] for i in range(0, len(targets), batch_size)]
    
    client = JulesClient()
    if not client.start():
        print("Failed to start Jules MCP")
        return []
    
    session_ids = []
    
    for i, batch in enumerate(batches, 1):
        batch_name = f"AutoScan-{i}-{datetime.now().strftime('%H%M')}"
        prompt = create_batch_prompt(batch)
        
        print(f"   Creating session: {batch_name} ({len(batch)} contracts)")
        
        resp = client.call("jules_create_session", {
            "title": f"Auto Audit: {batch_name}",
            "prompt": prompt,
            "source": "sources/github/kimasplund/scone-hunter",
            "starting_branch": "main",
            "require_plan_approval": False,
            "automation_mode": "AUTO_CREATE_PR",
            "tags": ["security-hunt", "auto-scan", f"batch-{i}"]
        })
        
        if "result" in resp:
            content = resp["result"].get("content", [])
            if content:
                text = content[0].get("text", "")
                import re
                match = re.search(r'"id":\s*"(\d+)"', text)
                if match:
                    sid = match.group(1)
                    session_ids.append(sid)
                    print(f"      ✓ Session: {sid}")
        
        time.sleep(1)
    
    client.close()
    return session_ids


def main():
    print(f"🤖 SCONE HUNTER - AUTO SCAN")
    print(f"   Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    agg = TargetAggregator()
    
    # Step 1: Discover targets
    print("\n1️⃣ DISCOVER TARGETS")
    print("-" * 40)
    results = agg.refresh_all()
    print(f"   Pool size: {results['total_targets']} targets")
    
    # Step 2: Get unscanned targets
    print("\n2️⃣ SELECT TARGETS")
    print("-" * 40)
    targets = agg.get_batch_for_jules(batch_size=20)  # 2 sessions × 10
    print(f"   Selected: {len(targets)} contracts for scanning")
    
    if not targets:
        print("   No unscanned targets available!")
        return
    
    for t in targets[:5]:
        print(f"      • {t['name']} ({t['chain']})")
    if len(targets) > 5:
        print(f"      ... and {len(targets)-5} more")
    
    # Step 3: Create Jules sessions
    print("\n3️⃣ CREATE JULES SESSIONS")
    print("-" * 40)
    session_ids = create_jules_sessions(targets, batch_size=10)
    print(f"   Created: {len(session_ids)} sessions")
    
    # Mark targets as scanned
    for t in targets:
        agg.mark_scanned(t['address'], t['chain'])
    
    # Save session tracking
    tracking = {
        "timestamp": datetime.now().isoformat(),
        "targets_count": len(targets),
        "sessions": session_ids,
    }
    
    tracking_file = Path.home() / ".scone-hunter" / "auto_scan_runs.jsonl"
    with open(tracking_file, "a") as f:
        f.write(json.dumps(tracking) + "\n")
    
    # Summary
    stats = agg.get_stats()
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print(f"   Targets discovered: {stats['total_targets']}")
    print(f"   Targets scanned: {stats['scanned_count']}")
    print(f"   Sessions created: {len(session_ids)}")
    print(f"   Contracts queued: {len(targets)}")
    print("=" * 60)
    
    print("\n⏰ Sessions will complete in 15-60 minutes")
    print("   Run `python3 harvest.py` to check results")


if __name__ == "__main__":
    main()
