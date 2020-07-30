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



class OptionDeltaHedgeStrategy(CtaTemplate):
    """"""

    author = "用Python的交易员"

    spot_symbol = None
    option_level = -1
    s_month_type = OptionSMonth.NEXT_MONTH
    num_day_before_expired = 15
    fixed_size = 1
    win_len = 10
    hedge_interval = 15

    parameters = [
        "fixed_size",
        "spot_symbol",
        "option_level",
        "num_day_before_expired",
        "s_month_type",
        'win_len',
        'hedge_interval'
    ]
    variables = [
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.am_dict = {}
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

    
    def buy_option(self, option_bar, call_put, level, s_month_type):
        #s_month = (option_bar.datetime + datetime.timedelta(month_day_offset)).strftime('%Y%m')
        s_month = get_option_smonth(option_bar.datetime, s_month_type)
        print('cur month: {}, month type: {}, s month: {}'.format(
            option_bar.datetime.strftime('%Y%m'), s_month_type, s_month))
        bar = option_bar.get_real_bar(
            spot_price=self.spot_close_price, 
            call_put=call_put,
            level=level,
            s_month=s_month)
        if self.delta_dict[bar.symbol]:
            buy_size = abs(self.fixed_size/self.delta_dict[bar.symbol][-1])
        else:
            buy_size = self.fixed_size
        print('买: {} 价: {}, 现货价: {}, month: {}, date: {} buy_size: {}, delta: {}'.format(
            bar.symbol, bar.close_price, self.spot_close_price, 
            s_month, bar.datetime, buy_size, self.delta_dict[bar.symbol]))
        close = self.am_spot.close
        strike = option_bar.options[bar.symbol]['strike_price']
        for i in range(1, self.win_len+1):
            if len(self.delta_dict[bar.symbol]) >= i:
                print('spot: {}, strike: {}, delta: {:.4f}'.format(
                    close[-i], strike, self.delta_dict[bar.symbol][-i]))
        self.buy(bar.symbol, bar.close_price, buy_size, order_type=OrderType.MARKET)
        self.last_hedge_day = bar.datetime


    def on_bar(self, bar):
        """
        Callback of new bar data update.
        """
        #self.cancel_all()
        if isinstance(bar, BarData) is True:
            if self.pos_dict[bar.symbol] == 0:
                self.buy(bar.symbol, bar.close_price, self.fixed_size)
            self.spot_close_price = bar.close_price
            self.am_spot.update_bar(bar)
        elif isinstance(bar, OptionBarData) is True:            
            # 更新所有期权合约的array manager
            del_list = []
            for symbol in self.am_dict.keys():
                if not symbol in bar.symbol_based_dict:
                    del_list.append(symbol)
            for symbol in del_list:
                del self.am_dict[symbol]

            for symbol, contract_bar in bar.symbol_based_dict.items():
                if symbol not in self.am_dict:
                    self.am_dict[symbol] = ArrayManager(self.win_len)
                self.am_dict[symbol].update_bar(contract_bar)
                
                if self.spot_close_price:
                    # 计算delta(已知波动率)
                    full_option_data = bar.options[symbol]
                    exp_date = datetime.datetime.strptime(full_option_data['delist_date'], '%Y%m%d')
                    vol = talib.STDDEV(self.am_dict[symbol].return_array, self.win_len)[-1]
                    if abs(vol) > 0.0000001:
                        option = Option(full_option_data['call_put'], 
                                        self.spot_close_price,
                                        full_option_data['strike_price'],
                                        bar.datetime.replace(tzinfo=None),
                                        exp_date,
                                        vol=abs(vol))
                        option.get_price_delta()
                        self.delta_dict[symbol].append(option.delta)
                        if len(self.delta_dict[symbol]) > self.win_len:
                            self.delta_dict[symbol] = self.delta_dict[symbol][1:]
                        #print('cp: {} spot: {:.2f}, close: {:.3f}, model predict: {:.3f}, stike: {:.2f}, delist: {}, vol: {:.4f}'.format(
                        #    full_option_data['call_put'], self.spot_close_price, 
                        #    full_option_data['settle'],
                        #    option.calc_price,
                        #    full_option_data['strike_price'],
                        #    full_option_data['delist_date'], vol
                        #))
                    else:
                        #print('new symbol: {}'.format(symbol))
                        pass
                    

            if self.spot_close_price:
                option_symbol_list = self.get_option_list()
                if not option_symbol_list:
                    # 买入现货后 期权还是空仓，则买入认沽期权
                    print('买入现货后 期权还是空仓，则买入认沽期权')
                    self.buy_option(bar, 'P', self.option_level, self.s_month_type)
                else:
                    option_symbol = option_symbol_list[0]
                    num_day = bar.get_num_day_expired(option_symbol, bar.datetime.strftime("%Y%m%d"))
                    #print('num expired day: {}: {}, '.format(option_symbol, num_day))
                    option_bar = bar.symbol_based_dict[option_symbol]
                    if num_day <= self.num_day_before_expired:
                        # 如果期权快到期了，需要换仓
                        print('卖: {} 价: {}, 现货价: {}, 当前时间: {}， 到期时间: {}'.format(    
                            option_symbol, option_bar.close_price, self.spot_close_price, bar.datetime, bar.options[option_symbol]['delist_date']))
                        print('========================')
                        self.sell(        
                            option_symbol,
                            option_bar.close_price,
                            self.pos_dict[option_symbol],
                            order_type=OrderType.MARKET)
                        self.buy_option(bar, 'P', self.option_level, self.s_month_type)
                    elif (bar.datetime-self.last_hedge_day).days > self.hedge_interval:
                        # 每隔一段时间调一次仓
                        delta = self.delta_dict[option_symbol][-1]
                        cur_pos = self.pos_dict[option_symbol]
                        new_pos = abs(self.fixed_size/delta)
                        print('11111111delta: {}'.format(delta))
                        # 仓位差距大时,且 delta大于一个值时 才需要调仓
                        if abs(new_pos-cur_pos) > 0.05 and abs(delta) > 0.1:
                            if new_pos > cur_pos:
                                print ('{} cur_pos: {:.3f}, new_pos: {:.3f}, 仓位过少，买入一部分'.format(bar.datetime, cur_pos, new_pos))
                                self.buy(        
                                    option_symbol,
                                    option_bar.close_price,
                                    new_pos-cur_pos,
                                    order_type=OrderType.MARKET)
                            else:
                                print ('{} cur_pos: {:.3f}, new_pos: {:.3f}, 仓位过多，卖出一部分'.format(bar.datetime, cur_pos, new_pos))
                                self.sell(        
                                    option_symbol,
                                    option_bar.close_price,
                                    cur_pos-new_pos,
                                    order_type=OrderType.MARKET)
                            self.last_hedge_day = bar.datetime
                    # 计算持仓隐含波动率
                    full_option_data = bar.options[option_symbol]
                    exp_date = datetime.datetime.strptime(full_option_data['delist_date'], '%Y%m%d')
                    vol = talib.STDDEV(self.am_dict[option_symbol].return_array, self.win_len)[-1]
                    option1 = Option(full_option_data['call_put'], 
                                    self.spot_close_price,
                                    full_option_data['strike_price'],
                                    bar.datetime.replace(tzinfo=None),
                                    exp_date,
                                    price=full_option_data['settle'],
                                    vol=vol)
                    calc_price, _, theta, gamma, vega = option1.get_all()
                    imp_vol = option1.get_impl_vol()
                    print('{}, pos: {:.2f}, eval: {}, exp: {}, s: {}, k: {}, op price: {:.3f}, cal_price: {:.3f} '\
                        'delta: {:.3f}, vol: {:.3f}, imp vol: {:.3f}, theta {:.3f}, gamma: {:.3f}, vega: {:.3f}'.format(
                        option_symbol,
                        self.pos_dict[option_symbol],
                        bar.datetime.replace(tzinfo=None).strftime('%Y%m%d'),
                        full_option_data['delist_date'],
                        self.spot_close_price,
                        full_option_data['strike_price'],
                        full_option_data['settle'],
                        calc_price,
                        self.delta_dict[option_symbol][-1] if abs(vol) > 0.0000001 else -111111,
                        vol,
                        imp_vol,
                        theta,
                        gamma,
                        vega
                    ))

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
