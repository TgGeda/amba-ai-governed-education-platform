from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_evidence_chain_launchers_use_literal_repository_src_path() -> None:
    launchers = {
        ROOT / "run_evidence_chain_demo.bat": 'cd /d "%~dp0" || exit /b 1',
        ROOT / "scripts" / "run_evidence_chain_demo.cmd": 'cd /d "%~dp0.." || exit /b 1',
    }
    for path, expected_cd in launchers.items():
        content = path.read_text(encoding="ascii")
        assert expected_cd in content
        assert 'set "PYTHONPATH=%CD%\\src;%PYTHONPATH%"' in content
        assert '-m amba_ai.cli.evidence_chain_demo %*' in content
        assert 'exit /b %ERRORLEVEL%' in content
        assert "\x07" not in content
        assert "F:\\AmbaAI" not in content


def test_launchers_do_not_embed_workstation_specific_absolute_paths() -> None:
    for path in (
        ROOT / "run_evidence_chain_demo.bat",
        ROOT / "scripts" / "run_evidence_chain_demo.cmd",
    ):
        content = path.read_text(encoding="ascii")
        assert "F:" not in content
        assert "C:\\Users" not in content
