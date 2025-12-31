import akshare as ak
import pandas as pd
from datetime import datetime
import ssl
import requests
import urllib3
import traceback
import random
import numpy as np

# 强制禁用 SSL 验证
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkey patch requests
old_request = requests.Session.request
def new_request(self, method, url, *args, **kwargs):
    kwargs['verify'] = False
    # 设置较长的超时
    if 'timeout' not in kwargs:
        kwargs['timeout'] = 10
    return old_request(self, method, url, *args, **kwargs)
requests.Session.request = new_request

# 尝试 Patch akshare 的内部字典 (如果是导入即运行的可能会失效，但在函数调用时可能有效)
# 这是一个黑魔法，尝试预填充常用股票的市场代码
# 0: 深市, 1: 沪市, 8: 北交所 (东财的规则)
known_codes = {
    '600519': '1', # 茅台
    '000001': '0', # 平安
    '000300': '1', # 沪深300 (指数通常有不同接口，这里仅作示例)
}

class DataFetcher:
    @staticmethod
    def get_realtime_data(symbol: str, use_mock_on_fail: bool = True):
        try:
            print(f"Fetching spot data for {symbol}...")
            df = ak.stock_zh_a_spot_em()
            
            if df is None or df.empty:
                raise ValueError("Returned empty dataframe")
            
            # 确保代码列是字符串
            df['代码'] = df['代码'].astype(str)
            
            target = df[df['代码'] == symbol]
            
            if target.empty:
                print(f"Symbol {symbol} not found in spot data.")
                # print("Available codes sample:", df['代码'].head().tolist())
                raise ValueError("Symbol not found")
            
            row = target.iloc[0]
            
            price = row['最新价']
            pct_change = row['涨跌幅']
            name = row['名称']
            
            # 类型转换
            try: price = float(price)
            except: price = 0.0
                
            try: pct_change = float(pct_change)
            except: pct_change = 0.0

            return {
                'symbol': symbol,
                'name': name,
                'price': price,
                'percent': pct_change,
                'timestamp': datetime.now().strftime("%H:%M:%S")
            }
        except Exception as e:
            print(f"Realtime data fetch failed: {e}")
            if use_mock_on_fail:
                print("Using MOCK data for realtime.")
                return {
                    'symbol': symbol,
                    'name': f"Mock-{symbol}",
                    'price': round(random.uniform(10, 1000), 2),
                    'percent': round(random.uniform(-10, 10), 2),
                    'timestamp': datetime.now().strftime("%H:%M:%S")
                }
            return None

    @staticmethod
    def get_kline_data(symbol: str, period: str = "daily", adjust: str = "qfq", use_mock_on_fail: bool = True):
        try:
            # 尝试 Patch akshare 内部字典 (如果有办法访问到)
            # 实际上比较难，我们直接捕获异常
            
            df = ak.stock_zh_a_hist(symbol=symbol, period=period, adjust=adjust)
            
            if df is None or df.empty:
                raise ValueError("Empty kline data")
            
            df['日期'] = pd.to_datetime(df['日期'])
            df.set_index('日期', inplace=True)
            
            rename_map = {'开盘': 'Open', '收盘': 'Close', '最高': 'High', '最低': 'Low', '成交量': 'Volume'}
            available_cols = set(df.columns)
            actual_rename = {k: v for k, v in rename_map.items() if k in available_cols}
            df.rename(columns=actual_rename, inplace=True)
            
            target_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            df = df[[c for c in target_cols if c in df.columns]]
            
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            return df
        except Exception as e:
            print(f"Kline data fetch failed: {e}")
            if use_mock_on_fail:
                print("Using MOCK data for K-line.")
                # 生成模拟K线数据
                dates = pd.date_range(end=datetime.now(), periods=30)
                data = {
                    'Open': np.random.uniform(100, 200, 30),
                    'High': np.random.uniform(200, 220, 30),
                    'Low': np.random.uniform(90, 100, 30),
                    'Close': np.random.uniform(100, 200, 30),
                    'Volume': np.random.randint(1000, 10000, 30)
                }
                # 简单修正 High/Low
                for i in range(30):
                    data['High'][i] = max(data['Open'][i], data['Close'][i]) + random.uniform(0, 5)
                    data['Low'][i] = min(data['Open'][i], data['Close'][i]) - random.uniform(0, 5)

                df = pd.DataFrame(data, index=dates)
                return df
            return None

if __name__ == "__main__":
    print("Fetching realtime data for 600519...")
    print(DataFetcher.get_realtime_data("600519"))
    
    print("Fetching daily kline data for 600519...")
    df = DataFetcher.get_kline_data("600519")
    if df is not None:
        print(df.tail())
