# coding=utf-8

from datetime import datetime


from vnpy.app.cta_strategy.base import BacktestingMode
from vnpy.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from vnpy.trader.constant import OptionSMonth, Direction



def show_volatility():
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
        end=datetime(2020, 7, 1),
        rate=0.3/10000,
        slippage=0,
        size=5000,
        capital=1_000_0,
        mode=BacktestingMode.BAR
    )
    engine.load_data()
    engine.show_option_params(
        param_list=['realized_vol', 'imp_vol'], 
        call_put='C', 
        level=-1, 
        s_month_type=OptionSMonth.NEXT_MONTH)


if __name__ == '__main__':
    show_volatility()
