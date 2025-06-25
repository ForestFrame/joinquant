# test_fetch.py
import asyncio
from data_fetch import get_orderbook_summary  # 假设你把前面的代码封装成了 data_fetch.py
import pprint

if __name__ == "__main__":
    data = get_orderbook_summary()
    print(data)
