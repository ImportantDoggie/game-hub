import sqlite3
from pathlib import Path
from datetime import datetime

APP_DIR = Path.home() / "AppData" / "Local" / "GameHub"
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR / "library.db"


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                launch_target TEXT NOT NULL UNIQUE,
                launch_kind TEXT NOT NULL DEFAULT 'exe',
                process_name TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'Manual',
                play_seconds INTEGER NOT NULL DEFAULT 0,
                last_played TEXT NOT NULL DEFAULT '',
                favorite INTEGER NOT NULL DEFAULT 0,
                artwork_path TEXT NOT NULL DEFAULT ''
            )
        """)
        # Safe migration for existing installations created by older GAME HUB builds.
        columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(games)")
        }
        if "artwork_path" not in columns:
            self.conn.execute(
                "ALTER TABLE games ADD COLUMN artwork_path TEXT NOT NULL DEFAULT ''"
            )
        self.conn.commit()

    def all_games(self):
        rows = self.conn.execute(
            "SELECT * FROM games ORDER BY favorite DESC, title COLLATE NOCASE"
        ).fetchall()
        return [dict(row) for row in rows]

    def add_game(self, title, target, kind="exe", process_name="", source="Manual"):
        self.conn.execute("""
            INSERT OR IGNORE INTO games
                (title, launch_target, launch_kind, process_name, source)
            VALUES (?, ?, ?, ?, ?)
        """, (title, target, kind, process_name, source))
        self.conn.commit()

    def add_playtime(self, game_id, seconds):
        self.conn.execute("""
            UPDATE games
            SET play_seconds=play_seconds+?, last_played=?
            WHERE id=?
        """, (int(seconds), datetime.now().isoformat(timespec="seconds"), game_id))
        self.conn.commit()

    def set_artwork(self, game_id, path):
        self.conn.execute(
            "UPDATE games SET artwork_path=? WHERE id=?",
            (str(path), game_id)
        )
        self.conn.commit()

    def toggle_favorite(self, game_id):
        self.conn.execute("""
            UPDATE games
            SET favorite=CASE favorite WHEN 1 THEN 0 ELSE 1 END
            WHERE id=?
        """, (game_id,))
        self.conn.commit()

    def remove_game(self, game_id):
        self.conn.execute("DELETE FROM games WHERE id=?", (game_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
