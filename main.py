"""公考刷题 - 托盘程序入口
启动后常驻菜单栏，点击齿轮图标：
  - 🎲 随机来一道（随机弹窗）
  - 📚 按模块刷题（弹窗，可指定模块）
  - 📖 刷套卷（弹窗，按整张卷顺序刷）
  - 🔥 错题重练（弹窗，仅错题）
  - 🖥️ 打开主窗口（完整界面，含套卷筛选）
  - 📋 导出错题 Markdown
  - 退出
"""
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QPainter, QPixmap, QColor, QBrush, QFont
from PyQt5.QtWidgets import (
    QAction, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import DB_PATH, get_conn, list_filter_values

# 当前版本号（和 version.txt 保持一致；运行时会自动从 version.txt 读）
CURRENT_VERSION = "20261027.1500"


def _load_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.txt")) as f:
            for line in f:
                if line.startswith("version="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return CURRENT_VERSION


def make_icon():
    """托盘图标：⚙️ emoji 渲染（Apple Color Emoji）"""
    pix = QPixmap(128, 128)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    f = QFont("Apple Color Emoji")
    f.setPixelSize(112)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, "⚙️")
    p.end()
    return QIcon(pix)


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("公考刷题")
        self._conn = None
        self._main_win = None
        self._popups = []
        self._init_db()
        self._init_tray()
        # 首次启动不弹窗口，托盘常驻
        QTimer.singleShot(200, self._show_main_if_empty)

    def _init_db(self):
        self._conn = get_conn()
        total = self._conn.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"]
        if total == 0:
            QTimer.singleShot(100, self._warn_empty)

    def _warn_empty(self):
        QMessageBox.information(
            self, "首次启动",
            f"题库还是空的。\n请先运行：\n\n"
            f"  python3 importer.py repo\n\n"
            f"（repo 目录需要先从 GitHub 下载）\n\n"
            f"数据库位置：{DB_PATH}")

    def _init_tray(self):
        icon = make_icon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("公考刷题")

        menu = QMenu()
        act_rand = QAction("🎲 随机来一道", self)
        act_rand.triggered.connect(lambda: self._open_popup(wrong_only=False))
        menu.addAction(act_rand)

        menu.addSeparator()
        modules = ["言语理解与表达", "数量关系", "判断推理", "资料分析", "常识判断"]
        for m in modules:
            a = QAction(f"📚 {m}", self)
            a.triggered.connect(lambda _, mm=m: self._open_popup(module=mm))
            menu.addAction(a)

        menu.addSeparator()
        act_wrong = QAction("🔥 错题重练", self)
        act_wrong.triggered.connect(lambda: self._open_popup(wrong_only=True))
        menu.addAction(act_wrong)

        # 刷套卷：让用户从所有 paper 里选
        act_paper = QAction("📖 刷套卷", self)
        act_paper.triggered.connect(self._pick_paper_and_open)
        menu.addAction(act_paper)

        act_open = QAction("🖥️ 打开主窗口", self)
        act_open.triggered.connect(self._open_main)
        menu.addAction(act_open)

        act_export = QAction("📋 导出错题 Markdown", self)
        act_export.triggered.connect(self._export_wrong)
        menu.addAction(act_export)

        act_report = QAction("📊 刷题总结", self)
        act_report.triggered.connect(self._show_report)
        menu.addAction(act_report)

        act_update = QAction("🔄 检查更新", self)
        act_update.triggered.connect(self._check_update)
        menu.addAction(act_update)

        menu.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._open_popup()

    def _show_main_if_empty(self):
        """题库非空时，托盘启动提示可直接刷题"""
        pass

    def _open_popup(self, module=None, wrong_only=False, paper=None):
        from popup import PopupQuiz
        # 已存在弹窗：复用同一个，按新条件刷新题目，不再多开
        for dlg in list(self._popups):
            dlg._module = module
            dlg._wrong_only = wrong_only
            dlg._paper = paper
            dlg._paper_queue = []
            dlg._paper_idx = 0
            for b in dlg.card._buttons.values():
                b.show()
            dlg.load_next()
            dlg.showNormal()
            dlg.raise_()
            dlg.activateWindow()
            return
        dlg = PopupQuiz(self._conn, module=module, wrong_only=wrong_only, paper=paper)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.finished.connect(lambda r, d=dlg: self._popups.remove(d) if d in self._popups else None)
        self._popups.append(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _pick_paper_and_open(self):
        """弹窗让用户选套卷，然后整张卷按顺序刷"""
        papers = list_filter_values(self._conn, "paper")
        if not papers:
            QMessageBox.information(self, "提示", "题库里还没有套卷")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("选择套卷")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("选一张试卷，按题号顺序刷："))
        cb = QComboBox(dlg); cb.setEditable(True)
        for p in papers:
            cb.addItem(p)
        # 让搜索体验更好
        cb.setInsertPolicy(QComboBox.NoInsert)
        v.addWidget(cb)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec_() == QDialog.Accepted:
            paper = cb.currentText().strip()
            if paper:
                self._open_popup(paper=paper)

    def _open_main(self):
        if self._main_win is None:
            from main_window import MainWindow
            self._main_win = MainWindow(self._conn)
        self._main_win.show()
        self._main_win.raise_()
        self._main_win.activateWindow()

    def _export_wrong(self):
        from db import export_wrong_markdown
        path = export_wrong_markdown(self._conn)
        try:
            import subprocess
            subprocess.Popen(["open", "-R", path])
        except Exception:
            pass
        self.tray.showMessage(
            "公考刷题", f"错题本已导出：{os.path.basename(path)}",
            QSystemTrayIcon.Information, 3000)

    def _show_report(self):
        from report_dialog import ReportDialog
        dlg = ReportDialog(self._conn, self)
        dlg.exec_()

    def _check_update(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QDialogButtonBox
        import threading

        ver = _load_version()

        dlg = QDialog(self)
        dlg.setWindowTitle("检查更新")
        dlg.resize(520, 360)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(f"当前版本：v{ver}"))
        log = QPlainTextEdit(); log.setReadOnly(True)
        v.addWidget(log, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)

        def progress(msg):
            log.appendPlainText(msg)

        def do_update():
            try:
                from update import check_and_update
                needs_restart, msg = check_and_update(ver, progress=progress)
                log.appendPlainText("")
                log.appendPlainText(msg)
                if needs_restart:
                    log.appendPlainText("")
                    log.appendPlainText("⚠️ 请退出程序后重新打开以应用更新。")
            except Exception as e:
                log.appendPlainText(f"更新失败：{e}")

        threading.Thread(target=do_update, daemon=True).start()
        dlg.exec_()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--plain", action="store_true", help="跳过托盘，直接弹主窗（Intel Mac 调试用）")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 让 Ctrl+C 能正常终止 Qt 事件循环（否则终端卡死、回显乱套）
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # 先测 PyQt5 能不能正常起来
    print("[gwy-quiz] PyQt5 启动中...", flush=True)

    from db import get_conn
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"]
    print(f"[gwy-quiz] 题库 {n} 题 ✓", flush=True)

    if args.plain or (not QSystemTrayIcon.isSystemTrayAvailable()):
        print("[gwy-quiz] 托盘不可用，直接弹主窗", flush=True)
        from main_window import MainWindow
        w = MainWindow(conn)
        w.show()
        sys.exit(app.exec_())

    print("[gwy-quiz] 注册托盘图标...", flush=True)
    w = App()
    print("[gwy-quiz] 托盘启动成功 ✓", flush=True)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
