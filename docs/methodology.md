# Benchmark Methodology (`docs/methodology.md`)

This document specifies how each of the five benchmark dimensions in `bench.py` is defined, measured, and interpreted.

---

## 1. Latency (`metrics/latency.py`)

- **Protocol**: Strictly sequential (`concurrency = 1`) across the sampled symbols with a configurable inter-request sleep (`--sleep`, default `1.5s`).
- **Why sequential**: Measuring latency under concurrent load conflates network/server response time with client-side connection pool queueing and server-side rate throttling.
- **Reported statistics**:
  - `median_s` (p50): Typical single-symbol daily-bar call latency.
  - `p90_s`: Nearest-rank 90th percentile (`s[min(n - 1, round(0.9 * n + 0.5) - 1)]`). For small sample sizes (`n < 10`), nearest-rank returns the sample maximum rather than an interpolated number that implies precision we do not have.
  - `max_s`: Worst-case call latency observed in the run.
- **Proxy guard**: `bench.py` sets `requests.Session.trust_env = False` and aborts if `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` environment variables are present unless `--allow-proxy` is explicitly passed.

---

## 2. Reliability & Failure Mode Classification (`metrics/reliability.py`)

- **Protocol**: Counts outcomes over $N$ sequential daily-bar requests and separates loud errors from silent empty payloads.
- **Why this matters**: Several undocumented JSON endpoints (most notably Eastmoney `push2his`) respond to rate-limited or blocked clients with **HTTP 200 and an empty `klines` list**. A naive parser turns that into an empty `DataFrame` without raising an exception, silently creating missing-data gaps in downstream backtests.
- **Columns in `results/reliability.csv`**:
  - `ok`: Requests returning a non-empty OHLCV frame with all required columns.
  - `empty_or_blocked`: Requests returning HTTP 200 with an empty payload or explicit block signal.
  - `errored`: Requests failing with HTTP status errors, timeouts, or schema mismatches.
  - `success_rate`: `ok / n`.
  - `top_failure`: Most frequent failure bucket (`timeout`, `empty`, `blocked`, `not installed`, `token`, `connection`, `other`).

---

## 3. Rate Ceiling (`metrics/rate_limit.py`)

- **Opt-in only (`--probe-limits`)**: Off by default because probing concurrency ceilings can get your exit IP temporarily blocked.
- **Protocol**: Ramps `ThreadPoolExecutor` concurrency across `LADDER = (1, 2, 4, 8, 16)`, firing `3 * c` burst requests at each step.
- **Stopping rule**: Stops immediately at the first concurrency level where any request raises `FetchError` or returns 0 rows, and cools down for `30s` before testing the next source.

---

## 4. Historical Coverage & Silent Truncation (`metrics/coverage.py`)

- **Protocol**: Requests `[start, end]` for each symbol and inspects the returned date span (`first_date`, `last_date`, `n_rows`, `n_fields`).
- **Truncation detection (`truncated_at_start`)**: Flags `True` when `first_date - requested_start > 3 calendar days` (allowing 3 days of slack for weekends/holidays). This surfaces endpoints like Sina Finance (`CN_MarketData.getKLineData`), which cap `datalen` (~1023 bars per request) and silently return a truncated suffix of the requested window.

---

## 5. Pairwise Close-Price Agreement & Adjustment-Step Inference (`metrics/agreement.py`)

When two data sources disagree on historical close prices, the disagreement comes from one of two fundamentally different causes:
1. **Different adjustment conventions** (e.g., unadjusted vs. backward-adjusted, or different corporate-action factor anchors).
2. **Genuinely different underlying price data** (e.g., rounding differences, bad ticks, or corrupted vendor series).

### How `agreement.py` Separates the Two Without an External Calendar

For each pair of sources $(A, B)$ and each symbol, we align daily close prices on their inner-joined trading dates and compute the day-by-day ratio:

$$r_t = \frac{\text{Close}_{A,t}}{\text{Close}_{B,t}}$$

- **Relative mismatch (`mismatch_days`)**: Any trading day where $\frac{|A_t - B_t|}{|B_t|} > 10^{-4}$ (`TOL = 1e-4`).
- **Ratio step (`adjustment_steps`)**: Any trading day where the day-over-day relative change in $r_t$ exceeds `STEP_TOL = 1e-3`:
  $$\left|\frac{r_t}{r_{t-1}} - 1\right| > 10^{-3}$$
- **Piecewise-constant check (`flat_between`)**: Partition the series into contiguous segments between steps. Within every segment, the ratio must remain flat:
  $$\frac{\max_{t \in \text{seg}} r_t}{\min_{t \in \text{seg}} r_t} - 1 \le 10^{-3}$$
- **Sparsity guard (`MAX_STEP_RATE = 0.05`)**: Corporate actions occur at most a few times per year. If "steps" appear on more than 5% of compared trading days, the ratio is wandering every day rather than stepping on ex-dividend dates.
- **Decision rule (`explained_by_adjustment`)**:
  $$\texttt{explained\_by\_adjustment} = (\texttt{mismatch\_days} > 0) \land (0 < \texttt{steps} \le 0.05 \times N) \land \texttt{flat\_between}$$

This logic is pinned by deterministic synthetic tests in [`tests/test_agreement.py`](../tests/test_agreement.py).
