"""Sina finance kline endpoint. No credentials.

Two things worth knowing before you trust this one. Prices are unadjusted, so
anything comparing it against an adjusted source has to reconstruct the
adjustment first. And `datalen` is capped per request, so a long history needs
paging rather than one large call — this adapter deliberately does not page, it
takes what one call gives and reports n_rows so the coverage metric can show the
truncation instead of hiding it.

akshare's own docs warn that repeated calls to the Sina source get the IP
banned. Our runs did not trigger it at low concurrency; that is a statement
about our request rate and exit IP, not a guarantee.
"""
import time

import pandas as pd
import requests

from .base import FetchError, FetchResult
from ._symbols import sina_symbol

name = "sina"
needs_token = False

_URL = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
        "/CN_MarketData.getKLineData")


def available() -> bool:
    return True


def daily(symbol: str, start: str, end: str, adjust: str = "",
          session=None) -> FetchResult:
    if adjust not in ("", "none"):
        raise FetchError("sina returns unadjusted prices only; "
                         "reconstruct adjustment upstream")
    t0 = time.perf_counter()
    try:
        r = (session or requests).get(
            _URL,
            params={"symbol": sina_symbol(symbol), "scale": "240",
                    "ma": "no", "datalen": "1023"},
            headers={"User-Agent": "Mozilla/5.0",
                     "Referer": "https://finance.sina.com.cn/"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        raise FetchError(f"sina request failed: {exc}") from exc
    elapsed = time.perf_counter() - t0

    if not data:
        raise FetchError("sina returned an empty series")

    df = pd.DataFrame(data)
    df = df.rename(columns={"day": "date"})
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    lo = pd.to_datetime(start, format="%Y%m%d", errors="coerce")
    hi = pd.to_datetime(end, format="%Y%m%d", errors="coerce")
    if pd.notna(lo):
        df = df[df["date"] >= lo]
    if pd.notna(hi):
        df = df[df["date"] <= hi]
    df = df[["date", "open", "high", "low", "close", "volume"]].sort_values("date")
    return FetchResult(df=df.reset_index(drop=True), elapsed_s=elapsed,
                       n_rows=len(df), raw_fields=list(data[0].keys()))


class SinaSource:
    """Registry-facing wrapper. bench.py constructs sources with a shared
    requests.Session so connection reuse does not show up as latency variance."""

    name = name
    needs_token = needs_token

    def __init__(self, session=None):
        self._session = session

    def available(self) -> bool:
        return available()

    def daily(self, symbol: str, start: str, end: str, adjust: str = ""):
        return daily(symbol, start, end, adjust, session=self._session)
