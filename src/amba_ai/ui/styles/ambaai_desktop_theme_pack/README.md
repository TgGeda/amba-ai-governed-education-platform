# AmbaAI 4-App Inspired Desktop Theme Pack

Included QSS themes:

1. `vscode_dark_plus.qss` — inspired by VS Code Dark+
2. `jetbrains_darcula.qss` — inspired by JetBrains Darcula
3. `office_fluent.qss` — inspired by Microsoft Office / Fluent UI
4. `slack_aubergine.qss` — inspired by Slack Aubergine

These are AmbaAI-adapted themes, not exact copies.

Install from the project root:

```bat
cd /d F:\AmbaAI\amba_ai_project
call .venv\Scripts\activate
set PYTHONPATH=src
python ambaai_desktop_theme_pack\install_themes.py
python -m compileall src
python -m amba_ai.main
```

Then select: View -> Themes.
