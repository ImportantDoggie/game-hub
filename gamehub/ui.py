import os
import subprocess
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QRunnable, QThreadPool, QObject, Signal, Slot, QSize
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QIcon, QPixmap, QPainter, QColor, QLinearGradient
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QFrame,
    QGraphicsOpacityEffect
)
from PySide6.QtCore import QPropertyAnimation, QEasingCurve

from .db import Database
from .scanner import scan_all
from .tracker import PlaytimeTracker

APP_DIR = Path.home() / "AppData" / "Local" / "GameHub"
ART_DIR = APP_DIR / "artwork"
ART_DIR.mkdir(parents=True, exist_ok=True)

BG = "#08090d"
TEXT = "#f5f5f7"
MUTED = "#c0c1c8"
ACCENT = "#65cfff"


def fmt_time(seconds):
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{hours} ч {minutes:02d} мин" if hours else f"{minutes} мин"


def steam_app_id(game):
    target = str(game.get("launch_target", ""))
    if target.startswith("steam://rungameid/"):
        return target.rsplit("/", 1)[-1]
    return ""


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


class ArtworkSignals(QObject):
    finished = Signal(int, str)


class ArtworkWorker(QRunnable):
    def __init__(self, game_id, url, destination):
        super().__init__()
        self.game_id = game_id
        self.url = url
        self.destination = destination
        self.signals = ArtworkSignals()

    @Slot()
    def run(self):
        try:
            request = urllib.request.Request(
                self.url, headers={"User-Agent": "GAME-HUB/1.0"}
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read()
            if not data:
                raise ValueError("Empty artwork response")
            self.destination.write_bytes(data)
            self.signals.finished.emit(self.game_id, str(self.destination))
        except Exception:
            self.signals.finished.emit(self.game_id, "")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.tracker = PlaytimeTracker()
        self.tracker.tick.connect(self.on_tick)
        self.tracker.finished.connect(self.on_finished)
        self.pool = QThreadPool.globalInstance()
        self.scan_worker = None
        self.art_jobs = set()
        self.current_filter = "Все игры"
        self._backdrop_pixmap = None

        self.setWindowTitle("GAME HUB")
        self.resize(1600, 900)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {BG}; color: {TEXT}; font-family: 'Segoe UI';
            }}
            QLabel#eyebrow {{
                color: #e2e3e8; font-size: 11px; letter-spacing: 3px;
            }}
            QLabel#muted {{ color: {MUTED}; }}
            QPushButton {{
                color: {TEXT}; background: rgba(24, 26, 32, 220);
                border: 1px solid rgba(210, 220, 235, 65);
                border-radius: 7px; padding: 10px 16px;
            }}
            QPushButton:hover {{
                background: rgba(66, 83, 105, 235); border-color: {ACCENT};
            }}
            QPushButton:focus {{ border: 2px solid {ACCENT}; }}
            QPushButton#play {{
                background: #f4f4f6; color: #111217; border: 0;
                font-weight: 700; padding: 13px 24px;
            }}
            QPushButton#play:hover {{ background: #ccefff; }}
            QLineEdit {{
                background: rgba(16, 18, 24, 220); border: 1px solid #555965;
                border-radius: 18px; padding: 10px 15px; color: {TEXT};
            }}
            QListWidget {{ background: transparent; border: 0; outline: 0; }}
            QListWidget::item {{
                background: rgba(7, 8, 12, 175); border: 2px solid transparent;
                border-radius: 10px; padding: 3px; margin: 5px; color: {TEXT};
            }}
            QListWidget::item:selected {{
                background: rgba(38, 57, 72, 210); border: 3px solid {ACCENT};
            }}
        """)

        self._build_ui()
        self.refresh()
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("Return"), self, activated=self.launch_selected)
        QShortcut(QKeySequence("Left"), self, activated=self.select_previous)
        QShortcut(QKeySequence("Right"), self, activated=self.select_next)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # The image label fills the window; a translucent overlay keeps text legible.
        self.backdrop = QLabel(central)
        self.backdrop.setGeometry(0, 0, 1, 1)
        self.backdrop.setScaledContents(True)
        self.backdrop.lower()
        self.backdrop.setStyleSheet("""
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #66717d, stop:0.45 #343944, stop:1 #07080b);
        """)
        self.shade = QFrame(central)
        self.shade.setGeometry(0, 0, 1, 1)
        self.shade.lower()
        self.shade.setStyleSheet("""
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 rgba(5,7,12,55), stop:0.48 rgba(5,7,12,115),
                stop:0.78 rgba(5,7,12,205), stop:1 rgba(0,0,0,250));
        """)

        top = QHBoxLayout()
        top.setContentsMargins(42, 20, 42, 10)
        brand = QLabel("GAME HUB")
        brand.setFont(QFont("Segoe UI", 15, QFont.Bold))
        brand.setStyleSheet("letter-spacing: 4px;")
        top.addWidget(brand)
        top.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("⌕   Поиск по библиотеке")
        self.search.setFixedWidth(255)
        self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search)
        fullscreen = QPushButton("⛶")
        fullscreen.setToolTip("Полный экран · F11")
        fullscreen.clicked.connect(self.toggle_fullscreen)
        top.addWidget(fullscreen)
        outer.addLayout(top)

        hero = QHBoxLayout()
        hero.setContentsMargins(58, 42, 58, 10)
        hero.setSpacing(20)
        info = QVBoxLayout()
        info.setSpacing(12)

        self.hero_source = QLabel("ТВОЯ ИГРОВАЯ БИБЛИОТЕКА")
        self.hero_source.setObjectName("eyebrow")
        info.addWidget(self.hero_source)

        self.hero_title = QLabel("ТВОЯ СЛЕДУЮЩАЯ ИГРА")
        self.hero_title.setWordWrap(True)
        self.hero_title.setMaximumWidth(850)
        self.hero_title.setFont(QFont("Segoe UI", 31, QFont.Bold))
        info.addWidget(self.hero_title)

        self.hero_desc = QLabel("Выбери игру в библиотеке и приготовься к запуску.")
        self.hero_desc.setObjectName("muted")
        self.hero_desc.setWordWrap(True)
        info.addWidget(self.hero_desc)
        info.addSpacing(12)

        actions = QHBoxLayout()
        self.launch_btn = QPushButton("▶   ИГРАТЬ")
        self.launch_btn.setObjectName("play")
        self.launch_btn.clicked.connect(self.launch_selected)
        actions.addWidget(self.launch_btn)

        self.favorite_btn = QPushButton("☆  В избранное")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        actions.addWidget(self.favorite_btn)

        artwork_btn = QPushButton("▧  Обложка")
        artwork_btn.setToolTip("Выбрать локальное изображение для игры")
        artwork_btn.clicked.connect(self.choose_artwork)
        actions.addWidget(artwork_btn)

        info.addLayout(actions)
        info.addStretch()
        hero.addLayout(info, 1)

        stats = QVBoxLayout()
        stats.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        self.count_label = QLabel("0")
        self.count_label.setFont(QFont("Segoe UI", 42, QFont.Light))
        self.count_label.setAlignment(Qt.AlignRight)
        stats.addWidget(self.count_label)
        count_caption = QLabel("ИГР В КОЛЛЕКЦИИ")
        count_caption.setObjectName("eyebrow")
        count_caption.setAlignment(Qt.AlignRight)
        stats.addWidget(count_caption)
        hero.addLayout(stats)
        outer.addLayout(hero, 1)

        section = QHBoxLayout()
        section.setContentsMargins(48, 4, 48, 0)
        title = QLabel("ТВОЯ БИБЛИОТЕКА")
        title.setObjectName("eyebrow")
        section.addWidget(title)
        section.addStretch()
        for label, value in (
            ("Все", "Все игры"),
            ("Избранное", "Избранное"),
            ("Недавно играли", "Недавно запускались"),
        ):
            button = QPushButton(label)
            button.setFlat(True)
            button.clicked.connect(
                lambda checked=False, selected=value: self.set_filter(selected)
            )
            section.addWidget(button)
        outer.addLayout(section)

        self.list = QListWidget()
        self.list.setFlow(QListWidget.LeftToRight)
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setWrapping(False)
        self.list.setSpacing(8)
        self.list.setGridSize(QSize(174, 160))
        self.list.setIconSize(QSize(150, 112))
        self.list.setMinimumHeight(205)
        self.list.currentItemChanged.connect(self.show_details)
        outer.addWidget(self.list)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(48, 5, 48, 18)
        self.status = QLabel("Enter — запуск  ·  ← → — выбор  ·  F11 — полный экран")
        self.status.setObjectName("muted")
        bottom.addWidget(self.status, 1)

        scan_button = QPushButton("⟳  Сканировать ПК")
        scan_button.clicked.connect(self.scan_library)
        bottom.addWidget(scan_button)

        add_button = QPushButton("+  Добавить игру")
        add_button.clicked.connect(self.add_game)
        bottom.addWidget(add_button)

        remove_button = QPushButton("Убрать игру")
        remove_button.clicked.connect(self.remove_selected)
        bottom.addWidget(remove_button)
        outer.addLayout(bottom)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for widget in (getattr(self, "backdrop", None), getattr(self, "shade", None)):
            if widget:
                widget.setGeometry(0, 0, self.width(), self.height())

    def select_previous(self):
        if self.list.count():
            self.list.setCurrentRow(max(0, self.list.currentRow() - 1))

    def select_next(self):
        if self.list.count():
            self.list.setCurrentRow(min(self.list.count() - 1, self.list.currentRow() + 1))

    def selected_game_id(self):
        item = self.list.currentItem() if hasattr(self, "list") else None
        return item.data(Qt.UserRole) if item else None

    def selected_game(self):
        game_id = self.selected_game_id()
        return next(
            (game for game in self.db.all_games() if game["id"] == game_id), None
        )

    def _art_path(self, game):
        custom = game.get("artwork_path", "")
        if custom and Path(custom).is_file():
            return Path(custom)

        appid = steam_app_id(game)
        if not appid:
            return None

        # Steam's library portrait and wide hero artwork use public CDN paths.
        portrait = ART_DIR / f"{appid}_portrait.jpg"
        if portrait.is_file():
            return portrait

        key = f"{appid}_portrait"
        if key not in self.art_jobs:
            self.art_jobs.add(key)
            worker = ArtworkWorker(
                int(game["id"]),
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
                portrait,
            )
            worker.signals.finished.connect(self._artwork_ready)
            self.pool.start(worker)
        return None

    def _hero_path(self, game):
        custom = game.get("artwork_path", "")
        if custom and Path(custom).is_file():
            return Path(custom)

        appid = steam_app_id(game)
        if not appid:
            return None

        hero = ART_DIR / f"{appid}_hero.jpg"
        if hero.is_file():
            return hero

        key = f"{appid}_hero"
        if key not in self.art_jobs:
            self.art_jobs.add(key)
            worker = ArtworkWorker(
                int(game["id"]),
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_hero.jpg",
                hero,
            )
            worker.signals.finished.connect(self._artwork_ready)
            self.pool.start(worker)
        return None

    def _artwork_ready(self, game_id, path):
        # Remove both possible keys; a failed download is retried on next refresh.
        game = next((g for g in self.db.all_games() if g["id"] == game_id), None)
        if game:
            appid = steam_app_id(game)
            self.art_jobs.discard(f"{appid}_portrait")
            self.art_jobs.discard(f"{appid}_hero")
        if path:
            self.refresh()

    def _fallback_icon(self, title):
        pixmap = QPixmap(300, 220)
        pixmap.fill(QColor("#202733"))
        painter = QPainter(pixmap)
        gradient = QLinearGradient(0, 0, 300, 220)
        gradient.setColorAt(0, QColor("#46556b"))
        gradient.setColorAt(1, QColor("#121722"))
        painter.fillRect(pixmap.rect(), gradient)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 17, QFont.Bold))
        painter.drawText(
            pixmap.rect().adjusted(16, 12, -16, -12),
            Qt.AlignCenter | Qt.TextWordWrap,
            title,
        )
        painter.end()
        return QIcon(pixmap)

    def _icon_for(self, game):
        path = self._art_path(game)
        if path:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                return QIcon(pixmap)
        return self._fallback_icon(game["title"])

    def refresh(self):
        if not hasattr(self, "list"):
            return

        games = self.db.all_games()
        if self.current_filter == "Избранное":
            games = [game for game in games if game["favorite"]]
        elif self.current_filter == "Недавно запускались":
            games = sorted(
                [game for game in games if game["last_played"]],
                key=lambda game: game["last_played"],
                reverse=True,
            )

        query = self.search.text().strip().lower()
        if query:
            games = [game for game in games if query in game["title"].lower()]

        selected_id = self.selected_game_id()
        self.list.blockSignals(True)
        self.list.clear()

        for game in games:
            item = QListWidgetItem(
                self._icon_for(game),
                f'{game["title"]}\n{fmt_time(game["play_seconds"])}',
            )
            item.setData(Qt.UserRole, game["id"])
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            item.setSizeHint(QSize(164, 150))
            self.list.addItem(item)
            if game["id"] == selected_id:
                self.list.setCurrentItem(item)

        if self.list.count() and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)

        self.list.blockSignals(False)
        self.count_label.setText(str(len(self.db.all_games())))
        self.show_details(self.list.currentItem())

    def show_details(self, current, previous=None):
        game = self.selected_game()
        if not game:
            self.hero_title.setText("ТВОЯ СЛЕДУЮЩАЯ ИГРА")
            self.hero_source.setText("GAME HUB")
            self.hero_desc.setText("Добавь игры или выбери одну из библиотеки.")
            self.favorite_btn.setText("☆  В избранное")
            self.favorite_btn.setEnabled(False)
            self.launch_btn.setEnabled(False)
            self._set_backdrop(None)
            return

        self.hero_title.setText(game["title"])
        self.hero_source.setText(str(game["source"]).upper())
        self.hero_desc.setText(
            f'{fmt_time(game["play_seconds"])} сыграно   ·   '
            f'{game["last_played"] or "Ещё не запускалась"}'
        )
        self.favorite_btn.setEnabled(True)
        self.launch_btn.setEnabled(True)
        self.favorite_btn.setText(
            "★  В избранном" if game["favorite"] else "☆  В избранное"
        )
        self._set_backdrop(self._hero_path(game))

    def _set_backdrop(self, path):
        if not path or not Path(path).is_file():
            self.backdrop.setPixmap(QPixmap())
            self.backdrop.setStyleSheet("""
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #53616d, stop:0.35 #303a45,
                    stop:0.72 #171b23, stop:1 #07080b);
            """)
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        self._backdrop_pixmap = pixmap
        scaled = pixmap.scaled(
            self.backdrop.size(), Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        self.backdrop.setPixmap(scaled)
        self.backdrop.setStyleSheet("background:#090a0e;")

    def set_filter(self, value):
        self.current_filter = value
        self.refresh()

    def scan_library(self):
        if self.scan_worker is not None:
            return
        self.status.setText("Сканирую Steam, Epic Games и ярлыки Windows…")
        self.scan_worker = ScanWorker()
        self.scan_worker.signals.finished.connect(self._scan_done)
        self.scan_worker.signals.failed.connect(self._scan_failed)
        self.pool.start(self.scan_worker)

    def _scan_done(self, found):
        for game in found:
            self.db.add_game(
                game["title"], game["target"], game["kind"],
                game["process_name"], game["source"]
            )
        self.scan_worker = None
        self.status.setText(
            f"Сканирование завершено · найдено записей: {len(found)}"
        )
        self.refresh()

    def _scan_failed(self, message):
        self.scan_worker = None
        self.status.setText("Ошибка сканирования")
        QMessageBox.warning(self, "Ошибка сканирования", message)

    def add_game(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери игру или ярлык", "",
            "Игры и ярлыки (*.exe *.lnk);;Все файлы (*.*)"
        )
        if not path:
            return
        file_path = Path(path)
        self.db.add_game(
            file_path.stem, str(file_path),
            "shortcut" if file_path.suffix.lower() == ".lnk" else "exe",
            file_path.name if file_path.suffix.lower() == ".exe" else "",
            "Добавлена вручную",
        )
        self.refresh()
        self.status.setText(f"Добавлена игра: {file_path.stem}")

    def choose_artwork(self):
        game = self.selected_game()
        if not game:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери обложку или фоновое изображение", "",
            "Изображения (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not path:
            return
        self.db.set_artwork(game["id"], path)
        self.refresh()
        self.status.setText("Изображение игры обновлено")

    def launch_selected(self):
        game = self.selected_game()
        if not game:
            self.status.setText("Сначала выбери игру.")
            return

        try:
            kind = game["launch_kind"]
            target = game["launch_target"]
            if kind in ("steam", "uri") or target.startswith(
                ("steam://", "com.epicgames.launcher://")
            ):
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl(target))
                process = None
            elif kind == "shortcut" or target.lower().endswith(".lnk"):
                os.startfile(target)
                process = None
            else:
                process = subprocess.Popen(
                    [target], cwd=str(Path(target).parent)
                )

            self.tracker.start(
                game["id"], process,
                game["process_name"] or Path(target).name
            )
            self.status.setText(
                f'Запущена игра: {game["title"]} · учёт времени активна'
            )
        except Exception as exc:
            QMessageBox.critical(self, "Не удалось запустить игру", str(exc))

    def on_tick(self, game_id, elapsed):
        game = self.selected_game()
        if game and game["id"] == game_id:
            self.hero_desc.setText(
                f"Идёт игровая сессия · {fmt_time(elapsed)}"
            )
        self.status.setText(f"Игровая сессия: {fmt_time(elapsed)}")

    def on_finished(self, game_id, elapsed):
        if elapsed:
            self.db.add_playtime(game_id, elapsed)
            self.refresh()
            self.status.setText(
                f"Сессия завершена · добавлено {fmt_time(elapsed)}"
            )

    def toggle_favorite(self):
        game = self.selected_game()
        if game:
            self.db.toggle_favorite(game["id"])
            self.refresh()

    def remove_selected(self):
        game = self.selected_game()
        if game and QMessageBox.question(
            self, "Убрать игру",
            f'Убрать «{game["title"]}» из библиотеки? Файлы игры не будут удалены.'
        ) == QMessageBox.Yes:
            self.db.remove_game(game["id"])
            self.refresh()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event):
        self.tracker.stop()
        self.db.close()
        event.accept()
