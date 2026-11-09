from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_widgets_do_not_write_authoritative_artifacts_directly():
 files=[ROOT/'src/amba_ai/ui/features/governance/governance_widget.py',ROOT/'src/amba_ai/ui/features/readiness/readiness_widget.py']
 for path in files:
  text=path.read_text(encoding='utf-8');assert '.write_text(' not in text;assert '.write_bytes(' not in text;assert 'open(' not in text;assert 'subprocess.run' not in text
def test_long_running_operations_use_qprocess():
 g=(ROOT/'src/amba_ai/ui/features/governance/governance_manager.py').read_text(encoding='utf-8');r=(ROOT/'src/amba_ai/ui/features/readiness/readiness_manager.py').read_text(encoding='utf-8');assert 'QProcess' in g and 'QProcess' in r;assert 'subprocess' not in g and 'subprocess' not in r
