"""Wall-clock latency per source, one symbol at a time, strictly sequential.

Sequential on purpose. Concurrency is measured separately in rate_limit; mixing
the two would report a latency number that is really a queueing artifact.
Reports median and p90 rather than mean — these distributions have a long right
tail (one retry dominates the mean and tells you nothing about a typical call).
"""
import statistics
import time

import pandas as pd

from sources.base import FetchError


def run(srcs, symbols, args) -> pd.DataFrame:
    rows = []
    for src in srcs:
        samples, failures = [], 0
        for sym in symbols:
            try:
                res = src.daily(sym, args.start, args.end, adjust=args.adjust)
                samples.append(res.elapsed_s)
            except FetchError:
                failures += 1
            time.sleep(getattr(args, "sleep", 0.2))
        rows.append({
            "source": src.name,
            "n_ok": len(samples),
            "n_failed": failures,
            "median_s": round(statistics.median(samples), 3) if samples else None,
            "p90_s": round(_p90(samples), 3) if samples else None,
            "max_s": round(max(samples), 3) if samples else None,
        })
    return pd.DataFrame(rows)


def _p90(xs):
    if not xs:
        return float("nan")
    s = sorted(xs)
    # nearest-rank; with n<10 this returns the max, which is the honest answer
    # rather than an interpolated number implying precision we do not have.
    return s[min(len(s) - 1, int(round(0.9 * len(s) + 0.5)) - 1)]
