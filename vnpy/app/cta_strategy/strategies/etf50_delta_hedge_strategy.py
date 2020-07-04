# coding=utf-8

import datetime
from dateutil.relativedelta import relativedelta

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


def get_season_end_month(dt, season_offset = 0):
    '''
        获取当前月所在季度的第一个月
    '''
    year = int(dt.strftime('%Y'))
    month = int(dt.strftime('%m'))
    season_end_month = int((month-1)/3)*3 + 3

    ans_year = year + int((season_end_month + season_offset*3-1)/12)
    ans_month = (season_end_month + season_offset*3-1)%12 + 1
    return '{}{:02d}'.format(ans_year, ans_month)


class OptionDeltaHedgeStrategy(CtaTemplate):
    """"""

    author = "用Python的交易员"

    spot_symbol = None
    option_level = -1
    s_month_type = OptionSMonth.NEXT_MONTH
    num_day_before_expired = 15
    fixed_size = 1

    parameters = [
        "fixed_size",
        "spot_symbol",
        "option_level",
        "num_day_before_expired",
        "s_month_type",
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

    
    def get_smonth(self, dt, s_month_type):
        if s_month_type == OptionSMonth.CUR_MONTH:
            return dt.strftime('%Y%m')
        elif s_month_type == OptionSMonth.NEXT_MONTH:
            return (dt + relativedelta(months=1)).strftime('%Y%m')
        elif s_month_type == OptionSMonth.NEXT_SEASON:
            return get_season_end_month(dt, 1)
        elif s_month_type == OptionSMonth.NEXT_2SEASON:
            return get_season_end_month(dt, 2)
        else:
            raise Exception("unknown s_month type {}".format(s_month_type))
    
    def buy_option(self, option_bar, call_put, level, s_month_type):
        #s_month = (option_bar.datetime + datetime.timedelta(month_day_offset)).strftime('%Y%m')
        s_month = self.get_smonth(option_bar.datetime, s_month_type)
        print('cur month: {}, month type: {}, s month: {}'.format(
            option_bar.datetime.strftime('%Y%m'), s_month_type, s_month))
        option_bar = option_bar.get_real_bar(
            spot_price=self.spot_close_price, 
            call_put=call_put,
            level=level,
            s_month=s_month)
        #print('尝试买入期权: {}, 挂单价: {}, 现货价: {}, month: {}, date: {}'.format(
        print('买: {} 价: {}, 现货价: {}, month: {}, date: {}'.format(
            option_bar.symbol, option_bar.close_price, self.spot_close_price, s_month, option_bar.datetime))
        self.buy(option_bar.symbol, option_bar.close_price, self.fixed_size, order_type=OrderType.MARKET)


    def on_bar(self, bar):
        """
        Callback of new bar data update.
        """
        #self.cancel_all()
        if isinstance(bar, BarData) is True:
            if self.pos_dict[bar.symbol] == 0:
                self.buy(bar.symbol, bar.close_price, self.fixed_size)
            self.spot_close_price = bar.close_price
        elif isinstance(bar, OptionBarData) is True:
            if self.pos_dict[self.spot_symbol] > 0:
                option_symbol_list = self.get_option_list()
                if not option_symbol_list:
                    # 买入现货后 期权还是空仓，则买入当月虚一档认沽期权
                    print('买入现货后 期权还是空仓，则买入认沽期权')
                    self.buy_option(bar, 'P', self.option_level, self.s_month_type)
                else:
                    # assert len(option_symbol_list) == 1
                    option_symbol = option_symbol_list[0]
                    num_day = bar.get_num_day_expired(option_symbol, bar.datetime.strftime("%Y%m%d"))
                    #print('num expired day: {}: {}, '.format(option_symbol, num_day))
                    if num_day <= self.num_day_before_expired:
                        # 如果期权快到期了，需要换仓
                        option_bar = bar.symbol_based_dict[option_symbol]
                        #print('期权快到期了，需要换仓, 期权 {} 当前结算价: {}, 当前现货价格: {}, 当前时间: {}， 到期时间: {}'.format(    
                        #    option_symbol, option_bar.close_price, self.spot_close_price, bar.datetime, bar.options[option_symbol]['delist_date']))
                        print('卖: {} 价: {}, 当前现货价格: {}, 当前时间: {}， 到期时间: {}'.format(    
                            option_symbol, option_bar.close_price, self.spot_close_price, bar.datetime, bar.options[option_symbol]['delist_date']))
                        print('========================')
                        self.sell(        
                            option_symbol,
                            option_bar.close_price,
                            self.pos_dict[option_symbol],
                            order_type=OrderType.MARKET)
                        self.buy_option(bar, 'P', self.option_level, self.s_month_type)


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
