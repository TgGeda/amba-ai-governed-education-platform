from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtWidgets import QApplication
from amba_ai.ui.main_window import MainWindow
from amba_ai.ui.features.governance.main_window_integration import install_submission_workspaces
def main():
 app=QApplication.instance() or QApplication(sys.argv);window=MainWindow();install_submission_workspaces(window,ROOT);window.show();return app.exec()
if __name__=='__main__':raise SystemExit(main())
