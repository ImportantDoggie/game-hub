# GAME HUB

A Windows 10/11 desktop game library launcher built with Python + PySide6.

## Features in this starter build
- Scans Steam libraries (Steam app manifests), Epic Games manifests, and Windows Start Menu/Desktop shortcuts.
- Add games manually by selecting an `.exe` or shortcut.
- Launch games from the library.
- Tracks elapsed time while a launched game process is running.
- Stores the library and playtime in a local SQLite database.
- Search, favorites, recently played, fullscreen mode, keyboard navigation.

## Run from source
1. Install Python 3.10+ on Windows.
2. Open a terminal in this folder.
3. Run `python -m venv .venv`
4. Activate it: `.venv\\Scripts\\activate`
5. Run `pip install -r requirements.txt`
6. Run `python main.py`

## Build a Windows executable
Run `build.bat` from a Windows machine. The output will be in `dist\\GAME-HUB.exe`.

## Notes
- No launcher can reliably discover every game installed on every PC. This build scans common Steam/Epic/Windows shortcut locations and supports manual additions.
- Steam games are launched through their `steam://rungameid/APPID` URI when an app ID is known.
- Epic games are launched via their installed executable when the manifest provides it.
- Shortcut resolution uses Windows PowerShell/COM when available.
- Playtime is tracked for the process launched by GAME HUB and its child processes. Some games that delegate to another launcher may need a future platform-specific integration.
- Game metadata/artwork is intentionally local-first in this starter build; online cover-art lookup can be added in a later version.


## Build automatically on GitHub (no Python needed on your PC)
1. Create a new GitHub repository (for example `game-hub`).
2. Upload the contents of this project folder to the repository (including the hidden `.github` folder).
3. Open the repository's **Actions** tab.
4. Select **Build GAME HUB for Windows** and click **Run workflow**.
5. When the run completes, open it and download the `GAME-HUB-Windows` artifact.
6. Extract it; it contains `GAME-HUB.exe`.

The workflow builds on a GitHub-hosted Windows runner. Python is installed only on that temporary build machine, not on your PC.
