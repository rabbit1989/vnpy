# coding=utf-8

import datetime
from collections import defaultdict
from dateutil.relativedelta import relativedelta

import talib

from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)
from vnpy.trader.constant import OrderType, OptionSMonth
from vnpy.trader.object import OptionBarData
from vnpy.trader.utility import Option, get_option_smonth


# TODO: fill
trade_day_set = (

)



class RealizedVolStrategy(CtaTemplate):
    '''
        一个简单的买入已实现波动率策略
    '''
    author = "white"

    spot_symbol = None
    option_level = -1
    call_put = 'C'
    s_month_type = OptionSMonth.NEXT_MONTH
    fixed_size = 1
    win_len = 10

    parameters = [
        "fixed_size",
        "spot_symbol",
        "option_level",
        "s_month_type",
        'win_len',
        'call_put'
    ]
    variables = [
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.am_spot = ArrayManager(self.win_len)
        self.spot_close_price = None
        self.last_hedge_day = None
        self.delta_dict = defaultdict(list)

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        pass


    def on_bar(self, bar):
        """
        Callback of new bar data update.
        """
        if isinstance(bar, BarData) is True:
            self.spot_close_price = bar.close_price
            self.am_spot.update_bar(bar)
        elif isinstance(bar, OptionBarData) is True and self.spot_close_price is not None:   
            # 如果明天的明天是节假日就买入
            next_date = (bar.datetime + datetime.timedelta(1)).strftime('%Y%m')
            next_next_date = (bar.datetime + datetime.timedelta(2)).strftime('%Y%m')
            if next_date in trade_day_set and not next_next_date in trade_day_set:
                # 可以买入了
                s_month = get_option_smonth(bar.datetime, self.s_month_type)
                option_bar = bar.get_real_bar(
                    spot_price=self.spot_close_price, 
                    call_put=self.call_put,
                    level=self.option_level,
                    s_month=s_month)
                full_option_data = bar.options[option_bar.symbol]
                vol = talib.STDDEV(self.am_spot.return_array, self.win_len)[-1]

                if abs(vol) > 0.0000001:
                    exp_date = datetime.datetime.strptime(full_option_data['delist_date'], '%Y%m%d')
                    option = Option(full_option_data['call_put'], 
                                    self.spot_close_price,
                                    full_option_data['strike_price'],
                                    bar.datetime.replace(tzinfo=None),
                                    exp_date,
                                    price=full_option_data['settle'],
                                    vol=abs(vol))
                    _, delta = option.get_price_delta()
                    option_pos = self.fixed_size/delta
                    
                    # 买入期权
                    self.buy(option_bar.symbol, option_bar.close_price, option_pos, order_type=OrderType.MARKET)

                    # 卖出现货
                    self.short(self.spot_symbol, self.spot_close_price, self.fixed_size, order_type=OrderType.MARKET)
            else: 
                option_symbol_list = self.get_option_list()
                if option_symbol_list:
                    # 如果持仓就立刻卖了， 反正是T+1
                    option_symbol = option_symbol_list[0]
                    self.sell(option_symbol, None, self.pos_dict[option_symbol], order_type=OrderType.MARKET)
                    self.cover(self.spot_symbol, None, self.pos_dict[self.spot_symbol], order_type=OrderType.MARKET)
        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        #print('on_trade: {}'.format(trade))
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
