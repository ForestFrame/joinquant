import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 获取涨幅前100名的A股股票代码和名称
def get_top_stocks():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",       # 页码
        "pz": "100",     # 每页数量
        "po": "1",       # 排序方式
        "np": "1",       # 未知参数，默认填1
        "fltt": "2",     # 是否排序
        "fid": "f3",     # 按涨跌幅排序
        "fs": "m:1+t:2,m:0+t:6,m:0+t:13,m:1+t:23,m:0+t:80",  # 多市场股票代码筛选
        "fields": "f12,f14"  # f12为股票代码，f14为股票名称
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/"
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        # 提取股票代码和名称的元组列表
        if "data" in data and "diff" in data["data"]:
            return [(s.get("f12"), s.get("f14")) for s in data["data"]["diff"]]
    except Exception as e:
        print(f"获取涨幅排名失败: {e}")
    return []

# 获取某只股票的盘口数据（买1~5，卖1~5）
def get_orderbook(secid):
    url = "http://push2delay.eastmoney.com/api/qt/stock/get"
    params = {"secid": secid}  # secid格式：1.股票代码(沪市)，0.股票代码(深市)
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json().get("data", {})

        # 内部函数：将价格从整数转为小数，保留两位小数
        def pv(p, v):
            return round(p / 100, 2), v

        # 买1~5档
        buy = [
            pv(data.get("f19", 0), data.get("f20", 0)),
            pv(data.get("f17", 0), data.get("f18", 0)),
            pv(data.get("f15", 0), data.get("f16", 0)),
            pv(data.get("f13", 0), data.get("f14", 0)),
            pv(data.get("f11", 0), data.get("f12", 0)),
        ]
        # 卖1~5档
        sell = [
            pv(data.get("f39", 0), data.get("f40", 0)),
            pv(data.get("f37", 0), data.get("f38", 0)),
            pv(data.get("f35", 0), data.get("f36", 0)),
            pv(data.get("f33", 0), data.get("f34", 0)),
            pv(data.get("f31", 0), data.get("f32", 0)),
        ]
        return buy, sell
    except Exception as e:
        return [], []  # 请求失败时返回空列表

# 格式化价格和数量，控制输出对齐
def format_price_vol(price, vol, price_width=6, vol_width=4):
    price_str = f"{price:>{price_width}.2f}"  # 格式化价格：右对齐，保留两位小数
    vol_str = f"{vol:>{vol_width}d}"         # 格式化数量：右对齐整数
    return f"({price_str} / {vol_str})"

# 生成空盘口数据的格式，用于补位
def format_empty_price_vol(price_width=6, vol_width=4):
    return f"({' '*price_width} / {' '*vol_width})"

# 将买卖盘信息格式化为可读文本行
def format_orderbook_lines(name, code, buy, sell):
    header = f"{name}（{code}）："
    buy_labels = ["买一", "买二", "买三", "买四", "买五"]
    sell_labels = ["卖一", "卖二", "卖三", "卖四", "卖五"]
    buy_fields, sell_fields = [], []

    for i in range(5):
        # 处理买盘
        if i < len(buy):
            p, v = buy[i]
            buy_fields.append(f"{buy_labels[i]}：{format_price_vol(p, v)}" if p or v else f"{buy_labels[i]}：{format_empty_price_vol()}")
        else:
            buy_fields.append(f"{buy_labels[i]}：{format_empty_price_vol()}")

        # 处理卖盘
        if i < len(sell):
            p, v = sell[i]
            sell_fields.append(f"{sell_labels[i]}：{format_price_vol(p, v)}" if p or v else f"{sell_labels[i]}：{format_empty_price_vol()}")
        else:
            sell_fields.append(f"{sell_labels[i]}：{format_empty_price_vol()}")

    buy_line = " | ".join(buy_fields)
    sell_line = " | ".join(sell_fields)
    sep_line = "-" * max(len(header), len(buy_line), len(sell_line))
    return f"{header}\n{buy_line}\n{sell_line}\n{sep_line}"

# 获取单只股票盘口并判断是否需要打印
def fetch_and_print(code, name):
    # 构造 secid，根据股票代码判断沪市或深市
    secid = "1." + code if code.startswith("6") else "0." + code
    buy, sell = get_orderbook(secid)

    # 若无数据则跳过
    if not buy and not sell:
        return

    # 条件1：卖一到卖五全为空（涨停封死情况）
    if all(p == 0 and v == 0 for p, v in sell):
        return

    # 条件2：卖2~卖5中有空位，说明封单不够强，有换手潜力
    if any(p == 0 or v == 0 for p, v in sell[1:]):
        print(format_orderbook_lines(name, code, buy, sell))

def get_orderbook_summary():
    """
    获取涨幅前100的股票及其盘口数据（买一到买五、卖一到卖五）。
    返回格式：
        [
            {
                "code": "000001",
                "name": "平安银行",
                "buy": [(价格1, 数量1), ..., (价格5, 数量5)],
                "sell": [(价格1, 数量1), ..., (价格5, 数量5)]
            },
            ...
        ]
    """
    stocks = get_top_stocks()
    if not stocks:
        print("未获取到股票列表")
        return []

    results = []

    # 使用线程池加速抓取
    def fetch_stock(code, name):
        secid = "1." + code if code.startswith("6") else "0." + code
        buy, sell = get_orderbook(secid)
        return {
            "code": code,
            "name": name,
            "buy": buy,
            "sell": sell
        }

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_stock, code, name): (code, name) for code, name in stocks}
        for future in as_completed(futures):
            result = future.result()
            if result and (result["buy"] or result["sell"]):
                results.append(result)

    return results

# 主循环：每隔 interval 秒轮询一次，并发拉取盘口数据
def main_loop(interval=2, max_workers=20):
    while True:
        start = time.time()
        stocks = get_top_stocks()

        if not stocks:
            print("未获取到股票列表，等待下一轮...")
            time.sleep(interval)
            continue

        print(f"获取到{len(stocks)}只股票，开始并发获取盘口数据...")

        # 多线程并发处理每只股票
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(fetch_and_print, code, name) for code, name in stocks]
            for future in as_completed(futures):
                _ = future.result()

        elapsed = time.time() - start
        wait_time = max(0, interval - elapsed)
        print(f"\n本轮耗时：{elapsed:.2f}秒，等待{wait_time:.2f}秒...\n{'='*80}")
        time.sleep(wait_time)

# 程序入口
if __name__ == "__main__":
    main_loop()
