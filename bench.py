#!/usr/bin/env python3
"""Benchmark A-share market data sources.

No credentials are stored in this file. TUSHARE_TOKEN is read from the
environment (or a local .env that is gitignored) and is never written
to any output file.
"""
import argparse, json, os, platform, random, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

import requests

from sources import src_akshare, src_eastmoney, src_sina, src_tushare
from metrics import latency, reliability, rate_limit, coverage, agreement

REGISTRY = {
    "akshare":   src_akshare.AkshareSource,
    "tushare":   src_tushare.TushareSource,     # reads os.environ["TUSHARE_TOKEN"]
    "eastmoney": src_eastmoney.EastmoneySource,
    "sina":      src_sina.SinaSource,
}
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY")


def guard_proxy(allow: bool) -> None:
    """Timing through a local proxy measures the proxy, not the endpoint.
    Refuse to record numbers unless the caller explicitly opts in."""
    live = [v for v in PROXY_VARS if os.environ.get(v)]
    if live and not allow:
        sys.exit(
            f"Proxy env vars set ({', '.join(live)}). Latency numbers taken "
            f"through a proxy are not comparable — unset them, or pass "
            f"--allow-proxy to record anyway (results will be flagged)."
        )
    if not allow:
        for v in PROXY_VARS:
            os.environ.pop(v, None)


def make_session(allow_proxy: bool) -> requests.Session:
    s = requests.Session()
    s.trust_env = allow_proxy          # ignore *_proxy and .netrc when False
    s.headers["User-Agent"] = "a-share-data-sources/0.1 (+github.com/<you>)"
    return s


def load_symbols(path: str, k: int, seed: int) -> list[str]:
    codes = [ln.strip() for ln in Path(path).read_text().splitlines()
             if ln.strip() and not ln.startswith("#")]
    if not codes:
        sys.exit(f"{path} is empty. Add one six-digit code per line.")
    rng = random.Random(seed)          # fixed seed => same sample across runs
    return codes if len(codes) <= k else rng.sample(codes, k)


def provenance(args) -> dict:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        commit = "unknown"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "proxy_allowed": args.allow_proxy,
        "symbols_n": args.n_symbols,
        "seed": args.seed,
        "window": f"{args.start}..{args.end}",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sources", default="akshare,eastmoney,sina")
    p.add_argument("--symbols-file", default=os.environ.get("BENCH_SYMBOLS_FILE", "symbols.txt"))
    p.add_argument("--n-symbols", type=int, default=12)
    p.add_argument("--seed", type=int, default=20260801)
    p.add_argument("--start", default=os.environ.get("BENCH_START", "20230101"))
    p.add_argument("--end",   default=os.environ.get("BENCH_END",   "20241231"))
    p.add_argument("--repeats", type=int, default=10)
    p.add_argument("--sleep", type=float, default=1.5)
    p.add_argument("--probe-limits", action="store_true",
                   help="Ramp concurrency until the source refuses. Stops on "
                        "first failure. Can get your IP blocked. Off by default.")
    p.add_argument("--allow-proxy", action="store_true")
    p.add_argument("--out", default="results")
    args = p.parse_args()

    guard_proxy(args.allow_proxy)
    session = make_session(args.allow_proxy)
    symbols = load_symbols(args.symbols_file, args.n_symbols, args.seed)

    srcs = []
    for name in [s.strip() for s in args.sources.split(",") if s.strip()]:
        if name not in REGISTRY:
            sys.exit(f"unknown source: {name}")
        src = REGISTRY[name](session=session)
        if src.needs_token and not src.available():
            print(f"[skip] {name}: token not set, skipping", file=sys.stderr)
            continue
        srcs.append(src)

    out = Path(args.out); (out / "raw").mkdir(parents=True, exist_ok=True)
    meta = provenance(args)

    tables = {
        "latency":     latency.run(srcs, symbols, args),
        "reliability": reliability.run(srcs, symbols, args),
        "coverage":    coverage.run(srcs, symbols, args),
        "agreement":   agreement.run(srcs, symbols, args),
    }
    if args.probe_limits:
        tables["rate_limits"] = rate_limit.run(srcs, symbols[0], args)

    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2))
    write_summary(out / "summary.md", meta, tables)   # renders the README table
    print(f"wrote {out/'summary.md'}")


if __name__ == "__main__":
    main()
