# coding=utf-8

from datetime import datetime

#import matplotlib.pyplot as plt
#import pandas as pd
#import statsmodels.api as sm
#from statsmodels.tsa.arima_model import ARIMA
#from statsmodels.tsa.seasonal import seasonal_decompose
#from statsmodels.tsa.stattools import adfuller as ADF


from vnpy.app.cta_strategy.base import BacktestingMode
from vnpy.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from vnpy.trader.constant import OptionSMonth, Direction


def analyse(param_list, load_from_db):
    file_path = 'param.csv'
    if load_from_db:
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
            end=datetime(2020, 10, 1),
            rate=0.3/10000,
            slippage=0,
            size=5000,
            capital=1_000_0,
            mode=BacktestingMode.BAR
        )
        engine.load_data()

    
        d = engine.show_option_params(
            param_list=param_list, 
            call_put='C', 
            level=-1,
            s_month_type=OptionSMonth.NEXT_SEASON, 
            change_pos_day=30)
        with open(file_path, 'w') as fp:
            fp.write('imp_vol,date\n')
            imp_vol_l = d['imp_vol']
            date_l = d['date']
            for imp_vol, date in zip(imp_vol_l, date_l):
                fp.write('{},{}\n'.format(imp_vol, date))
            print('finish writing')
    



if __name__ == '__main__':
    analyse(param_list=['realized_vol', 
                        'imp_vol', 
                        'delta',
                        'theta',
                        'gamma',
                        'vega',
                        'calc_price',
                        'spot_price',
                        'op_price',
                        'k',
                        'vol', 
                        'date'],
            load_from_db=False)
    