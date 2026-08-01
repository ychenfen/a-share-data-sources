"""akshare, Eastmoney-backed daily bars (stock_zh_a_hist).

Note on the adjust argument, because it differs by function and the difference
matters: stock_zh_a_hist accepts "", "qfq" and "hfq". stock_zh_a_daily (the
Sina-backed one) additionally accepts "qfq-factor" and "hfq-factor", which
return the adjustment factors as columns — that is the cheap way to implement
"store raw plus factors" without switching vendors.

The empty string means unadjusted and is the default, so the shortest possible
call hands back raw prices. That default is the single most common cause of
ex-dividend gaps being counted as real losses.
"""
import time

import pandas as pd

from .base import FetchError, FetchResult

name = "akshare"
needs_token = False

_RENAME = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
           "最低": "low", "成交量": "volume"}


def available() -> bool:
    try:
        import akshare  # noqa: F401
    except ImportError:
        return False
    return True


def daily(symbol: str, start: str, end: str, adjust: str = "hfq") -> FetchResult:
    if adjust not in ("", "qfq", "hfq"):
        raise ValueError(f"stock_zh_a_hist does not accept adjust={adjust!r}")
    try:
        import akshare as ak
    except ImportError as exc:
        raise FetchError("akshare is not installed") from exc

    t0 = time.perf_counter()
    try:
        raw = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                 start_date=start, end_date=end, adjust=adjust)
    except Exception as exc:
        raise FetchError(f"akshare call failed: {exc}") from exc
    elapsed = time.perf_counter() - t0

    if raw is None or raw.empty:
        raise FetchError("akshare returned an empty frame")

    fields = list(raw.columns)
    df = raw.rename(columns=_RENAME)
    missing = [c for c in ("date", "open", "high", "low", "close") if c not in df]
    if missing:
        raise FetchError(f"akshare frame missing columns: {missing}; got {fields}")
    df["date"] = pd.to_datetime(df["date"])
    keep = ["date", "open", "high", "low", "close"] + (["volume"] if "volume" in df else [])
    df = df[keep].sort_values("date")
    return FetchResult(df=df.reset_index(drop=True), elapsed_s=elapsed,
                       n_rows=len(df), raw_fields=fields)


class AkshareSource:
    """Registry-facing wrapper. bench.py constructs sources with a shared
    requests.Session so connection reuse does not show up as latency variance."""

    name = name
    needs_token = needs_token

    def __init__(self, session=None):
        self._session = session

    def available(self) -> bool:
        return available()

    def daily(self, symbol: str, start: str, end: str, adjust: str = "hfq"):
        return daily(symbol, start, end, adjust)
