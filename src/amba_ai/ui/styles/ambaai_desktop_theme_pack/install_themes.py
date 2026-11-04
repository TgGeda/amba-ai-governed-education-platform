from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
styles = ROOT / "src" / "amba_ai" / "ui" / "styles"
styles.mkdir(parents=True, exist_ok=True)
source = Path(__file__).parent

for file in source.glob("*.qss"):
    target = styles / file.name
    target.write_text(file.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Installed {target}")

print("Done. Open AmbaAI -> View -> Themes and select one of the new themes.")
