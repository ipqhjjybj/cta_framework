方式一：直接运行示例脚本（最快）                                                                                                                                             
   
cd /Users/shenzhuoheng/git/cta_framework                                                                                                                                     
python examples/run_ma_crossover.py                             

带参数：
python examples/run_ma_crossover.py \
--fast 10 \
--slow 30 \
--capital 50000 \
--output-dir results/my_test

---
方式二：用真实数据（CCXT 从交易所下载）

先下载数据：
python -m data.data_fetcher \
--exchange binance \
--symbol BTC/USDT \
--timeframe 1h \
--start 2023-01-01 \
--end 2023-12-31 \
--output tests/fixtures/BTC_USDT_1h.csv

然后运行：
python examples/run_ma_crossover.py --csv-dir tests/fixtures

---
方式三：写 Python 脚本（最灵活）

from datetime import datetime
from core.engine import BacktestEngine
from core.event_queue import EventQueue
from core.portfolio import PortfolioManager
from data.csv_handler import CSVDataHandler
from execution.commission import CryptoMakerTakerCommission
from execution.simulated import SimulatedExecutionHandler
from execution.slippage import FixedBpsSlippage
from strategies.ma_crossover import MACrossoverStrategy
from analytics.performance import PerformanceAnalyzer
from analytics.reporter import ConsoleReporter

eq = EventQueue()

data = CSVDataHandler(
    csv_dir="tests/fixtures",
    symbols=["BTC/USDT"],
    timeframe="1h",
    start=datetime(2023, 1, 1),
    end=datetime(2023, 12, 31, 23),
)

strategy = MACrossoverStrategy(["BTC/USDT"], eq, fast_period=20, slow_period=50)
portfolio = PortfolioManager(100_000, eq, risk_per_trade=0.02)
execution = SimulatedExecutionHandler(eq, FixedBpsSlippage(2.0), CryptoMakerTakerCommission())

engine = BacktestEngine("my_bt", data, strategy, portfolio, execution, eq)
result = engine.run()

metrics = PerformanceAnalyzer(result.equity_curve).analyze()
ConsoleReporter().report(result, metrics)

---
方式四：运行测试验证框架

python -m pytest tests/ -v -p no:pytest_ethereum