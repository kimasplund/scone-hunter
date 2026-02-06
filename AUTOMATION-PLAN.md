# Scone Hunter Automation Plan

## IR-v2 Analysis

### Problem: Automate continuous smart contract vulnerability scanning

**Dimension Scoring:**

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Sequential Dependencies | 3 | Some order matters (targets → scan → results → notify) |
| Criteria Clarity | 4 | Clear: find exploitable vulns with >70% confidence |
| Solution Space Known | 4 | Three components needed (1,2,3 from Kim) |
| Single Answer Needed | 2 | Multiple implementations possible |
| Evidence Available | 5 | Can test everything empirically |
| Opposing Valid Views | 2 | Not much debate on approach |
| Problem Novelty | 3 | Novel integration, known components |
| Robustness Required | 4 | Needs to run reliably 24/7 |
| Solution Exists | 3 | Partial (jules_batch_scan.py works) |
| Time Pressure | 3 | Moderate (want it soon but not crisis) |
| Stakeholder Complexity | 1 | Just Kim |

**Pattern Scores:**
- SRC = 3.75 (sequential steps with validation)
- HE = 3.50 (can test each component)
- ToT = 3.25 (clear criteria)
- BoT = 2.80 (not exploring many options)

**Recommendation: SRC (Self-Reflecting Chain)** — Build sequentially, validate each step.

---

## Implementation Plan

### Component 1: Target Discovery (Expand Contract Pool)

**Goal:** Automatically find new high-value contracts to audit

**Sources:**
1. **Immunefi Programs** — Scrape active bug bounty programs
2. **DeFiLlama** — Top TVL protocols by chain
3. **New Deployments** — Watch for fresh contract deploys on-chain
4. **GitHub Security** — Watch for new protocol launches

**Implementation:**
```python
# target_discovery.py
class TargetDiscovery:
    def scrape_immunefi(self) -> list[Target]:
        """Get all active Immunefi programs with contracts."""
        
    def get_defi_llama_top(self, chain: str, limit: int = 50) -> list[Target]:
        """Get top TVL protocols from DeFiLlama."""
        
    def watch_new_deploys(self, chain: str, min_value: int) -> list[Target]:
        """Monitor for new contract deployments."""
        
    def dedupe_and_prioritize(self, targets: list) -> list:
        """Remove duplicates, sort by bounty potential."""
```

**Files to Create:**
- `scone_hunter/discovery/immunefi.py`
- `scone_hunter/discovery/defillama.py`
- `scone_hunter/discovery/onchain.py`
- `scone_hunter/discovery/__init__.py`

---

### Component 2: Daily Cron Batching

**Goal:** Run batch scans automatically every day

**Schedule:**
- 00:00 UTC: Discover new targets
- 00:30 UTC: Create Jules batch sessions (10 contracts each)
- 12:00 UTC: Check session status, retry failures
- 18:00 UTC: Extract results, notify

**Implementation:**
```python
# cron_scheduler.py
SCHEDULE = {
    "discover": "0 0 * * *",    # Midnight UTC
    "batch": "30 0 * * *",      # 00:30 UTC
    "check": "0 12 * * *",      # Noon UTC
    "harvest": "0 18 * * *",    # 6 PM UTC
}

async def daily_discover():
    """Find new targets, save to pool."""
    
async def daily_batch():
    """Create Jules sessions for top targets."""
    
async def daily_check():
    """Check session status, retry failures."""
    
async def daily_harvest():
    """Extract findings, notify if critical."""
```

**Clawdbot Cron Integration:**
```bash
# Add via cron tool
cron add --text "Run scone-hunter discovery" --schedule "0 0 * * *"
cron add --text "Run scone-hunter batch scan" --schedule "30 0 * * *"
cron add --text "Check scone-hunter sessions" --schedule "0 12 * * *"
cron add --text "Harvest scone-hunter findings" --schedule "0 18 * * *"
```

---

### Component 3: Results Aggregator

**Goal:** Pull findings when sessions complete, dedupe, notify

**Features:**
1. **Session Monitor** — Poll Jules for COMPLETED sessions
2. **Artifact Extractor** — Pull PRs, findings, PoCs
3. **Deduplication** — Avoid reporting same vuln twice
4. **Notification** — Alert on high-confidence findings
5. **Dashboard** — Track stats (scanned, found, submitted)

**Implementation:**
```python
# results_aggregator.py
class ResultsAggregator:
    def poll_completed_sessions(self) -> list[Session]:
        """Get all COMPLETED Jules sessions."""
        
    def extract_findings(self, session_id: str) -> list[Finding]:
        """Pull audit findings from session artifacts."""
        
    def dedupe(self, findings: list) -> list:
        """Remove duplicates using contract+vuln hash."""
        
    def notify(self, finding: Finding):
        """Send alert via WhatsApp/Telegram."""
        
    def update_dashboard(self, stats: dict):
        """Update tracking dashboard."""
```

**Notification Format:**
```
🚨 POTENTIAL VULNERABILITY FOUND

Contract: Alchemix AlchemistV2
Chain: Ethereum
Type: Reentrancy
Confidence: 85%
Est. Bounty: $50,000 - $300,000

PR: https://github.com/kimasplund/scone-hunter/pull/42

Action Required: Manual review before submission
```

---

## File Structure

```
scone-hunter/
├── scone_hunter/
│   ├── discovery/           # NEW: Target discovery
│   │   ├── __init__.py
│   │   ├── immunefi.py
│   │   ├── defillama.py
│   │   └── onchain.py
│   ├── automation/          # NEW: Cron automation
│   │   ├── __init__.py
│   │   ├── scheduler.py
│   │   └── jobs.py
│   ├── aggregator/          # NEW: Results collection
│   │   ├── __init__.py
│   │   ├── extractor.py
│   │   ├── deduper.py
│   │   └── notifier.py
│   └── ... (existing)
├── jules_batch_scan.py      # Existing batch scanner
├── cron_runner.py           # NEW: Entry point for cron
└── dashboard.html           # NEW: Stats dashboard
```

---

## Execution Plan

### Phase 1: Results Aggregator (Today)
Build the harvester first so we can see what current sessions produce.

### Phase 2: Discovery Module (Tomorrow)
Add Immunefi + DeFiLlama scrapers to expand target pool.

### Phase 3: Cron Integration (Day 3)
Wire everything to Clawdbot cron for 24/7 operation.

### Phase 4: Dashboard (Day 4)
Simple HTML dashboard showing stats.

---

## Metrics to Track

| Metric | Target |
|--------|--------|
| Contracts scanned/day | 100+ |
| Sessions used/day | 10-20 (of 100 quota) |
| High-confidence findings/week | 5+ |
| Bounty submissions/month | 2+ |
| Revenue target | €25,000 |

---

*Generated by IR-v2 (SRC pattern) — 2026-02-06*
