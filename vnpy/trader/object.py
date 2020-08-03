"""
Basic data structure used for general trading function in VN Trader.
"""

from collections import defaultdict

from dataclasses import dataclass
from datetime import datetime
from logging import INFO

from .constant import Direction, Exchange, Interval, Offset, Status, Product, OptionType, OrderType

ACTIVE_STATUSES = set([Status.SUBMITTING, Status.NOTTRADED, Status.PARTTRADED])


@dataclass
class BaseData:
    """
    Any data object needs a gateway_name as source
    and should inherit base data.
    """

    gateway_name: str


@dataclass
class TickData(BaseData):
    """
    Tick data contains information about:
        * last trade in market
        * orderbook snapshot
        * intraday market statistics.
    """

    symbol: str
    exchange: Exchange
    datetime: datetime

    name: str = ""
    volume: float = 0
    open_interest: float = 0
    last_price: float = 0
    last_volume: float = 0
    limit_up: float = 0
    limit_down: float = 0

    open_price: float = 0
    high_price: float = 0
    low_price: float = 0
    pre_close: float = 0

    bid_price_1: float = 0
    bid_price_2: float = 0
    bid_price_3: float = 0
    bid_price_4: float = 0
    bid_price_5: float = 0

    ask_price_1: float = 0
    ask_price_2: float = 0
    ask_price_3: float = 0
    ask_price_4: float = 0
    ask_price_5: float = 0

    bid_volume_1: float = 0
    bid_volume_2: float = 0
    bid_volume_3: float = 0
    bid_volume_4: float = 0
    bid_volume_5: float = 0

    ask_volume_1: float = 0
    ask_volume_2: float = 0
    ask_volume_3: float = 0
    ask_volume_4: float = 0
    ask_volume_5: float = 0

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"


@dataclass
class BarData(BaseData):
    """
    Candlestick bar data of a certain trading period.
    """

    symbol: str
    exchange: Exchange
    datetime: datetime

    interval: Interval = None
    volume: float = 0
    open_interest: float = 0
    open_price: float = 0
    high_price: float = 0
    low_price: float = 0
    close_price: float = 0

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"



class OptionBarData(BaseData):
    """
        bar data for option, symbol_based_dict和prop_based_dict存的东西是一样的，
        只是key不一样， symbol_based_dict key是合约码, prop_based_dict的结构类似：
        prop_based_dict = {
            'call': {
                1:{
                    'price1': {
                        'symbol': xxxx,
                        'exchange': xxxx,
                        'datetime': xxxxx,
                        'interval': xxxx,
                        'volume': xxxx,
                        'open_interest': xxxx,
                        'open_price': xxxx,
                        'high_price': xxxxx,
                        'low_price': xxxxx,
                        'close_price': xxxxxx,
                        'gateway_name': xxxxx,
                    },
                    'price2': {
                        xxxxxx
                    }
                },
                2: {
                    xxxx
                },
                4:{
                    xxxx
                }
            },
            'put': {
                xxxx
            }
        }
    """
    def __init__(
        self, 
        symbol: str,
        exchange: Exchange,
        datetime: datetime,
        interval: Interval,
        gateway_name: str,
        options: dict,
    ):
        self.symbol = symbol,
        self.exchange = exchange
        self.datetime = datetime
        self.interval = interval
        self.gateway_name = gateway_name
        self.options = options
        self.symbol_based_dict = {}
        rec_dd = lambda: defaultdict(rec_dd)
        self.prop_based_dict = rec_dd()

        for symbol, option in self.options.items():
            bar = BarData(
                symbol=symbol,
                exchange=self.exchange,
                datetime=self.datetime,
                interval=self.interval,
                volume=option['vol'],
                open_interest=0,
                open_price=option['open'],
                high_price=option['high'],
                low_price=option['low'],
                close_price=option['settle'],
                gateway_name="DB",
            )
            self.symbol_based_dict[symbol] = bar
            self.prop_based_dict[option['call_put']][option['s_month']][option['strike_price']] = bar

    def get_real_bar(self, spot_price, call_put, level, s_month):
        '''
            获取指定档位/类型的期权
            level 为正表示实值期权，为负表示虚值
        '''
        #print('OptionBarData.get_real_bar():  prop_based_dict: {}'.format(self.prop_based_dict[call_put].keys()))
        small_bar_list = [(price, bar) for price, bar in self.prop_based_dict[call_put][s_month].items() if price < spot_price]
        big_bar_list = [(price, bar) for price, bar in self.prop_based_dict[call_put][s_month].items() if price >= spot_price]
        small_bar_list = sorted(small_bar_list, key=lambda x: x[0], reverse=True)
        big_bar_list = sorted(big_bar_list, key=lambda x: x[0])
        if call_put == 'P':
            if level > 0:
                pair = big_bar_list[level-1]
            else:
                pair = small_bar_list[-level-1]
        else:
            if level > 0:
                pair = small_bar_list[level-1]
            else:
                pair = big_bar_list[-level-1]
        return pair[1]

    
    def get_num_day_expired(self, symbol, cur_date_str):
        '''
            指定期权还有多少天到期
        '''
        delist_date_str = self.options[symbol]['delist_date']
        cur_date = datetime.strptime(cur_date_str, '%Y%m%d')
        delist_date = datetime.strptime(delist_date_str, '%Y%m%d')
        return (delist_date-cur_date).days


@dataclass
class OrderData(BaseData):
    """
    Order data contains information for tracking lastest status
    of a specific order.
    """

    symbol: str
    exchange: Exchange
    orderid: str

    type: OrderType = OrderType.LIMIT
    direction: Direction = None
    offset: Offset = Offset.NONE
    price: float = 0
    volume: float = 0
    traded: float = 0
    status: Status = Status.SUBMITTING
    datetime: datetime = None

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"
        self.vt_orderid = f"{self.gateway_name}.{self.orderid}"

    def is_active(self) -> bool:
        """
        Check if the order is active.
        """
        if self.status in ACTIVE_STATUSES:
            return True
        else:
            return False

    def create_cancel_request(self) -> "CancelRequest":
        """
        Create cancel request object from order.
        """
        req = CancelRequest(
            orderid=self.orderid, symbol=self.symbol, exchange=self.exchange
        )
        return req


@dataclass
class TradeData(BaseData):
    """
    Trade data contains information of a fill of an order. One order
    can have several trade fills.
    """

    symbol: str
    exchange: Exchange
    orderid: str
    tradeid: str
    direction: Direction = None

    offset: Offset = Offset.NONE
    price: float = 0
    volume: float = 0
    datetime: datetime = None

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"
        self.vt_orderid = f"{self.gateway_name}.{self.orderid}"
        self.vt_tradeid = f"{self.gateway_name}.{self.tradeid}"


@dataclass
class PositionData(BaseData):
    """
    Positon data is used for tracking each individual position holding.
    """

    symbol: str
    exchange: Exchange
    direction: Direction

    volume: float = 0
    frozen: float = 0
    price: float = 0
    pnl: float = 0
    yd_volume: float = 0

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"
        self.vt_positionid = f"{self.vt_symbol}.{self.direction.value}"


@dataclass
class AccountData(BaseData):
    """
    Account data contains information about balance, frozen and
    available.
    """

    accountid: str

    balance: float = 0
    frozen: float = 0

    def __post_init__(self):
        """"""
        self.available = self.balance - self.frozen
        self.vt_accountid = f"{self.gateway_name}.{self.accountid}"


@dataclass
class LogData(BaseData):
    """
    Log data is used for recording log messages on GUI or in log files.
    """

    msg: str
    level: int = INFO

    def __post_init__(self):
        """"""
        self.time = datetime.now()


@dataclass
class ContractData(BaseData):
    """
    Contract data contains basic information about each contract traded.
    """

    symbol: str
    exchange: Exchange
    name: str
    product: Product
    size: int
    pricetick: float

    min_volume: float = 1           # minimum trading volume of the contract
    stop_supported: bool = False    # whether server supports stop order
    net_position: bool = False      # whether gateway uses net position volume
    history_data: bool = False      # whether gateway provides bar history data

    option_strike: float = 0
    option_underlying: str = ""     # vt_symbol of underlying contract
    option_type: OptionType = None
    option_expiry: datetime = None
    option_portfolio: str = ""
    option_index: str = ""          # for identifying options with same strike price

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"


@dataclass
class SubscribeRequest:
    """
    Request sending to specific gateway for subscribing tick data update.
    """

    symbol: str
    exchange: Exchange

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"


@dataclass
class OrderRequest:
    """
    Request sending to specific gateway for creating a new order.
    """

    symbol: str
    exchange: Exchange
    direction: Direction
    type: OrderType
    volume: float
    price: float = 0
    offset: Offset = Offset.NONE
    reference: str = ""

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"

    def create_order_data(self, orderid: str, gateway_name: str) -> OrderData:
        """
        Create order data from request.
        """
        order = OrderData(
            symbol=self.symbol,
            exchange=self.exchange,
            orderid=orderid,
            type=self.type,
            direction=self.direction,
            offset=self.offset,
            price=self.price,
            volume=self.volume,
            gateway_name=gateway_name,
        )
        return order


@dataclass
class CancelRequest:
    """
    Request sending to specific gateway for canceling an existing order.
    """

    orderid: str
    symbol: str
    exchange: Exchange

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"


@dataclass
class HistoryRequest:
    """
    Request sending to specific gateway for querying history data.
    """

    symbol: str
    exchange: Exchange
    start: datetime
    end: datetime = None
    interval: Interval = None

    def __post_init__(self):
        """"""
        self.vt_symbol = f"{self.symbol}.{self.exchange.value}"
