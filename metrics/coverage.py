"""How much history each source actually returns for the requested window.

Reports the returned span rather than a pass/fail, because the interesting
failures here are partial: Sina caps `datalen` per request, so it silently hands
back a truncated series that looks complete. Comparing first_date against the
requested start is what surfaces that.
"""
import time

import pandas as pd

from sources.base import FetchError


def run(srcs, symbols, args) -> pd.DataFrame:
    rows = []
    for src in srcs:
        for sym in symbols:
            rec = {"source": src.name, "symbol": sym}
            try:
                res = src.daily(sym, args.start, args.end, adjust=args.adjust)
                d = res.df["date"]
                rec.update({
                    "n_rows": res.n_rows,
                    "first_date": str(d.min().date()) if len(d) else None,
                    "last_date": str(d.max().date()) if len(d) else None,
                    "n_fields": len(res.raw_fields),
                    "truncated_at_start": _truncated(d, args.start),
                    "error": None,
                })
            except FetchError as exc:
                rec.update({"n_rows": 0, "first_date": None, "last_date": None,
                            "n_fields": 0, "truncated_at_start": None,
                            "error": str(exc)[:120]})
            rows.append(rec)
            time.sleep(getattr(args, "sleep", 0.2))
    return pd.DataFrame(rows)


def _truncated(dates, start) -> bool | None:
    """True if the series starts materially later than requested.

    Three calendar days of slack: the requested start is often a weekend or a
    holiday, and treating that as truncation would flag every clean run.
    """
    if not len(dates):
        return None
    want = pd.to_datetime(start, format="%Y%m%d", errors="coerce")
    if pd.isna(want):
        return None
    return bool((dates.min() - want).days > 3)
