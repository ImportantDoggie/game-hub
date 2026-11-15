from dataclasses import dataclass

@dataclass
class Game:
    id: int
    title: str
    launch_target: str
    launch_kind: str = "exe"  # exe | steam | shortcut | uri
    process_name: str = ""
    source: str = "Manual"
    play_seconds: int = 0
    last_played: str = ""
    favorite: bool = False
