"""Configuration management for SCONE Hunter."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Config:
    """Scanner configuration."""
    
    # AI APIs
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    ai_model: str = "claude-sonnet-4-5-20250514"
    use_gemini: bool = False  # Use Gemini CLI as analyzer
    
    # Blockchain APIs
    etherscan_api_key: str = ""
    alchemy_api_key: str = ""
    infura_api_key: str = ""
    
    # RPC URLs
    ethereum_rpc_url: str = ""
    bsc_rpc_url: str = "https://bsc-dataseed.binance.org/"
    base_rpc_url: str = "https://mainnet.base.org"
    
    # Bug Bounty
    immunefi_api_key: str = ""
    code4rena_api_key: str = ""
    
    # Notifications
    discord_webhook_url: str = ""
    slack_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    whatsapp_alert_number: str = ""  # Phone number for WhatsApp alerts via Clawdbot
    
    # Scanner settings
    min_tvl_usd: int = 10000
    max_concurrent_scans: int = 5
    scan_timeout_seconds: int = 300
    
    # Paths
    data_dir: Path = field(default_factory=lambda: Path.home() / ".scone-hunter")
    
    def __post_init__(self):
        """Load configuration from environment."""
        load_dotenv()
        
        # AI APIs
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.ai_model = os.getenv("AI_MODEL", self.ai_model)
        self.use_gemini = os.getenv("USE_GEMINI", "").lower() in ("true", "1", "yes")
        
        # Blockchain APIs
        self.etherscan_api_key = os.getenv("ETHERSCAN_API_KEY", "")
        self.alchemy_api_key = os.getenv("ALCHEMY_API_KEY", "")
        self.infura_api_key = os.getenv("INFURA_API_KEY", "")
        
        # RPC URLs
        alchemy_key = self.alchemy_api_key
        self.ethereum_rpc_url = os.getenv(
            "ETHEREUM_RPC_URL",
            f"https://eth-mainnet.g.alchemy.com/v2/{alchemy_key}" if alchemy_key else ""
        )
        self.bsc_rpc_url = os.getenv("BSC_RPC_URL", self.bsc_rpc_url)
        self.base_rpc_url = os.getenv("BASE_RPC_URL", self.base_rpc_url)
        
        # Bug Bounty
        self.immunefi_api_key = os.getenv("IMMUNEFI_API_KEY", "")
        self.code4rena_api_key = os.getenv("CODE4RENA_API_KEY", "")
        
        # Notifications
        self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.whatsapp_alert_number = os.getenv("WHATSAPP_ALERT_NUMBER", "")
        
        # Scanner settings
        self.min_tvl_usd = int(os.getenv("MIN_TVL_USD", self.min_tvl_usd))
        self.max_concurrent_scans = int(os.getenv("MAX_CONCURRENT_SCANS", self.max_concurrent_scans))
        self.scan_timeout_seconds = int(os.getenv("SCAN_TIMEOUT_SECONDS", self.scan_timeout_seconds))
        
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def get_rpc_url(self, chain: str) -> str:
        """Get RPC URL for a chain."""
        urls = {
            "ethereum": self.ethereum_rpc_url,
            "bsc": self.bsc_rpc_url,
            "base": self.base_rpc_url,
        }
        return urls.get(chain, "")
    
    def get_explorer_api_key(self, chain: str) -> str:
        """Get block explorer API key for a chain."""
        # For now, use Etherscan key for all (they own BSCScan too)
        return self.etherscan_api_key
    
    def validate(self) -> list[str]:
        """Validate configuration, return list of issues."""
        issues = []
        
        if not self.anthropic_api_key and not self.openai_api_key:
            issues.append("No AI API key configured (need ANTHROPIC_API_KEY or OPENAI_API_KEY)")
        
        if not self.etherscan_api_key:
            issues.append("No ETHERSCAN_API_KEY configured")
        
        if not self.ethereum_rpc_url:
            issues.append("No Ethereum RPC URL configured (need ALCHEMY_API_KEY or ETHEREUM_RPC_URL)")
        
        return issues
