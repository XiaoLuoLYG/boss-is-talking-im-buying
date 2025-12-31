import sys
import time
import datetime
import threading
import ssl
import urllib3
import requests
import os
import json
from functools import partial

# -----------------------------------------------------------------------------
# SSL / Proxy Configuration
# -----------------------------------------------------------------------------
# 1. Disable SSL Verify
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkey patch requests to force verify=False
_old_request = requests.Session.request
def _new_request(self, method, url, *args, **kwargs):
    kwargs['verify'] = False
    return _old_request(self, method, url, *args, **kwargs)
requests.Session.request = _new_request

# 2. Proxy Configuration
# Uncomment and set your proxy if needed, or set HTTP_PROXY/HTTPS_PROXY env vars
# os.environ["HTTP_PROXY"] = 
# os.environ["HTTPS_PROXY"] = 

import pandas as pd
import akshare as ak
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QThread, Signal, Slot, QPoint, QSize
import pyqtgraph as pg

# -----------------------------------------------------------------------------
# Configuration / Constants
# -----------------------------------------------------------------------------
DEFAULT_STOCKS = ["600519", "000001", "002594", "601318"] # 默认股票列表
INDICES = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006"
}
REFRESH_INTERVAL_MS = 2000     # 实时数据刷新间隔 (2秒)
CHART_INTERVAL_MS = 60000      # 图表刷新间隔 (1分钟)
BACKGROUND_COLOR = (20, 20, 20, 230)
TEXT_COLOR = "#E0E0E0"
UP_COLOR = "#FF5252"
DOWN_COLOR = "#00E676"
BORDER_COLOR = "rgba(255, 255, 255, 30)"

# -----------------------------------------------------------------------------
# Fast Data Fetcher (Using Akshare)
# -----------------------------------------------------------------------------
class FastFetcher:
    @staticmethod
    def get_sec_id(code):
        # 腾讯接口前缀规则
        if code.startswith("sh") or code.startswith("sz") or code.startswith("bj"):
            return code
            
        if code.startswith("6") or code.startswith("5") or code.startswith("9"):
            return f"sh{code}"
        elif code.startswith("0") or code.startswith("3") or code.startswith("2"):
            # 特殊处理：上证指数代码也是 000001，但一般个股 000001 是平安银行
            # 如果是指数，调用方通常直接传入 sh000001
            # 这里默认 0 开头是 sz (深市)
            return f"sz{code}"
        elif code.startswith("8") or code.startswith("4"):
            return f"bj{code}"
        return f"sz{code}" # Default

    @staticmethod
    def fetch_quotes(codes_list):
        """
        使用 腾讯财经 (qt.gtimg.cn) 获取行情
        """
        if not codes_list:
            return {}
        
        # 统一转换为带前缀的代码
        request_codes = []
        code_map = {} # request_code -> input_code (or list of input_codes)
        
        for c in codes_list:
            sec_id = FastFetcher.get_sec_id(c)
            if sec_id not in request_codes:
                request_codes.append(sec_id)
            if sec_id not in code_map:
                code_map[sec_id] = []
            code_map[sec_id].append(c)
            
        result = {}
        try:
            # 腾讯接口一次可以请求多个
            url = f"http://qt.gtimg.cn/q={','.join(request_codes)}"
            resp = requests.get(url, timeout=3)
            if resp.status_code != 200:
                return {}
                
            # 解析
            # v_sh600519="1~贵州茅台~600519~1760.00~..."
            content = resp.content.decode('gbk', errors='ignore')
            lines = content.strip().split(';')
            
            for line in lines:
                line = line.strip()
                if not line: continue
                
                # extracting v_sh600519
                if '=' not in line: continue
                
                var_name, val_str = line.split('=', 1)
                qt_code = var_name.split('_')[-1] # sh600519
                
                val_str = val_str.strip('"')
                parts = val_str.split('~')
                
                if len(parts) < 33: continue
                
                # 3: price, 31: change, 32: pct
                try:
                    name = parts[1]
                    price = float(parts[3])
                    change = float(parts[31])
                    pct = float(parts[32])
                    
                    # 填充回 result
                    # result 的 key 应该是 qt_code (即 get_sec_id 的返回值)
                    result[qt_code] = {
                        "name": name,
                        "price": price,
                        "pct": pct,
                        "change": change
                    }
                except:
                    pass
                    
            return result
            
        except Exception as e:
            print(f"Quote fetch failed: {e}")
            return {}

# -----------------------------------------------------------------------------
# Workers
# -----------------------------------------------------------------------------
class QuoteWorker(QThread):
    quotes_signal = Signal(dict) # {code: {name, price, pct}}
    
    def __init__(self, stock_codes):
        super().__init__()
        self.stock_codes = list(set(stock_codes)) # Unique
        # 添加指数
        self.index_ids = list(INDICES.values())
        self.running = True

    def update_stocks(self, new_codes):
        self.stock_codes = list(set(new_codes))

    def run(self):
        while self.running:
            try:
                # 1. Fetch Stocks
                stock_data = FastFetcher.fetch_quotes(self.stock_codes)
                
                # 2. Fetch Indices
                index_data = FastFetcher.fetch_quotes(self.index_ids)
                
                # Merge
                final_data = {"stocks": stock_data, "indices": index_data}
                self.quotes_signal.emit(final_data)
                
            except Exception as e:
                print(f"Quote loop error: {e}")
            
            # Sleep
            for _ in range(int(REFRESH_INTERVAL_MS / 100)):
                if not self.running: break
                self.msleep(100)
    
    def stop(self):
        self.running = False
        self.wait()

class ChartWorker(QThread):
    chart_signal = Signal(str, str, object) # code, type, dataframe
    
    def __init__(self):
        super().__init__()
        self.queue = [] # (code, type)
        self.running = True
        self.mutex = QtCore.QMutex()
        self.condition = QtCore.QWaitCondition()

    def request_chart(self, code, chart_type="daily"):
        self.mutex.lock()
        self.queue.append((code, chart_type))
        self.condition.wakeOne()
        self.mutex.unlock()

    def run(self):
        while self.running:
            self.mutex.lock()
            if not self.queue:
                self.condition.wait(self.mutex)
            if not self.queue:
                self.mutex.unlock()
                continue
            
            code, chart_type = self.queue.pop(0)
            self.mutex.unlock()
            
            # Fetch Data
            try:
                df = None
                if chart_type == "daily":
                    # 日线
                    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
                    if not df.empty:
                        df = df.tail(100) # 只取最近100天
                elif chart_type == "min":
                    # 分时 (这里用 1 分钟 K 线模拟分时走势，因为 trends2 接口数据格式不同，处理麻烦)
                    # 或者使用 stock_zh_a_min
                    df = ak.stock_zh_a_hist_min_em(symbol=code, period='1', adjust='qfq')
                    if not df.empty:
                        # 优先只显示当天数据
                        try:
                            today = datetime.datetime.now().strftime("%Y-%m-%d")
                            # 假设 '时间' 列格式为 "YYYY-MM-DD HH:MM:SS"
                            df_today = df[df['时间'].str.startswith(today)]
                            if not df_today.empty:
                                df = df_today
                            else:
                                df = df.tail(240)
                        except Exception:
                            df = df.tail(240) # Fallback
                
                self.chart_signal.emit(code, chart_type, df)
                
            except Exception as e:
                print(f"Chart fetch error for {code}: {e}")
            
    def stop(self):
        self.running = False
        self.mutex.lock()
        self.condition.wakeOne()
        self.mutex.unlock()
        self.wait()

# -----------------------------------------------------------------------------
# UI Components
# -----------------------------------------------------------------------------
class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data):
        pg.GraphicsObject.__init__(self)
        self.data = data # [(t, open, close, min, max), ...]
        self.picture = QtGui.QPicture()
        self.generatePicture()

    def generatePicture(self):
        p = QtGui.QPainter(self.picture)
        w = 0.4
        for (t, open, close, min, max) in self.data:
            if open > close:
                p.setPen(pg.mkPen(DOWN_COLOR))
                p.setBrush(pg.mkBrush(DOWN_COLOR))
            else:
                p.setPen(pg.mkPen(UP_COLOR))
                p.setBrush(pg.mkBrush(UP_COLOR))
            p.drawLine(QtCore.QPointF(t, min), QtCore.QPointF(t, max))
            p.drawRect(QtCore.QRectF(t - w, open, w * 2, close - open))
        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())

class StockItemWidget(QtWidgets.QWidget):
    expand_signal = Signal(str, bool) # code, expanded
    
    def __init__(self, code, parent_worker):
        super().__init__()
        self.code = code
        self.worker = parent_worker
        self.expanded = False
        self.chart_type = "min" # min or daily
        
        self.chart_timer = QtCore.QTimer(self)
        self.chart_timer.setInterval(CHART_INTERVAL_MS)
        self.chart_timer.timeout.connect(self.refresh_chart)
        
        self.setup_ui()
        
    def refresh_chart(self):
        if self.expanded and self.isVisible():
            self.worker.request_chart(self.code, self.chart_type)

    def setup_ui(self):
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # 1. Info Row (Clickable)
        self.info_widget = QtWidgets.QWidget()
        self.info_widget.setFixedHeight(30)
        self.info_widget.setStyleSheet(f"background-color: transparent;")
        self.info_layout = QtWidgets.QHBoxLayout(self.info_widget)
        self.info_layout.setContentsMargins(5, 0, 5, 0)
        
        self.lbl_name = QtWidgets.QLabel(self.code)
        self.lbl_name.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: bold;")
        self.lbl_price = QtWidgets.QLabel("--.--")
        self.lbl_price.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: bold;")
        self.lbl_pct = QtWidgets.QLabel("0.00%")
        self.lbl_pct.setStyleSheet(f"color: {TEXT_COLOR};")
        
        self.info_layout.addWidget(self.lbl_name)
        self.info_layout.addStretch()
        self.info_layout.addWidget(self.lbl_price)
        self.info_layout.addSpacing(10)
        self.info_layout.addWidget(self.lbl_pct)
        
        self.layout.addWidget(self.info_widget)
        
        # 2. Chart Container (Hidden by default)
        self.chart_container = QtWidgets.QWidget()
        self.chart_container.hide()
        self.chart_layout = QtWidgets.QVBoxLayout(self.chart_container)
        self.chart_layout.setContentsMargins(0, 5, 0, 5)
        
        # Controls
        self.controls_layout = QtWidgets.QHBoxLayout()
        self.btn_min = QtWidgets.QPushButton("分时")
        self.btn_day = QtWidgets.QPushButton("日K")
        for btn in [self.btn_min, self.btn_day]:
            btn.setCheckable(True)
            btn.setFixedSize(40, 20)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255,255,255,20);
                    color: {TEXT_COLOR}; border: none; border-radius: 3px;
                }}
                QPushButton:checked {{ background-color: rgba(255,255,255,60); }}
            """)
        
        self.btn_min.setChecked(True)
        self.btn_group = QtWidgets.QButtonGroup(self)
        self.btn_group.addButton(self.btn_min)
        self.btn_group.addButton(self.btn_day)
        
        self.btn_min.clicked.connect(lambda: self.switch_chart("min"))
        self.btn_day.clicked.connect(lambda: self.switch_chart("daily"))
        
        self.controls_layout.addWidget(self.btn_min)
        self.controls_layout.addWidget(self.btn_day)
        self.controls_layout.addStretch()
        
        self.chart_layout.addLayout(self.controls_layout)
        
        # Graph
        self.graph_widget = pg.GraphicsLayoutWidget()
        self.graph_widget.setBackground(None)
        self.graph_widget.setFixedHeight(120)
        self.graph_widget.ci.layout.setContentsMargins(0, 0, 0, 0)
        self.plot_item = self.graph_widget.addPlot()
        self.plot_item.hideAxis('bottom')
        self.plot_item.showGrid(x=False, y=True, alpha=0.3)
        
        self.chart_layout.addWidget(self.graph_widget)
        self.layout.addWidget(self.chart_container)
        
        # Click Event
        self.info_widget.mousePressEvent = self.on_click
        
    def on_click(self, event):
        self.expanded = not self.expanded
        if self.expanded:
            self.chart_container.show()
            self.worker.request_chart(self.code, self.chart_type)
            self.chart_timer.start()
        else:
            self.chart_container.hide()
            self.chart_timer.stop()
        self.expand_signal.emit(self.code, self.expanded)
        
    def switch_chart(self, ctype):
        self.chart_type = ctype
        if self.expanded:
            self.worker.request_chart(self.code, ctype)
            
    def update_quote(self, data):
        # data: {name, price, pct, ...}
        self.lbl_name.setText(data['name'])
        self.lbl_price.setText(str(data['price']))
        pct = data['pct']
        self.lbl_pct.setText(f"{pct:+.2f}%")
        
        color = UP_COLOR if pct >= 0 else DOWN_COLOR
        self.lbl_price.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.lbl_pct.setStyleSheet(f"color: {color};")
        
    def update_chart(self, ctype, df):
        if ctype != self.chart_type or df is None: return
        self.plot_item.clear()
        
        if ctype == "daily":
            # Draw Candles
            candle_data = []
            for i in range(len(df)):
                row = df.iloc[i]
                candle_data.append((i, float(row['开盘']), float(row['收盘']), float(row['最低']), float(row['最高'])))
            item = CandlestickItem(candle_data)
            self.plot_item.addItem(item)
        else:
            # Draw Line (Close price for Min)
            prices = df['收盘'].astype(float).values
            self.plot_item.plot(prices, pen=pg.mkPen(color=UP_COLOR if prices[-1] >= prices[0] else DOWN_COLOR, width=1.5))


# -----------------------------------------------------------------------------
# Main Window
# -----------------------------------------------------------------------------
class StockMonitor(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.stocks = self.load_stocks()
        self.dragging = False
        self.offset = QPoint()
        
        self.setup_ui()
        self.setup_workers()
        
        # Initial transparency
        self.setWindowOpacity(0.4)

    def enterEvent(self, event):
        self.setWindowOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setWindowOpacity(0.4)
        super().leaveEvent(event)
        
    def setup_ui(self):
        # Allow resizing, keep on top if desired (optional)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        # self.setAttribute(Qt.WA_TranslucentBackground) # Usually conflicts with standard window frame on some OS
        
        # Remove fixed width to allow resizing
        # self.setFixedWidth(240)
        self.resize(300, 400) # Set a reasonable default size
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Background Frame
        self.frame = QtWidgets.QFrame()
        self.frame.setStyleSheet(f"""
            QFrame#MainFrame {{
                background-color: rgba{BACKGROUND_COLOR};
                /* border: 1px solid {BORDER_COLOR}; */
                /* border-radius: 8px; */
            }}
        """)
        self.frame.setObjectName("MainFrame")
        self.frame_layout = QtWidgets.QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.addWidget(self.frame)
        
        # 1. Indices Bar
        self.indices_widget = QtWidgets.QWidget()
        self.indices_layout = QtWidgets.QHBoxLayout(self.indices_widget)
        self.indices_layout.setContentsMargins(0, 0, 0, 5)
        self.index_labels = {}
        for name in ["上证指数", "深证成指"]: # 只显示两个核心的，节省空间
            lbl = QtWidgets.QLabel(f"{name}: --.--%")
            lbl.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 10px;")
            self.indices_layout.addWidget(lbl)
            self.index_labels[name] = lbl
        self.frame_layout.addWidget(self.indices_widget)
        
        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet(f"color: {BORDER_COLOR};")
        self.frame_layout.addWidget(line)

        # 2. Stock List Area (Scrollable)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.scroll_content = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(2)
        self.scroll_layout.addStretch() # Push items up
        
        self.scroll_area.setWidget(self.scroll_content)
        self.frame_layout.addWidget(self.scroll_area)
        
        # Stock Items Map
        self.stock_items = {} # code -> widget
        
        # Context Menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def setup_workers(self):
        self.chart_worker = ChartWorker()
        self.chart_worker.chart_signal.connect(self.on_chart_data)
        self.chart_worker.start()
        
        self.quote_worker = QuoteWorker(self.stocks)
        self.quote_worker.quotes_signal.connect(self.on_quote_data)
        self.quote_worker.start()
        
        # Init List
        self.refresh_stock_list()

    def load_stocks(self):
        config_path = os.path.join(os.path.dirname(__file__), "stock_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("stocks", DEFAULT_STOCKS)
            except Exception as e:
                print(f"Error loading config: {e}")
        return list(DEFAULT_STOCKS)

    def save_stocks(self):
        config_path = os.path.join(os.path.dirname(__file__), "stock_config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({"stocks": self.stocks}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")


    def refresh_stock_list(self):
        # Clear existing (lazy way: remove all and rebuild, can be optimized)
        # Note: Removing widgets from layout doesn't delete them immediately in Qt
        for code, item in self.stock_items.items():
            self.scroll_layout.removeWidget(item)
            item.deleteLater()
        self.stock_items.clear()
        
        # Rebuild
        # Remove stretch
        item = self.scroll_layout.takeAt(self.scroll_layout.count() - 1)
        if item.spacerItem():
            del item
            
        for code in self.stocks:
            item_widget = StockItemWidget(code, self.chart_worker)
            self.scroll_layout.addWidget(item_widget)
            self.stock_items[code] = item_widget
            
        self.scroll_layout.addStretch()
        self.quote_worker.update_stocks(self.stocks)
        
        # Update Window Height based on content (Mini mode)
        self.resize(240, 100 + len(self.stocks) * 35)

    @Slot(dict)
    def on_quote_data(self, data):
        # Update Indices
        indices = data.get("indices", {})
        # indices keys are like "1.000001" (market.code)
        
        for name, code in INDICES.items():
            if name not in self.index_labels: continue
            
            # code in INDICES is already "1.000001" or similar
            quote = indices.get(code)
            
            if quote:
                pct = quote['pct']
                color = UP_COLOR if pct >= 0 else DOWN_COLOR
                self.index_labels[name].setText(f"{name}: {pct:+.2f}%")
                self.index_labels[name].setStyleSheet(f"color: {color}; font-size: 10px;")

        # Update Stocks
        stocks = data.get("stocks", {})
        for code in self.stock_items:
            # Construct the key used in stocks dict
            # FastFetcher.get_sec_id returns "1.600519" etc.
            key = FastFetcher.get_sec_id(code)
            
            quote = stocks.get(key)
            if quote:
                self.stock_items[code].update_quote(quote)

    @Slot(str, str, object)
    def on_chart_data(self, code, ctype, df):
        if code in self.stock_items:
            self.stock_items[code].update_chart(ctype, df)

    # -------------------------------------------------------------------------
    # Interactions
    # -------------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(f"background-color: rgb(40,40,40); color: {TEXT_COLOR};")
        
        add_action = menu.addAction("添加股票")
        del_action = menu.addAction("删除股票")
        menu.addSeparator()
        exit_action = menu.addAction("退出")
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == exit_action:
            self.quote_worker.stop()
            self.chart_worker.stop()
            QtWidgets.QApplication.quit()
        elif action == add_action:
            code, ok = QtWidgets.QInputDialog.getText(self, "添加", "请输入股票代码:")
            if ok and code:
                if code not in self.stocks:
                    self.stocks.append(code)
                    self.save_stocks()
                    self.refresh_stock_list()
        elif action == del_action:
            code, ok = QtWidgets.QInputDialog.getText(self, "删除", "请输入要删除的代码:")
            if ok and code in self.stocks:
                self.stocks.remove(code)
                self.save_stocks()
                self.refresh_stock_list()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = StockMonitor()
    window.show()
    sys.exit(app.exec())
