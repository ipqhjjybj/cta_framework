# CLAUDE.md — CTA Framework

## 项目概述

事件驱动的加密货币 CTA 回测框架。核心是一个单线程确定性事件循环：
`MarketEvent(4) → SignalEvent(3) → OrderEvent(2) → FillEvent(1)`（数字为优先级）。

## 常用命令

```bash
# 运行测试
pytest tests/ -v
pytest tests/unit/ -v
pytest tests/integration/ -v

# 合成数据快速验证
python examples/run_turtle.py
python examples/run_supertrend.py

# 真实数据回测（需先下载）
python examples/run_turtle.py --csv-dir data/raw --start 2021-01-01 --end 2025-12-31 \
    --entry 480 --exit 240 --atr 336 --trend 4800 --adx 336 --adx-min 20 --max-dd 0.25

# 下载数据
python -m data.data_fetcher --exchange binance --symbol BTC/USDT --timeframe 1h \
    --start 2021-01-01 --end 2025-12-31 --output data/raw/BTC_USDT_1h.csv
```

## 架构约定

### 事件系统

- 所有事件使用 `@dataclass(frozen=True)`，不可变
- 事件优先级：`MARKET=4 > SIGNAL=3 > ORDER=2 > FILL=1`
- `EventQueue` 实现了 `__len__`，**空队列为 falsy**。构造时必须用：
  ```python
  # 正确
  self._eq = event_queue if event_queue is not None else EventQueue()
  # 错误（空队列会创建新的disconnected队列）
  self._eq = event_queue or EventQueue()
  ```

### Engine 事件循环顺序（关键）

```python
for bar_list in data.iter_bars():
    for event in bar_list:
        execution.on_market(event)   # 更新价格
        portfolio.on_market(event)   # 更新净值、峰值
    for event in bar_list:
        eq.put(event)                # 入队
    drain()                          # 触发策略→组合→执行
```

`portfolio.on_market()` **必须在 drain 之前调用**，否则 `on_signal()` 时价格字典为空，导致零交易。

### Portfolio 现金记账（SHORT）

```python
# 开 SHORT：收到卖出款
self._cash += qty * price - commission

# 平 SHORT（买回）：支付买回款（cash 已含卖出款，不要再加 pnl）
self._cash -= qty * price + commission  # 正确
# self._cash += pnl                     # 错误！会双重计算
```

### ATR 仓位管理

`SignalEvent.strength` 编码止损比率 `= stop_distance / price`：
- `0 < strength < 1.0` → ATR sizing：`qty = (equity × risk%) / (strength × price)`
- `strength == 1.0` → 固定名义：`qty = (equity × risk%) / price`

策略通过 `_sig()` 方法设置 `strength = min(atr_mult × atr / price, 0.99)`。

## 关键文件

| 文件 | 职责 |
|------|------|
| `core/engine.py` | 主循环，协调所有组件 |
| `core/portfolio.py` | 信号→订单转换，P&L记账，风控 |
| `core/events.py` | 四类冻结事件数据类 |
| `strategies/turtle.py` | 海龟系统（含 ADX 过滤） |
| `strategies/supertrend.py` | Supertrend 自适应趋势 |
| `data/csv_handler.py` | CSV 数据加载，按 `symbol_timeframe.csv` 命名 |
| `analytics/performance.py` | Sharpe/Sortino/Calmar/MaxDD/VaR |

## 新增策略

继承 `core.strategy.Strategy`，实现两个方法：

```python
class MyStrategy(Strategy):
    @property
    def warmup_period(self) -> int:
        return 50  # 策略所需最少 K 线数

    def calculate_signals(self, event: MarketEvent) -> list[SignalEvent]:
        bars = list(self.bars(event.symbol))  # 历史 K 线（含当前）
        # 返回 SignalEvent 列表，direction: LONG / SHORT / EXIT
        # strength = stop_distance / price（用于 ATR 仓位计算）
```

`on_fill()` 可选实现，用于在策略层跟踪持仓状态（止损价格等）。

## 参数经验（1h BTC 数据）

| 原版参数（日线） | 1h 等价值 | 说明 |
|----------------|----------|------|
| entry 20天 | `480` | 1天=24根1h K线 |
| exit 10天 | `240` | |
| ATR 14天 | `336` | |
| SMA 200天 | `4800` | 趋势过滤 |
| ADX 14天 | `336` | 横盘过滤，ADX<20不开仓 |

使用 `--entry 20 --exit 10`（默认值）在1h数据上等同于看20小时突破，噪音极大，不推荐。

## 已知问题与修复记录

- **熔断器永久停止**：使用 `peak_lookback_bars=6048`（252天滚动窗口）代替 all-time peak，避免熔断后无法恢复
- **CAGR NaN**：当最终净值为负时取分数幂会产生 NaN，已在 `analytics/performance.py` 加保护
- **代理支持**：`ccxt_handler.py` 支持 `--proxy` 参数和环境变量 `https_proxy/http_proxy/all_proxy`

## 测试数据

`tests/fixtures/BTC_USDT_1h.csv`：合成随机游走数据，seed=42，8760 根 1h K 线，起始价格 16500。
用于单元测试和快速集成验证，不含真实市场趋势。
