from __future__ import annotations
import hashlib, json, unicodedata
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
CATALOG=ROOT/"kb/passages/verified_passage_catalog.json"

def canonicalize(text: str) -> str:
    text=unicodedata.normalize("NFC",text.replace("\r\n","\n").replace("\r","\n"))
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()

def main() -> int:
    payload=json.loads(CATALOG.read_text(encoding="utf-8"))
    failures=[]
    for p in payload["passages"]:
        actual=hashlib.sha256(canonicalize(p["exact_source_excerpt"]).encode("utf-8")).hexdigest()
        if actual != p["exact_source_excerpt_sha256"]:
            failures.append(p["passage_id"])
    if failures:
        print("hash_failures="+",".join(failures),file=sys.stderr); return 1
    print(f"passage_hashes_verified={len(payload['passages'])}")
    return 0
if __name__=="__main__": raise SystemExit(main())
