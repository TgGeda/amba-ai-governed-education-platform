from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from typing import Any
import hmac,json
class ManifestVerificationError(ValueError):pass

def verify_manifest(root:Path,manifest_path:Path)->dict[str,Any]:
    payload=json.loads(manifest_path.read_text(encoding='utf-8'));failures=[]
    seen=set()
    for entry in payload['entries']:
        rel=entry['path']
        if rel in seen:failures.append(f"duplicate entry:{rel}");continue
        seen.add(rel);path=root/rel
        if not path.is_file():failures.append(f"missing:{rel}");continue
        digest=sha256(path.read_bytes()).hexdigest()
        if not hmac.compare_digest(digest,entry['sha256']):failures.append(f"hash_mismatch:{rel}")
        if path.stat().st_size!=entry['size_bytes']:failures.append(f"size_mismatch:{rel}")
    boundaries=payload['claim_boundaries']
    for key in ('national_ai_readiness_score','official_itu_score','official_itu_certification','formal_y3172_conformance','legal_effect','binding_finding_eligible'):
        if boundaries.get(key) is not False:failures.append(f"unsafe_claim_boundary:{key}")
    return {'valid':not failures,'entry_count':len(payload['entries']),'failures':failures,'manifest_sha256':sha256(manifest_path.read_bytes()).hexdigest()}
