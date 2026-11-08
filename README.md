# A-Share Market Data Sources, Compared and Benchmarked

<p align="left">
  <a href="README.md"><strong>English</strong></a> ·
  <a href="README_CN.md">简体中文</a>
</p>

<p align="left">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="Code License: MIT" />
  <img src="https://img.shields.io/badge/docs-CC%20BY%204.0-lightgrey.svg" alt="Docs License: CC BY 4.0" />
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB.svg" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/sources-akshare%20%7C%20tushare%20%7C%20eastmoney%20%7C%20sina-10A37F.svg" alt="Data Sources" />
</p>

Four commonly used ways to pull Chinese A-share OHLCV data — **akshare**, **tushare pro**, **eastmoney push2his**, and **sina finance** — measured on the same symbols, the same date range, and the same machine.

This repository does not host market data. It hosts a measurement script and the tables it produces, so you can re-run the numbers on your own network instead of trusting mine.

## Why this exists

Every A-share data question in English ends at "just use akshare". That answer skips the part that costs you a week: the four sources disagree with each other, and they disagree in ways that quietly corrupt a backtest rather than raising an exception.

Three failure modes drove this repo:

1. Concurrent requests against the eastmoney kline endpoint get the client blocked. Not throttled with a `429` — blocked, with the endpoint returning empty payloads that parse fine and become silent gaps in a DataFrame.
2. Forward-adjusted (前复权) prices are recomputed from the present backwards. The same symbol, same date range, pulled six months apart, returns different numbers. Any backtest keyed on forward-adjusted prices is not reproducible unless you pin a snapshot.
3. Cross-source close prices agree on almost every trading day and then disagree on ex-dividend days, which is exactly where an unadjusted-vs-adjusted mismatch hides.

The benchmark script is built to surface these three, not to declare a winner.

## Comparison

Measured from a mainland China host. Everything in this table is produced by `bench.py` and will drift — re-run it rather than citing it.

| | akshare | tushare pro | eastmoney (push2his) | sina finance |
|---|---|---|---|---|
| **Access** | Python package | HTTP API + SDK | undocumented public JSON | undocumented public JSON |
| **Token required** | No | **Yes** (points-tiered) | No | No |
| **Daily history depth** | back to listing | back to listing | back to listing | paged, ~1000 bars per request |
| **Intraday bars** | 1/5/15/30/60 min via upstream wrappers | gated behind higher point tiers | 1/5/15/30/60 min, short lookback for 1-min | short lookback only |
| **Adjustment** | `adjust="qfq"` / `"hfq"` / `""` | raw prices + a separate adjustment-factor table you apply yourself | server-side, `fqt=0/1/2` | raw only, adjust it yourself |
| **Rate limiting** | inherits whatever the upstream endpoint enforces; no local queue | documented per-minute quota tied to your point tier | undocumented; parallel requests trigger blocks | undocumented; realtime endpoint checks `Referer` |
| **Failure mode** | breaks when an upstream response schema changes | fails loudly with a quota error | fails **quietly** with an empty payload | fails quietly with a truncated series |
| **Best fit** | exploration, and the breadth of derived datasets nothing else has | pipelines that must be reproducible and auditable | bulk OHLCV where you want adjustment done server-side | fallback when the primary source stops answering |

### On "stability"

Two different things get called stability, and they trade off against each other.

*Contract stability* — will the field names and semantics still be the same next quarter. tushare wins this outright, because it is a product with a documented schema and a paying user base. The two undocumented JSON endpoints have been stable in practice for years, but nothing obliges them to stay that way.

*Access stability* — will you still be allowed to call it. Here the ordering flips: the free endpoints are the ones that decide unilaterally to stop answering you, and the signal that this happened is an HTTP 200 with nothing in it.

akshare sits in an awkward middle. It is the most convenient of the four and it is the one most likely to break on a Tuesday, because it is a wrapper over sources it does not control. That is not a criticism of the project — it is the structural cost of the wrapper design, and worth accepting for exploratory work.

## The adjustment trap

The single most expensive mistake in this area is not picking a slow data source. It is picking the wrong adjustment mode and never noticing.

- **Unadjusted (不复权)** prices carry the ex-dividend gap. Compute a next-day return across an ex-dividend date and you book a loss the holder never took.
- **Forward-adjusted (前复权)** prices are recomputed every time a dividend or split lands, because the factor chain anchors on the latest bar. Historical values are therefore not stable over calendar time. On a long-listed name with a history of large stock dividends, extending the chain far enough back can even produce non-positive prices.
- **Backward-adjusted (后复权)** prices anchor on the listing date, so history is stable and reproducible, but the numbers on the right-hand side of the series stop matching what anyone sees on a screen.

None of these is correct in general. Backward adjustment is the reproducible choice for research; forward adjustment is the readable choice for display; unadjusted is what you want only when you are explicitly modeling cash flows. Mixing two of them in one pipeline — which happens the moment two data sources with different defaults meet — produces errors concentrated on a handful of days per year, which is small enough to survive a smoke test and large enough to flip a result.

`qfq_drift.py` in this repo demonstrates the instability directly: it hashes a fixed forward-adjusted window and re-checks it on a schedule.

> Further reading: [qfq vs hfq — which adjusted price should an A-share backtest use?](https://stock.yuchenxu.cn/en/guide/a-share-forward-backward-price-adjustment), which walks through what specifically breaks when you pick the wrong one ([中文版](https://stock.yuchenxu.cn/guide/qianfuquan-houfuquan-qubie)).

## Quick start

```bash
git clone https://github.com/ychenfen/a-share-data-sources.git
cd a-share-data-sources
pip install -r requirements.txt
cp .env.example .env            # then edit .env
cp symbols.txt.example symbols.txt
```

`.env`:

```bash
# Required only if you want tushare included in the run.
TUSHARE_TOKEN=

# One six-digit A-share code per line. Not shipped with the repo —
# pick your own sample so the results are yours.
BENCH_SYMBOLS_FILE=symbols.txt

BENCH_START=20230101
BENCH_END=20241231
```

Run it:

```bash
python bench.py --sources akshare,eastmoney,sina --out results/
python bench.py --sources tushare --out results/     # needs TUSHARE_TOKEN
```

Run offline unit tests:

```bash
pytest -q
```

### Minimal per-source calls

All four, reduced to the smallest call that returns daily bars. `SYMBOL` is read from the environment — no codes are hard-coded anywhere in this repo.

```python
import os
SYMBOL = os.environ["BENCH_SYMBOL"]          # six-digit A-share code
START, END = os.environ["BENCH_START"], os.environ["BENCH_END"]
```

**akshare**

```python
import akshare as ak

df = ak.stock_zh_a_hist(
    symbol=SYMBOL, period="daily",
    start_date=START, end_date=END,
    adjust="hfq",                            # "" = unadjusted, "qfq", "hfq"
)
```

**tushare pro**

```python
import tushare as ts

pro = ts.pro_api(os.environ["TUSHARE_TOKEN"])
suffix = "SH" if SYMBOL.startswith(("6", "9")) else "SZ"
raw = pro.daily(ts_code=f"{SYMBOL}.{suffix}", start_date=START, end_date=END)
adj = pro.adj_factor(ts_code=f"{SYMBOL}.{suffix}", start_date=START, end_date=END)
# tushare returns unadjusted prices; you join adj_factor and apply it yourself.
```

**eastmoney push2his**

```python
import requests

market = "1" if SYMBOL.startswith(("6", "9")) else "0"
r = requests.get(
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    params={
        "secid": f"{market}.{SYMBOL}",
        "klt": "101",                        # 101=daily, 5=5min, 15, 30, 60
        "fqt": "2",                          # 0=none, 1=forward, 2=backward
        "beg": START, "end": END,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    },
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=10,
)
klines = (r.json().get("data") or {}).get("klines") or []
# An empty `klines` with HTTP 200 is the block signal. Treat it as an error.
```

**sina finance**

```python
prefix = "sh" if SYMBOL.startswith(("6", "9")) else "sz"
r = requests.get(
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
    "/CN_MarketData.getKLineData",
    params={"symbol": f"{prefix}{SYMBOL}", "scale": "240", "ma": "no", "datalen": "1023"},
    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"},
    timeout=10,
)
# Prices are unadjusted. `datalen` is capped — page backwards for longer histories.
# The realtime endpoint (hq.sinajs.cn) rejects requests without a sina Referer.
```

## What the benchmark measures

Five dimensions, each with its own module. See [`docs/methodology.md`](docs/methodology.md) for the full definitions.

| Dimension | Question it answers | Output |
|---|---|---|
| Latency | how long one daily-bar request takes, p50 / p90 | `results/latency.csv` |
| Reliability | success rate over N sequential requests, counting empty-but-200 as failure | `results/reliability.csv` |
| Rate ceiling | at what concurrency the source stops answering (opt-in, off by default) | `results/rate_limits.csv` |
| Coverage | earliest bar available, trading-day count, silent start truncation | `results/coverage.csv` |
| Agreement | pairwise close-price mismatch between sources, plus whether the disagreement is explained by a different adjustment convention or by the data itself differing | `results/agreement.csv` |

All five are merged into `results/summary.md`, which is what the comparison table above is generated from.

## Measurement notes

**Disable your proxy.** Timing a remote endpoint through a local HTTP proxy measures the proxy. On one mainland China host, a control endpoint reported roughly 3.1 s TTFB through a local proxy and roughly 150 ms direct — a 20x error introduced entirely by the measurement path. `bench.py` sets `trust_env=False` by default and refuses to record timings if proxy environment variables are set, unless you pass `--allow-proxy`.

**Be a reasonable client.** Default concurrency is 1. The rate-ceiling probe is behind `--probe-limits`, stops at the first refusal, and sleeps before exiting. Do not run it in a loop. Getting yourself blocked is easy and the block is not always brief.

**Results are local and dated.** Every output file carries a header with the timestamp, the resolved package versions, the git commit, and a coarse network location. Numbers taken from a different country will not match, because at least two of these endpoints behave differently by origin.

## Limitations

Worth stating plainly, since the point of the repo is measurement honesty:

- The sample is whatever symbols you put in `symbols.txt`. A dozen names is not the market. Coverage and agreement results in particular are sensitive to whether your sample includes names with heavy corporate-action history.
- The rate-ceiling number is a lower bound observed once, not a documented limit. It moves with time of day and with whatever the endpoint owner decided this week.
- Agreement testing compares close prices only. Volume, turnover and amount fields have their own unit and rounding differences between sources, which this version does not check. That was a scope cut, not a claim that they agree.
- The adjustment-versus-data split in `agreement.csv` is inferred from price behaviour, not read off a corporate-action calendar. The test is whether the ratio between two sources is piecewise constant: a real adjustment difference steps on a corporate action and stays flat in between, while genuinely different data wanders. It cannot name the action, and it deliberately refuses to call anything an adjustment when steps appear on more than 5% of days — at that rate the ratio is drifting, not stepping. See `tests/test_agreement.py`.
- Nothing here evaluates data *correctness* against an authoritative reference, because there is no free authoritative reference to check against. Cross-source agreement is a weaker proxy: four sources can be wrong together, and two of them share upstream plumbing.

## Contributing

Useful contributions, roughly in order of value: a result set from outside mainland China; a source adapter that follows the `Source` protocol in `sources/base.py`; a corporate-action case where two sources disagree and you can say which one is right.

Please do not commit market data files. Aggregate measurements only.

## Citation

```bibtex
@software{xu2026asharedatasources,
  author       = {Xu, Yuchen},
  title        = {a-share-data-sources: Empirical Benchmark of Chinese A-Share Market Data Sources},
  year         = {2026},
  publisher    = {GitHub},
  url          = {https://github.com/ychenfen/a-share-data-sources}
}
```

## License

Code is [MIT](LICENSE). Measurement outputs under `results/` and documentation are [CC BY 4.0](LICENSE-docs) — reuse them, with attribution back to this repository.

---

## 中文摘要（完整版见 [README_CN.md](README_CN.md)）

这个仓库比较四种取 A 股行情数据的方式：akshare、tushare pro、东方财富 push2his 接口、新浪财经接口。同样的股票池、同样的时间区间、同一台机器，测延迟、成功率、并发上限、覆盖范围，以及四个源之间的收盘价一致性。

仓库不存放行情数据，只存放测量脚本和它产出的表格。数据源的行为会随时间和网络位置变化，所以表里的数字应该被重跑，而不是被引用。

几个已经踩过的坑：

东方财富的 K 线接口并发抓取会被封，但封的表现不是 429，而是 HTTP 200 配一个空的 klines 数组——它能被正常解析，然后变成 DataFrame 里一段谁也没注意到的缺口。新浪的实时接口会校验 Referer，日线接口单次返回条数有上限，需要自己翻页。

复权方式的问题比数据源选择更贵。前复权因子从当前时点往回算，每次分红送股都会重算全部历史价格，所以同一段前复权数据半年后再取数值不同，回测不可复现；送转历史多的老票往回推得足够远，甚至可能算出非正的价格。后复权锚在上市首日，历史稳定、适合研究，代价是右端价格和行情软件上看到的对不上。不复权则保留除息缺口，跨除息日算次日收益会把除权当成亏损。

三者没有哪个绝对正确，错的是在一条管线里混用两种——两个默认口径不同的数据源接在一起就会发生，而且误差只集中在一年里的几天，小到能通过冒烟测试，大到能改变结论。

延伸阅读：[前复权、后复权、不复权：选错一个，回测结果就是错的](https://stock.yuchenxu.cn/guide/qianfuquan-houfuquan-qubie)（含三种复权方式对照表和三步自查）、[A股历史行情数据源实测对比](https://stock.yuchenxu.cn/guide/a-gu-hangqing-shujuyuan-shice)（本仓库的配套文章，含四个通道的限流实测）
