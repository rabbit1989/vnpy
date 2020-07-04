from datetime import datetime


from vnpy.app.cta_strategy.base import BacktestingMode
from vnpy.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from vnpy.app.cta_strategy.strategies.etf50_delta_hedge_strategy import (
    OptionDeltaHedgeStrategy
)
from vnpy.trader.constant import OptionSMonth


engine = BacktestingEngine()
engine.set_parameters(
    configs = {
        '50etf.SSE': {
            'pricetick': 0.01
        },
        '50etf_option.SSE': {
            'pricetick': 0.001
        }
    },
    interval="d",
    start=datetime(2017, 12, 1),
    end=datetime(2020, 6, 30),
    rate=0.3/10000,
    slippage=0,
    size=300,
    capital=1_000_0,
    mode=BacktestingMode.BAR
)
engine.add_strategy(
    OptionDeltaHedgeStrategy, 
    {'spot_symbol': '50etf',
     'option_level': 1,
     "num_day_before_expired": 20,
     "s_month_type": OptionSMonth.NEXT_SEASON,
    })



engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()