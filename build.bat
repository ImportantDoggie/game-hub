@echo off
setlocal
py -m pip install --upgrade pip
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --clean --windowed --name GAME-HUB --collect-all PySide6 main.py
echo.
echo Build finished. Look in dist\GAME-HUB\
pause
