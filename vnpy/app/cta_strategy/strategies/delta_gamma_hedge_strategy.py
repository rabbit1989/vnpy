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
from vnpy.trader.utility import Option

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


class OptionDeltaGammaHedgeStrategy(CtaTemplate):
    """"""

    # 一种波动率交易策略，delta 和 gamma 都接近0， 保留vega

    author = "用Python的交易员"

    spot_symbol = None
    option_configs = []
    fixed_size = 1
    win_len = 10
    hedge_interval = 15
    num_day_before_expired = 15

    parameters = [
        "fixed_size",
        "spot_symbol",
        'win_len',
        'hedge_interval',
        'option_configs',
        'num_day_before_expired'
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
        self.greeks = {}

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
    

    def cal_hedge_pos(self, delta_l, delta_s, gamma_l, gamma_s):
        
        # 先判断方向
        if delta_l*gamma_s/gamma_l > delta_s:
            pos_s = 1
        else:
            pos_s = -1
        pos_spot = (delta_l*gamma_s/gamma_l - delta_s) * pos_s
        abs_sum = abs(pos_spot) + abs(pos_s)
        if abs_sum > 2:
            ratio = abs_sum / 2
            pos_spot /= ratio
            pos_s /= ratio        
        pos_l = -gamma_s/gamma_l*pos_s

        hedged_delta = pos_s*delta_s + pos_l*delta_l + pos_spot
        hedged_gamma = pos_s*gamma_s + pos_l*gamma_l
        print('hedged delta: {:.3f}, hedged gamma: {:.3f}'.format(hedged_delta, hedged_gamma))
        return pos_s, pos_l, pos_spot


    def update_all_pos(self, bar):
        option_symbol_list = self.get_option_list()
        should_buy = False
        if option_symbol_list:
            # 看看是否到换仓时间了
            assert len(option_symbol_list) == 2
            for symbol in option_symbol_list:
                num_day = bar.get_num_day_expired(symbol, bar.datetime.strftime("%Y%m%d"))
                if num_day <= self.num_day_before_expired:
                    print('======= 换仓时间到了========')
                    should_buy = True
            
            if (bar.datetime-self.last_hedge_day).days > self.hedge_interval:
                print('======== 调仓时间到了 ========')
                should_buy = True

            if should_buy is True:
                # 卖掉手头的仓位
                for symbol in option_symbol_list:
                    pos = self.pos_dict[symbol]
                    if pos > 0:
                        print('sell {}, pos: {}'.format(symbol, pos))
                        self.sell(symbol, None, pos, order_type=OrderType.MARKET)
                    else:
                        print('cover {}, pos: {}'.format(symbol, pos))
                        self.cover(symbol, None, -pos, order_type=OrderType.MARKET)
                # 卖现货
                self.sell(self.spot_symbol, None, self.pos_dict[self.spot_symbol], order_type=OrderType.MARKET)
        else:
            should_buy = True

        if should_buy is True:
            l = []
            for i, config in enumerate(self.option_configs):
                s_month = self.get_smonth(bar.datetime, config['s_month_type'])
                print('option {} cur month: {}, month type: {}, s month: {}'.format(
                    i, bar.datetime.strftime('%Y%m'), config['s_month_type'], s_month))
                option_bar = bar.get_real_bar(
                    spot_price=self.spot_close_price, 
                    call_put=config['call_put'],
                    level=config['level'],
                    s_month=s_month)
                l.append((option_bar, s_month))

            # 计算仓位使得delta和gamma均为0
            bar_l = l[0][0]
            bar_s = l[1][0]
            greek_l = self.greeks[bar_l.symbol]
            greek_s = self.greeks[bar_s.symbol]
            delta_l = greek_l['delta']
            delta_s = -greek_s['delta']
            gamma_l = greek_l['gamma']
            gamma_s = -greek_s['gamma']
            theta_l = greek_l['theta']
            theta_s = -greek_s['theta']
            vega_l = greek_l['vega']
            vega_s = -greek_s['vega']

            print('===================================================')

            pos_s, pos_l, pos_spot = self.cal_hedge_pos(delta_l, delta_s, gamma_l, gamma_s)
            if pos_s * pos_l < 0:
                assert False
            if pos_s < 0 and pos_l < 0:
                # 如果long short 计算出来的是负的，那么方向反过来就行了
                 bar_s, bar_l = bar_l, bar_s
                 pos_s, pos_l = -pos_l, -pos_s
                 delta_s, delta_l = -delta_l, -delta_s
                 gamma_s, gamma_l = -gamma_l, -gamma_s
                 theta_s, theta_l = -theta_l, -theta_s
                 greek_s, greek_l = greek_l, greek_s
                 vega_s, vega_l = vega_l, vega_s

            print('买开: {} 价: {:.3f}, 现货价: {:.2f}, month: {}, date: {} buy_size: {:.3f}, delta: {:.3f}, gamma: {:.3f}, theta: {:.4f}, vega: {:.3f}, imp vol: {:.3f}'.format(
                bar_l.symbol, bar_l.close_price, self.spot_close_price, 
                    l[0][1], bar.datetime, pos_l, delta_l, gamma_l, 
                    theta_l, vega_l, greek_l['imp_vol']))
            
            print('卖开: {} 价: {:.3f}, 现货价: {:.2f}, month: {}, date: {} buy_size: {:.3f}, delta: {:.3f}, gamma: {:.3f}, theta: {:.4f}, vega: {:.4f} imp vol: {:.3f}'.format(
                bar_s.symbol, bar_s.close_price, self.spot_close_price, 
                    l[1][1], bar.datetime, pos_s, delta_s, gamma_s, 
                    theta_s, vega_s, greek_s['imp_vol']))
            
            print('买现货, 价: {}, buy_size: {}'.format(self.spot_close_price, pos_spot))

            # 买入仓位
            self.buy(bar_l.symbol, bar_l.close_price, pos_l, order_type=OrderType.MARKET)
            self.short(bar_s.symbol, bar_l.close_price, pos_s, order_type=OrderType.MARKET)
            self.buy(self.spot_symbol, self.spot_close_price, pos_spot, order_type=OrderType.MARKET)
            print('total expected pos: {}'.format(abs(pos_l) + abs(pos_s) + abs(pos_spot)))
            self.last_hedge_day = bar.datetime
        
            

    def on_bar(self, bar):
        """
        Callback of new bar data update.
        """
        #self.cancel_all()
        if isinstance(bar, BarData) is True:
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
                if symbol in self.greeks:
                    del self.greeks[symbol]
            option_symbol_list = self.get_option_list()
            log_mark = False
            total_delta = 0
            total_gamma = 0
            for symbol, contract_bar in bar.symbol_based_dict.items():
                if symbol not in self.am_dict:
                    self.am_dict[symbol] = ArrayManager(self.win_len)
                self.am_dict[symbol].update_bar(contract_bar)
                
                if self.spot_close_price:
                    # 计算greeks
                    full_option_data = bar.options[symbol]
                    exp_date = datetime.datetime.strptime(full_option_data['delist_date'], '%Y%m%d')
                    vol = talib.STDDEV(self.am_dict[symbol].return_array, self.win_len)[-1]
                    if abs(vol) > 0.0000001:
                        option = Option(full_option_data['call_put'], 
                                        self.spot_close_price,
                                        full_option_data['strike_price'],
                                        bar.datetime.replace(tzinfo=None),
                                        exp_date,
                                        price=full_option_data['settle'],
                                        vol=abs(vol))

                        calc_price, delta, theta, gamma, vega = option.get_all()
                        imp_vol = option.get_impl_vol()
                        if symbol in option_symbol_list:
                            if log_mark is False:
                                log_mark = True
                                print('===========================================================')
                            print('{},  eval: {}, exp: {}, s: {}, k: {}, op price: {:.3f}, cal_price: {:.3f} '\
                                'delta: {:.3f}, vol: {:.3f}, imp vol: {:.3f}, theta {:.3f}, vega: {:.3f}, gamma: {:.3f}, pos: {:.3f}'.format(
                                symbol,
                                bar.datetime.replace(tzinfo=None).strftime('%Y%m%d'),
                                full_option_data['delist_date'],
                                self.spot_close_price,
                                full_option_data['strike_price'],
                                full_option_data['settle'],
                                calc_price,
                                delta,
                                vol,
                                imp_vol,
                                theta,
                                vega,
                                gamma, self.pos_dict[symbol]))
                            total_delta += self.pos_dict[symbol]*delta
                            total_gamma += self.pos_dict[symbol]*gamma
                            print('symbol: {} pos: {:3f}, delta: {:3f}, gamma: {:3f}'.format(
                                symbol, self.pos_dict[symbol], delta, gamma))
                        self.greeks[symbol] = {
                            'delta': delta,
                            'vol': vol,
                            'imp_vol': imp_vol,
                            'theta': theta,
                            'gamma': gamma,
                            'calc_price': calc_price,
                            'vega': vega,
                        }
                    else:
                        #print('new symbol: {}'.format(symbol))
                        pass
            if log_mark:
                # 计算total delta时把现货delta也加上
                print('total detla: {:.3f}, total gamma: {:.3f}'.format(
                    total_delta + self.pos_dict[self.spot_symbol], total_gamma))

            if self.spot_close_price:
                self.update_all_pos(bar)
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
