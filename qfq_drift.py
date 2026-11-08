#!/usr/bin/env python3
"""Snapshot a fixed forward-adjusted window and detect when it changes.

Forward adjustment factors are anchored on the most recent bar, so every
dividend or split rewrites the whole history. This script makes that
observable: same symbol, same window, hashed on each run.

Append-only log at results/qfq_drift.csv:
    run_date, source, symbol, window, sha256_first16, changed_since_last
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from bench import REGISTRY, make_session


def hash_series(df: pd.DataFrame) -> str:
    """Compute a deterministic 16-hex-char SHA-256 digest of (date, close) pairs."""
    norm = df[["date", "close"]].sort_values("date")
    payload = "\n".join(
        f"{pd.to_datetime(d).strftime('%Y-%m-%d')}:{float(c):.4f}"
        for d, c in zip(norm["date"], norm["close"])
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def record_snapshot(
    out_csv: Path,
    source_name: str,
    symbol: str,
    window: str,
    digest: str,
    run_date: str | None = None,
) -> dict:
    run_date = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    last_digest = None
    if out_csv.is_file():
        with open(out_csv, "r", encoding="utf-8", newline="") as fp:
            for row in csv.DictReader(fp):
                if (
                    row.get("source") == source_name
                    and row.get("symbol") == symbol
                    and row.get("window") == window
                ):
                    last_digest = row.get("sha256_first16")

    changed = False if last_digest is None else (last_digest != digest)
    write_header = not out_csv.is_file()
    with open(out_csv, "a", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        if write_header:
            writer.writerow(
                ["run_date", "source", "symbol", "window", "sha256_first16", "changed_since_last"]
            )
        writer.writerow([run_date, source_name, symbol, window, digest, str(changed).lower()])

    return {
        "run_date": run_date,
        "source": source_name,
        "symbol": symbol,
        "window": window,
        "sha256_first16": digest,
        "changed_since_last": changed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="eastmoney", choices=["akshare", "eastmoney", "tushare"])
    parser.add_argument("--symbol", default=os.environ.get("BENCH_SYMBOL", ""), help="Six-digit A-share code")
    parser.add_argument("--start", default=os.environ.get("BENCH_START", "20230101"))
    parser.add_argument("--end", default=os.environ.get("BENCH_END", "20231231"))
    parser.add_argument("--out", type=Path, default=Path("results/qfq_drift.csv"))
    parser.add_argument("--allow-proxy", action="store_true")
    args = parser.parse_args(argv)

    if not args.symbol:
        raise SystemExit("Pass --symbol <6-digit-code> or set BENCH_SYMBOL in environment.")

    src = REGISTRY[args.source](session=make_session(args.allow_proxy))
    res = src.daily(args.symbol, args.start, args.end, adjust="qfq")
    digest = hash_series(res.df)
    window = f"{args.start}..{args.end}"
    rec = record_snapshot(args.out, args.source, args.symbol, window, digest)
    print(rec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
