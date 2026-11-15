import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QRunnable, QThreadPool, QObject, Signal, Slot, QSize
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut, QIcon, QPixmap, QPainter, QLinearGradient, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QFrame
)
from .db import Database
from .scanner import scan_all
from .tracker import PlaytimeTracker

BG = "#070B18"
PANEL = "#10182B"
PANEL2 = "#17233B"
TEXT = "#F5F7FF"
MUTED = "#9BA9C6"
BLUE = "#4B8DFF"
CYAN = "#65D9FF"

def fmt_time(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    return f"{h} ч {m:02d} мин" if h else f"{m} мин"

class ScanSignals(QObject):
    finished = Signal(list)
    failed = Signal(str)

class ScanWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = ScanSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(scan_all())
        except Exception as exc:
            self.signals.failed.emit(str(exc))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.tracker = PlaytimeTracker()
        self.tracker.tick.connect(self.on_tick)
        self.tracker.finished.connect(self.on_finished)
        self.pool = QThreadPool.globalInstance()
        self.scan_worker = None
        self.current_filter = "Все игры"
        self.games = []
        self.setWindowTitle("GAME HUB")
        self.resize(1440, 900)
        self.setMinimumSize(1024, 680)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background:{BG}; color:{TEXT}; font-family:'Segoe UI'; }}
            QLabel#muted {{ color:{MUTED}; }}
            QLabel#eyebrow {{ color:{CYAN}; font-size:10px; font-weight:700; letter-spacing:3px; }}
            QPushButton {{ background:{PANEL2}; color:{TEXT}; border:1px solid #293957; border-radius:12px;
                padding:11px 16px; font-weight:600; }}
            QPushButton:hover {{ background:#24385B; border-color:{BLUE}; }}
            QPushButton:focus {{ border:2px solid {CYAN}; }}
            QPushButton#primary {{ background:{BLUE}; border:0; color:white; padding:15px 22px; }}
            QPushButton#primary:hover {{ background:#6AA2FF; }}
            QLineEdit {{ background:#0D1527; border:1px solid #263653; border-radius:12px;
                padding:13px 16px; color:{TEXT}; selection-background-color:{BLUE}; }}
            QListWidget {{ background:transparent; border:0; outline:0; }}
            QListWidget::item {{ background:#121D33; border:1px solid #263653; border-radius:15px;
                padding:10px; margin:7px; color:{TEXT}; }}
            QListWidget::item:selected {{ background:#1B3156; border:2px solid {BLUE}; }}
        """)
        self._build()
        self.refresh()
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("Return"), self, activated=self.launch_selected)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("background:#0A1121;border-right:1px solid #1B2942;")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(22, 30, 18, 24)
        logo = QLabel("GAME HUB")
        logo.setFont(QFont("Segoe UI", 19, QFont.Bold))
        sl.addWidget(logo)
        tagline = QLabel("YOUR GAME SPACE")
        tagline.setObjectName("eyebrow")
        sl.addWidget(tagline)
        sl.addSpacing(54)
        nav_title = QLabel("БИБЛИОТЕКА")
        nav_title.setObjectName("eyebrow")
        sl.addWidget(nav_title)
        for label, key in [("▦   Все игры", "Все игры"), ("☆   Избранное", "Избранное"), ("◷   Недавно играли", "Недавно запускались")]:
            button = QPushButton(label)
            button.setStyleSheet("text-align:left; padding:13px 12px; background:transparent; border:0;")
            button.clicked.connect(lambda checked=False, value=key: self.set_filter(value))
            sl.addWidget(button)
        sl.addStretch()
        self.scan_btn = QPushButton("⟳  Сканировать ПК")
        self.scan_btn.clicked.connect(self.scan_library)
        sl.addWidget(self.scan_btn)
        add_btn = QPushButton("+  Добавить игру")
        add_btn.clicked.connect(self.add_game)
        sl.addWidget(add_btn)
        root.addWidget(sidebar)

        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(34, 28, 34, 22)
        main.setSpacing(18)
        top = QHBoxLayout()
        intro = QVBoxLayout()
        eyebrow = QLabel("PLAY YOUR WAY")
        eyebrow.setObjectName("eyebrow")
        intro.addWidget(eyebrow)
        heading = QLabel("Игровое пространство")
        heading.setFont(QFont("Segoe UI", 25, QFont.Bold))
        intro.addWidget(heading)
        top.addLayout(intro)
        top.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("⌕   Поиск по библиотеке")
        self.search.setFixedWidth(300)
        self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search)
        fullscreen = QPushButton("⛶")
        fullscreen.setToolTip("Полный экран (F11)")
        fullscreen.clicked.connect(self.toggle_fullscreen)
        top.addWidget(fullscreen)
        main.addLayout(top)

        hero = QFrame()
        hero.setMinimumHeight(220)
        hero.setStyleSheet("""QFrame { border:1px solid #2C4772; border-radius:22px;
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1A3767,stop:0.48 #172342,stop:1 #291D46); }""")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(30, 24, 30, 24)
        info = QVBoxLayout()
        focus = QLabel("СЕЙЧАС В ФОКУСЕ")
        focus.setObjectName("eyebrow")
        info.addWidget(focus)
        self.hero_title = QLabel("ТВОЯ СЛЕДУЮЩАЯ ИГРА")
        self.hero_title.setWordWrap(True)
        self.hero_title.setFont(QFont("Segoe UI", 25, QFont.Bold))
        info.addWidget(self.hero_title)
        self.hero_desc = QLabel("Выбери игру в библиотеке и приготовься к запуску.")
        self.hero_desc.setObjectName("muted")
        self.hero_desc.setWordWrap(True)
        info.addWidget(self.hero_desc)
        info.addStretch()
        actions = QHBoxLayout()
        self.launch_btn = QPushButton("▶   ИГРАТЬ")
        self.launch_btn.setObjectName("primary")
        self.launch_btn.clicked.connect(self.launch_selected)
        actions.addWidget(self.launch_btn)
        self.favorite_btn = QPushButton("☆  В избранное")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        actions.addWidget(self.favorite_btn)
        info.addLayout(actions)
        hl.addLayout(info, 1)
        stats = QVBoxLayout()
        stats.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.count_label = QLabel("0")
        self.count_label.setFont(QFont("Segoe UI", 38, QFont.Bold))
        self.count_label.setAlignment(Qt.AlignRight)
        caption = QLabel("ИГР В КОЛЛЕКЦИИ")
        caption.setObjectName("eyebrow")
        caption.setAlignment(Qt.AlignRight)
        stats.addWidget(self.count_label)
        stats.addWidget(caption)
        hl.addLayout(stats)
        main.addWidget(hero)

        section = QHBoxLayout()
        title = QLabel("ТВОЯ БИБЛИОТЕКА")
        title.setObjectName("eyebrow")
        section.addWidget(title)
        section.addStretch()
        self.filter_label = QLabel("Все игры")
        self.filter_label.setObjectName("muted")
        section.addWidget(self.filter_label)
        main.addLayout(section)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setWrapping(True)
        self.list.setWordWrap(True)
        self.list.setSpacing(10)
        self.list.setGridSize(QSize(190, 148))
        self.list.setIconSize(QSize(150, 82))
        self.list.currentItemChanged.connect(self.show_details)
        main.addWidget(self.list, 1)

        bottom = QHBoxLayout()
        self.status = QLabel("Готово · Enter — запуск · Ctrl+F — поиск · F11 — полный экран")
        self.status.setObjectName("muted")
        bottom.addWidget(self.status, 1)
        remove = QPushButton("Убрать игру")
        remove.clicked.connect(self.remove_selected)
        bottom.addWidget(remove)
        main.addLayout(bottom)
        root.addWidget(content, 1)

    def _tile_icon(self, title):
        pix = QPixmap(150, 82)
        pix.fill(QColor("#152A4D"))
        painter = QPainter(pix)
        gradient = QLinearGradient(0, 0, 150, 82)
        palettes = [("#1E5799", "#7B3FA1"), ("#146B78", "#253D83"), ("#653A82", "#183C68")]
        first, second = palettes[sum(ord(c) for c in title) % len(palettes)]
        gradient.setColorAt(0, QColor(first))
        gradient.setColorAt(1, QColor(second))
        painter.fillRect(pix.rect(), gradient)
        painter.setPen(QColor(255, 255, 255, 35))
        painter.drawEllipse(80, -30, 110, 110)
        painter.end()
        return QIcon(pix)

    def refresh(self):
        if not hasattr(self, "list"):
            return
        all_games = self.db.all_games()
        query = self.search.text().strip().lower()
        if self.current_filter == "Избранное":
            all_games = [g for g in all_games if g["favorite"]]
        elif self.current_filter == "Недавно запускались":
            all_games = sorted([g for g in all_games if g["last_played"]], key=lambda g: g["last_played"], reverse=True)
        if query:
            all_games = [g for g in all_games if query in g["title"].lower()]
        selected_id = self.selected_game_id()
        self.list.blockSignals(True)
        self.list.clear()
        for game in all_games:
            item = QListWidgetItem(self._tile_icon(game["title"]), f'{game["title"]}\n{fmt_time(game["play_seconds"])}')
            item.setData(Qt.UserRole, game["id"])
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            item.setSizeHint(QSize(174, 128))
            self.list.addItem(item)
            if game["id"] == selected_id:
                self.list.setCurrentItem(item)
        if self.list.count() and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self.count_label.setText(str(len(self.db.all_games())))
        self.filter_label.setText(self.current_filter)
        self.show_details(self.list.currentItem())

    def selected_game_id(self):
        item = self.list.currentItem() if hasattr(self, "list") else None
        return item.data(Qt.UserRole) if item else None

    def selected_game(self):
        game_id = self.selected_game_id()
        return next((g for g in self.db.all_games() if g["id"] == game_id), None)

    def show_details(self, current, previous=None):
        game = self.selected_game()
        if not game:
            self.hero_title.setText("ТВОЯ СЛЕДУЮЩАЯ ИГРА")
            self.hero_desc.setText("Добавь игры или выбери одну из библиотеки.")
            self.favorite_btn.setText("☆  В избранное")
            self.favorite_btn.setEnabled(False)
            self.launch_btn.setEnabled(False)
            return
        self.hero_title.setText(game["title"])
        self.hero_desc.setText(f'{game["source"]}  ·  {fmt_time(game["play_seconds"])} сыграно  ·  {game["last_played"] or "Ещё не запускалась"}')
        self.favorite_btn.setEnabled(True)
        self.launch_btn.setEnabled(True)
        self.favorite_btn.setText("★  В избранном" if game["favorite"] else "☆  В избранное")

    def set_filter(self, value):
        self.current_filter = value
        self.refresh()

    def scan_library(self):
        if self.scan_worker is not None:
            return
        self.scan_btn.setEnabled(False)
        self.status.setText("Сканирую Steam, Epic Games и ярлыки Windows в фоне…")
        self.scan_worker = ScanWorker()
        self.scan_worker.signals.finished.connect(self._scan_done)
        self.scan_worker.signals.failed.connect(self._scan_failed)
        self.pool.start(self.scan_worker)

    def _scan_done(self, found):
        for game in found:
            self.db.add_game(game["title"], game["target"], game["kind"], game["process_name"], game["source"])
        self.scan_worker = None
        self.scan_btn.setEnabled(True)
        self.status.setText(f"Сканирование завершено. Найдено: {len(found)}; дубликаты пропущены.")
        self.refresh()

    def _scan_failed(self, message):
        self.scan_worker = None
        self.scan_btn.setEnabled(True)
        self.status.setText("Ошибка сканирования.")
        QMessageBox.warning(self, "Ошибка сканирования", message)

    def add_game(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбери игру или ярлык", "", "Игры и ярлыки (*.exe *.lnk);;Все файлы (*.*)")
        if not path:
            return
        p = Path(path)
        self.db.add_game(p.stem, str(p), "shortcut" if p.suffix.lower() == ".lnk" else "exe",
                         p.name if p.suffix.lower() == ".exe" else "", "Добавлена вручную")
        self.refresh()
        self.status.setText(f"Добавлена игра: {p.stem}")

    def launch_selected(self):
        game = self.selected_game()
        if not game:
            self.status.setText("Сначала выбери игру.")
            return
        try:
            kind, target = game["launch_kind"], game["launch_target"]
            if kind in ("steam", "uri") or target.startswith(("steam://", "com.epicgames.launcher://")):
                QDesktopServices.openUrl(QUrl(target))
                process = None
            elif kind == "shortcut" or target.lower().endswith(".lnk"):
                os.startfile(target)
                process = None
            else:
                process = subprocess.Popen([target], cwd=str(Path(target).parent))
            self.tracker.start(game["id"], process, game["process_name"] or Path(target).name)
            self.status.setText(f'Запущена игра: {game["title"]} · учёт времени активна')
        except Exception as exc:
            QMessageBox.critical(self, "Не удалось запустить игру", str(exc))

    def on_tick(self, game_id, elapsed):
        game = self.selected_game()
        if game and game["id"] == game_id:
            self.hero_desc.setText(f"Идёт игровая сессия · {fmt_time(elapsed)}")
        self.status.setText(f"Игровая сессия: {fmt_time(elapsed)}")

    def on_finished(self, game_id, elapsed):
        if elapsed:
            self.db.add_playtime(game_id, elapsed)
            self.refresh()
            self.status.setText(f"Сессия завершена · добавлено {fmt_time(elapsed)}")

    def toggle_favorite(self):
        game = self.selected_game()
        if game:
            self.db.toggle_favorite(game["id"])
            self.refresh()

    def remove_selected(self):
        game = self.selected_game()
        if game and QMessageBox.question(self, "Убрать игру", f'Убрать «{game["title"]}» из библиотеки? Файлы игры не будут удалены.') == QMessageBox.Yes:
            self.db.remove_game(game["id"])
            self.refresh()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event):
        self.tracker.stop()
        self.db.close()
        event.accept()
