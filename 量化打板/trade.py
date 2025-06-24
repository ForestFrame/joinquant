from data_fetch import get_orderbook_summary
from datetime import datetime, timedelta
from jqdatasdk import *

auth('13367910668','YZR0803lonely')

def initialize(context):
    # 初始化此策略
    # 设定沪深300作为基准
    set_benchmark('000300.XSHG')
    # 获取起始资金
    init_cash = context.portfolio.starting_cash
    schedule_run_min_tasks()
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 10:30运行自定义卖出函数
    run_daily(morning_sell_all, time='10:00')
    subscribe('000001.XSHE', 'tick')
    # 全局变量
    g.buy_per = 20
    g.top_100_stocks = []
    g.bought_stocks = []


def extract_bought_stocks(context):
    g.bought_stocks = []
    for account in context.subportfolios:
        # 提取 long_positions 中的股票代码
        for stock_code in account.long_positions.keys():
            g.bought_stocks.append(stock_code)


def schedule_run_min_tasks(start_time='9:20', end_time='14:00'):
    """
    每隔1分钟从 start_time 到 end_time 注册 run_min 到 run_daily。

    参数：
        start_time (str): 起始时间，格式如 '9:20'
        end_time (str): 结束时间，格式如 '15:00'
    """
    current = datetime.strptime(start_time, '%H:%M')
    end = datetime.strptime(end_time, '%H:%M')

    while current <= end:
        time_str = current.strftime('%H:%M')  # 使用两位小时格式
        run_daily(run_min, time_str)
        current += timedelta(minutes=1)


def add_one_minute(time_str):
    """
    将形如 '9:20' 的时间字符串加 1 分钟，返回新的时间字符串（格式：'HH:MM'）

    参数:
        time_str (str): 时间字符串，如 '9:20'

    返回:
        str: 加一分钟后的时间字符串，如 '9:21'
    """
    dt = datetime.strptime(time_str, '%H:%M')
    dt_plus_1 = dt + timedelta(minutes=1)
    return dt_plus_1.strftime('%-H:%M')


def run_min(context):
    g.cash_per_stock = context.portfolio.total_value / g.buy_per
    print(f"当前总权益: {context.portfolio.total_value:.2f}, 每只股票分配资金: {g.cash_per_stock:.2f}")
    g.top_100_stocks = get_orderbook_summary()
    unsubscribe_all()
    subscribe_stocks(g.top_100_stocks)


def morning_sell_all(context):
    # 将目前所有的股票卖出
    for security in context.portfolio.positions:
        # 全部卖出
        res = order_target(security, 0)
        if res == None:
            print(f"{security} 卖出失败")
            continue
        g.bought_stocks.remove(security)
        # 记录这次卖出
        print(f"卖出 {security}")


def handle_tick(context, tick):
    # print(tick.datetime)
    # print(g.top_100_stocks)
    price_above_2_stocks =  filter_low_price_stocks(g.top_100_stocks)
    empty_sell_stocks = filter_stocks_with_empty_sell(price_above_2_stocks)
    buy_stocks(context, empty_sell_stocks)
    extract_bought_stocks(context)


def map_to_jq_code(stock_code):
    """
    将6位股票代码映射为聚宽格式，如 '000001' -> '000001.XSHE'
    """
    if stock_code.startswith(('000', '001', '002', '003')):
        return stock_code + '.XSHE'  # 深市主板/中小板
    elif stock_code.startswith('30'):
        return stock_code + '.XSHE'  # 创业板
    elif stock_code.startswith('68'):
        return stock_code + '.XSHG'  # 科创板（上交所）
    elif stock_code.startswith('60'):
        return stock_code + '.XSHG'  # 沪市主板
    elif stock_code.startswith('4') or stock_code.startswith('8'):
        return stock_code + '.BJ'  # 北交所
    else:
        raise ValueError(f"无法识别的股票代码前缀: {stock_code}")


def extract_jq_code_name_pairs(stock_data):
    """
    提取股票信息列表中的 (聚宽格式代码, 股票名称) 对。

    参数:
        stock_data (list): 每个元素是包含 'code' 和 'name' 的股票字典。

    返回:
        list of tuples: 形如 [('300801.XSHE', '泰和科技'), ...]
    """
    result = []
    for stock in stock_data:
        code = stock.get('code', '')
        name = stock.get('name', '')
        try:
            jq_code = map_to_jq_code(code)
            result.append((jq_code, name))
        except ValueError:
            # 若无法转换，跳过或可设置为: result.append(('', name))
            continue
    return result


def filter_low_price_stocks(stock_data):
    """
    剔除买一价小于2元的股票。

    参数:
        stock_data (list): 股票信息列表，每个元素是一个字典，包含code、name、buy、sell字段。

    返回:
        list: 过滤后的股票信息列表。
    """
    filtered = []
    for stock in stock_data:
        buy_one_price = stock.get('buy', [(0, 0)])[0][0]
        if buy_one_price >= 2:
            filtered.append(stock)
    return filtered


def filter_stocks_with_empty_sell(stocks):
    result = []
    for stock in stocks:
        code = stock.get('code')
        name = stock.get('name')
        sell = stock.get('sell')  # list of (price, volume)

        if not sell or len(sell) < 5:
            # 如果卖盘不完整，直接跳过
            continue

        is_empty = [(p == 0.0 and v == 0) for p, v in sell]

        # 如果卖盘中有任意一个为空，就输出并加入结果
        if any(is_empty):
            # print(f"{name}-{code}：卖1~卖5中存在空挡，具体为空位：", [i + 1 for i, empty in enumerate(is_empty) if empty])
            result.append(stock)

    return result


def subscribe_stocks(stock_list):
    """
    对给定的股票列表进行循环订阅

    参数：
    - stock_list: List[Tuple[str, str]]，形如 [('301292', '海科新源'), ...]

    返回：
    - None
    """
    stocks = extract_jq_code_name_pairs(stock_list)
    for code, name in stocks:
        try:
            subscribe(code, 'tick')
            # print(f"成功订阅：{name}（{jq_code}）")
        except Exception as e:
            print(f"订阅失败：{name}（{code}），错误信息：{e}")


def buy_stocks(context, stocks):
    """
    从stocks中选出未买入的个股，按照指定仓位进行买入，买价来自 get_current_tick 的卖一价（a1_p）

    参数:
        context: 聚宽上下文
        stocks: List[Dict]，形如 [{'code': '301292', 'name': '海科新源', 'buy': [...], 'sell': [...]}, ...]
    """
    jq_codes = [map_to_jq_code(stock['code']) for stock in stocks]
    code_map = {map_to_jq_code(stock['code']): (stock['code'], stock['name']) for stock in stocks}

    tick_data = get_current_tick(jq_codes)

    for jq_code in jq_codes:
        if jq_code in g.bought_stocks:
            continue

        if context.portfolio.available_cash < 1000:
            return

        code, name = code_map[jq_code]
        tick = tick_data.get(jq_code)
        if tick is None:
            print(f"{name}-{jq_code} 无法获取 tick 数据")
            continue

        buy_price = tick.a1_p
        if not buy_price or buy_price == 0.0:
            print(f"{name}-{jq_code} 卖一价格无效")
            continue

        quantity = int(g.cash_per_stock // buy_price // 100) * 100
        if quantity <= 0:
            print(f"{name}-{jq_code} 可买股数不足1手 ({quantity} 股)")
            continue

        res = order(jq_code, quantity)
        if res is None:
            print(f"{name}-{jq_code} 买入失败")
            continue

        g.bought_stocks.append(jq_code)
        print(f"买入 {name}-{jq_code}，买价：{round(buy_price, 2)}，数量：{quantity} 股")







