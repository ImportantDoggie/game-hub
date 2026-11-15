import time
import psutil
from PySide6.QtCore import QObject, QTimer, Signal


class PlaytimeTracker(QObject):
    tick = Signal(int, int)
    finished = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.active = None
        self.elapsed = 0
        self.last_count = time.monotonic()
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._poll)

    def start(self, game_id, process, process_name=""):
        self.stop()
        self.active = {
            "id": game_id,
            "pid": getattr(process, "pid", None),
            "name": (process_name or "").lower(),
            "started": time.monotonic(),
        }
        self.elapsed = 0
        self.last_count = time.monotonic()
        self.timer.start()

    def _matching_process_alive(self):
        if not self.active:
            return False

        pid = self.active["pid"]
        name = self.active["name"]

        try:
            if pid:
                root = psutil.Process(pid)
                if root.is_running():
                    return True
                # The launched process may spawn the actual game and exit.
                try:
                    children = root.children(recursive=True)
                    if any(child.is_running() for child in children):
                        return True
                except (psutil.Error, PermissionError):
                    pass

            if name:
                wanted = name.casefold()
                for proc in psutil.process_iter(["name", "exe"]):
                    try:
                        proc_name = (proc.info.get("name") or "").casefold()
                        proc_exe = (proc.info.get("exe") or "").casefold()
                        if proc_name == wanted or (
                            proc_exe and proc_exe.endswith("\\" + wanted)
                        ):
                            return True
                    except (psutil.Error, PermissionError):
                        continue
        except (psutil.Error, PermissionError):
            return False

        # URI/shortcut launchers may not expose a PID. In that case process-name
        # matching is the only safe local fallback.
        return False

    def _poll(self):
        if not self.active:
            return

        now = time.monotonic()
        delta = max(0, min(2, int(now - self.last_count)))
        self.last_count = now

        if self._matching_process_alive():
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
