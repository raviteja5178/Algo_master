"""
Candle data model.  Index 0 = most-recent completed candle, 1 = previous, etc.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    def __repr__(self) -> str:
        return (
            f"Candle({self.timestamp.strftime('%Y-%m-%d %H:%M')} "
            f"O={self.open} H={self.high} L={self.low} C={self.close})"
        )
