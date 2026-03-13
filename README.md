# CTA Framework

事件驱动的加密货币 CTA 回测框架，基于 Python 构建，支持完整的成本/滑点模拟、多策略扩展和绩效分析。

## 特性

- **事件驱动架构**：MarketEvent → SignalEvent → OrderEvent → FillEvent 因果链，单线程确定性回测
- **真实成本模拟**：Maker/Taker 手续费 + 固定 bps 滑点
- **ATR 仓位管理**：按每笔风险敞口（而非固定比例）计算开仓量
- **回撤熔断器**：权益从滚动峰值回撤超过阈值时暂停开仓，支持自动重置
- **ADX 趋势过滤**：市场横盘时（ADX < 阈值）不开新仓，减少震荡市磨损
- **多策略内置**：海龟系统、Supertrend、均线交叉、通道突破、均值回归
- **HTML 报告**：权益曲线、月度收益热图、完整绩效指标

## 项目结构

```
cta_framework/
├── core/
│   ├── engine.py            # BacktestEngine — 主事件循环
│   ├── events.py            # 四类冻结事件数据类
│   ├── event_queue.py       # 优先级事件队列
│   ├── portfolio.py         # PortfolioManager — 仓位管理 + 风控
│   ├── strategy.py          # Strategy 抽象基类
│   └── data_handler.py      # DataHandler 抽象基类
├── data/
│   ├── csv_handler.py       # CSV 数据加载（多品种、时间戳对齐）
│   ├── ccxt_handler.py      # CCXT 实时/历史数据（支持代理）
│   ├── data_fetcher.py      # 数据预下载 CLI 工具
│   └── cache.py             # Parquet 缓存层
├── strategies/
│   ├── turtle.py            # 海龟系统（通道突破 + ATR止损 + ADX过滤）
│   ├── supertrend.py        # Supertrend 自适应趋势跟踪
│   ├── ma_crossover.py      # 均线交叉
│   ├── breakout.py          # 通道突破
│   └── mean_reversion.py    # 布林带均值回归
├── execution/
│   ├── simulated.py         # SimulatedExecutionHandler
│   ├── slippage.py          # 固定 bps / 百分比滑点模型
│   └── commission.py        # Crypto Maker/Taker 手续费
├── analytics/
│   ├── performance.py       # Sharpe / Sortino / Calmar / MaxDD / VaR
│   ├── trade_stats.py       # 逐笔交易统计
│   ├── visualizer.py        # 权益曲线 / 月度收益热图
│   └── reporter.py          # 控制台 + HTML 报告
├── examples/
│   ├── run_turtle.py        # 海龟策略回测入口
│   └── run_supertrend.py    # Supertrend 策略回测入口
└── tests/
    ├── unit/                # 单元测试
    ├── integration/         # 集成测试
    └── fixtures/            # 合成测试数据（随机游走 BTC 8760 根 1h K 线）
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 使用内置合成数据（无需下载）

```bash
# 海龟策略（合成数据，快速验证）
python examples/run_turtle.py

# Supertrend 策略
python examples/run_supertrend.py
```

### 下载真实数据

```bash
# 直连
python -m data.data_fetcher \
    --exchange binance --symbol BTC/USDT --timeframe 1h \
    --start 2021-01-01 --end 2025-12-31 \
    --output data/raw/BTC_USDT_1h.csv

# 通过代理（或设置环境变量 https_proxy）
python -m data.data_fetcher \
    --exchange binance --symbol BTC/USDT --timeframe 1h \
    --start 2021-01-01 --end 2025-12-31 \
    --output data/raw/BTC_USDT_1h.csv \
    --proxy http://10.11.12.20:8889
```

### 海龟策略（真实数据，推荐参数）

```bash
python examples/run_turtle.py \
    --csv-dir data/raw \
    --start 2021-01-01 --end 2025-12-31 \
    --entry 480 --exit 240 \
    --atr 336 --trend 4800 \
    --adx 336 --adx-min 20 \
    --max-dd 0.25 \
    --output-dir results/turtle_final
```

### Supertrend 策略（真实数据）

```bash
python examples/run_supertrend.py \
    --csv-dir data/raw \
    --start 2021-01-01 --end 2025-12-31 \
    --atr 14 --mult 3.0 \
    --max-dd 0.25 \
    --output-dir results/supertrend_real
```

## 策略说明

### 海龟系统 (Turtle)

经典趋势跟踪策略，适合捕捉 BTC 的长周期单边行情。

| 参数 | 含义 | 1h 数据推荐值 |
|------|------|--------------|
| `--entry` | 入场通道回溯期（K 线数） | `480`（≈ 20 个交易日） |
| `--exit` | 出场通道回溯期 | `240`（≈ 10 个交易日） |
| `--atr` | ATR 计算周期 | `336`（≈ 14 天） |
| `--trend` | SMA 趋势过滤周期 | `4800`（≈ 200 天） |
| `--adx` | ADX 过滤周期（0=关闭） | `336`（≈ 14 天） |
| `--adx-min` | 最低 ADX 阈值 | `20`（<20 视为横盘不入场） |
| `--max-dd` | 回撤熔断阈值 | `0.25` |
| `--risk` | 每笔交易风险敞口（净值比例） | `0.01`（1%） |

> **注意**：1h BTC 数据使用原版参数（`--entry 20 --exit 10`）相当于只看 20 小时的突破，噪音极大。推荐使用上表的日线等价参数。

### Supertrend

自适应 ATR 趋势带，价格穿越趋势带时触发信号。参数更少，对横盘行情的自适应能力优于固定通道突破。

| 参数 | 含义 | 推荐值 |
|------|------|--------|
| `--atr` | ATR 平滑周期 | `14` |
| `--mult` | 趋势带宽度倍数 | `3.0` |
| `--trend` | 长期 SMA 宏观过滤（0=关闭） | `0` 或 `4800` |

## 风险管理

### ATR 仓位管理

仓量 = (当前净值 × 风险比例) / (ATR × 止损倍数)

例：净值 100,000 USDT，风险 1%，ATR 1,000，止损倍数 2.0 → 仓量 = 1,000 / 2,000 = 0.5 BTC

### 回撤熔断器

- 当净值从滚动峰值（默认过去 252 天）下跌超过 `max_drawdown_pct` 时，暂停新开仓
- 随着时间推移，旧峰值自动滑出窗口，熔断器自动重置
- EXIT 信号和止损单不受熔断器影响，始终执行

## 事件流

```
DataHandler.iter_bars()
    │
    ▼ MarketEvent(priority=4)
EventQueue
    │
    ├──► Strategy.calculate_signals() ──► SignalEvent(priority=3)
    │
    ├──► Portfolio.on_signal() ──────────► OrderEvent(priority=2)
    │
    ├──► Execution.on_order() ──────────► FillEvent(priority=1)
    │
    └──► Portfolio.on_fill() / Strategy.on_fill()
         PerformanceAnalyzer → ConsoleReporter + HTMLReporter
```

优先级保证因果顺序：同一时间戳内，市场数据先处理，成交回报最后处理。

## 运行测试

```bash
# 全部测试
pytest tests/ -v

# 仅单元测试
pytest tests/unit/ -v

# 集成测试（需要 tests/fixtures/ 下的合成数据）
pytest tests/integration/ -v
```

## 输出报告

回测完成后，在 `--output-dir` 指定目录下生成：

- `report.html` — 完整 HTML 绩效报告（含交易列表、指标、图表）
- `equity_curve.png` — 权益曲线
- `monthly_returns.png` — 月度收益热图

## 扩展自定义策略

继承 `core.strategy.Strategy`，实现 `calculate_signals()` 方法：

```python
from core.strategy import Strategy
from core.events import MarketEvent, SignalEvent, SignalDirection

class MyStrategy(Strategy):
    @property
    def warmup_period(self) -> int:
        return 50  # 预热所需最少 K 线数

    def calculate_signals(self, event: MarketEvent) -> list[SignalEvent]:
        bars = list(self.bars(event.symbol))
        # ... 计算逻辑 ...
        return [SignalEvent(
            symbol=event.symbol,
            timestamp=event.timestamp,
            direction=SignalDirection.LONG,
            strength=0.02,  # stop_distance / price，用于 ATR 仓位计算
        )]
```
