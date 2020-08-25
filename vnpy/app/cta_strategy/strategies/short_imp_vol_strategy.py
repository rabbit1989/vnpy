# coding=utf-8

import datetime
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from decimal import Decimal

import numpy as np
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
from vnpy.trader.constant import OrderType, OptionSMonth, Direction
from vnpy.trader.object import OptionBarData
from vnpy.trader.utility import Option, get_option_smonth


trade_day_set = (
{'2018-06-22', '2018-09-25', '2019-05-24', '2019-01-08', '2018-08-07', '2020-05-07', '2018-01-08', '2020-03-24', '2018-02-28', '2019-07-03', '2019-04-16', '2019-05-16', '2019-05-31', '2020-03-06', '2018-08-22', '2019-12-05', '2020-06-09', '2019-08-29', '2018-04-13', '2018-03-02', '2020-01-20', '2019-06-27', '2019-11-19', '2019-10-15', '2018-05-28', '2019-12-10', '2018-04-02', '2018-09-10', '2019-04-30', '2018-12-26', '2019-06-12', '2018-07-04', '2020-05-15', '2018-02-12', '2019-02-22', '2018-11-30', '2018-12-25', '2019-07-30', '2019-07-24', '2019-01-29', '2019-03-12', '2019-06-13', '2018-02-26', '2020-01-15', '2020-06-04', '2018-11-20', '2019-10-14', '2018-12-28', '2019-09-24', '2020-03-05', '2019-08-14', '2018-05-14', '2019-07-15', '2018-09-06', '2019-03-13', '2019-02-19', '2019-06-26', '2019-04-12', '2019-12-13', '2017-12-27', '2020-02-20', '2019-07-01', '2019-12-31', '2019-03-01', '2020-03-12', '2019-12-26', '2017-12-29', '2019-01-15', '2018-01-11', '2019-03-25', '2019-09-18', '2018-06-07', '2019-06-10', '2020-01-13', '2019-08-09', '2020-04-22', '2020-03-04', '2019-02-01', '2019-02-21', '2019-08-16', '2019-01-23', '2019-11-20', '2019-09-06', '2018-11-14', '2018-11-12', '2020-05-27', '2019-05-30', '2020-03-27', '2018-05-23', '2019-07-04', '2019-12-23', '2019-12-27', '2018-01-22', '2020-04-21', '2019-01-18', '2018-07-02', '2020-01-17', '2019-02-12', '2019-07-11', '2018-08-20', '2020-06-12', '2020-05-11', '2018-07-06', '2020-04-15', '2020-03-25', '2019-05-28', '2019-04-03', '2019-09-27', '2018-03-13', '2017-12-25', '2018-08-31', '2019-04-25', '2018-01-16', '2018-06-19', '2018-08-30', '2019-05-27', '2018-09-03', '2020-04-24', '2020-01-10', '2020-03-30', '2019-12-16', '2018-07-17', '2018-11-28', '2018-08-23', '2018-03-28', '2018-08-10', '2019-04-10', '2019-04-11', '2019-11-12', '2019-05-22', '2020-01-07', '2020-03-16', '2018-11-19', '2018-02-07', '2020-03-11', '2019-11-27', '2018-03-27', '2020-06-16', 
'2018-03-23', '2019-05-09', '2019-09-04', '2018-10-18', '2018-11-15', '2019-02-25', '2018-07-16', '2018-03-06', '2019-04-29', '2019-10-08', '2019-11-26', '2020-02-25', '2018-04-03', '2018-05-21', '2019-10-09', '2018-02-23', '2018-11-07', '2020-02-10', '2018-07-23', '2018-11-27', '2019-12-24', '2018-08-28', '2019-08-07', '2018-01-24', '2019-11-05', '2018-03-21', '2020-04-16', '2018-12-11', '2019-03-21', '2018-10-15', '2019-06-04', '2018-07-05', '2019-09-25', '2018-08-27', '2019-01-22', '2018-10-24', '2019-05-07', '2019-08-19', '2020-05-22', '2018-09-28', '2018-11-06', '2019-11-08', '2018-02-01', '2018-08-13', '2019-03-06', '2020-05-28', '2019-11-13', '2018-09-17', '2018-08-15', '2018-06-14', '2018-12-24', '2019-02-13', '2019-07-17', '2020-05-06', '2019-01-04', '2019-04-17', '2018-08-16', '2019-10-18', '2018-11-05', '2019-08-13', '2018-03-01', '2020-01-06', '2020-05-14', '2018-05-24', '2018-09-11', '2019-06-05', '2018-09-14', '2018-09-26', '2019-12-30', '2019-03-07', '2018-12-21', '2018-12-03', '2018-03-16', '2020-06-03', '2018-08-14', '2018-06-21', '2018-06-26', '2018-09-27', '2019-01-16', '2018-07-03', '2019-03-15', '2018-02-13', '2020-02-21', '2018-09-18', '2019-08-27', '2019-04-08', '2020-04-01', '2018-07-09', 
'2018-04-23', '2018-08-29', '2020-04-17', '2019-11-25', '2018-02-06', '2019-11-21', '2019-03-20', '2018-02-02', '2019-08-15', '2018-12-13', '2018-03-30', '2018-10-29', '2019-01-17', '2019-07-16', '2018-05-10', '2020-05-12', '2019-06-25', '2019-07-10', '2019-12-19', '2019-09-03', '2020-02-11', '2018-06-11', '2018-04-27', '2018-05-02', '2020-03-23', '2020-03-20', '2019-01-25', '2018-06-20', '2019-12-25', '2020-06-15', '2018-06-06', '2018-12-14', '2018-10-09', '2018-03-20', '2018-01-05', '2018-09-20', '2018-10-31', '2019-01-02', '2020-05-25', '2019-04-01', '2020-04-13', '2020-03-19', '2018-11-29', '2019-03-29', '2018-10-26', '2018-05-29', '2018-09-07', '2019-07-02', '2019-12-02', '2019-11-11', '2018-08-24', '2020-06-05', '2018-10-16', '2018-12-18', '2018-04-12', '2019-09-19', '2020-06-17', '2020-04-02', '2018-01-15', '2018-06-04', '2018-11-16', '2019-02-28', '2020-03-09', '2018-07-19', '2018-07-11', '2019-03-27', '2020-05-20', '2018-01-10', '2019-08-08', '2019-12-12', '2020-01-09', '2018-09-19', '2019-11-15', '2019-10-17', '2018-06-13', '2019-10-25', '2018-01-03', '2018-02-27', '2019-09-05', '2020-04-29', '2019-03-26', '2019-06-14', '2019-12-04', '2019-07-12', '2019-02-20', '2019-09-10', '2019-10-29', '2019-10-21', '2018-04-25', '2018-10-25', '2019-03-22', '2020-04-03', '2020-04-09', '2020-03-10', '2018-02-22', '2020-02-24', '2018-11-21', '2018-01-26', '2018-10-30', '2018-05-08', '2019-09-23', '2018-11-08', '2019-01-09', '2020-04-10', '2019-05-14', '2020-04-14', 
'2019-07-26', '2018-01-17', '2020-06-08', '2018-01-19', '2019-04-09', '2018-12-10', '2019-06-06', '2019-09-11', '2018-07-25', '2019-03-11', '2020-04-27', 
'2019-08-30', '2020-01-08', '2018-10-11', '2019-11-22', '2018-04-20', '2020-01-21', '2019-08-20', '2018-05-09', '2019-08-28', '2018-02-05', '2020-05-26', '2018-07-26', '2017-12-26', '2020-02-17', '2018-04-17', '2018-07-27', '2018-08-08', '2020-03-02', '2020-02-19', '2019-05-21', '2018-12-17', '2019-10-11', '2019-06-19', '2018-10-08', '2020-02-12', '2019-05-06', '2019-08-06', '2018-07-20', '2018-06-29', '2018-11-13', '2018-04-09', '2019-01-30', '2018-10-17', '2018-05-22', '2018-03-08', '2017-12-21', '2019-05-23', '2018-05-15', '2019-05-08', '2020-01-14', '2019-03-28', '2018-07-24', '2019-06-28', '2019-03-05', '2018-01-29', '2019-07-05', '2018-02-08', '2018-06-28', '2019-01-24', '2019-01-07', '2018-05-07', '2019-04-22', '2018-08-06', '2019-04-02', '2019-03-08', '2019-11-06', '2018-05-03', '2018-03-15', '2020-02-18', '2019-01-14', '2018-03-09', '2019-12-11', '2018-01-25', '2018-06-08', '2020-02-03', '2018-11-09', '2018-06-25', '2018-10-22', '2019-09-26', '2019-07-25', '2018-08-17', '2019-10-24', '2020-01-23', '2019-07-29', '2018-01-30', '2020-04-08', '2019-04-24', '2018-04-19', '2020-03-13', '2019-10-23', '2018-03-12', '2019-08-26', '2018-02-09', '2020-05-19', '2018-12-20', '2018-07-30', '2018-05-11', '2017-12-28', '2019-06-24', '2019-05-17', '2019-11-29', '2019-09-30', '2018-12-12', '2019-09-20', '2019-07-09', '2018-12-05', '2019-10-28', '2019-07-31', '2020-03-17', '2020-05-08', '2019-02-14', '2019-12-06', '2018-04-10', '2018-03-14', '2019-09-12', '2018-03-29', '2019-06-17', '2020-04-30', '2018-03-19', '2018-12-27', '2020-02-14', '2019-02-27', '2018-08-03', '2020-06-11', '2018-12-07', '2019-11-07', '2018-04-26', '2018-07-18', '2018-09-13', '2019-11-18', '2019-12-17', '2019-04-23', '2019-12-20', '2018-01-04', '2020-04-20', '2020-01-02', '2020-02-13', '2018-05-18', '2018-06-27', '2019-08-05', '2019-09-16', '2019-08-22', '2018-11-22', '2020-02-04', '2018-05-16', '2020-05-13', '2019-05-15', '2019-08-01', '2018-11-26', '2018-08-21', '2018-03-26', '2018-05-04', '2019-06-11', '2018-07-13', '2018-01-02', '2019-02-26', '2018-05-17', '2019-07-18', '2019-12-09', '2019-03-04', '2018-08-01', '2019-03-18', '2019-06-21', '2018-04-16', '2019-06-03', '2018-05-30', '2018-06-15', '2019-04-04', '2019-04-18', '2018-09-05', '2019-07-22', '2018-04-11', '2018-11-23', '2019-12-03', '2019-09-09', '2018-01-09', '2020-02-05', '2019-03-19', '2019-05-20', '2019-12-18', '2020-02-06', '2019-09-02', '2018-10-12', '2020-04-28', '2019-11-04', '2020-01-22', 
'2020-03-18', '2018-05-31', '2018-11-01', '2020-03-03', '2019-02-11', '2019-07-08', '2018-01-12', '2020-05-18', '2019-09-17', '2020-01-16', '2019-02-15', '2019-01-11', '2018-09-04', '2019-01-03', '2019-01-31', '2018-08-09', '2018-11-02', '2019-05-10', '2019-07-19', '2020-05-29', '2018-12-19', '2018-01-18', '2018-07-31', '2020-04-23', '2019-10-30', '2019-10-10', '2019-07-23', '2019-01-10', '2018-09-21', '2019-11-14', '2018-06-05', '2020-02-26', '2019-08-12', '2019-05-13', '2018-03-07', '2018-03-22', '2019-03-14', '2019-05-29', '2019-01-21', '2020-02-27', '2019-04-15', '2018-10-23', '2018-01-23', '2019-10-16', '2018-10-19', '2019-08-23', '2018-12-06', '2018-10-10', '2018-06-12', '2019-08-02', '2017-12-20', '2020-06-01', '2018-03-05', 
'2018-04-18', '2018-05-25', '2020-02-07', '2019-04-26', '2020-06-02', '2019-08-21', '2019-06-18', '2020-05-21', '2018-06-01', '2019-06-20', '2019-04-19', '2018-07-12', '2018-07-10', '2018-08-02', '2020-06-10', '2018-09-12', '2019-10-22', '2019-11-28', '2018-01-31', '2019-10-31', '2018-04-24', '2018-04-04', '2020-02-28', '2020-01-03', '2017-12-22', '2018-02-14', '2019-01-28', '2018-12-04', '2020-03-26', '2020-04-07', '2019-11-01', '2020-03-31', '2019-02-18'})

class PosState:
    Long = 'long'
    Short = 'short'
    Empty = 'empty'


def no_trade_in_days(dt, start_delta, end_delta):
    cnt = 0
    for i in range(start_delta, end_delta+1):
        date_str = (dt + datetime.timedelta(i)).strftime('%F')
        if not date_str in trade_day_set:
            cnt += 1
    return cnt >= end_delta-start_delta


class ShortImpVolStrategy(CtaTemplate):
    '''
        1.rv 低于 iv，做空波动率，rv 高于 iv 空仓，大假前空仓
        2. iv 高于k日最高，做多波动率， 买入后高于0.3平仓 或低于k日品藏
    '''
    author = "white"

    spot_symbol = None
    option_level = -1
    call_put = 'C'
    s_month_type = OptionSMonth.NEXT_MONTH
    fixed_size = 1
    win_len = 5
    break_percent = 0

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
        self.iv_array = []
        

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
    
    

    def short_volatility(self, option_bar, option):
        _, delta = option.get_price_delta()
        option_pos = self.fixed_size/delta
            #print('fixed size: {}, delta: {:3f}, cal_price: {:3f}, opt price: {} option_pos: {:.3f}'.format(
            #    self.fixed_size, delta, cal_price, full_option_data['settle'], option_pos))
        # 卖出期权
        self.short(option_bar.symbol, option_bar.close_price, option_pos, order_type=OrderType.MARKET)
        # 买入现货
        self.buy(self.spot_symbol, self.spot_close_price, self.fixed_size, order_type=OrderType.MARKET)


    def buy_volatility(self, option_bar, option):
        _, delta = option.get_price_delta()
        option_pos = self.fixed_size/delta
            #print('fixed size: {}, delta: {:3f}, cal_price: {:3f}, opt price: {} option_pos: {:.3f}'.format(
            #    self.fixed_size, delta, cal_price, full_option_data['settle'], option_pos))
        # 买入期权
        self.buy(option_bar.symbol, option_bar.close_price, option_pos, order_type=OrderType.MARKET)
        # 卖空现货
        self.short(self.spot_symbol, self.spot_close_price, self.fixed_size, order_type=OrderType.MARKET)



    def on_bar(self, bar):
        """
        Callback of new bar data update.
        """
        if isinstance(bar, BarData) is True:
            self.spot_close_price = bar.close_price
            self.am_spot.update_bar(bar)


        elif isinstance(bar, OptionBarData) is True and self.spot_close_price is not None:
            option_symbol_list = self.get_option_list()
            #if not option_symbol_list:            
            if True:
                s_month = get_option_smonth(bar.datetime, self.s_month_type)
                option_bar = bar.get_real_bar(
                    spot_price=self.spot_close_price, 
                    call_put=self.call_put,
                    level=self.option_level,
                    s_month=s_month)
            #else:
            #    option_bar = bar.symbol_based_dict[option_symbol_list[0]]
            rv = self.am_spot.vol_array[-1]
            full_option_data = bar.options[option_bar.symbol]
            exp_date = datetime.datetime.strptime(full_option_data['delist_date'], '%Y%m%d')
            option = Option(full_option_data['call_put'], 
                            self.spot_close_price,
                            full_option_data['strike_price'],
                            bar.datetime.replace(tzinfo=None),
                            exp_date,
                            price=full_option_data['settle'],
                            vol=abs(rv))
            iv = option.get_impl_vol()

            # 判断突破信号
            pre_max_vol = None
            pre_min_vol = None
            local_max = False
            local_min = False
            if len(self.iv_array) >= self.win_len:
                pre_max_vol = np.max(self.iv_array)
                pre_min_vol = np.min(self.iv_array)
                self.iv_array[:] = self.iv_array[1:]

            self.iv_array.append(iv)
            if pre_max_vol and pre_min_vol:
                cur_max_vol = np.max(self.iv_array)
                cur_min_vol = np.min(self.iv_array) 
                if cur_max_vol / pre_max_vol > 1+self.break_percent:
                    local_max = True
                elif cur_min_vol / pre_min_vol < 1-self.break_percent:
                    local_min = True
            
            # 判断仓位状态
            pos_state = PosState.Empty
            if option_symbol_list:
                option_symbol = option_symbol_list[0]
                if self.pos_dict[option_symbol] > 0:
                    pos_state = PosState.Long
                else:
                    pos_state = PosState.Short

            long_holiday_come = no_trade_in_days(bar.datetime, 2, 6)

            if (long_holiday_come is True and pos_state == PosState.Short) or \
              (pos_state == PosState.Short and (rv > iv or local_max is True)):
                # 两种情况会清仓: 
                # (1): 如果长假快到了且持仓
                # (2): 如果持仓且 (rv大于iv or iv 高于k日线)
                print('=========================================')
                print('====== clear pos: long holiday: {}, pos_state: {}, rv: {:.3f}, iv: {:.3f}, local_max: {}'.format(
                    long_holiday_come, pos_state, rv, iv, local_max))
                self.cover(option_symbol, None, -self.pos_dict[option_symbol], order_type=OrderType.MARKET)
                self.sell(self.spot_symbol, None, self.pos_dict[self.spot_symbol], order_type=OrderType.MARKET)
            elif pos_state == PosState.Empty and rv < iv and abs(rv) > 0.00001 and local_min is True:
                print('=========================================')
                print('======short_volatility======= rv: {:.3f}, iv: {:.3f}'.format(rv, iv))
                
                # 如果空仓且rv小于iv且iv低于k日线, 则卖出波动率                    
                self.short_volatility(option_bar, option)
            elif pos_state == PosState.Empty and (local_max is True or long_holiday_come is True):
                print('=========================================')
                print('======buy_volatility=======: local_max: {}, long holiday: {}'.format(local_max, long_holiday_come))
                # 如果空仓且(达到localmax, 或长假快到了)， 做多
                self.buy_volatility(option_bar, option)
            elif pos_state == PosState.Long and (iv > 0.3 or local_min is True):
                print('=========================================')
                print('====== clear pos: pos_state: {}, iv: {:.3f}, local_min: {}'.format(
                    pos_state, iv, local_min))
                
                # 如果持有多仓，且 (iv > 0.3 或 local_min到了），则清仓
                self.sell(option_symbol, None, self.pos_dict[option_symbol], order_type=OrderType.MARKET)
                self.cover(self.spot_symbol, None, -self.pos_dict[self.spot_symbol], order_type=OrderType.MARKET)
            


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
        print('on_trade: {}, {}, {}, {}, {:.3f}, {:.3f},'.format(
            trade.datetime.strftime('%F'), 
            trade.symbol,
            trade.direction, 
            trade.offset,
            trade.price, 
            trade.volume))
        self.last_trade_date = trade.datetime.strftime('%F')
        self.last_trade_symbol = trade.symbol
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
