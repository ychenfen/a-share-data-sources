"""Eastmoney push2his kline endpoint. No credentials.

The reason this adapter is longer than the requests call it wraps: push2his
answers a rate-limited client with HTTP 200 and an empty `klines` list. Parsed
naively that becomes an empty DataFrame, which downstream looks identical to
"this symbol has no history" and turns into a silent gap. Every empty payload
is raised as FetchError here so the benchmark counts it as a failure.
"""
import time

import pandas as pd
import requests

from .base import FetchError, FetchResult
from ._symbols import eastmoney_secid

name = "eastmoney"
needs_token = False

_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_FQT = {"": "0", "qfq": "1", "hfq": "2"}
_COLS = ["date", "open", "close", "high", "low", "volume", "amount",
         "amplitude", "pct_chg", "chg", "turnover"]


def available() -> bool:
    return True


def daily(symbol: str, start: str, end: str, adjust: str = "hfq",
          session=None) -> FetchResult:
    if adjust not in _FQT:
        raise ValueError(f"unsupported adjust: {adjust!r}")
    params = {
        "secid": eastmoney_secid(symbol),
        "klt": "101",
        "fqt": _FQT[adjust],
        "beg": start,
        "end": end,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    t0 = time.perf_counter()
    try:
        r = (session or requests).get(_URL, params=params,
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        raise FetchError(f"eastmoney request failed: {exc}") from exc
    elapsed = time.perf_counter() - t0

    klines = ((payload.get("data") or {}).get("klines")) or []
    if not klines:
        # HTTP 200 with nothing in it is the block signal, not an empty history.
        raise FetchError("eastmoney returned HTTP 200 with empty klines "
                         "(rate limited or blocked)")

    rows = [k.split(",") for k in klines]
    df = pd.DataFrame(rows, columns=_COLS[: len(rows[0])])
    for c in df.columns:
        if c != "date":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    df = df[["date", "open", "high", "low", "close", "volume"]].sort_values("date")
    return FetchResult(df=df.reset_index(drop=True), elapsed_s=elapsed,
                       n_rows=len(df), raw_fields=_COLS[: len(rows[0])])


class EastmoneySource:
    """Registry-facing wrapper. bench.py constructs sources with a shared
    requests.Session so connection reuse does not show up as latency variance."""

    name = name
    needs_token = needs_token

    def __init__(self, session=None):
        self._session = session

    def available(self) -> bool:
        return available()

    def daily(self, symbol: str, start: str, end: str, adjust: str = "hfq"):
        return daily(symbol, start, end, adjust, session=self._session)
