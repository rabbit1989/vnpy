from vnpy.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from vnpy.app.cta_strategy.strategies.etf50_delta_hedge_strategy import (
    Etf50DeltaHedgeStrategy
)
from datetime import datetime

engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="50etf.SSE",
    interval="d",
    start=datetime(2015, 1, 1),
    end=datetime(2020, 6, 30),
    rate=0.3/10000,
    slippage=0.2,
    size=300,
    pricetick=0.2,
    capital=1_000_000,
)
engine.add_strategy(Etf50DeltaHedgeStrategy, {})

engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()