# CTA 回测框架实现计划

## Context
开发一个事件驱动的加密货币 CTA 回测框架，基于 Python，支持完整的成本/滑点模拟。目标是构建一个模块化、可扩展的量化交易回测系统，从数据读取到策略信号，再到订单执行和绩效分析，全流程覆盖。

---

## 项目结构

```
cta_framework/
├── core/
│   ├── __init__.py
│   ├── engine.py                  # BacktestEngine - 主编排器
│   ├── events.py                  # 事件数据类 (Market/Signal/Order/Fill)
│   ├── event_queue.py             # 优先级事件队列
│   ├── data_handler.py            # 抽象 DataHandler 基类
│   ├── strategy.py                # 抽象 Strategy 基类
│   ├── portfolio.py               # PortfolioManager
│   └── execution_handler.py      # 抽象 ExecutionHandler 基类
│
├── data/
│   ├── __init__.py
│   ├── csv_handler.py             # CSVDataHandler
│   ├── ccxt_handler.py            # CCXTDataHandler (交易所实时/历史数据)
│   ├── data_fetcher.py            # 预下载数据工具
│   ├── cache.py                   # Parquet 缓存层
│   └── schema.py                  # OHLCV 数据 Pydantic schema
│
├── execution/
│   ├── __init__.py
│   ├── simulated.py               # SimulatedExecutionHandler
│   ├── slippage.py                # 滑点模型 (FixedBps/Percentage/VolumeBased)
│   └── commission.py              # 手续费模型 (CryptoMakerTaker/Zero)
│
├── strategies/
│   ├── __init__.py
│   ├── ma_crossover.py            # 均线交叉策略
│   ├── breakout.py                # 通道突破策略
│   └── mean_reversion.py         # 均值回归 (布林带)
│
├── analytics/
│   ├── __init__.py
│   ├── performance.py             # PerformanceAnalyzer - 所有指标
│   ├── trade_stats.py             # 交易统计 (TradeRecord)
│   ├── visualizer.py              # 图表 (权益曲线/回撤/月收益热图)
│   └── reporter.py                # 报告生成 (控制台/HTML)
│
├── utils/
│   ├── __init__.py
│   ├── logger.py                  # 日志配置
│   └── timeframe.py               # 时间框架工具函数
│
├── config/
│   ├── config_schema.py           # Pydantic BacktestConfig
│   ├── default_config.yaml        # 默认配置
│   └── example_btc_ma.yaml        # BTC MA 交叉示例配置
│
├── tests/
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试
│   └── fixtures/
│       └── btc_usdt_1h_sample.csv # 测试用 CSV 数据
│
├── examples/
│   ├── run_ma_crossover.py
│   └── backtest_notebook.ipynb
│
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

---

## 数据流（事件循环）

```
DataHandler.iter_bars()
        |
        | 每个时间戳产生 [MarketEvent(BTC), MarketEvent(ETH), ...]
        v
   EventQueue.put(MarketEvent)
        |
        |========== DRAIN LOOP (直到队列为空) ==========|
        |                                               |
        |--[MarketEvent]--> Strategy.calculate_signals()|
        |                       | → [SignalEvent]       |
        |                       v                       |
        |               EventQueue.put(SignalEvent) --->|
        |                                               |
        |--[SignalEvent]--> Portfolio.on_signal()        |
        |                       | → OrderEvent          |
        |                       v                       |
        |               EventQueue.put(OrderEvent) ---->|
        |                                               |
        |--[OrderEvent]--> Execution.on_order()          |
        |                       | → FillEvent           |
        |                       v                       |
        |               EventQueue.put(FillEvent) ------>|
        |                                               |
        |--[FillEvent]--> Portfolio.on_fill()            |
        |              -> Strategy.on_fill()   (结束) ->|
        |================================================|
        v
Portfolio.update_market_values()   # 更新浮动盈亏
        v (下一个时间戳)
...
PerformanceAnalyzer.analyze() → BacktestResult → Reporter
```

---

## 核心设计决策

1. **事件不可变**: 所有事件使用 `@dataclass(frozen=True)`，避免状态污染
2. **优先级队列**: MARKET(4) > SIGNAL(3) > ORDER(2) > FILL(1)，确保因果正确性
3. **同步事件循环**: 单线程确定性，避免竞态条件，易于调试
4. **不可变 PortfolioState**: 每次 `on_fill` 创建新的状态对象，历史状态可追溯
5. **配置驱动**: 所有参数通过 YAML + Pydantic 验证，无硬编码值

---

## 实现阶段

### Phase 1: 事件系统基础（第1周）
- `core/events.py` - 四种冻结事件数据类
- `core/event_queue.py` - 优先级队列
- `config/config_schema.py` - Pydantic BacktestConfig
- `utils/logger.py` - 日志配置
- `tests/unit/test_events.py` + `test_event_queue.py`

### Phase 2: 数据管道（第2周）
- `core/data_handler.py` - 抽象基类
- `data/schema.py` - OHLCV 验证
- `data/csv_handler.py` - 多品种 CSV 读取（时间戳对齐）
- `data/cache.py` - Parquet 缓存
- `tests/fixtures/btc_usdt_1h_sample.csv` + 单元测试

### Phase 3: 策略 + 投资组合（第3周）
- `core/strategy.py` - Strategy 抽象基类（含 warmup 追踪）
- `strategies/ma_crossover.py` - 第一个具体策略
- `core/portfolio.py` - PortfolioManager（固定比例仓位管理）
- 测试: 信号在正确的交叉点触发，P&L 计算准确

### Phase 4: 执行引擎（第4周）
- `execution/slippage.py` - FixedBps / Percentage / VolumeBasedSlippage
- `execution/commission.py` - CryptoMakerTaker / Zero
- `execution/simulated.py` - 市价/限价/止损单模拟
- `core/engine.py` - BacktestEngine（完整事件调度循环）
- `tests/integration/test_engine_full_loop.py`

### Phase 5: 分析与报告（第5周）
- `analytics/performance.py` - Sharpe / Sortino / Calmar / MaxDD / VaR
- `analytics/trade_stats.py` - 交易级统计
- `analytics/visualizer.py` - 权益曲线 / 回撤图 / 月收益热图
- `analytics/reporter.py` - 控制台 + HTML 报告

### Phase 6: 更多策略 + CCXT（第6周）
- `strategies/breakout.py` + `mean_reversion.py`
- `data/ccxt_handler.py` - 交易所历史数据获取（含分页、缓存）
- `examples/run_ma_crossover.py` + Jupyter Notebook

---

## 关键依赖

```
# requirements.txt
numpy>=1.26.0
pandas>=2.2.0
pydantic>=2.7.0
pandas-ta>=0.3.14b0
ccxt>=4.2.97
pyyaml>=6.0.1
matplotlib>=3.8.0
plotly>=5.20.0
tabulate>=0.9.0
jinja2>=3.1.3
rich>=13.7.1
python-dateutil>=2.9.0
orjson>=3.10.0

# requirements-dev.txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=5.0.0
pytest-mock>=3.14.0
black>=24.0.0
ruff>=0.4.0
mypy>=1.10.0
jupyter>=1.0.0
```

---

## 验证方式

1. 单元测试: `pytest tests/unit/ -v --cov=core --cov-report=term-missing`
2. 集成测试: 用样本 CSV 运行完整回测循环，验证权益曲线非零、Sharpe 值合理
3. 端到端示例: `python examples/run_ma_crossover.py` 输出完整绩效报告
4. 可选: 对比已知结果（例如 buy-and-hold BTC 2023 年收益约 155%）验证 P&L 计算正确性
