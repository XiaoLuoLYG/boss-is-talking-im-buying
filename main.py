import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QLabel, QHBoxLayout, QFrame, QMenu, QInputDialog,
                             QSizePolicy)
from PyQt6.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QCursor, QAction, QColor, QPalette

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import mplfinance as mpf
import pandas as pd

from data_fetcher import DataFetcher

# 配置常量
DEFAULT_SYMBOL = "600519" # 茅台
REFRESH_INTERVAL = 3000 # 3秒刷新一次

class DataWorker(QThread):
    data_signal = pyqtSignal(dict)
    
    def __init__(self, symbol):
        super().__init__()
        self.symbol = symbol
        self.running = True

    def run(self):
        while self.running:
            data = DataFetcher.get_realtime_data(self.symbol)
            if data:
                self.data_signal.emit(data)
            self.msleep(REFRESH_INTERVAL)

    def stop(self):
        self.running = False
        self.wait()

class KlineWorker(QThread):
    kline_signal = pyqtSignal(pd.DataFrame)
    
    def __init__(self, symbol):
        super().__init__()
        self.symbol = symbol

    def run(self):
        df = DataFetcher.get_kline_data(self.symbol)
        if df is not None:
            self.kline_signal.emit(df)

class MiniWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            MiniWidget {
                background-color: rgba(0, 0, 0, 150);
                border-radius: 5px;
            }
            QLabel {
                color: white;
                font-family: "Microsoft YaHei";
                font-weight: bold;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.name_label = QLabel("Loading...")
        self.price_label = QLabel("--")
        self.percent_label = QLabel("--%")
        
        # 字体大小
        self.name_label.setStyleSheet("font-size: 14px;")
        self.price_label.setStyleSheet("font-size: 14px; color: #FFD700;")
        self.percent_label.setStyleSheet("font-size: 14px;")
        
        layout.addWidget(self.name_label)
        layout.addSpacing(10)
        layout.addWidget(self.price_label)
        layout.addSpacing(10)
        layout.addWidget(self.percent_label)

    def update_data(self, data):
        self.name_label.setText(f"{data['name']} ({data['symbol']})")
        self.price_label.setText(f"{data['price']:.2f}")
        
        pct = data['percent']
        if pct > 0:
            self.percent_label.setStyleSheet("color: #FF4500; font-size: 14px;") # Red for up
            self.percent_label.setText(f"+{pct:.2f}%")
        elif pct < 0:
            self.percent_label.setStyleSheet("color: #00FF00; font-size: 14px;") # Green for down
            self.percent_label.setText(f"{pct:.2f}%")
        else:
            self.percent_label.setStyleSheet("color: white; font-size: 14px;")
            self.percent_label.setText(f"{pct:.2f}%")

class ChartWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 200); border-radius: 5px;")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        # Mplfinance setup
        self.figure = Figure(figsize=(4, 3), dpi=100)
        self.figure.patch.set_alpha(0) # Transparent figure background
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet("background-color: transparent;")
        
        self.layout.addWidget(self.canvas)
        
    def plot(self, df):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        # Transparent axes
        ax.patch.set_alpha(0)
        
        # Style
        mc = mpf.make_marketcolors(up='r', down='g', edge='i', wick='i', volume='in', inherit=True)
        s  = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True, facecolor='none', figcolor='none')
        
        try:
            mpf.plot(df, type='candle', ax=ax, style=s, volume=False) # Volume currently off to save space
            self.canvas.draw()
        except Exception as e:
            print(f"Plotting error: {e}")

class StockWidget(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.symbol = DEFAULT_SYMBOL
        self.is_expanded = False
        
        # Window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Components
        self.mini_widget = MiniWidget()
        self.chart_widget = ChartWidget()
        self.chart_widget.hide() # Hidden by default
        
        self.main_layout.addWidget(self.mini_widget)
        self.main_layout.addWidget(self.chart_widget)
        
        # Data logic
        self.data_worker = DataWorker(self.symbol)
        self.data_worker.data_signal.connect(self.update_ui)
        self.data_worker.start()
        
        self.kline_worker = None
        
        # Move logic
        self.old_pos = None

    def update_ui(self, data):
        self.mini_widget.update_data(data)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()
        elif event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def mouseDoubleClickEvent(self, event):
        # Toggle expanded mode
        self.toggle_expanded()

    def toggle_expanded(self):
        if self.is_expanded:
            self.chart_widget.hide()
            self.is_expanded = False
            self.resize(self.mini_widget.sizeHint())
        else:
            self.chart_widget.show()
            self.is_expanded = True
            self.fetch_kline()
            # Resize logic might be needed if layout doesn't expand auto
            # self.resize(300, 300) # Example

    def fetch_kline(self):
        if self.kline_worker and self.kline_worker.isRunning():
            return
        
        self.kline_worker = KlineWorker(self.symbol)
        self.kline_worker.kline_signal.connect(self.chart_widget.plot)
        self.kline_worker.start()

    def show_context_menu(self, pos):
        menu = QMenu(self)
        
        change_action = QAction("Change Symbol", self)
        change_action.triggered.connect(self.change_symbol)
        menu.addAction(change_action)
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        
        menu.exec(pos)

    def change_symbol(self):
        text, ok = QInputDialog.getText(self, "Change Symbol", "Enter Stock Symbol (e.g. 600519):")
        if ok and text:
            self.symbol = text
            # Restart worker
            self.data_worker.stop()
            self.data_worker = DataWorker(self.symbol)
            self.data_worker.data_signal.connect(self.update_ui)
            self.data_worker.start()
            
            if self.is_expanded:
                self.fetch_kline()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StockWidget()
    window.show()
    sys.exit(app.exec())

