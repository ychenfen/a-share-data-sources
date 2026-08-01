"""Success rate per source, and — more useful — how it fails.

The distinction that matters for A-share sources is between a call that errors
and a call that returns HTTP 200 with nothing in it. The second kind is what
corrupts a pipeline, because it parses cleanly into an empty frame and looks
like "no history for this symbol". Adapters raise FetchError for both, but the
message is preserved here so the two are countable separately.
"""
import time

import pandas as pd

from sources.base import FetchError


def run(srcs, symbols, args) -> pd.DataFrame:
    rows = []
    for src in srcs:
        ok = empty = errored = 0
        reasons = {}
        for sym in symbols:
            try:
                res = src.daily(sym, args.start, args.end, adjust=args.adjust)
                if res.n_rows == 0:
                    empty += 1
                else:
                    ok += 1
            except FetchError as exc:
                msg = str(exc)
                if "empty" in msg.lower() or "blocked" in msg.lower():
                    empty += 1
                else:
                    errored += 1
                reasons[_bucket(msg)] = reasons.get(_bucket(msg), 0) + 1
            time.sleep(getattr(args, "sleep", 0.2))
        n = len(symbols)
        rows.append({
            "source": src.name,
            "n": n,
            "ok": ok,
            "empty_or_blocked": empty,
            "errored": errored,
            "success_rate": round(ok / n, 3) if n else None,
            "top_failure": max(reasons, key=reasons.get) if reasons else None,
        })
    return pd.DataFrame(rows)


def _bucket(msg: str) -> str:
    m = msg.lower()
    for key in ("timeout", "empty", "blocked", "not installed", "token", "connection"):
        if key in m:
            return key
    return "other"
