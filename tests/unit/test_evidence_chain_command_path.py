from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_evidence_chain_launchers_set_src_pythonpath() -> None:
    paths = (
        ROOT / "run_evidence_chain_demo.bat",
        ROOT / "scripts" / "run_evidence_chain_demo.cmd",
    )
    for path in paths:
        content = path.read_text(encoding="ascii")
        assert 'set "PYTHONPATH=%CD%\\src;%PYTHONPATH%"' in content
        assert '-m amba_ai.cli.evidence_chain_demo' in content
