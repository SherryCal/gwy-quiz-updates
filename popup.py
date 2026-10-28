"""隐蔽模式快捷刷题弹窗 - 可 resize + 自绘黑标题栏
关键：边缘 resize 直接在 Dialog 自己的 mouse 事件里处理，不用 overlay widget
Qt 规则：子控件（按钮）先收到事件，如果它们 accept 了就不冒泡到父 Dialog
"""
import sys
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QPalette, QColor, QCursor
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from db import fetch_questions, record_answer
from quiz_card import QuizCard
from quiz_card import (BG_EDITOR, FG_MAIN, FG_DIM, _make_palette)

from main_window import apply_macos_transparent_titlebar


MARGIN = 6        # 边缘感应区宽度
MIN_W, MIN_H = 480, 360


class PopupQuiz(QDialog):
    def __init__(self, conn, module=None, wrong_only=False, paper=None):
        super().__init__()
        self.conn = conn
        self._module = module
        self._wrong_only = wrong_only
        self._paper = paper
        self._paper_queue = []
        self._paper_idx = 0
        self.setWindowTitle("公考刷题")
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint
            | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)

        pal = _make_palette()
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.resize(760, 560)

        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 30,
                  screen.bottom() - self.height() - 60)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget(); bar.setFixedHeight(28)
        bar.setStyleSheet(f"QWidget {{ background: {BG_EDITOR}; }}")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(12, 0, 8, 0); bar_l.setSpacing(6)
        tip = QLabel("随机刷题")
        tip.setStyleSheet(f"color: {FG_DIM}; font-size: 11px; background: transparent;")
        bar_l.addWidget(tip); bar_l.addStretch(1)

        min_btn = QPushButton("－"); min_btn.setFixedSize(22, 16)
        min_btn.setStyleSheet(self._title_btn_style())
        min_btn.clicked.connect(self.showMinimized)
        self._min_btn = min_btn
        bar_l.addWidget(min_btn)

        close_btn = QPushButton("×"); close_btn.setFixedSize(22, 16)
        close_btn.setStyleSheet(self._title_btn_style())
        close_btn.clicked.connect(self.close)
        self._close_btn = close_btn
        bar_l.addWidget(close_btn)
        root.addWidget(bar)
        self._bar = bar

        body = QWidget(); body.setStyleSheet(f"QWidget {{ background: {BG_EDITOR}; }}")
        body.setPalette(pal); body.setAutoFillBackground(True)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(10, 6, 10, 10)
        self.card = QuizCard()
        self.card.answered.connect(self._on_answered)
        self.card.next_requested.connect(self.load_next)
        bl.addWidget(self.card)
        root.addWidget(body, 1)

        # resize 状态（直接在 Dialog 自身处理）
        self._drag_pos = None       # 标题栏拖动
        self._resize_dir = None     # 当前 resize 方向
        self._resize_start_pos = None
        self._resize_start_geo = None

        self.load_next()

    def _title_btn_style(self):
        return (f"QPushButton {{ background: rgba(0, 0, 0, 60); border: 1px solid #3C3C3C;"
                f" border-radius: 2px; color: {FG_MAIN}; font-size: 10px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: rgba(0, 0, 0, 140); border-color: {FG_DIM}; }}")

    # --- 边缘 hit test ---
    def _hit_edge(self, pos):
        w, h = self.width(), self.height()
        m = MARGIN
        x, y = pos.x(), pos.y()
        direction = ""
        if y <= m: direction += "T"
        if y >= h - m: direction += "B"
        if x <= m: direction += "L"
        if x >= w - m: direction += "R"
        return direction or None

    # --- mouse 事件（子控件没 consume 才会到这里）---
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        edge = self._hit_edge(e.pos())
        if edge:
            # 点在边缘 → 开始 resize
            self._resize_dir = edge
            self._resize_start_pos = e.globalPos()
            self._resize_start_geo = self.geometry()
            e.accept()
        elif e.y() < 28:
            # 标题栏区域（但边缘不算，边缘给 resize）→ 开始拖动
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            e.accept()
        else:
            # 内容区 → 忽略，让子控件处理
            e.ignore()

    def mouseMoveEvent(self, e):
        if self._resize_dir and self._resize_start_pos:
            # 正在 resize
            delta = e.globalPos() - self._resize_start_pos
            geo = QRect(self._resize_start_geo)
            d = self._resize_dir
            if "L" in d:
                new_left = geo.left() + delta.x()
                if geo.right() - new_left + 1 >= MIN_W:
                    geo.setLeft(new_left)
                else:
                    geo.setLeft(geo.right() - MIN_W + 1)
            if "R" in d:
                geo.setRight(geo.right() + delta.x())
                if geo.width() < MIN_W:
                    geo.setRight(geo.left() + MIN_W - 1)
            if "T" in d:
                new_top = geo.top() + delta.y()
                if geo.bottom() - new_top + 1 >= MIN_H:
                    geo.setTop(new_top)
                else:
                    geo.setTop(geo.bottom() - MIN_H + 1)
            if "B" in d:
                geo.setBottom(geo.bottom() + delta.y())
                if geo.height() < MIN_H:
                    geo.setBottom(geo.top() + MIN_H - 1)
            self.setGeometry(geo)
            e.accept()
        elif self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag_pos)
            e.accept()
        else:
            # 只在边缘区改光标，其它地方让子控件决定
            edge = self._hit_edge(e.pos())
            if edge:
                cursor_map = {
                    "L": Qt.SizeHorCursor, "R": Qt.SizeHorCursor,
                    "T": Qt.SizeVerCursor, "B": Qt.SizeVerCursor,
                    "TL": Qt.SizeFDiagCursor, "BR": Qt.SizeFDiagCursor,
                    "TR": Qt.SizeBDiagCursor, "BL": Qt.SizeBDiagCursor,
                }
                self.setCursor(cursor_map.get(edge))
                e.accept()
            else:
                self.setCursor(Qt.ArrowCursor)
                e.ignore()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        self._resize_dir = None
        self._resize_start_pos = None
        self._resize_start_geo = None

    def showEvent(self, event):
        super().showEvent(event)
        if apply_macos_transparent_titlebar(self):
            self._bar.hide()
        self.raise_(); self.activateWindow(); self.setFocus()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 已显示的按钮重新换行（窗口变大/变小时选项按钮重算换行）
        if self.card._question:
            self.card.resizeEvent(e)

    def load_next(self):
        if self._paper:
            if not self._paper_queue:
                self._paper_queue = fetch_questions(
                    self.conn, paper=self._paper, limit=1000, random_order=False)
                self._paper_idx = 0
            if self._paper_idx < len(self._paper_queue):
                q = self._paper_queue[self._paper_idx]
                self._paper_idx += 1
                self.card.show_question(q)
                return
            self.card._meta.setText(f"✅ {self._paper} 全部刷完")
            self.card._stem.setText("可以换张卷或切回随机刷题。")
            for b in self.card._buttons.values():
                b.hide()
            self._paper = None
            self._paper_queue = []
            return

        qs = fetch_questions(self.conn, module=self._module,
                             wrong_only=self._wrong_only,
                             limit=1, random_order=True)
        if qs:
            self.card.show_question(qs[0])
        else:
            self.card._meta.setText("没有符合条件的题目了")
            self.card._stem.setText("换个筛选条件试试。")
            for b in self.card._buttons.values():
                b.hide()

    def _on_answered(self, correct):
        q = self.card._question
        record_answer(self.conn, q["id"], "", correct)
