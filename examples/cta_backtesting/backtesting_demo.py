# coding=utf-8
from datetime import datetime


from vnpy.app.cta_strategy.base import BacktestingMode
from vnpy.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from vnpy.app.cta_strategy.strategies.etf50_delta_hedge_strategy import OptionDeltaHedgeStrategy
from vnpy.app.cta_strategy.strategies.delta_gamma_hedge_strategy import OptionDeltaGammaHedgeStrategy
from vnpy.app.cta_strategy.strategies.realized_vol_strategy import RealizedVolStrategy
from vnpy.app.cta_strategy.strategies.channel_break_vol_strategy import ChannelBreakVolStrategy
from vnpy.app.cta_strategy.strategies.channel_break_imp_vol_strategy_v2 import ChannelBreakImpVolStrategyV2
from vnpy.app.cta_strategy.strategies.short_imp_vol_strategy import ShortImpVolStrategy
from vnpy.trader.constant import OptionSMonth, Direction


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


# engine.add_strategy(
#    OptionDeltaHedgeStrategy, 
#    {'spot_symbol': '50etf',
#     'option_level': -2,
#     "num_day_before_expired": 50,
#     "s_month_type": OptionSMonth.NEXT_SEASON,
#     'hedge_interval': 15 # 隔多少天重新调仓
#    })


# engine.add_strategy(
#     OptionDeltaGammaHedgeStrategy, 
#     {'spot_symbol': '50etf',
#      'option_configs':[
#          {
#             'level': -2,
#             "s_month_type": OptionSMonth.NEXT_MONTH,
#             'call_put': 'P',
#             'direction': Direction.LONG,
#          },
#          {
#             'level': -2,
#             "s_month_type": OptionSMonth.NEXT_SEASON,
#             'call_put': 'P',
#             'direction': Direction.SHORT,
#          }
#      ],
#      'num_day_before_expired': 15, # 多少天换仓一次
#      'hedge_interval': 10, # 隔多少天重新调仓
#      'win_len': 10, # 计算波动率的窗口大小
#     })


# engine.add_strategy(
#     RealizedVolStrategy, 
#     {'spot_symbol': '50etf',
#      'option_level': -1,
#      "s_month_type": OptionSMonth.NEXT_SEASON,
#      'call_put': 'C'
#     })

# engine.add_strategy(
#    ChannelBreakVolStrategy, 
#    {'spot_symbol': '50etf',
#     'option_level': -1,
#     "s_month_type": OptionSMonth.NEXT_SEASON,
#     'call_put': 'C'
#    })


# engine.add_strategy(
#     ShortImpVolStrategy, 
#     {'spot_symbol': '50etf',
#      'option_level': -1,
#      "s_month_type": OptionSMonth.NEXT_SEASON,
#      'call_put': 'C'
#     })

engine.add_strategy(
    ChannelBreakImpVolStrategyV2, 
    {'spot_symbol': '50etf',
     'option_level': -1,
     "s_month_type": OptionSMonth.NEXT_SEASON,
     'call_put': 'C'
    })



engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()