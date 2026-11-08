# A 股行情数据源实测对比与一致性基准 (`a-share-data-sources`)

<p align="left">
  <a href="README.md">English</a> ·
  <a href="README_CN.md"><strong>简体中文</strong></a>
</p>

<p align="left">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="Code License: MIT" />
  <img src="https://img.shields.io/badge/docs-CC%20BY%204.0-lightgrey.svg" alt="Docs License: CC BY 4.0" />
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB.svg" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/sources-akshare%20%7C%20tushare%20%7C%20eastmoney%20%7C%20sina-10A37F.svg" alt="Data Sources" />
</p>

本仓库对四种最常用的 A 股日线行情获取方式——**akshare**、**tushare pro**、**东方财富 `push2his` 接口**、**新浪财经接口**——在相同的股票样本、相同的时间区间、同一台机器上进行可复现的实测基准测试。

**本仓库不存放任何行情数据**，仅提供标准化测量脚本、复权阶跃检测算法与单元测试，方便你在自己的网络环境下重跑真实指标。

---

## 为什么要做这个基准测试？

几乎所有关于“A 股怎么拉行情”的回答都会停留在“直接用 akshare”。但真正把数据接进研究管线后，以下三个隐蔽的故障模式往往会浪费掉整整一周的排查时间：

1. **东方财富 `push2his` 的静默封禁（HTTP 200 + 空数组）**：并发请求东方财富 K 线接口触发风控时，服务端不会返回 `429 Too Many Requests`，而是返回状态码 `200 OK` 配一个空的 `klines: []`。如果不做专门拦截，解析器会安静地生成空 `DataFrame`，在面板数据里留下毫无报错的缺失段。
2. **前复权（`qfq`）的时间漂移陷阱**：前复权因子以“最新交易日”为锚点向历史倒推。每次发生分红送转，全部历史前复权价格都会被重写。同一个代码、同一段历史区间，相隔半年拉取会得到不同的数字——任何基于动态拉取前复权价格的回测天然不可复现（本仓库的 `qfq_drift.py` 专门用于哈希追踪这一漂移）。
3. **跨数据源的除权日断层**：不同数据源的收盘价在 99% 的交易日完全一致，偏偏在除权除息日出现跳变。通过计算两源收盘价之比 $r_t = A_t / B_t$ 是否呈**分段常数（Piecewise Constant）**，`metrics/agreement.py` 能在不依赖外部除权日历的情况下，自动区分“复权口径差异”与“底层脏数据差异”。

---

## 四大通道实测对比

| 维度 | akshare | tushare pro | 东方财富 (`push2his`) | 新浪财经 (`sina`) |
|---|---|---|---|---|
| **接入方式** | Python 开源包 | 官方 HTTP API + SDK | 未公开文档的公共 JSON 接口 | 未公开文档的公共 JSON 接口 |
| **是否需要 Token** | 否 | **是**（按积分分级） | 否 | 否 |
| **日线历史深度** | 可追溯至上市首日 | 可追溯至上市首日 | 可追溯至上市首日 | 单次上限约 1023 根 K 线，更长需翻页 |
| **复权支持** | `adjust="qfq"` / `"hfq"` / `""` | 返回不复权原价 + 独立 `adj_factor` 表 | 服务端复权 `fqt=0/1/2` | 仅返回不复权价格，需自行计算复权 |
| **限流机制** | 取决于底层所调上游接口 | 按积分等级明确规定每分钟配额 | 未公开；并发抓取极易触发封禁 | 未公开；实时接口强制校验 `Referer` |
| **典型失败表现** | 上游网页/接口改版时抛异常 | 配额超限时明确报错 | **静默失败**（HTTP 200 + 空 `klines`） | **静默截断**（超出 `datalen` 的早期历史丢失） |
| **最佳适用场景** | 快速探索、获取丰富的衍生/另类数据集 | 要求严格可复现、可审计的研究管线 | 需要服务端直接返回复权结果的批量日线 | 主数据源故障时的备用对账源 |

---

## 快速开始

```bash
git clone https://github.com/ychenfen/a-share-data-sources.git
cd a-share-data-sources
pip install -r requirements.txt
cp .env.example .env
cp symbols.txt.example symbols.txt   # 在 symbols.txt 中填入你自选的 6 位代码（每行一个）
```

运行基准测试：

```bash
python bench.py --sources akshare,eastmoney,sina --out results/
python bench.py --sources tushare --out results/     # 需在环境变量或 .env 中配置 TUSHARE_TOKEN
```

运行离线单元测试（验证分段常数复权检测算法）：

```bash
pytest -v
```

---

## 五大评测维度说明

详见 [`docs/methodology.md`](docs/methodology.md)：

1. **延迟 (`results/latency.csv`)**：严格单线程顺序请求（`concurrency=1`），输出 `median_s` (p50)、`p90_s` 与 `max_s`。默认禁用本地代理（`trust_env=False`），防止代理转发延迟污染测量结果。
2. **可靠性与故障分类 (`results/reliability.csv`)**：显式将“HTTP 200 但返回空数组”统计为 `empty_or_blocked` 失败，而非正常空结果。
3. **并发上限探测 (`results/rate_limits.csv`)**：默认关闭（需传 `--probe-limits` 开启），按 `(1, 2, 4, 8, 16)` 阶梯递增并发，遇到首次拒绝立即停止并冷却 30 秒。
4. **覆盖度与静默截断 (`results/coverage.csv`)**：对比返回序列的首日 `first_date` 与请求起点 `start`，自动标记新浪等单次条数受限接口的头部截断（`truncated_at_start`）。
5. **跨源一致性与复权归因 (`results/agreement.csv`)**：两两比对收盘价，计算比值序列 $r_t = A_t / B_t$ 的阶跃次数与段内平坦度，自动判定不一是源于复权口径差异（`explained_by_adjustment = True`）还是底层数据本身不一致。

---

## 延伸阅读

- [前复权、后复权、不复权：选错一个，回测结果就是错的](https://stock.yuchenxu.cn/guide/qianfuquan-houfuquan-qubie)（English: [qfq vs hfq — which adjusted price should an A-share backtest use?](https://stock.yuchenxu.cn/en/guide/a-share-forward-backward-price-adjustment)）
- [A 股历史行情数据源实测对比](https://stock.yuchenxu.cn/guide/a-gu-hangqing-shujuyuan-shice)

## 开源协议

代码部分采用 [MIT License](LICENSE) 开源；文档与测量报告结构采用 [CC BY 4.0](LICENSE-docs) 协议。
