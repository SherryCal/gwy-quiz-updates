"""刷题卡片控件 - Trae CN 黑底风格
新特性：共享文章显示 + <img> 图片渲图（图形推理、资料分析公式图）
"""
import json
import os

from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFontMetrics, QPalette, QColor, QPixmap
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

BG_EDITOR   = "#1E1E1E"
BG_SUB      = "#252526"
BG_HOVER    = "#2A2D2E"
FG_MAIN     = "#D4D4D4"
FG_DIM      = "#808080"
BORDER      = "#3C3C3C"
ACCENT      = "#0E639C"
CORRECT     = "#4EC9B0"
WRONG       = "#F48771"
HL          = "#264F78"

STYLE = f"""
QuizCard {{ background: {BG_EDITOR}; }}
QWidget {{ background: {BG_EDITOR}; color: {FG_MAIN}; }}
QFrame {{ background: {BG_EDITOR}; }}
QFrame#card {{
    background: {BG_EDITOR}; border: 1px solid {BORDER}; border-radius: 0px;
}}
QLabel {{ background: transparent; color: {FG_MAIN}; }}
QLabel#meta {{ color: {FG_DIM}; font-size: 12px; }}
QLabel#stem {{ font-size: 15px; line-height: 1.7; color: {FG_MAIN}; }}
QLabel#result {{ font-size: 15px; font-weight: bold; }}
QLabel#analysis {{
    background: {BG_SUB}; border-radius: 4px; padding: 10px;
    color: {FG_MAIN}; font-size: 13px; border: 1px solid {BORDER};
}}
QPushButton.opt {{
    background: {BG_SUB}; color: {FG_MAIN}; border: 1px solid {BORDER};
    border-radius: 0px; padding: 10px 14px; text-align: left; font-size: 14px;
}}
QPushButton.opt:hover {{ background: {BG_HOVER}; border-color: #454545; }}
QPushButton.opt:disabled {{ color: #5A5A5A; }}
QPushButton.opt[correct="true"] {{ background: #1E3D2D; border-color: {CORRECT}; color: {CORRECT}; }}
QPushButton.opt[wrong="true"] {{ background: #3D1E1E; border-color: {WRONG}; color: {WRONG}; }}
QPushButton.action {{
    background: rgba(0, 0, 0, 60); color: {FG_MAIN}; border: 1px solid {BORDER};
    border-radius: 2px; padding: 8px 22px; font-size: 14px;
}}
QPushButton.action:hover {{ background: rgba(0, 0, 0, 120); border-color: {FG_DIM}; }}
QPushButton.action:pressed {{ background: rgba(0, 0, 0, 180); }}
QScrollArea {{ background: {BG_EDITOR}; border: none; }}
QScrollArea::viewport {{ background: {BG_EDITOR}; }}
QScrollBar:vertical {{ background: {BG_EDITOR}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 2px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background: #454545; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

LETTERS = ("A", "B", "C", "D")


def _make_palette():
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG_EDITOR))
    pal.setColor(QPalette.Base, QColor(BG_EDITOR))
    pal.setColor(QPalette.WindowText, QColor(FG_MAIN))
    pal.setColor(QPalette.Text, QColor(FG_MAIN))
    pal.setColor(QPalette.AlternateBase, QColor(BG_EDITOR))
    pal.setColor(QPalette.ToolTipBase, QColor(BG_EDITOR))
    pal.setColor(QPalette.ToolTipText, QColor(FG_MAIN))
    pal.setColor(QPalette.Button, QColor(BG_SUB))
    pal.setColor(QPalette.ButtonText, QColor(FG_MAIN))
    pal.setColor(QPalette.Highlight, QColor(HL))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    return pal


class QuizCard(QWidget):
    answered = pyqtSignal(bool)
    next_requested = pyqtSignal()

    def __init__(self, parent=None, font_scale=1.0):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        pal = _make_palette()
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self._question = None
        self._answered = False
        self._scale = font_scale

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame(); card.setObjectName("card")
        card.setStyleSheet(f"QFrame#card {{ background: {BG_EDITOR}; border: 1px solid {BORDER}; border-radius: 0px; }}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        root.addWidget(card)

        self._meta = QLabel(); self._meta.setObjectName("meta")
        self._meta.setStyleSheet(f"color: {FG_DIM}; font-size: 12px; background: transparent;")
        layout.addWidget(self._meta)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # 关键：关掉横向 scroll bar，强制所有内部控件走 wordwrap
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {BG_EDITOR}; border: none; }}"
            f"QScrollArea::viewport {{ background: {BG_EDITOR}; }}")
        self._scroll = scroll

        inner = QWidget(); inner.setObjectName("inner")
        inner.setStyleSheet(f"background: {BG_EDITOR};")
        inner.setPalette(pal); inner.setAutoFillBackground(True)
        self._inner = inner
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(8)
        scroll.setWidget(inner)
        # 关键：viewport 也强制调色板（macOS 默认 Base=白色，这是白底白字的根因）
        vp = scroll.viewport()
        vp.setPalette(pal); vp.setAutoFillBackground(True)
        layout.addWidget(scroll, 1)

        self._stem = QLabel(); self._stem.setObjectName("stem")
        self._stem.setWordWrap(True)
        self._stem.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._stem.setStyleSheet(f"color: {FG_MAIN}; background: transparent; font-size: 15px;")
        self._inner_layout.addWidget(self._stem)

        # 共享文章（一材多题的"材"，如言语片段阅读、判断推理材料题）
        self._passage = QLabel()
        self._passage.setWordWrap(True)
        self._passage.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._passage.setStyleSheet(
            f"background: {BG_SUB}; border: 1px solid {BORDER}; padding: 10px;"
            f" color: {FG_MAIN}; font-size: 13px; border-radius: 4px;")
        self._passage.hide()
        # passage 应该在 stem 上面（先看材料再看题）
        self._inner_layout.insertWidget(0, self._passage)

        # 图片容器（题干中 <img> 标签，图形推理题目图等）
        self._image_host = QWidget(); self._image_host.setStyleSheet("background: transparent;")
        self._image_layout = QVBoxLayout(self._image_host)
        self._image_layout.setContentsMargins(0, 4, 0, 4)
        self._image_layout.setSpacing(6)
        self._inner_layout.addWidget(self._image_host)
        self._image_host.hide()

        self._buttons = {}
        for letter in LETTERS:
            btn = QPushButton(); btn.setProperty("class", "opt")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, l=letter: self._choose(l))
            self._buttons[letter] = btn
            self._inner_layout.addWidget(btn)

        self._result = QLabel(); self._result.setObjectName("result")
        self._result.hide()
        self._inner_layout.addWidget(self._result)

        self._analysis = QLabel(); self._analysis.setObjectName("analysis")
        self._analysis.setWordWrap(True)
        self._analysis.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._analysis.hide()
        self._inner_layout.addWidget(self._analysis)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self._next_btn = QPushButton("下一题"); self._next_btn.setProperty("class", "action")
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.clicked.connect(self.next_requested.emit)
        bottom.addWidget(self._next_btn)
        layout.addLayout(bottom)
        self._apply_scale()

    def _apply_scale(self):
        base = self._scale
        self._stem.setStyleSheet(
            f"color: {FG_MAIN}; background: transparent; font-size: {int(15*base)}px;")
        for b in self._buttons.values():
            b.setStyleSheet(f"font-size: {int(14*base)}px;")
        self._analysis.setStyleSheet(
            f"background:{BG_SUB};border-radius:4px;padding:10px;color:{FG_MAIN};"
            f"font-size:{int(13*base)}px;border:1px solid {BORDER};")

    def set_font_scale(self, scale):
        self._scale = scale
        self._apply_scale()

    def show_question(self, q):
        # sqlite3.Row 没有 .get()，先转 dict 兜底
        q = dict(q) if not isinstance(q, dict) else q
        self._question = q
        self._answered = False
        self._meta.setText(
            f"{q['paper']} · {q['module']} / {q['subtype'] or '-'} · 第{q['seq']}题")

        # 共享文章
        passage = q.get("shared_passage") or ""
        if passage:
            self._passage.setText(passage)
            self._passage.show()
        else:
            self._passage.hide()

        # 图片渲图
        self._clear_images()
        images_raw = q.get("images") or ""
        if images_raw:
            try:
                paths = json.loads(images_raw)
            except Exception:
                paths = []
            for p in paths:
                self._add_image(p)

        stem = q["stem"]
        # stem 里的 [图] 占位符已经在 importer 层被 clean_html 替掉了；
        # 这里再兜底替换一次（以防旧数据）
        stem = stem.replace("[图]", "").strip()
        if len(q.get("answer", "")) > 1:
            stem += "\n（本题为多选）"
        self._stem.setText(stem)

        # 彻底重置按钮状态（polish 刷新样式，防止上一题残留）
        vp_w = self._scroll.viewport().width()
        for letter in LETTERS:
            text = q[f"option_{letter.lower()}"] or ""
            btn = self._buttons[letter]
            btn.setProperty("correct", "")
            btn.setProperty("wrong", "")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            if text:
                btn.setText(f"{letter}. {text}")
                btn.setEnabled(True)
                btn.show()
                # 手动换行：按当前 viewport 宽度把长文字拆成多行
                self._wrap_button_text(btn, vp_w)
            else:
                btn.hide()

        self._result.hide()
        self._analysis.hide()

    def _clear_images(self):
        """清掉上一题所有图片"""
        while self._image_layout.count():
            item = self._image_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._image_host.hide()

    def _add_image(self, path):
        from db import resolve_image
        local = resolve_image(path)
        if not local:
            return
        pm = QPixmap(local)
        if pm.isNull():
            return
        # 限制宽度：用当前 scroll viewport 宽 - 20px 余量，防止横向撑出
        vp_w = self._scroll.viewport().width()
        max_w = max(vp_w - 20, 280)
        if pm.width() > max_w:
            pm = pm.scaledToWidth(max_w, Qt.SmoothTransformation)
        lbl = QLabel()
        lbl.setPixmap(pm)
        lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lbl.setStyleSheet("background: transparent;")
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._image_layout.addWidget(lbl)
        self._image_host.show()

    def resizeEvent(self, event):
        """每次尺寸变了，同步 inner 最小宽度到 viewport，强制 wordwrap 生效"""
        super().resizeEvent(event)
        vp_w = self._scroll.viewport().width()
        if vp_w > 0:
            self._inner.setMinimumWidth(vp_w)
            self._inner.setMaximumWidth(vp_w)
            # 已显示的按钮重新换行
            if self._question:
                for b in self._buttons.values():
                    if b.isVisible():
                        self._wrap_button_text(b, vp_w)

    def _wrap_button_text(self, btn, vp_w):
        """把按钮 text 按 viewport 宽度拆成多行（插 \n），防止撑出横向 scroll bar"""
        if vp_w <= 0:
            return
        text = btn.text()
        if not text or "\n" in text:
            return
        fm = QFontMetrics(btn.font())
        # QPushButton 内边距：左右各 14px（样式表 padding）
        max_w = vp_w - 40  # 留 40px 余量给 border + 行间距
        if fm.horizontalAdvance(text) <= max_w:
            return  # 够宽不用拆
        # 按字符逐个加，超了就找最近的空格/标点拆
        result = []
        line = ""
        for ch in text:
            trial = line + ch
            if fm.horizontalAdvance(trial) > max_w and line:
                # 拆在最近的空格/标点之后（中文没有空格就按字符硬拆）
                split_idx = len(line)
                for i in range(len(line) - 1, max(len(line) - 20, 0), -1):
                    if line[i] in (" ", "，", "。", "、", "；", "：", "/", "(", "（"):
                        split_idx = i + 1
                        break
                result.append(line[:split_idx])
                line = line[split_idx:] + ch
            else:
                line = trial
        if line:
            result.append(line)
        btn.setText("\n".join(result))

    def _choose(self, letter):
        if self._answered or not self._question:
            return
        self._answered = True
        q = self._question
        correct = letter == q["answer"]
        for l, btn in self._buttons.items():
            btn.setEnabled(False)
            btn.setProperty("correct", l == q["answer"])
            btn.setProperty("wrong", l == letter and not correct)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._result.setText("✓ 回答正确" if correct else f"✗ 正确答案：{q['answer']}")
        self._result.setStyleSheet(
            f"color: {CORRECT if correct else WRONG}; background: transparent;"
            f" font-size: 15px; font-weight: bold;")
        self._result.show()
        if q["analysis"]:
            self._analysis.setText(q["analysis"])
            self._analysis.show()
        self.answered.emit(correct)
