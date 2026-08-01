from dataclasses import dataclass, field
from typing import Protocol, Optional
import pandas as pd


class FetchError(Exception):
    """Raised for any outcome that is not a usable price series,
    including HTTP 200 with an empty or truncated payload."""


@dataclass
class FetchResult:
    df: pd.DataFrame            # columns: date, open, high, low, close, volume
    elapsed_s: float
    n_rows: int
    raw_fields: list = field(default_factory=list)


class Source(Protocol):
    name: str
    needs_token: bool

    def available(self) -> bool: ...

    def daily(self, symbol: str, start: str, end: str,
              adjust: str = "hfq") -> FetchResult: ...
