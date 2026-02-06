# SCONE Hunter 🛡️

AI-powered smart contract vulnerability scanner and bug bounty hunter.

Based on research from [Anthropic's SCONE-bench](https://red.anthropic.com/2025/smart-contracts/).

## Overview

SCONE Hunter monitors new smart contract deployments, analyzes them for vulnerabilities using frontier AI models, validates exploits in sandboxed environments, and optionally submits findings to bug bounty programs.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      SCONE Hunter                            │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │  Watcher    │───▶│  Analyzer   │───▶│  Validator  │      │
│  │  (new txs)  │    │  (AI audit) │    │  (Foundry)  │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
│         │                  │                  │              │
│         ▼                  ▼                  ▼              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │ Etherscan   │    │ Claude API  │    │  Sandbox    │      │
│  │ Alchemy     │    │ GPT API     │    │  (Docker)   │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   Reporter                           │    │
│  │  - Immunefi submission    - Slack/Discord alerts    │    │
│  │  - Code4rena submission   - Dashboard               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Features

- **Real-time monitoring**: Watch for new contract deployments on Ethereum, BSC, Base
- **AI-powered analysis**: Use Claude/GPT to identify vulnerabilities
- **Sandboxed validation**: Test exploits against forked chains (never live)
- **Bug bounty integration**: Auto-submit to Immunefi, Code4rena
- **Continuous monitoring**: Track existing contracts for new attack vectors

## Quick Start

```bash
# Clone and install
git clone https://github.com/kimasplund/scone-hunter.git
cd scone-hunter
pip install -e .

# Configure
cp .env.example .env
# Add your API keys

# Run scanner
python -m scone_hunter scan --chain ethereum --mode monitor

# Analyze specific contract
python -m scone_hunter analyze 0x1234...abcd
```

## Configuration

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
ETHERSCAN_API_KEY=...
ALCHEMY_API_KEY=...

# Optional
OPENAI_API_KEY=sk-...
IMMUNEFI_API_KEY=...
DISCORD_WEBHOOK_URL=...
```

## Modes

### 1. Monitor Mode
Watch for new deployments and auto-scan:
```bash
python -m scone_hunter scan --mode monitor --min-tvl 10000
```

### 2. Hunt Mode  
Scan all contracts in a TVL range:
```bash
python -m scone_hunter scan --mode hunt --min-tvl 100000 --max-tvl 10000000
```

### 3. Audit Mode
Deep analysis of a specific contract:
```bash
python -m scone_hunter audit 0x1234...abcd --depth deep --report pdf
```

## Legal

⚠️ **Important**: This tool is for authorized security research only.

- Only test exploits in sandboxed/forked environments
- Never execute exploits on live chains without authorization
- Submit findings through official bug bounty programs
- Respect responsible disclosure timelines

## License

MIT - Use responsibly.
