from pathlib import Path
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def test_artifacts_generate_deterministically():
 commands=([sys.executable,str(ROOT/'tools/standards/generate_y3172_mapping.py')],[sys.executable,str(ROOT/'tools/submission/generate_agent_architecture.py')])
 for command in commands:subprocess.run(command,check=True,cwd=ROOT)
 paths=[ROOT/'submission/artifacts/y3172_architecture_mapping.json',ROOT/'submission/artifacts/agent_architecture.json'];first=[p.read_bytes() for p in paths]
 for command in commands:subprocess.run(command,check=True,cwd=ROOT)
 assert first==[p.read_bytes() for p in paths]
 y=json.loads(paths[0].read_text(encoding='utf-8'));a=json.loads(paths[1].read_text(encoding='utf-8'));assert y['entry_count']==13;assert y['formal_conformance'] is False;assert y['itu_certification'] is False;assert a['agent_count']==8;assert a['claim_boundaries']['assessment_agents_can_execute'] is False
