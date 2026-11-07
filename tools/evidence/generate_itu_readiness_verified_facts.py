from __future__ import annotations

import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from amba_ai.readiness.verified_framework import verified_itu_ai_readiness_framework

CATALOG_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "readiness_reference_minimal"
    / "simulation"
    / "data"
    / "framework"
    / "dimensions.json"
)
OUTPUT_PATH = REPOSITORY_ROOT / "kb" / "records" / "itu_ai_readiness_2_verified_facts.json"


def main() -> int:
    framework = verified_itu_ai_readiness_framework(
        CATALOG_PATH,
        repository_root=REPOSITORY_ROOT,
    )
    payload = framework.to_dict()
    payload["source_artifact"] = {
        "path": "kb/sources/international/ITU_AI_READINESS_REPORT.pdf",
        "sha256": "71191768d46b60778c15f8d62b162aff73a319785cfc31ebf76bb944b0c68273",
        "artifact_integrity_status": "verified",
    }
    payload["claim_boundaries"] = {
        "national_readiness_claimed": False,
        "itu_certification_claimed": False,
        "runtime_authorization_from_readiness": False,
        "official_methodology_reconciled": False,
        "reference_code_independently_establishes_methodology": False,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(OUTPUT_PATH)
    print(f"output={OUTPUT_PATH.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"factor_count={len(framework.factors)}")
    print(f"dimension_count={len(framework.dimensions)}")
    print(f"metric_count={len(framework.metric_catalog.metrics)}")
    print("overall_project_score=null")
    print(f"score_status={framework.score_status.value}")
    print("national_assessment=false")
    print("official_itu_certification=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
