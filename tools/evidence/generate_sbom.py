from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[2]

def parse_requirements(path:Path):
 components=[]
 for raw in path.read_text(encoding='utf-8').splitlines():
  line=raw.strip()
  if not line or line.startswith('#') or line.startswith(('-r','--')):continue
  marker=line.split(';',1)[0].strip();m=re.match(r'^([A-Za-z0-9_.-]+)(.*)$',marker)
  if not m:continue
  name=m.group(1);constraint=m.group(2).strip();version=None
  exact=re.match(r'^==\s*([^,\s]+)$',constraint)
  if exact:version=exact.group(1)
  normalized=name.lower().replace('_','-')
  component={'type':'library','name':name,'bom-ref':f'pkg:pypi/{normalized}@{version}' if version else f'pkg:pypi/{normalized}','purl':f'pkg:pypi/{normalized}@{version}' if version else f'pkg:pypi/{normalized}','properties':[{'name':'amba-gov:requirement','value':line}]}
  if version:component['version']=version
  components.append(component)
 return sorted(components,key=lambda x:(x['name'].lower(),x.get('version','')))
def main():
 source=ROOT/'requirements.txt';source_hash=sha256(source.read_bytes()).hexdigest();payload={'bomFormat':'CycloneDX','specVersion':'1.5','serialNumber':'urn:uuid:00000000-0000-5000-8000-000000000001','version':1,'metadata':{'component':{'type':'application','name':'AMBA-GOV','version':'evidence-closure'},'properties':[{'name':'amba-gov:dependency-source','value':'requirements.txt'},{'name':'amba-gov:dependency-source-sha256','value':source_hash},{'name':'amba-gov:generation-mode','value':'deterministic-static-requirements-parse'}]},'components':parse_requirements(source)}
 out=ROOT/'submission/artifacts/sbom.cdx.json';out.parent.mkdir(parents=True,exist_ok=True);text=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n';out.write_text(text,encoding='utf-8',newline='\n');print(f'component_count={len(payload["components"])}');print(f'sha256={sha256(text.encode()).hexdigest()}')
if __name__=='__main__':main()
