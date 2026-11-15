import time
import psutil
from PySide6.QtCore import QObject, QTimer, Signal

class PlaytimeTracker(QObject):
    tick = Signal(int, int)  # game_id, accumulated seconds this session
    finished = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.active = None
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._poll)
        self.elapsed = 0
        self.last_count = time.monotonic()

    def start(self, game_id, process, process_name=""):
        self.stop()
        self.active = {"id": game_id, "pid": getattr(process, "pid", None), "name": process_name.lower()}
        self.elapsed = 0
        self.last_count = time.monotonic()
        self.timer.start()

    def _poll(self):
        if not self.active:
            return
        now = time.monotonic()
        delta = max(0, int(now - self.last_count))
        self.last_count = now
        alive = False
        pid = self.active["pid"]
        name = self.active["name"]
        try:
            if pid and psutil.pid_exists(pid):
                root = psutil.Process(pid)
                alive = root.is_running()
                if not alive:
                    alive = any(p.info.get("name", "").lower() == name
                                for p in psutil.process_iter(["name"]))
            elif name:
                alive = any(p.info.get("name", "").lower() == name
                            for p in psutil.process_iter(["name"]))
        except (psutil.Error, PermissionError):
            alive = bool(name) and any(
                p.info.get("name", "").lower() == name
                for p in psutil.process_iter(["name"])
            )
        if alive:
            self.elapsed += delta
            self.tick.emit(self.active["id"], self.elapsed)
        else:
            self.stop()

    def stop(self):
        if self.timer.isActive():
            self.timer.stop()
        if self.active:
            self.finished.emit(self.active["id"], self.elapsed)
        self.active = None
        self.elapsed = 0
