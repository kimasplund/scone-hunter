"""Data models for SCONE Hunter."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Chain(str, Enum):
    """Supported blockchain networks."""
    ETHEREUM = "ethereum"
    BSC = "bsc"
    BASE = "base"


class Severity(str, Enum):
    """Vulnerability severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnType(str, Enum):
    """Common vulnerability types."""
    REENTRANCY = "reentrancy"
    FLASH_LOAN = "flash_loan"
    PRICE_MANIPULATION = "price_manipulation"
    ACCESS_CONTROL = "access_control"
    INTEGER_OVERFLOW = "integer_overflow"
    ROUNDING_ERROR = "rounding_error"
    LOGIC_ERROR = "logic_error"
    FRONT_RUNNING = "front_running"
    SANDWICH = "sandwich"
    ORACLE_MANIPULATION = "oracle_manipulation"
    UNPROTECTED_FUNCTION = "unprotected_function"
    DELEGATE_CALL = "delegate_call"
    SELFDESTRUCT = "selfdestruct"
    OTHER = "other"


@dataclass
class Contract:
    """Smart contract information."""
    address: str
    chain: Chain
    name: Optional[str] = None
    source_code: Optional[str] = None
    abi: Optional[list] = None
    bytecode: Optional[str] = None
    creator: Optional[str] = None
    creation_tx: Optional[str] = None
    creation_block: Optional[int] = None
    tvl_usd: Optional[float] = None
    verified: bool = False
    proxy: bool = False
    implementation: Optional[str] = None


@dataclass
class Vulnerability:
    """Detected vulnerability."""
    vuln_type: VulnType
    severity: Severity
    description: str
    location: Optional[str] = None  # Function or line
    exploit_code: Optional[str] = None
    estimated_impact: Optional[float] = None  # USD
    confidence: float = 0.0
    references: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Result of contract analysis."""
    contract: Contract
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    confidence: float = 0.0
    analysis_time: float = 0.0
    model_used: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw_response: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ExploitResult:
    """Result of exploit validation."""
    analysis: AnalysisResult
    vulnerability: Vulnerability
    success: bool = False
    profit_native: float = 0.0  # In native token (ETH/BNB)
    profit_usd: float = 0.0
    gas_used: int = 0
    gas_cost_usd: float = 0.0
    exploit_tx: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def net_profit_usd(self) -> float:
        """Calculate net profit after gas."""
        return self.profit_usd - self.gas_cost_usd


@dataclass
class ScanResult:
    """Result of a scanning session."""
    chain: Chain
    contracts_scanned: int = 0
    vulnerabilities_found: int = 0
    exploits_validated: int = 0
    total_potential_impact: float = 0.0
    total_cost: float = 0.0
    duration_seconds: float = 0.0
    results: list[AnalysisResult] = field(default_factory=list)
