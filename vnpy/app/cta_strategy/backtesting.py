# coding=utf-8

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Callable
from itertools import product
from functools import lru_cache
from time import time
import multiprocessing
import random
import traceback

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import talib
from deap import creator, base, tools, algorithms
from pandas import DataFrame
from pyecharts import Kline,Overlap,Line


from vnpy.app.portfolio_strategy.backtesting import PortfolioDailyResult
from vnpy.app.cta_strategy import ArrayManager
from vnpy.trader.constant import (Direction, Offset, Exchange,
                                  Interval, Status, OrderType)
from vnpy.trader.database import database_manager
from vnpy.trader.object import OrderData, TradeData, BarData, OptionBarData, TickData
from vnpy.trader.utility import round_to, Option, get_option_smonth, date_diff


from .base import (
    BacktestingMode,
    EngineType,
    STOPORDER_PREFIX,
    StopOrder,
    StopOrderStatus,
    INTERVAL_DELTA_MAP
)
from .template import CtaTemplate

# Set seaborn style
sns.set_style("whitegrid")

# Set deap algo
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
creator.create("Individual", list, fitness=creator.FitnessMax)



class OptimizationSetting:
    """
    Setting for runnning optimization.
    """

    def __init__(self):
        """"""
        self.params = {}
        self.target_name = ""

    def add_parameter(
        self, name: str, start: float, end: float = None, step: float = None
    ):
        """"""
        if not end and not step:
            self.params[name] = [start]
            return

        if start >= end:
            print("参数优化起始点必须小于终止点")
            return

        if step <= 0:
            print("参数优化步进必须大于0")
            return

        value = start
        value_list = []

        while value <= end:
            value_list.append(value)
            value += step

        self.params[name] = value_list

    def set_target(self, target_name: str):
        """"""
        self.target_name = target_name

    def generate_setting(self):
        """"""
        keys = self.params.keys()
        values = self.params.values()
        products = list(product(*values))

        settings = []
        for p in products:
            setting = dict(zip(keys, p))
            settings.append(setting)

        return settings

    def generate_setting_ga(self):
        """"""
        settings_ga = []
        settings = self.generate_setting()
        for d in settings:
            param = [tuple(i) for i in d.items()]
            settings_ga.append(param)
        return settings_ga


class BacktestingEngine:
    """"""

    engine_type = EngineType.BACKTESTING
    gateway_name = "BACKTESTING"

    def __init__(self):
        """"""
        self.configs = {}
        self.start = None
        self.end = None
        self.rate = 0
        self.slippage = 0
        self.size = 1
        self.pricetick = 0
        self.capital = 1_000_000
        self.mode = BacktestingMode.BAR
        self.inverse = False

        self.strategy_class = None
        self.strategy = None
        self.tick: TickData
        self.bar: BarData
        self.datetime = None

        self.interval = None
        self.days = 0
        self.callback = None

        self.stop_order_count = 0
        self.stop_orders = {}
        self.active_stop_orders = {}

        self.limit_order_count = 0
        self.limit_orders = {}
        self.active_limit_orders = {}

        self.market_order_count = 0
        self.active_market_orders = {}


        self.trade_count = 0
        self.trades = {}

        self.logs = []

        self.daily_results = {}
        self.daily_df = None
        
        # 缓存多品种数据当前的cursor，用于方法get_next_data
        self.data_cache_list = []

    def clear_data(self):
        """
        Clear all data of last backtesting.
        """
        self.strategy = None
        self.tick = None
        self.bar = None
        self.datetime = None

        self.stop_order_count = 0
        self.stop_orders.clear()
        self.active_stop_orders.clear()

        self.limit_order_count = 0
        self.limit_orders.clear()
        self.active_limit_orders.clear()

        self.trade_count = 0
        self.trades.clear()

        self.logs.clear()
        self.daily_results.clear()

    def set_parameters(
        self,
        configs : list,
        interval: Interval,
        start: datetime,
        rate: float,
        slippage: float,
        size: float,
        capital: int = 0,
        end: datetime = None,
        mode: BacktestingMode = BacktestingMode.BAR,
        inverse: bool = False
    ):
        """"""
        self.mode = mode
        self.interval = Interval(interval)
        self.rate = rate
        self.slippage = slippage
        self.size = size
        self.start = start


        # get symbol and exchange
        for vt_symbol, config in configs.items():
            symbol, exchange_str = vt_symbol.split(".")
            config['symbol'] = symbol
            config['exchange'] = Exchange(exchange_str)
            self.configs[symbol] = config

        self.capital = capital
        self.end = end
        self.inverse = inverse

    def add_strategy(self, strategy_class: type, setting: dict):
        """"""
        self.strategy_class = strategy_class
        self.strategy = strategy_class(
            self, strategy_class.__name__, self.configs.keys(), setting
        )

    def load_data(self):
        """"""
        self.output("开始加载历史数据")

        if not self.end:
            self.end = datetime.now()

        if self.start >= self.end:
            self.output("起始日期必须小于结束日期")
            return

        for symbol, config in self.configs.items():
            exchange = config['exchange']
            if self.mode == BacktestingMode.BAR:
                cursor = load_bar_data(
                    symbol,
                    exchange,
                    self.interval,
                    self.start,
                    self.end                    
                )
            else:
                cursor = load_tick_data(
                    symbol,
                    exchange,
                    self.start,
                    self.end
                )
            config['cursor'] = cursor            
            self.output(f"{symbol} 数据量：{cursor.count()}")

    def stat_vol(self, call_put, level, s_month_type, change_pos_day):
        # 统计一下节假日day1/2/3的real_vol/imp_vol 均值/中位数
        win_len = 20
        gen_obj_func = lambda data: data.to_bar()
        am_spot = ArrayManager(win_len)
        self.output("开始回放历史数据")
        dates = []
        log_returns = defaultdict(list)
        imp_vols = defaultdict(list)
        results = defaultdict(dict)
        spot_close_price = None
        opt_symbol = None
        while True:
            bar = self.get_next_data(gen_obj_func)
            if bar is None:
                break
            try:
                if isinstance(bar, BarData) is True:
                    spot_close_price = bar.close_price
                    am_spot.update_bar(bar)
                else:
                    if spot_close_price:
                        # 根据参数选出一个期权
                        #print('{} {} {}'.format(len(log_returns['day1']), len(log_returns['day2']), len(log_returns['day3'])))
                        if (opt_symbol is None or bar.get_num_day_expired(opt_symbol, bar.datetime.strftime("%Y%m%d")) < change_pos_day):
                            s_month = get_option_smonth(bar.datetime, s_month_type)
                            print('期权调仓: s_month: {}'.format(s_month))
                            opt_bar = bar.get_real_bar(
                                spot_price=spot_close_price, 
                                call_put=call_put,
                                level=level,
                                s_month=s_month)
                            opt_symbol = opt_bar.symbol

                        # 计算隐含波动率
                        full_option_data = bar.options[opt_symbol]
                        exp_date = datetime.strptime(full_option_data['delist_date'], '%Y%m%d')
                        option = Option(full_option_data['call_put'], 
                                        spot_close_price,
                                        full_option_data['strike_price'],
                                        bar.datetime.replace(tzinfo=None),
                                        exp_date,
                                        price=full_option_data['settle'],
                                        vol=0)

                        imp_vol = option.get_impl_vol()

                        # 更新 datetime
                        dates.append(bar.datetime)
                        # 更新数据
                        day = None
                        if len(dates) > 1 and date_diff(dates[-1], dates[-2]) > 1:
                            #print('day1: {}, {}'.format(dates[-2], dates[-1]))
                            day = 'day1'
                        elif len(dates) > 2 and date_diff(dates[-1], dates[-2]) == 1 and date_diff(dates[-2], dates[-3]) > 1:
                            day = 'day2'
                            #print('day2: {}, {}, {}'.format(dates[-3], dates[-2], dates[-1]))
                        elif len(dates) > 3 and date_diff(dates[-1], dates[-3]) == 2 and date_diff(dates[-3], dates[-4]) > 1:
                            day = 'day3'
                            #print('day3: {}, {}, {}, {}'.format(dates[-4], dates[-3], dates[-2], dates[-1]))
                        elif len(dates) > 4 and date_diff(dates[-1], dates[-4]) == 3 and date_diff(dates[-4], dates[-5]) > 1:
                            day = 'day4'
                        elif len(dates) > 5 and date_diff(dates[-1], dates[-5]) == 4 and date_diff(dates[-5], dates[-6]) > 1:
                            day = 'day5'
                        if day:
                            log_returns[day].append(am_spot.return_array[-1])
                            imp_vols[day].append(imp_vol)
                            #print('{} {} {:.3f} {:.3f}'.format(day, dates[-1], am_spot.return_array[-1], imp_vol))
            except Exception:
                self.output("触发异常，回测终止")
                self.output(traceback.format_exc())
                return
        # 统计结果
        for day in log_returns.keys():
            results[day]['real_vol'] = talib.STDDEV(np.array(log_returns[day]), len(log_returns[day]))[-1] * np.sqrt(252)
            results[day]['mean_imp_vol'] = np.mean(imp_vols[day])
            results[day]['median_imp_vol'] = np.median(imp_vols[day])
            results[day]['real_vol_len'] = len(log_returns[day])
            results[day]['imp_vol_len'] = len(imp_vols[day])
            
        
        print('======== results: ==========')
        for k, v in results.items():
            print('{}: {}'.format(k, v))
        # for day in log_returns.keys():
        #     returns = np.sort(log_returns[day])
        #     vols = np.sort(imp_vols[day])
        #     print('================ {} ==================='.format(day))
        #     print('================ {} ==================='.format(day))
        #     print('================ {} ==================='.format(day))
        #     for a, b in zip(returns, vols):
        #         print('{:.3f}, {:.3f}'.format(a, b))        


    def show_option_params(self, param_list, call_put, level, s_month_type, change_pos_day):
        '''
            
        '''
        win_len = 10
        gen_obj_func = lambda data: data.to_bar()
        self.output("开始回放历史数据")
        am_spot = ArrayManager(win_len)
        times = []
        param_dict = defaultdict(list)
        spot_close_price = None
        opt_symbol = None
        opt_bar = None
        realized_vol = None

        while True:
            bar = self.get_next_data(gen_obj_func)
            if bar is None:
                break
            try:
                if isinstance(bar, BarData) is True:
                    spot_close_price = bar.close_price
                    am_spot.update_bar(bar)
                    realized_vol = talib.STDDEV(am_spot.return_array, win_len)[-1] * np.sqrt(252)
                else:
                    if spot_close_price:
                        # 根据参数选出一个期权
                        if opt_symbol is None \
                          or bar.get_num_day_expired(opt_symbol, bar.datetime.strftime("%Y%m%d")) < change_pos_day:
                            print('期权调仓')
                            s_month = get_option_smonth(bar.datetime, s_month_type)
                            opt_bar = bar.get_real_bar(
                                spot_price=spot_close_price, 
                                call_put=call_put,
                                level=level,
                                s_month=s_month)
                            opt_symbol = opt_bar.symbol

                        # 计算希腊字母
                        full_option_data = bar.options[opt_symbol]
                        exp_date = datetime.strptime(full_option_data['delist_date'], '%Y%m%d')
                        if abs(realized_vol) > 0.0000001:
                            option = Option(full_option_data['call_put'], 
                                            spot_close_price,
                                            full_option_data['strike_price'],
                                            bar.datetime.replace(tzinfo=None),
                                            exp_date,
                                            price=full_option_data['settle'],
                                            vol=abs(realized_vol))

                            calc_price, delta, theta, gamma, vega = option.get_all()
                            imp_vol = option.get_impl_vol()
                            d = {
                                'realized_vol': round(realized_vol, 3),
                                'imp_vol': round(imp_vol, 3),
                                'delta': round(delta, 3),
                                'theta': round(theta, 4),
                                'gamma': round(gamma, 4),
                                'vega': round(vega, 4),
                                'calc_price': round(calc_price, 4),
                                'spot_price': round(spot_close_price, 3),
                                'op_price': full_option_data['settle'],
                                'k': full_option_data['strike_price'],
                            }
                            print('{} {}'.format(bar.datetime.strftime("%F"), d))
                            for param in param_list:
                                param_dict[param].append(d[param])
                            times.append(bar.datetime.strftime('%F'))
            except Exception:
                self.output("触发异常，回测终止")
                self.output(traceback.format_exc())
        figure_name = '_'.join(param_list)
        overlap = Overlap()
        for param in param_list:
            line = Line(param)
            # 如果是现货，换一个坐标轴显示
            new_axis = False
            yaxis_index = 0
            if param == 'spot_price':
                new_axis = True
                yaxis_index = 1             
            line.add(param, times, param_dict[param], is_label_show=True, is_datazoom_show=True)
            overlap.add(line, yaxis_index=yaxis_index, is_add_yaxis=new_axis)

        overlap.render(figure_name+'.html')
        self.output("历史数据回放结束")
    

    def run_backtesting(self):
        """"""
        if self.mode == BacktestingMode.BAR:
            func = self.new_bar
            gen_obj_func = lambda data: data.to_bar()
        else:
            func = self.new_tick
            gen_obj_func = lambda data: data.to_tick()

        self.strategy.on_init()            
        self.strategy.inited = True
        self.output("策略初始化完成")

        self.strategy.on_start()
        self.strategy.trading = True
        self.output("开始回放历史数据")

        while True:
            data_obj = self.get_next_data(gen_obj_func)
            if data_obj is None:
                break
            try:
                func(data_obj)
            except Exception:
                self.output("触发异常，回测终止")
                self.output(traceback.format_exc())
                return
        self.output("历史数据回放结束")


    def calculate_result(self):
        """"""
        self.output("开始计算逐日盯市盈亏")

        if not self.trades:
            self.output("成交记录为空，无法计算")
            return

        # Add trade data into daily reuslt.
        for trade in self.trades.values():
            d = trade.datetime.date()
            daily_result = self.daily_results[d]
            daily_result.add_trade(trade)

        # Calculate daily result by iteration.
        pre_closes = {}
        start_poses = {}

        # 构造 sizes, rates, slip

        for daily_result in self.daily_results.values():
            daily_result.calculate_pnl(
                pre_closes,
                start_poses,
                self.size,
                self.rate,
                self.slippage,
            )

            pre_closes = daily_result.close_prices
            start_poses = daily_result.end_poses

        # Generate dataframe
        results = defaultdict(list)
        acc_pnl = 0
        for daily_result in self.daily_results.values():
            for key, value in daily_result.__dict__.items():
                results[key].append(value)
            acc_pnl += daily_result.total_pnl
            print('date: {}, pnl: {:.3f}, acc pnl: {:.3f}'.format(
                daily_result.date, daily_result.total_pnl, acc_pnl))

        self.daily_df = DataFrame.from_dict(results).set_index("date")

        self.output("逐日盯市盈亏计算完成")
        return self.daily_df

    def calculate_statistics(self, df: DataFrame = None, output=True):
        """"""
        self.output("开始计算策略统计指标")

        # Check DataFrame input exterior
        if df is None:
            df = self.daily_df

        # Check for init DataFrame
        if df is None:
            # Set all statistics to 0 if no trade.
            start_date = ""
            end_date = ""
            total_days = 0
            profit_days = 0
            loss_days = 0
            end_balance = 0
            max_drawdown = 0
            max_ddpercent = 0
            max_drawdown_duration = 0
            total_net_pnl = 0
            daily_net_pnl = 0
            total_commission = 0
            daily_commission = 0
            total_slippage = 0
            daily_slippage = 0
            total_turnover = 0
            daily_turnover = 0
            total_trade_count = 0
            daily_trade_count = 0
            total_return = 0
            annual_return = 0
            daily_return = 0
            return_std = 0
            sharpe_ratio = 0
            return_drawdown_ratio = 0
        else:
            # Calculate balance related time series data
            df["balance"] = df["net_pnl"].cumsum() + self.capital
            df["return"] = np.log(df["balance"] / df["balance"].shift(1)).fillna(0)
            df["highlevel"] = (
                df["balance"].rolling(
                    min_periods=1, window=len(df), center=False).max()
            )
            df["drawdown"] = df["balance"] - df["highlevel"]
            df["ddpercent"] = df["drawdown"] / df["highlevel"] * 100

            # Calculate statistics value
            start_date = df.index[0]
            end_date = df.index[-1]

            total_days = len(df)
            profit_days = len(df[df["net_pnl"] > 0])
            loss_days = len(df[df["net_pnl"] < 0])

            end_balance = df["balance"].iloc[-1]
            max_drawdown = df["drawdown"].min()
            max_ddpercent = df["ddpercent"].min()
            max_drawdown_end = df["drawdown"].idxmin()

            if isinstance(max_drawdown_end, date):
                max_drawdown_start = df["balance"][:max_drawdown_end].idxmax()
                max_drawdown_duration = (max_drawdown_end - max_drawdown_start).days
            else:
                max_drawdown_duration = 0

            total_net_pnl = df["net_pnl"].sum()
            daily_net_pnl = total_net_pnl / total_days

            total_commission = df["commission"].sum()
            daily_commission = total_commission / total_days

            total_slippage = df["slippage"].sum()
            daily_slippage = total_slippage / total_days

            total_turnover = df["turnover"].sum()
            daily_turnover = total_turnover / total_days

            total_trade_count = df["trade_count"].sum()
            daily_trade_count = total_trade_count / total_days

            total_return = (end_balance / self.capital - 1) * 100
            annual_return = total_return / total_days * 240
            daily_return = df["return"].mean() * 100
            return_std = df["return"].std() * 100

            if return_std:
                sharpe_ratio = daily_return / return_std * np.sqrt(240)
            else:
                sharpe_ratio = 0

            return_drawdown_ratio = -total_return / max_ddpercent

        # Output
        if output:
            self.output("-" * 30)
            self.output(f"首个交易日：\t{start_date}")
            self.output(f"最后交易日：\t{end_date}")

            self.output(f"总交易日：\t{total_days}")
            self.output(f"盈利交易日：\t{profit_days}")
            self.output(f"亏损交易日：\t{loss_days}")

            self.output(f"起始资金：\t{self.capital:,.2f}")
            self.output(f"结束资金：\t{end_balance:,.2f}")

            self.output(f"总收益率：\t{total_return:,.2f}%")
            self.output(f"年化收益：\t{annual_return:,.2f}%")
            self.output(f"最大回撤: \t{max_drawdown:,.2f}")
            self.output(f"百分比最大回撤: {max_ddpercent:,.2f}%")
            self.output(f"最长回撤天数: \t{max_drawdown_duration}")

            self.output(f"总盈亏：\t{total_net_pnl:,.2f}")
            self.output(f"总手续费：\t{total_commission:,.2f}")
            self.output(f"总滑点：\t{total_slippage:,.2f}")
            self.output(f"总成交金额：\t{total_turnover:,.2f}")
            self.output(f"总成交笔数：\t{total_trade_count}")

            self.output(f"日均盈亏：\t{daily_net_pnl:,.2f}")
            self.output(f"日均手续费：\t{daily_commission:,.2f}")
            self.output(f"日均滑点：\t{daily_slippage:,.2f}")
            self.output(f"日均成交金额：\t{daily_turnover:,.2f}")
            self.output(f"日均成交笔数：\t{daily_trade_count}")

            self.output(f"日均收益率：\t{daily_return:,.2f}%")
            self.output(f"收益标准差：\t{return_std:,.2f}%")
            self.output(f"Sharpe Ratio：\t{sharpe_ratio:,.2f}")
            self.output(f"收益回撤比：\t{return_drawdown_ratio:,.2f}")

        statistics = {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total_days,
            "profit_days": profit_days,
            "loss_days": loss_days,
            "capital": self.capital,
            "end_balance": end_balance,
            "max_drawdown": max_drawdown,
            "max_ddpercent": max_ddpercent,
            "max_drawdown_duration": max_drawdown_duration,
            "total_net_pnl": total_net_pnl,
            "daily_net_pnl": daily_net_pnl,
            "total_commission": total_commission,
            "daily_commission": daily_commission,
            "total_slippage": total_slippage,
            "daily_slippage": daily_slippage,
            "total_turnover": total_turnover,
            "daily_turnover": daily_turnover,
            "total_trade_count": total_trade_count,
            "daily_trade_count": daily_trade_count,
            "total_return": total_return,
            "annual_return": annual_return,
            "daily_return": daily_return,
            "return_std": return_std,
            "sharpe_ratio": sharpe_ratio,
            "return_drawdown_ratio": return_drawdown_ratio,
        }

        # Filter potential error infinite value
        for key, value in statistics.items():
            if value in (np.inf, -np.inf):
                value = 0
            statistics[key] = np.nan_to_num(value)

        self.output("策略统计指标计算完成")
        return statistics

    def show_chart(self, df: DataFrame = None):
        """"""
        # Check DataFrame input exterior
        if df is None:
            df = self.daily_df

        # Check for init DataFrame
        if df is None:
            return

        plt.figure(figsize=(10, 16))

        balance_plot = plt.subplot(4, 1, 1)
        balance_plot.set_title("Balance")
        df["balance"].plot(legend=True)

        drawdown_plot = plt.subplot(4, 1, 2)
        drawdown_plot.set_title("Drawdown")
        drawdown_plot.fill_between(range(len(df)), df["drawdown"].values)

        pnl_plot = plt.subplot(4, 1, 3)
        pnl_plot.set_title("Daily Pnl")
        df["net_pnl"].plot(kind="bar", legend=False, grid=False, xticks=[])

        distribution_plot = plt.subplot(4, 1, 4)
        distribution_plot.set_title("Daily Pnl Distribution")
        df["net_pnl"].hist(bins=50)

        plt.show()

    def run_optimization(self, optimization_setting: OptimizationSetting, output=True):
        """"""
        # Get optimization setting and target
        settings = optimization_setting.generate_setting()
        target_name = optimization_setting.target_name

        if not settings:
            self.output("优化参数组合为空，请检查")
            return

        if not target_name:
            self.output("优化目标未设置，请检查")
            return

        # Use multiprocessing pool for running backtesting with different setting
        # Force to use spawn method to create new process (instead of fork on Linux)
        ctx = multiprocessing.get_context("spawn")
        pool = ctx.Pool(multiprocessing.cpu_count())

        results = []
        for setting in settings:
            result = (pool.apply_async(optimize, (
                target_name,
                self.strategy_class,
                setting,
                self.vt_symbol,
                self.interval,
                self.start,
                self.rate,
                self.slippage,
                self.size,
                self.pricetick,
                self.capital,
                self.end,
                self.mode,
                self.inverse
            )))
            results.append(result)

        pool.close()
        pool.join()

        # Sort results and output
        result_values = [result.get() for result in results]
        result_values.sort(reverse=True, key=lambda result: result[1])

        if output:
            for value in result_values:
                msg = f"参数：{value[0]}, 目标：{value[1]}"
                self.output(msg)

        return result_values

    def run_ga_optimization(self, optimization_setting: OptimizationSetting, population_size=100, ngen_size=30, output=True):
        """"""
        # Get optimization setting and target
        settings = optimization_setting.generate_setting_ga()
        target_name = optimization_setting.target_name

        if not settings:
            self.output("优化参数组合为空，请检查")
            return

        if not target_name:
            self.output("优化目标未设置，请检查")
            return

        # Define parameter generation function
        def generate_parameter():
            """"""
            return random.choice(settings)

        def mutate_individual(individual, indpb):
            """"""
            size = len(individual)
            paramlist = generate_parameter()
            for i in range(size):
                if random.random() < indpb:
                    individual[i] = paramlist[i]
            return individual,

        # Create ga object function
        global ga_target_name
        global ga_strategy_class
        global ga_setting
        global ga_vt_symbol
        global ga_interval
        global ga_start
        global ga_rate
        global ga_slippage
        global ga_size
        global ga_pricetick
        global ga_capital
        global ga_end
        global ga_mode
        global ga_inverse

        ga_target_name = target_name
        ga_strategy_class = self.strategy_class
        ga_setting = settings[0]
        ga_vt_symbol = self.vt_symbol
        ga_interval = self.interval
        ga_start = self.start
        ga_rate = self.rate
        ga_slippage = self.slippage
        ga_size = self.size
        ga_pricetick = self.pricetick
        ga_capital = self.capital
        ga_end = self.end
        ga_mode = self.mode
        ga_inverse = self.inverse

        # Set up genetic algorithem
        toolbox = base.Toolbox()
        toolbox.register("individual", tools.initIterate, creator.Individual, generate_parameter)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("mate", tools.cxTwoPoint)
        toolbox.register("mutate", mutate_individual, indpb=1)
        toolbox.register("evaluate", ga_optimize)
        toolbox.register("select", tools.selNSGA2)

        total_size = len(settings)
        pop_size = population_size                      # number of individuals in each generation
        lambda_ = pop_size                              # number of children to produce at each generation
        mu = int(pop_size * 0.8)                        # number of individuals to select for the next generation

        cxpb = 0.95         # probability that an offspring is produced by crossover
        mutpb = 1 - cxpb    # probability that an offspring is produced by mutation
        ngen = ngen_size    # number of generation

        pop = toolbox.population(pop_size)
        hof = tools.ParetoFront()               # end result of pareto front

        stats = tools.Statistics(lambda ind: ind.fitness.values)
        np.set_printoptions(suppress=True)
        stats.register("mean", np.mean, axis=0)
        stats.register("std", np.std, axis=0)
        stats.register("min", np.min, axis=0)
        stats.register("max", np.max, axis=0)

        # Multiprocessing is not supported yet.
        # pool = multiprocessing.Pool(multiprocessing.cpu_count())
        # toolbox.register("map", pool.map)

        # Run ga optimization
        self.output(f"参数优化空间：{total_size}")
        self.output(f"每代族群总数：{pop_size}")
        self.output(f"优良筛选个数：{mu}")
        self.output(f"迭代次数：{ngen}")
        self.output(f"交叉概率：{cxpb:.0%}")
        self.output(f"突变概率：{mutpb:.0%}")

        start = time()

        algorithms.eaMuPlusLambda(
            pop,
            toolbox,
            mu,
            lambda_,
            cxpb,
            mutpb,
            ngen,
            stats,
            halloffame=hof
        )

        end = time()
        cost = int((end - start))

        self.output(f"遗传算法优化完成，耗时{cost}秒")

        # Return result list
        results = []

        for parameter_values in hof:
            setting = dict(parameter_values)
            target_value = ga_optimize(parameter_values)[0]
            results.append((setting, target_value, {}))

        return results

    def update_daily_close(self, bar):
        """"""
        d = self.datetime.date()
        close_prices = {}

        if type(bar) is not OptionBarData:
            close_prices[bar.vt_symbol] = bar.close_price
        else:
            # 把有仓位的期权合约拎出来，更新一下dailyresult
            for symbol in self.strategy.pos_dict.keys():
                option_bar = bar.symbol_based_dict.get(symbol, None)
                if option_bar is None:
                    continue
                close_prices[option_bar.vt_symbol] = option_bar.close_price
        #print('update_daily_close: {}'.format(close_prices))
        daily_result = self.daily_results.get(d, None)
        if daily_result:
            daily_result.update_close_prices(close_prices)
        else:
            self.daily_results[d] = PortfolioDailyResult(d, close_prices)


    def new_bar(self, bar: BarData):
        """"""
        self.bar = bar
        self.datetime = bar.datetime

        self.cross_market_order()
        self.cross_limit_order()
        self.cross_stop_order()
        self.strategy.on_bar(bar)
        self.update_daily_close(bar)


    def new_tick(self, tick: TickData):
        """"""
        self.tick = tick
        self.datetime = tick.datetime

        self.cross_market_order()
        self.cross_limit_order()
        self.cross_stop_order()
        self.strategy.on_tick(tick)

        self.update_daily_close(tick.last_price)

    def cross_market_order(self):
        """
        Cross market order with last bar/tick data.
        """
        if self.mode == BacktestingMode.BAR:
            if type(self.bar) is not OptionBarData:
                long_cross_price = self.bar.open_price
                short_cross_price = self.bar.open_price
        else:
            long_cross_price = self.tick.ask_price_1
            short_cross_price = self.tick.bid_price_1
        for order in list(self.active_market_orders.values()):
            if type(self.bar) is OptionBarData:
                # 如果是opt数据，从bar里面把真正的合约拿出来
                real_bar = self.bar.symbol_based_dict.get(order.symbol, None)
                if real_bar is None:
                    print('can not find real option bar for {}'.format(order.symbol))
                    continue
                #print('cross_market_order(): symbol: {}'.format(real_bar.symbol))
                long_cross_price = real_bar.open_price
                short_cross_price = real_bar.open_price
            elif order.symbol != self.bar.symbol:
                continue

            # Push order update with status "not traded" (pending).
            if order.status == Status.SUBMITTING:
                order.status = Status.NOTTRADED
                self.strategy.on_order(order)

            # Push order udpate with status "all traded" (filled).
            order.traded = order.volume
            order.status = Status.ALLTRADED
            self.strategy.on_order(order)

            self.active_market_orders.pop(order.vt_orderid)

            # Push trade update
            self.trade_count += 1

            if (order.direction == Direction.LONG and order.offset == Offset.OPEN) \
              or (order.direction == Direction.SHORT and order.offset == Offset.CLOSE):
                trade_price = long_cross_price
                pos_change = order.volume
            else:
                trade_price = short_cross_price
                pos_change = -order.volume
            #print('cross_market_order(): symbol: {}, trade price: {}, pos_change: {}'.format(
            #    real_bar.symbol, trade_price, pos_change))
            trade = TradeData(
                symbol=order.symbol,
                exchange=order.exchange,
                orderid=order.orderid,
                tradeid=str(self.trade_count),
                direction=order.direction,
                offset=order.offset,
                price=trade_price,
                volume=order.volume,
                datetime=self.datetime,
                gateway_name=self.gateway_name,
            )
            self.strategy.update_pos(order.symbol, pos_change, self.bar)
            self.strategy.on_trade(trade)

            self.trades[trade.vt_tradeid] = trade



    def cross_limit_order(self):
        """
        Cross limit order with last bar/tick data.
        """
        if self.mode == BacktestingMode.BAR:
            if type(self.bar) is not OptionBarData:
                long_cross_price = self.bar.low_price
                short_cross_price = self.bar.high_price
                long_best_price = self.bar.open_price
                short_best_price = self.bar.open_price
        else:
            long_cross_price = self.tick.ask_price_1
            short_cross_price = self.tick.bid_price_1
            long_best_price = long_cross_price
            short_best_price = short_cross_price
        for order in list(self.active_limit_orders.values()):
            if type(self.bar) is OptionBarData:
                # 如果是opt数据，从bar里面把真正的合约拿出来
                real_bar = self.bar.symbol_based_dict.get(order.symbol, None)
                if real_bar is None:
                    continue
                long_cross_price = real_bar.low_price
                short_cross_price = real_bar.high_price
                long_best_price = real_bar.open_price
                short_best_price = real_bar.open_price

            # Push order update with status "not traded" (pending).
            if order.status == Status.SUBMITTING:
                order.status = Status.NOTTRADED
                self.strategy.on_order(order)
            print('order price: {}, long cross price: {}'.format(order.price, long_cross_price))
            # Check whether limit orders can be filled.
            long_cross = (
                order.direction == Direction.LONG
                and order.price >= long_cross_price
                and long_cross_price > 0
            )

            short_cross = (
                order.direction == Direction.SHORT
                and order.price <= short_cross_price
                and short_cross_price > 0
            )

            if not long_cross and not short_cross:
                continue
            # Push order udpate with status "all traded" (filled).
            order.traded = order.volume
            order.status = Status.ALLTRADED
            self.strategy.on_order(order)

            self.active_limit_orders.pop(order.vt_orderid)

            # Push trade update
            self.trade_count += 1

            if long_cross:
                trade_price = min(order.price, long_best_price)
                pos_change = order.volume
            else:
                trade_price = max(order.price, short_best_price)
                pos_change = -order.volume

            trade = TradeData(
                symbol=order.symbol,
                exchange=order.exchange,
                orderid=order.orderid,
                tradeid=str(self.trade_count),
                direction=order.direction,
                offset=order.offset,
                price=trade_price,
                volume=order.volume,
                datetime=self.datetime,
                gateway_name=self.gateway_name,
            )

            self.strategy.update_pos(order.symbol, pos_change, self.bar)
            self.strategy.on_trade(trade)

            self.trades[trade.vt_tradeid] = trade

    def cross_stop_order(self):
        """
        Cross stop order with last bar/tick data.
        """
        if self.mode == BacktestingMode.BAR:
            if type(self.bar) is not OptionBarData:
                long_cross_price = self.bar.high_price
                short_cross_price = self.bar.low_price
                long_best_price = self.bar.open_price
                short_best_price = self.bar.open_price
        else:
            long_cross_price = self.tick.last_price
            short_cross_price = self.tick.last_price
            long_best_price = long_cross_price
            short_best_price = short_cross_price

        for stop_order in list(self.active_stop_orders.values()):
            # Check whether stop order can be triggered.
            long_cross = (
                stop_order.direction == Direction.LONG
                and stop_order.price <= long_cross_price
            )

            short_cross = (
                stop_order.direction == Direction.SHORT
                and stop_order.price >= short_cross_price
            )

            if not long_cross and not short_cross:
                continue

            # Create order data.
            self.limit_order_count += 1

            order = OrderData(
                symbol=self.symbol,
                exchange=self.exchange,
                orderid=str(self.limit_order_count),
                direction=stop_order.direction,
                offset=stop_order.offset,
                price=stop_order.price,
                volume=stop_order.volume,
                status=Status.ALLTRADED,
                gateway_name=self.gateway_name,
                datetime=self.datetime
            )

            self.limit_orders[order.vt_orderid] = order

            # Create trade data.
            if long_cross:
                trade_price = max(stop_order.price, long_best_price)
                pos_change = order.volume
            else:
                trade_price = min(stop_order.price, short_best_price)
                pos_change = -order.volume

            self.trade_count += 1

            trade = TradeData(
                symbol=order.symbol,
                exchange=order.exchange,
                orderid=order.orderid,
                tradeid=str(self.trade_count),
                direction=order.direction,
                offset=order.offset,
                price=trade_price,
                volume=order.volume,
                datetime=self.datetime,
                gateway_name=self.gateway_name,
            )

            self.trades[trade.vt_tradeid] = trade

            # Update stop order.
            stop_order.vt_orderids.append(order.vt_orderid)
            stop_order.status = StopOrderStatus.TRIGGERED

            if stop_order.stop_orderid in self.active_stop_orders:
                self.active_stop_orders.pop(stop_order.stop_orderid)

            # Push update to strategy.
            self.strategy.on_stop_order(stop_order)
            self.strategy.on_order(order)

            self.strategy.pos_dict[symbol] += pos_change
            self.strategy.on_trade(trade)

    def load_bar(
        self,
        vt_symbol: str,
        days: int,
        interval: Interval,
        callback: Callable,
        use_database: bool
    ):
        """"""
        self.days = days
        self.callback = callback

    def load_tick(self, vt_symbol: str, days: int, callback: Callable):
        """"""
        self.days = days
        self.callback = callback

    def send_order(
        self,
        strategy: CtaTemplate,
        symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        order_type: OrderType,
        lock: bool
    ):
        """"""
        #round_price = round_to(price, self.configs[symbol]['pricetick'])
        round_price = price
        if order_type == OrderType.STOP:
            vt_orderid = self.send_stop_order(symbol, direction, offset, round_price, volume)
        elif order_type == OrderType.LIMIT:
            vt_orderid = self.send_limit_order(symbol, direction, offset, round_price, volume)
        elif order_type == OrderType.MARKET:
            vt_orderid = self.send_market_order(symbol, direction, offset, round_price, volume)
        return [vt_orderid]

    def send_stop_order(
        self,
        symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ):
        """"""
        self.stop_order_count += 1

        stop_order = StopOrder(
            vt_symbol=symbol,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            stop_orderid=f"{STOPORDER_PREFIX}.{self.stop_order_count}",
            strategy_name=self.strategy.strategy_name,
        )

        self.active_stop_orders[stop_order.stop_orderid] = stop_order
        self.stop_orders[stop_order.stop_orderid] = stop_order

        return stop_order.stop_orderid

    def send_limit_order(
        self,
        symbol,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ):
        """"""
        self.limit_order_count += 1
        exchange = self.configs[symbol]['exchange'] if symbol in self.configs else Exchange('SSE') 
        order = OrderData(
            symbol=symbol,
            exchange=exchange,
            orderid='Limit_{}'.format(self.limit_order_count),
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            status=Status.SUBMITTING,
            gateway_name=self.gateway_name,
            datetime=self.datetime
        )

        self.active_limit_orders[order.vt_orderid] = order
        self.limit_orders[order.vt_orderid] = order

        return order.vt_orderid


    def send_market_order(
        self,
        symbol,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ):
        """"""
        self.market_order_count += 1
        exchange = self.configs[symbol]['exchange'] if symbol in self.configs else Exchange('SSE') 
        order = OrderData(
            symbol=symbol,
            exchange=exchange,
            orderid='Market_{}'.format(self.market_order_count),
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            status=Status.SUBMITTING,
            gateway_name=self.gateway_name,
            datetime=self.datetime
        )

        self.active_market_orders[order.vt_orderid] = order
        return order.vt_orderid


    def cancel_order(self, strategy: CtaTemplate, vt_orderid: str):
        """
        Cancel order by vt_orderid.
        """
        if vt_orderid.startswith(STOPORDER_PREFIX):
            self.cancel_stop_order(strategy, vt_orderid)
        else:
            self.cancel_limit_order(strategy, vt_orderid)
            self.cancel_market_order(strategy, vt_orderid)
        

    def cancel_stop_order(self, strategy: CtaTemplate, vt_orderid: str):
        """"""
        if vt_orderid not in self.active_stop_orders:
            return
        stop_order = self.active_stop_orders.pop(vt_orderid)

        stop_order.status = StopOrderStatus.CANCELLED
        self.strategy.on_stop_order(stop_order)

    def cancel_limit_order(self, strategy: CtaTemplate, vt_orderid: str):
        """"""
        if vt_orderid not in self.active_limit_orders:
            return
        order = self.active_limit_orders.pop(vt_orderid)

        order.status = Status.CANCELLED
        self.strategy.on_order(order)


    def cancel_market_order(self, strategy: CtaTemplate, vt_orderid: str):
        """"""
        if vt_orderid not in self.active_market_orders:
            return
        order = self.active_market_orders.pop(vt_orderid)

        order.status = Status.CANCELLED
        self.strategy.on_order(order)


    def cancel_all(self, strategy: CtaTemplate):
        """
        Cancel all orders, both limit and stop.
        """
        vt_orderids = list(self.active_limit_orders.keys())
        for vt_orderid in vt_orderids:
            self.cancel_limit_order(strategy, vt_orderid)


        market_orderids = list(self.active_market_orders.keys())
        for vt_orderid in market_orderids:
            self.cancel_market_order(vt_orderid)
        
        stop_orderids = list(self.active_stop_orders.keys())
        for vt_orderid in stop_orderids:
            self.cancel_stop_order(strategy, vt_orderid)
        


    def write_log(self, msg: str, strategy: CtaTemplate = None):
        """
        Write log message.
        """
        msg = f"{self.datetime}\t{msg}"
        self.logs.append(msg)

    def send_email(self, msg: str, strategy: CtaTemplate = None):
        """
        Send email to default receiver.
        """
        pass

    def sync_strategy_data(self, strategy: CtaTemplate):
        """
        Sync strategy data into json file.
        """
        pass

    def get_engine_type(self):
        """
        Return engine type.
        """
        return self.engine_type

    def get_pricetick(self, strategy: CtaTemplate):
        """
        Return contract pricetick data.
        """
        return self.pricetick

    def put_strategy_event(self, strategy: CtaTemplate):
        """
        Put an event to update strategy status.
        """
        pass

    def output(self, msg):
        """
        Output message of backtesting engine.
        """
        print(f"{datetime.now()}\t{msg}")

    def get_all_trades(self):
        """
        Return all trade data of current backtesting result.
        """
        return list(self.trades.values())

    def get_all_orders(self):
        """
        Return all limit order data of current backtesting result.
        """
        return list(self.limit_orders.values())

    def get_all_daily_results(self):
        """
        Return all daily result data.
        """
        return list(self.daily_results.values())

    def get_next_data(self, gen_obj_func):
        '''
            多品种场景下，获取下一个时间周期的数据
        '''
        if not self.data_cache_list:
            for vt_symbol, config in self.configs.items():
                # data pair: 0: 数据， 1:cursor, 2: vt_symbol 
                cursor = config['cursor']
                self.data_cache_list.append((cursor.next(), cursor, vt_symbol))
        
        def get_min_index():    
            min_date_time = None
            min_index = 0
            for i, ele in enumerate(self.data_cache_list):
                raw_data = ele[0]
                if min_date_time is None or raw_data['datetime'] < min_date_time:
                    min_index = i
                    min_date_time = raw_data['datetime']
            return min_index

        index = get_min_index()
        data_pair = self.data_cache_list[index]
        del self.data_cache_list[index]
        data_obj = gen_obj_func(data_pair[0])
        
        try:
            self.data_cache_list.append((data_pair[1].next(), 
                                         data_pair[1], 
                                         data_pair[2]))  
        except Exception:
            self.output('get_next_data(): no more data')
            return None
        return data_obj
    

class DailyResult:
    """"""

    def __init__(self, date: date, close_price: float):
        """"""
        self.date = date
        self.close_price = close_price
        self.pre_close = 0

        self.trades = []
        self.trade_count = 0

        self.start_pos = 0
        self.end_pos = 0

        self.turnover = 0
        self.commission = 0
        self.slippage = 0

        self.trading_pnl = 0
        self.holding_pnl = 0
        self.total_pnl = 0
        self.net_pnl = 0

    def add_trade(self, trade: TradeData):
        """"""
        self.trades.append(trade)

    def calculate_pnl(
        self,
        pre_close: float,
        start_pos: float,
        size: int,
        rate: float,
        slippage: float,
        inverse: bool
    ):
        """"""
        # If no pre_close provided on the first day,
        # use value 1 to avoid zero division error
        if pre_close:
            self.pre_close = pre_close
        else:
            self.pre_close = 1

        # Holding pnl is the pnl from holding position at day start
        self.start_pos = start_pos
        self.end_pos = start_pos

        if not inverse:     # For normal contract
            self.holding_pnl = self.start_pos * \
                (self.close_price - self.pre_close) * size
        else:               # For crypto currency inverse contract
            self.holding_pnl = self.start_pos * \
                (1 / self.pre_close - 1 / self.close_price) * size

        # Trading pnl is the pnl from new trade during the day
        self.trade_count = len(self.trades)

        for trade in self.trades:
            if trade.direction == Direction.LONG:
                pos_change = trade.volume
            else:
                pos_change = -trade.volume

            self.end_pos += pos_change

            # For normal contract
            if not inverse:
                turnover = trade.volume * size * trade.price
                self.trading_pnl += pos_change * \
                    (self.close_price - trade.price) * size
                self.slippage += trade.volume * size * slippage
            # For crypto currency inverse contract
            else:
                turnover = trade.volume * size / trade.price
                self.trading_pnl += pos_change * \
                    (1 / trade.price - 1 / self.close_price) * size
                self.slippage += trade.volume * size * slippage / (trade.price ** 2)

            self.turnover += turnover
            self.commission += turnover * rate

        # Net pnl takes account of commission and slippage cost
        self.total_pnl = self.trading_pnl + self.holding_pnl
        self.net_pnl = self.total_pnl - self.commission - self.slippage


def optimize(
    target_name: str,
    strategy_class: CtaTemplate,
    setting: dict,
    vt_symbol: str,
    interval: Interval,
    start: datetime,
    rate: float,
    slippage: float,
    size: float,
    pricetick: float,
    capital: int,
    end: datetime,
    mode: BacktestingMode,
    inverse: bool
):
    """
    Function for running in multiprocessing.pool
    """
    engine = BacktestingEngine()

    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=interval,
        start=start,
        rate=rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        capital=capital,
        end=end,
        mode=mode,
        inverse=inverse
    )

    engine.add_strategy(strategy_class, setting)
    engine.load_data()
    engine.run_backtesting()
    engine.calculate_result()
    statistics = engine.calculate_statistics(output=False)

    target_value = statistics[target_name]
    return (str(setting), target_value, statistics)


@lru_cache(maxsize=1000000)
def _ga_optimize(parameter_values: tuple):
    """"""
    setting = dict(parameter_values)

    result = optimize(
        ga_target_name,
        ga_strategy_class,
        setting,
        ga_vt_symbol,
        ga_interval,
        ga_start,
        ga_rate,
        ga_slippage,
        ga_size,
        ga_pricetick,
        ga_capital,
        ga_end,
        ga_mode,
        ga_inverse
    )
    return (result[1],)


def ga_optimize(parameter_values: list):
    """"""
    return _ga_optimize(tuple(parameter_values))


@lru_cache(maxsize=999)
def load_bar_data(
    symbol: str,
    exchange: Exchange,
    interval: Interval,
    start: datetime,
    end: datetime
):
    """"""
    return database_manager.load_bar_data(
        symbol, exchange, interval, start, end
    )


@lru_cache(maxsize=999)
def load_tick_data(
    symbol: str,
    exchange: Exchange,
    start: datetime,
    end: datetime
):
    """"""
    return database_manager.load_tick_data(
        symbol, exchange, start, end
    )


# GA related global value
ga_end = None
ga_mode = None
ga_target_name = None
ga_strategy_class = None
ga_setting = None
ga_vt_symbol = None
ga_interval = None
ga_start = None
ga_rate = None
ga_slippage = None
ga_size = None
ga_pricetick = None
ga_capital = None
