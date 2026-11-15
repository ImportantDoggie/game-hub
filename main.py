import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from gamehub.ui import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GAME HUB")
    app.setOrganizationName("GAME HUB")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
