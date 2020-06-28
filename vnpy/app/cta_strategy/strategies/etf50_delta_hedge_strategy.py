# coding=utf-8

import datetime

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
from vnpy.trader.object import OptionBarData


class OptionDeltaHedgeStrategy(CtaTemplate):
    """"""

    author = "用Python的交易员"

    spot_symbol = None
    fixed_size = 1

    parameters = [
        "fixed_size"
    ]
    variables = [
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager()
        self.spot_close_price = None

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
        self.bg.update_tick(tick)

    
    def buy_option(self, option_bar, call_put, level):
        s_month = option_bar.datetime.strftime("%Y%m")
        day = option_bar.datetime.strftime('%d')
        if int(day) > 19:
            # 如果当月快到期了，直接买入下月的吧
            s_month = (option_bar.datetime + datetime.timedelta(30)).strftime('%Y%m')
        option_bar = option_bar.get_real_bar(
            spot_price=self.spot_close_price, 
            call_put=call_put,
            level=level,
            s_month=s_month)
        print('尝试买入期权: {}, 挂单价: {}'.format(option_bar.symbol, option_bar.close_price))
        self.buy(option_bar.symbol, option_bar.close_price, self.fixed_size)


    def on_bar(self, bar):
        """
        Callback of new bar data update.
        """
        #self.cancel_all()
        if isinstance(bar, BarData) is True:
            if self.pos_dict[bar.symbol] == 0:
                self.buy(bar.symbol, bar.close_price, self.fixed_size)
            self.spot_close_price = bar.close_price
        elif isinstance(bar,OptionBarData) is True:
            if self.pos_dict[self.spot_symbol] > 0:
                option_symbol_list = self.get_option_list()
                if not option_symbol_list:
                    # 买入现货后 期权还是空仓，则买入当月虚一档认沽期权
                    print('买入现货后 期权还是空仓，则买入认沽期权')
                    self.buy_option(bar, 'P', -1)
                else:
                    assert len(option_symbol_list) == 1
                    option_symbol = option_symbol_list[0]
                    num_day = bar.get_num_day_expired(option_symbol, bar.datetime.strftime("%Y%m%d"))
                    if num_day < 5:
                        # 如果期权快到期了，需要换仓
                        option_bar = bar.symbol_based_dict(option_symbol)
                        print('期权快到期了，需要换仓, 期权 {} 当前结算价: {}'.format(
                            option_symbol, option_bar.close_price))
                        self.sell(        
                            option_symbol,
                            option_bar.close_price,
                            self.pos_dict[option_symbol])
                        self.buy_option(bar, 'P', -1)


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
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
