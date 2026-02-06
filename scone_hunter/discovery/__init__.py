"""Target discovery for smart contract scanning."""
from .immunefi import ImmunefiFetcher
from .defillama import DefiLlamaFetcher
from .aggregator import TargetAggregator

__all__ = ["ImmunefiFetcher", "DefiLlamaFetcher", "TargetAggregator"]
