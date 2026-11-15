import os, subprocess, time
from pathlib import Path
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QFrame, QStackedWidget, QProgressBar
)
from .db import Database
from .scanner import scan_all
from .tracker import PlaytimeTracker

BG = "#090B10"
PANEL = "#121722"
PANEL2 = "#1A2230"
TEXT = "#F4F6FA"
MUTED = "#9AA6B7"
ACCENT = "#55C7F3"

def fmt_time(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h} ч {m:02d} мин"
    return f"{m} мин"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.tracker = PlaytimeTracker()
        self.tracker.tick.connect(self.on_tick)
        self.tracker.finished.connect(self.on_finished)
        self.session_seconds = 0
        self.setWindowTitle("GAME HUB")
        self.resize(1360, 820)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI'; }}
            QLabel#muted {{ color: {MUTED}; }}
            QPushButton {{ background: {PANEL2}; color: {TEXT}; border: 1px solid #2B3545;
                border-radius: 10px; padding: 11px 16px; font-weight: 600; }}
            QPushButton:hover {{ border: 1px solid {ACCENT}; background: #243246; }}
            QPushButton:focus {{ border: 2px solid {ACCENT}; }}
            QLineEdit {{ background: {PANEL}; border: 1px solid #2B3545; border-radius: 10px;
                padding: 12px; color: {TEXT}; selection-background-color: {ACCENT}; }}
            QListWidget {{ background: transparent; border: 0; outline: 0; }}
            QListWidget::item {{ background: {PANEL}; border: 1px solid #202A39; border-radius: 13px;
                padding: 15px; margin: 5px 2px; }}
            QListWidget::item:selected {{ background: #20364A; border: 2px solid {ACCENT}; }}
        """)
        self._build()
        self.refresh()
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("Return"), self, activated=self.launch_selected)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(34, 26, 34, 24)
        outer.setSpacing(18)

        top = QHBoxLayout()
        brand = QVBoxLayout()
        title = QLabel("GAME HUB")
        title.setFont(QFont("Segoe UI", 25, QFont.Bold))
        sub = QLabel("ТВОЯ ИГРОВАЯ БИБЛИОТЕКА")
        sub.setObjectName("muted")
        sub.setStyleSheet("letter-spacing: 3px;")
        brand.addWidget(title)
        brand.addWidget(sub)
        top.addLayout(brand)
        top.addStretch()
        self.scan_btn = QPushButton("⟳  Сканировать ПК")
        self.scan_btn.clicked.connect(self.scan_library)
        self.add_btn = QPushButton("+  Добавить игру")
        self.add_btn.clicked.connect(self.add_game)
        self.full_btn = QPushButton("⛶  Полный экран")
        self.full_btn.clicked.connect(self.toggle_fullscreen)
        top.addWidget(self.scan_btn)
        top.addWidget(self.add_btn)
        top.addWidget(self.full_btn)
        outer.addLayout(top)

        hero = QFrame()
        hero.setStyleSheet(f"QFrame {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #172A3D, stop:0.55 #121722, stop:1 #241B2D); border: 1px solid #29394B; border-radius: 18px; }}")
        hero_l = QHBoxLayout(hero)
        hero_l.setContentsMargins(24, 18, 24, 18)
        left = QVBoxLayout()
        eyebrow = QLabel("WELCOME BACK")
        eyebrow.setObjectName("muted")
        eyebrow.setStyleSheet("letter-spacing: 3px;")
        self.hero_title = QLabel("ТВОИ ИГРЫ. ТВОИ ПРАВИЛА.")
        self.hero_title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.hero_desc = QLabel("Запускай игры и следи за своим игровым временем.")
        self.hero_desc.setObjectName("muted")
        left.addWidget(eyebrow)
        left.addWidget(self.hero_title)
        left.addWidget(self.hero_desc)
        left.addStretch()
        self.launch_btn = QPushButton("▶   ЗАПУСТИТЬ ВЫБРАННУЮ ИГРУ")
        self.launch_btn.clicked.connect(self.launch_selected)
        left.addWidget(self.launch_btn, 0, Qt.AlignLeft)
        hero_l.addLayout(left, 1)
        stats = QVBoxLayout()
        stats.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.count_label = QLabel("0")
        self.count_label.setFont(QFont("Segoe UI", 28, QFont.Bold))
        self.count_label.setAlignment(Qt.AlignRight)
        self.count_caption = QLabel("ИГР В БИБЛИОТЕКЕ")
        self.count_caption.setObjectName("muted")
        self.count_caption.setAlignment(Qt.AlignRight)
        stats.addWidget(self.count_label)
        stats.addWidget(self.count_caption)
        hero_l.addLayout(stats)
        outer.addWidget(hero)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("⌕  Найти игру...")
        self.search.textChanged.connect(self.refresh)
        controls.addWidget(self.search, 1)
        self.filter_btns = {}
        for label in ["Все игры", "Избранное", "Недавно запускались"]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, x=label: self.set_filter(x))
            controls.addWidget(btn)
            self.filter_btns[label] = btn
        outer.addLayout(controls)

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ListMode)
        self.list.setSpacing(2)
        self.list.currentItemChanged.connect(self.show_details)
        body.addWidget(self.list, 3)

        detail = QFrame()
        detail.setMinimumWidth(280)
        detail.setMaximumWidth(340)
        detail.setStyleSheet(f"QFrame {{ background: {PANEL}; border: 1px solid #202A39; border-radius: 16px; }}")
        d = QVBoxLayout(detail)
        d.setContentsMargins(20, 20, 20, 20)
        d.addWidget(QLabel("СЕЙЧАС В ФОКУСЕ"))
        self.detail_title = QLabel("Выбери игру")
        self.detail_title.setWordWrap(True)
        self.detail_title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        d.addWidget(self.detail_title)
        self.detail_source = QLabel("Добавь игры сканированием или вручную")
        self.detail_source.setObjectName("muted")
        self.detail_source.setWordWrap(True)
        d.addWidget(self.detail_source)
        d.addSpacing(14)
        d.addWidget(QLabel("ОБЩЕЕ ВРЕМЯ"))
        self.detail_time = QLabel("—")
        self.detail_time.setFont(QFont("Segoe UI", 22, QFont.Bold))
        d.addWidget(self.detail_time)
        d.addWidget(QLabel("ПОСЛЕДНИЙ ЗАПУСК"))
        self.detail_last = QLabel("—")
        self.detail_last.setObjectName("muted")
        d.addWidget(self.detail_last)
        d.addStretch()
        self.favorite_btn = QPushButton("☆  В избранное")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        self.remove_btn = QPushButton("Удалить из библиотеки")
        self.remove_btn.clicked.connect(self.remove_selected)
        d.addWidget(self.favorite_btn)
        d.addWidget(self.remove_btn)
        body.addWidget(detail, 1)
        outer.addLayout(body, 1)

        self.status = QLabel("Готово к игре · F11 — полноэкранный режим · Enter — запуск")
        self.status.setObjectName("muted")
        outer.addWidget(self.status)
        self.current_filter = "Все игры"
        self.games = []

    def refresh(self):
        all_games = self.db.all_games()
        query = self.search.text().strip().lower()
        if self.current_filter == "Избранное":
            all_games = [g for g in all_games if g["favorite"]]
        elif self.current_filter == "Недавно запускались":
            all_games = sorted([g for g in all_games if g["last_played"]], key=lambda x: x["last_played"], reverse=True)
        if query:
            all_games = [g for g in all_games if query in g["title"].lower()]
        self.games = all_games
        selected_id = self.selected_game_id()
        self.list.blockSignals(True)
        self.list.clear()
        for g in all_games:
            star = "★  " if g["favorite"] else ""
            item = QListWidgetItem(f"{star}{g['title']}\\n{g['source']}   ·   {fmt_time(g['play_seconds'])}")
            item.setData(Qt.UserRole, g["id"])
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint()))
            self.list.addItem(item)
            if g["id"] == selected_id:
                self.list.setCurrentItem(item)
        if self.list.count() and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self.count_label.setText(str(len(self.db.all_games())))
        if not self.list.currentItem():
            self.show_details(None)

    def selected_game_id(self):
        item = self.list.currentItem() if hasattr(self, "list") else None
        return item.data(Qt.UserRole) if item else None

    def selected_game(self):
        gid = self.selected_game_id()
        return next((g for g in self.db.all_games() if g["id"] == gid), None)

    def show_details(self, current, previous=None):
        game = self.selected_game()
        if not game:
            self.detail_title.setText("Выбери игру")
            self.detail_source.setText("Добавь игры сканированием или вручную")
            self.detail_time.setText("—")
            self.detail_last.setText("—")
            self.favorite_btn.setText("☆  В избранное")
            return
        self.detail_title.setText(game["title"])
        self.detail_source.setText(f"{game['source']} · {game['launch_kind']}")
        self.detail_time.setText(fmt_time(game["play_seconds"]))
        self.detail_last.setText(game["last_played"] or "Ещё не запускалась")
        self.favorite_btn.setText("★  Убрать из избранного" if game["favorite"] else "☆  В избранное")

    def set_filter(self, value):
        self.current_filter = value
        self.refresh()

    def scan_library(self):
        self.scan_btn.setEnabled(False)
        self.status.setText("Сканирование Steam, Epic Games и ярлыков Windows...")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            found = scan_all()
            for g in found:
                self.db.add_game(g["title"], g["target"], g["kind"], g["process_name"], g["source"])
            self.status.setText(f"Сканирование завершено. Найдено записей: {len(found)}. Дубликаты пропущены.")
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка сканирования", str(e))
            self.status.setText("Не удалось завершить сканирование.")
        finally:
            self.scan_btn.setEnabled(True)

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
            self.active_game = game
            self.tracker.start(game["id"], process, game["process_name"] or Path(target).name)
            self.status.setText(f"Запущена игра: {game['title']} · учёт времени активен")
            self.hero_title.setText(game["title"].upper())
            self.hero_desc.setText("Игра запущена · время будет сохранено автоматически")
        except Exception as e:
            QMessageBox.critical(self, "Не удалось запустить игру", str(e))
            self.status.setText("Ошибка запуска.")

    def on_tick(self, game_id, elapsed):
        self.session_seconds = elapsed
        game = self.selected_game()
        if game and game["id"] == game_id:
            self.detail_time.setText(fmt_time(game["play_seconds"] + elapsed))
        self.status.setText(f"Сессия: {fmt_time(elapsed)}")

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
        if game and QMessageBox.question(self, "Удалить игру", f"Убрать «{game['title']}» из библиотеки? Файлы игры не будут удалены.") == QMessageBox.Yes:
            self.db.remove_game(game["id"])
            self.refresh()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event):
        self.tracker.stop()
        self.db.close()
        event.accept()
