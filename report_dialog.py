"""刷题总结弹窗 - Trae CN 黑底 + 分模块条形图 + 提升建议"""
from PyQt5.QtCore import Qt, QRect, QSize, QPoint
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QFrame, QScrollArea, QSizePolicy,
)
import db

# === Trae CN 配色 ===
BG_EDITOR  = "#1E1E1E"
BG_SUB     = "#252526"
BG_HOVER   = "#2A2D2E"
FG_MAIN    = "#D4D4D4"
FG_DIM     = "#A8A8A8"   # 调亮：黑底上 808080 看不清
FG_DIMMER  = "#909090"   # 调亮：图表次要文字
ACCENT     = "#264F78"
CORRECT    = "#4EC9B0"
WRONG      = "#F48771"
BAR_COLOR  = "#37373D"
BAR_FILL   = "#0E639C"
BAR_GOOD   = "#4EC9B0"
BAR_BAD    = "#F48771"
WHITE      = "#FFFFFF"

DIALOG_STYLE = f"""
QDialog {{
    background: {BG_EDITOR};
    color: {FG_MAIN};
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}}
QWidget#ReportPanel {{ background: {BG_EDITOR}; }}
QWidget#ReportPanel QLabel {{ color: {FG_MAIN}; }}
QTabWidget::pane {{ border: 1px solid {BG_HOVER}; top: -1px; background: {BG_EDITOR}; }}
QTabBar::tab {{
    background: {BG_SUB}; color: {FG_DIM}; padding: 8px 20px;
    border: 1px solid {BG_HOVER}; border-bottom: none;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {BG_EDITOR}; color: {WHITE}; border-color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {WHITE}; }}
QLabel#Title {{ font-size: 18px; font-weight: bold; color: {WHITE}; }}
QLabel#Subtitle {{ color: {FG_DIM}; }}
QLabel#CardValue {{ font-size: 26px; font-weight: bold; color: {WHITE}; }}
QLabel#CardLabel {{ color: {FG_DIM}; font-size: 12px; }}
QFrame#Card {{
    background: {BG_SUB}; border: 1px solid {BG_HOVER};
    border-radius: 6px; padding: 10px;
}}
QLabel#Advice {{ color: {FG_MAIN}; padding: 4px 0; }}
QPushButton {{
    background: {BG_SUB}; color: {FG_MAIN}; border: 1px solid {BG_HOVER};
    padding: 8px 16px; border-radius: 4px;
}}
QPushButton:hover {{ background: {BG_HOVER}; color: {WHITE}; border-color: {ACCENT}; }}
"""


class BarChart(QWidget):
    """分模块条形图：上半 attempted、下半 wrong 叠加"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._data = []  # [{module, attempts, wrong, rate}]
        self._max = 1

    def set_data(self, modules):
        self._data = modules or []
        if self._data:
            self._max = max(m["attempts"] for m in self._data) or 1
        else:
            self._max = 1
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_EDITOR))

        if not self._data:
            p.setPen(QColor(FG_DIM))
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "本期暂无数据")
            return

        # 单组数据：不画柱，直接大字显示
        if len(self._data) == 1:
            m = self._data[0]
            font = QFont(); font.setPointSize(20); font.setBold(True); p.setFont(font)
            p.setPen(QColor(WHITE))
            p.drawText(QRect(0, 0, w, h // 2 + 10), Qt.AlignCenter,
                       f"{m['module']}：{m['attempts']} 题")
            font.setPointSize(16); p.setFont(font)
            rate_color = CORRECT if m["rate"] >= 70 else (WRONG if m["rate"] < 60 else FG_MAIN)
            p.setPen(QColor(rate_color))
            p.drawText(QRect(0, h // 2, w, h // 2), Qt.AlignCenter,
                       f"正确率 {m['rate']:.0f}%（对 {m['correct']} / 错 {m['wrong']}）")
            p.end()
            return

        n = len(self._data)
        margin_left = 60
        margin_bottom = 30
        margin_top = 10
        chart_h = h - margin_top - margin_bottom
        chart_w = w - margin_left - 10
        bar_gap = 6
        bar_w = max(12, (chart_w - bar_gap * (n - 1)) // n)

        # Y 轴刻度
        p.setPen(QColor(FG_DIMMER))
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        for i in range(5):
            y = margin_top + chart_h * i / 4
            val = int(self._max * (4 - i) / 4)
            p.drawText(QRect(0, int(y - 8), margin_left - 6, 16),
                       Qt.AlignRight | Qt.AlignVCenter, str(val))
            p.setPen(QColor(BG_HOVER))
            p.drawLine(margin_left, int(y), margin_left + chart_w, int(y))
            p.setPen(QColor(FG_DIMMER))

        # 每个模块的柱子
        for i, m in enumerate(self._data):
            x = margin_left + i * (bar_w + bar_gap)
            total_h = int(chart_h * m["attempts"] / self._max)
            wrong_h = int(chart_h * m["wrong"] / self._max)

            # 正确部分 (attempts - wrong) — 青色
            correct_h = total_h - wrong_h
            if correct_h > 0:
                p.fillRect(x, margin_top + (chart_h - total_h),
                           bar_w, correct_h, QColor(BAR_GOOD))
            # 错误部分 — 红色（堆在正确上面）
            if wrong_h > 0:
                p.fillRect(x, margin_top + (chart_h - total_h) + correct_h,
                           bar_w, wrong_h, QColor(BAR_BAD))

            # 模块名（X 轴标签）
            p.setPen(QColor(FG_MAIN))
            p.drawText(QRect(x, h - margin_bottom + 4, bar_w, 16),
                       Qt.AlignCenter, m["module"][:4])

            # 数量标在柱顶
            p.setPen(QColor(WHITE))
            p.drawText(QRect(x - 2, margin_top + (chart_h - total_h) - 16, bar_w + 4, 14),
                       Qt.AlignCenter, str(m["attempts"]))

            # 正确率在下方
            rate_color = CORRECT if m["rate"] >= 70 else (WRONG if m["rate"] < 60 else FG_MAIN)
            p.setPen(QColor(rate_color))
            p.drawText(QRect(x, h - margin_bottom - 14, bar_w, 14),
                       Qt.AlignCenter, f"{m['rate']:.0f}%")

        p.end()


class TrendChart(QWidget):
    """近 N 个时间桶的小条形图（attempts + rate 折线合一太复杂，只画 attempts）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._data = []

    def set_data(self, trend):
        self._data = trend or []
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(BG_EDITOR))

        if not self._data:
            p.setPen(QColor(FG_DIM))
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "暂无趋势数据")
            return

        # 单组数据：不画柱，直接显示数字
        if len(self._data) == 1:
            d = self._data[0]
            font = QFont(); font.setPointSize(18); font.setBold(True); p.setFont(font)
            p.setPen(QColor(WHITE))
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter,
                       f"{d['bucket']}：{d['attempts']} 题")
            p.end()
            return

        margin_left = 30
        margin_bottom = 22
        margin_top = 8
        chart_w = w - margin_left - 5
        chart_h = h - margin_top - margin_bottom
        n = len(self._data)
        bar_gap = 3
        bar_w = max(8, (chart_w - bar_gap * (n - 1)) // n)
        max_v = max((d["attempts"] for d in self._data), default=1) or 1

        # 网格
        p.setPen(QColor(BG_HOVER))
        for i in range(4):
            y = margin_top + chart_h * i / 3
            p.drawLine(margin_left, int(y), margin_left + chart_w, int(y))

        # 柱子
        for i, d in enumerate(self._data):
            x = margin_left + i * (bar_w + bar_gap)
            bh = int(chart_h * d["attempts"] / max_v)
            color = QColor(BAR_FILL) if d["rate"] >= 60 else QColor(BAR_BAD)
            p.fillRect(x, margin_top + chart_h - bh, bar_w, bh, color)

            # 数值
            p.setPen(QColor(FG_DIM))
            font = QFont(); font.setPointSize(8); p.setFont(font)
            short = d["bucket"].split("-")[-1]  # 只显示最后一段
            p.drawText(QRect(x, h - margin_bottom + 2, bar_w, 12),
                       Qt.AlignCenter, short)
            p.setPen(QColor(WHITE))
            p.drawText(QRect(x, margin_top + chart_h - bh - 12, bar_w, 12),
                       Qt.AlignCenter, str(d["attempts"]))

        p.end()


def make_card(title, big_value, sub1, sub2=None):
    frame = QFrame()
    frame.setObjectName("Card")
    frame.setStyleSheet(
        f"QFrame#Card {{ background: {BG_SUB}; border: 1px solid {BG_HOVER}; "
        f"border-radius: 6px; }}"
    )
    v = QVBoxLayout(frame)
    v.setContentsMargins(12, 8, 12, 8)
    v.setSpacing(2)

    t = QLabel(title); t.setObjectName("CardLabel"); v.addWidget(t)
    val = QLabel(str(big_value)); val.setObjectName("CardValue"); v.addWidget(val)
    s1 = QLabel(sub1); s1.setObjectName("CardLabel"); v.addWidget(s1)
    if sub2:
        s2 = QLabel(sub2); s2.setObjectName("CardLabel"); v.addWidget(s2)
    return frame


def period_panel(period, conn, close_btn):
    """返回一个 QWidget，展示该 period 的统计"""
    w = QWidget()
    w.setObjectName("ReportPanel")  # 让样式表里的颜色规则生效
    layout = QVBoxLayout(w)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(12)

    period_cn = {"day": "今日", "week": "本周", "month": "本月"}[period]

    # 总量卡片一排
    overall = db.stats_overall(conn, period)
    cards_row = QHBoxLayout()
    cards_row.setSpacing(10)

    rate_color = CORRECT if overall["rate"] >= 70 else (WRONG if overall["rate"] < 60 else FG_MAIN)
    cards_row.addWidget(make_card(
        f"{period_cn}做题数",
        overall["attempts"],
        f"独立题 {overall['unique_q']} 道",
        f"答对 {overall['correct']} / 答错 {overall['wrong']}"
    ))
    cards_row.addWidget(make_card(
        "正确率",
        f"{overall['rate']:.0f}%",
        "≥ 70% 理想",
    ))
    cards_row.addWidget(make_card(
        "错题数",
        overall["wrong"],
        f"错题重练 →",
    ))
    layout.addLayout(cards_row)

    # 分模块条形图
    modules = db.stats_by_module(conn, period)
    if modules:
        layout.addWidget(QLabel(f"模块分布（绿=正确 / 红=错误）"))
        bar = BarChart(); bar.set_data(modules)
        bar.setStyleSheet(f"background: {BG_EDITOR};")
        layout.addWidget(bar)
    else:
        tip = QLabel("本期暂无数据，去刷几道题吧！")
        tip.setStyleSheet(f"color: {FG_DIM}; padding: 20px;")
        tip.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip)

    # 趋势
    trend_limit = {"day": 7, "week": 8, "month": 6}[period]
    trend = db.stats_trend(conn, period, limit=trend_limit)
    if trend:
        layout.addWidget(QLabel(f"近 {trend_limit} 个{'天' if period=='day' else ('周' if period=='week' else '月')}趋势"))
        tr = TrendChart(); tr.set_data(trend)
        tr.setStyleSheet(f"background: {BG_EDITOR};")
        layout.addWidget(tr)

    # 提升建议
    layout.addWidget(QLabel("💡 提升建议"))
    advices = db.generate_advice(conn, period)
    advice_frame = QFrame()
    advice_frame.setStyleSheet(
        f"background: {BG_SUB}; border: 1px solid {BG_HOVER}; border-radius: 6px;"
    )
    av = QVBoxLayout(advice_frame)
    av.setContentsMargins(12, 8, 12, 8)
    av.setSpacing(4)
    for a in advices:
        lbl = QLabel(a)
        lbl.setObjectName("Advice")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {FG_MAIN}; padding: 3px 0;")
        av.addWidget(lbl)
    av.addStretch()
    layout.addWidget(advice_frame, 1)

    return w


class ReportDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("📊 刷题总结")
        self.setMinimumSize(720, 560)
        self.resize(880, 640)
        self.setStyleSheet(DIALOG_STYLE)
        # 和 popup 统一：无边框 + 自绘黑标题栏（有 PyObjC 时自动透明黑）
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        from quiz_card import _make_palette
        self.setPalette(_make_palette())
        self.setAutoFillBackground(True)
        self._drag_pos = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 自绘黑标题栏（和 popup 同款 28px 黑条 + 透明黑按钮）
        bar = QWidget(); bar.setFixedHeight(28)
        bar.setStyleSheet(f"QWidget {{ background: {BG_EDITOR}; }}")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(12, 0, 8, 0); bar_l.setSpacing(6)
        tip = QLabel("📊 刷题总结")
        tip.setStyleSheet(f"color: {FG_DIM}; font-size: 11px; background: transparent;")
        bar_l.addWidget(tip); bar_l.addStretch(1)

        btn_style = (f"QPushButton {{ background: rgba(0, 0, 0, 60); border: 1px solid #3C3C3C;"
                     f" border-radius: 2px; color: {FG_MAIN}; font-size: 10px; font-weight: bold; }}"
                     f"QPushButton:hover {{ background: rgba(0, 0, 0, 140); border-color: {FG_DIM}; }}")
        min_btn = QPushButton("－"); min_btn.setFixedSize(22, 16)
        min_btn.setStyleSheet(btn_style)
        min_btn.clicked.connect(self.showMinimized)
        bar_l.addWidget(min_btn)
        close_btn = QPushButton("×"); close_btn.setFixedSize(22, 16)
        close_btn.setStyleSheet(btn_style)
        close_btn.clicked.connect(self.accept)
        bar_l.addWidget(close_btn)
        root.addWidget(bar)
        self._bar = bar

        # Tab
        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_tab("day"), "📅 日报")
        self.tabs.addTab(self._make_tab("week"), "📈 周报")
        self.tabs.addTab(self._make_tab("month"), "🗓️ 月报")
        root.addWidget(self.tabs, 1)

    def showEvent(self, event):
        super().showEvent(event)
        from main_window import apply_macos_transparent_titlebar
        if apply_macos_transparent_titlebar(self):
            self._bar.hide()

    # --- 标题栏拖动（无边框后需要自绘）---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.y() < 28:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag_pos)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def _make_tab(self, period):
        panel = period_panel(period, self.conn, None)
        # 外层包一层 QScrollArea 防止内容溢出
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setStyleSheet(f"QScrollArea {{ background: {BG_EDITOR}; border: none; }}"
                         f"QScrollBar:vertical {{ background: {BG_SUB}; width: 8px; }}"
                         f"QScrollBar::handle:vertical {{ background: {BG_HOVER}; border-radius: 4px; }}")
        sa.setWidget(panel)
        return sa
