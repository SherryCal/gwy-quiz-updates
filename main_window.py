"""完整刷题主窗口 - Trae CN 黑底 + Frameless自绘黑标题栏"""
import sys
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from db import fetch_questions, list_filter_values, record_answer, stats
from quiz_card import *  # 导入 Trae CN 配色

# main_window.py 额外需要的配色（quiz_card 里没定义的）
BORDER_LT = "#454545"

# macOS 透明黑标题栏 + 强制普通窗口层级 + 清理 collectionBehavior
# FramelessWindowHint 在 macOS 上会偷偷把 collectionBehavior 设成 MoveToActiveSpace(256)，
# 导致窗口在 Spaces 间乱跳、层级异常。这里一并修正。
def apply_macos_transparent_titlebar(widget):
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import (NSApp, NSWindowTitleHidden, NSNormalWindowLevel,
                            NSWindowCollectionBehaviorCanJoinAllSpaces,
                            NSWindowCollectionBehaviorFullScreenAuxiliary,
                            NSWindowCollectionBehaviorParticipatesInCycle)
        # Qt 的 winId 不是 NSWindow 指针，要通过标题匹配找到真正的 NSWindow
        title = widget.windowTitle()
        ns_win = None
        for w in NSApp.windows():
            if w.title() == title or (not w.title() and widget.isVisible()):
                # Qt 的 FramelessWindowHint 窗口标题常常为空，取第一个可见的
                ns_win = w
                break
        if ns_win is None and NSApp.keyWindow():
            ns_win = NSApp.keyWindow()
        if ns_win is None:
            return False
        ns_win.setTitlebarAppearsTransparent_(True)
        ns_win.setTitleVisibility_(NSWindowTitleHidden)
        ns_win.setMovableByWindowBackground_(True)
        ns_win.setHasShadow_(False)
        # FramelessWindowHint 会让窗口变成 floating panel（永远置顶），强制设回普通层级
        ns_win.setLevel_(NSNormalWindowLevel)
        # 清理 MoveToActiveSpace(256)，保留跨 Space 跟随但不强制跳来跳去
        ns_win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorParticipatesInCycle)
        return True
    except Exception:
        return False


class TitleBar(QWidget):
    """自绘黑标题栏 - Trae CN 风格"""
    def __init__(self, parent, title="公考刷题"):
        super().__init__(parent)
        self.setFixedHeight(30)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(6)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 12px; background: transparent;")
        layout.addWidget(self.title_lbl)
        layout.addStretch(1)

        # 标题栏按钮（透明黑）
        self.min_btn = QPushButton("－")
        self.min_btn.setFixedSize(28, 18)
        self.min_btn.setStyleSheet(self._btn_style())
        self.min_btn.clicked.connect(self.window().showMinimized)
        layout.addWidget(self.min_btn)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(28, 18)
        self.close_btn.setStyleSheet(self._btn_style())
        self.close_btn.clicked.connect(self.window().close)
        layout.addWidget(self.close_btn)

        self.setStyleSheet(f"QWidget {{ background: {BG_EDITOR}; }}")

    def _btn_style(self):
        return f"""
            QPushButton {{ background: rgba(0, 0, 0, 60); border: 1px solid {BORDER}; border-radius: 3px;
                          color: {FG_MAIN}; font-size: 11px; font-weight: bold; }}
            QPushButton:hover {{ background: rgba(0, 0, 0, 140); border-color: {FG_DIM}; }}
        """

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.window().frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.window().move(e.globalPos() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


# 主窗口全局样式
WIN_STYLE = f"""
QMainWindow {{ background: {BG_EDITOR}; }}
QWidget {{ background: {BG_EDITOR}; color: {FG_MAIN}; }}
QSplitter {{ background: {BG_EDITOR}; }}
QSplitter::handle {{ background: {BORDER}; }}
QLabel {{ color: {FG_MAIN}; background: transparent; }}

QComboBox {{
    background: {BG_SUB}; border: 1px solid {BORDER}; border-radius: 2px;
    padding: 4px 8px; min-width: 120px; color: {FG_MAIN};
}}
QComboBox:hover {{ border-color: {BORDER_LT}; }}
QComboBox QAbstractItemView {{
    background: {BG_SUB}; color: {FG_MAIN};
    selection-background-color: {HL}; selection-color: #FFFFFF;
}}

QListWidget {{
    background: {BG_EDITOR}; border: 1px solid {BORDER}; border-radius: 0px;
    font-size: 12px; color: {FG_MAIN}; outline: 0;
}}
QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid #252526; color: {FG_MAIN}; }}
QListWidget::item:selected {{ background: {HL}; color: #FFFFFF; }}
QListWidget::item:hover {{ background: {BG_SUB}; }}
QListWidget::item[answered="true"] {{ color: {CORRECT}; }}
QListWidget::item[wrong="true"] {{ color: {WRONG}; }}

QPushButton.filter {{
    background: {BG_SUB}; border: 1px solid {BORDER}; border-radius: 2px;
    padding: 5px 14px; color: {FG_MAIN};
}}
QPushButton.filter:hover {{ background: {BG_HOVER}; border-color: {BORDER_LT}; }}
QPushButton.filter:checked {{ background: {HL}; border-color: {ACCENT}; color: #FFFFFF; }}

QLabel#stat {{ color: {FG_DIM}; font-size: 12px; background: transparent; }}

QScrollBar:vertical {{ background: {BG_EDITOR}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 2px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER_LT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


class MainWindow(QMainWindow):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self._questions = []
        self.setWindowTitle("公考刷题")
        self.resize(1080, 700)

        # 先 Frameless（兜底），showEvent 里有 PyObjC 就透明
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint
            | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)

        self.setStyleSheet(WIN_STYLE)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(BG_EDITOR))
        pal.setColor(QPalette.Base, QColor(BG_EDITOR))
        pal.setColor(QPalette.WindowText, QColor(FG_MAIN))
        pal.setColor(QPalette.Text, QColor(FG_MAIN))
        pal.setColor(QPalette.Button, QColor(BG_SUB))
        pal.setColor(QPalette.ButtonText, QColor(FG_MAIN))
        pal.setColor(QPalette.Highlight, QColor(HL))
        pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # 整体布局
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = TitleBar(self, "公考刷题")
        root.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        root.addWidget(body, 1)

        splitter = QSplitter()
        body_layout.addWidget(splitter)

        # 左侧
        left = QWidget(); left.setStyleSheet(f"QWidget {{ background: {BG_EDITOR}; }}")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 8, 10, 8); ll.setSpacing(8)

        self.module_cb = self._make_combo(ll, "全部模块")
        self.year_cb = self._make_combo(ll, "全部年份")
        self.region_cb = self._make_combo(ll, "全部省份")
        self.paper_cb = self._make_combo(ll, "全部套卷")
        row = QHBoxLayout()
        self.wrong_btn = QPushButton("错题重练"); self.wrong_btn.setProperty("class", "filter")
        self.wrong_btn.setCheckable(True)
        self.new_btn = QPushButton("只做新题"); self.new_btn.setProperty("class", "filter")
        self.new_btn.setCheckable(True)
        row.addWidget(self.wrong_btn); row.addWidget(self.new_btn)
        ll.addLayout(row)

        self.listw = QListWidget()
        self.listw.currentRowChanged.connect(self._on_select)
        ll.addWidget(self.listw, 1)

        self.stat_lbl = QLabel(); self.stat_lbl.setObjectName("stat")
        ll.addWidget(self.stat_lbl)
        splitter.addWidget(left)

        # 右侧
        right = QWidget(); right.setStyleSheet(f"QWidget {{ background: {BG_EDITOR}; }}")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 8, 10, 8)
        self.card = QuizCard()
        self.card.answered.connect(self._on_answered)
        self.card.next_requested.connect(self._next)
        rl.addWidget(self.card, 1)
        splitter.addWidget(right)
        splitter.setSizes([320, 760])

        for cb in (self.module_cb, self.year_cb, self.region_cb, self.paper_cb):
            cb.currentIndexChanged.connect(self.reload)
        self.wrong_btn.toggled.connect(self.reload)
        self.new_btn.toggled.connect(self.reload)

        self._fill_filters()
        self.reload()

    def showEvent(self, event):
        super().showEvent(event)
        if apply_macos_transparent_titlebar(self):
            self.title_bar.hide()

    def _make_combo(self, layout, placeholder):
        cb = QComboBox(); cb.addItem(placeholder, None)
        layout.addWidget(cb)
        return cb

    def _fill_filters(self):
        for m in list_filter_values(self.conn, "module"):
            self.module_cb.addItem(m, m)
        for y in list_filter_values(self.conn, "year"):
            if y:
                self.year_cb.addItem(f"{y}年", y)
        for r in list_filter_values(self.conn, "region"):
            self.region_cb.addItem(r, r)
        for p in list_filter_values(self.conn, "paper"):
            if p:
                self.paper_cb.addItem(p, p)

    def reload(self):
        self._questions = fetch_questions(
            self.conn,
            module=self.module_cb.currentData(),
            year=self.year_cb.currentData(),
            region=self.region_cb.currentData(),
            paper=self.paper_cb.currentData(),
            wrong_only=self.wrong_btn.isChecked(),
            unanswered_only=self.new_btn.isChecked(),
            limit=1000 if self.paper_cb.currentData() else 500)
        self.listw.blockSignals(True)
        self.listw.clear()
        done_ids = self._done_map()
        for q in self._questions:
            item = QListWidgetItem(f"[{q['year']}] {q['module'][:4]} 第{q['seq']}题 {q['subtype'] or ''}")
            p = done_ids.get(q["id"])
            if p:
                item.setData(Qt.UserRole + 1, True)
                if p > 0:
                    item.setData(Qt.UserRole + 2, True)
            self.listw.addItem(item)
        self.listw.blockSignals(False)
        s = stats(self.conn)
        self.stat_lbl.setText(
            f"题库 {s['total']} 题 · 已刷 {s['done']} · 错题 {s['wrong']} · 正确率 {s['rate']:.0f}%"
            f" ｜ 当前列表 {len(self._questions)} 题")
        if self._questions:
            self.listw.setCurrentRow(0)

    def _done_map(self):
        rows = self.conn.execute(
            "SELECT question_id, wrong FROM progress WHERE attempts > 0").fetchall()
        return {r["question_id"]: r["wrong"] for r in rows}

    def _on_select(self, row):
        if 0 <= row < len(self._questions):
            self.card.show_question(self._questions[row])

    def _on_answered(self, correct):
        q = self.card._question
        record_answer(self.conn, q["id"], "", correct)
        row = self.listw.currentRow()
        item = self.listw.item(row)
        if item:
            item.setData(Qt.UserRole + 1, True)
            if not correct:
                item.setData(Qt.UserRole + 2, True)
        s = stats(self.conn)
        self.stat_lbl.setText(
            f"题库 {s['total']} 题 · 已刷 {s['done']} · 错题 {s['wrong']} · 正确率 {s['rate']:.0f}%"
            f" ｜ 当前列表 {len(self._questions)} 题")

    def _next(self):
        row = self.listw.currentRow()
        if row + 1 < self.listw.count():
            self.listw.setCurrentRow(row + 1)
