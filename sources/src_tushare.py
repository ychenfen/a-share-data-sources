"""tushare pro daily bars, with adjustment applied from adj_factor.

tushare hands back unadjusted prices and a separate factor series; you join them
yourself. That is more work than a single adjust= argument and it is the reason
to prefer it for anything long-lived: the factor is a column you can inspect and
freeze, not a transformation someone else already baked into the numbers.

The token is read from the environment only. It is never written to any output
file, and available() does not print or log it.
"""
import os
import time

import pandas as pd

from .base import FetchError, FetchResult
from ._symbols import tushare_code

name = "tushare"
needs_token = True


def available() -> bool:
    if not os.environ.get("TUSHARE_TOKEN"):
        return False
    try:
        import tushare  # noqa: F401
    except ImportError:
        return False
    return True


def daily(symbol: str, start: str, end: str, adjust: str = "hfq") -> FetchResult:
    if adjust not in ("", "qfq", "hfq"):
        raise ValueError(f"unsupported adjust: {adjust!r}")
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise FetchError("TUSHARE_TOKEN is not set")
    try:
        import tushare as ts
    except ImportError as exc:
        raise FetchError("tushare is not installed") from exc

    code = tushare_code(symbol)
    t0 = time.perf_counter()
    try:
        pro = ts.pro_api(token)
        raw = pro.daily(ts_code=code, start_date=start, end_date=end)
        factor = (pro.adj_factor(ts_code=code, start_date=start, end_date=end)
                  if adjust else None)
    except Exception as exc:
        raise FetchError(f"tushare call failed: {exc}") from exc
    elapsed = time.perf_counter() - t0

    if raw is None or raw.empty:
        raise FetchError("tushare returned an empty frame")

    fields = list(raw.columns)
    df = raw.rename(columns={"trade_date": "date", "vol": "volume"}).copy()
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")

    if adjust:
        if factor is None or factor.empty:
            raise FetchError("adj_factor came back empty; cannot adjust")
        f = factor.rename(columns={"trade_date": "date"}).copy()
        f["date"] = pd.to_datetime(f["date"], format="%Y%m%d")
        df = df.merge(f[["date", "adj_factor"]], on="date", how="left")
        if df["adj_factor"].isna().any():
            raise FetchError("adj_factor has gaps over the requested window")
        # hfq anchors on the earliest factor, qfq on the latest.
        anchor = df["adj_factor"].iloc[df["date"].argmin()] if adjust == "hfq" \
            else df["adj_factor"].iloc[df["date"].argmax()]
        ratio = df["adj_factor"] / anchor
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] * ratio

    keep = ["date", "open", "high", "low", "close"] + (["volume"] if "volume" in df else [])
    df = df[keep].sort_values("date")
    return FetchResult(df=df.reset_index(drop=True), elapsed_s=elapsed,
                       n_rows=len(df), raw_fields=fields)


class TushareSource:
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
