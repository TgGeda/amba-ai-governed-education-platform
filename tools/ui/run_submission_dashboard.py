from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtWidgets import QApplication
from amba_ai.ui.features.governance.submission_dashboard import SubmissionDashboard
def main():
 app=QApplication.instance() or QApplication(sys.argv);app.setApplicationName('AMBA-GOV Submission Dashboard');window=SubmissionDashboard(ROOT);window.show();return app.exec()
if __name__=='__main__':raise SystemExit(main())
