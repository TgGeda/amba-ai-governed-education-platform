from __future__ import annotations
from hashlib import sha256
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
import json

from amba_ai.governance.models import to_canonical_json


def _dict(value: Any) -> dict[str, Any]:
    if value is None: return {}
    if isinstance(value, dict): return value
    method=getattr(value,'to_dict',None)
    if not callable(method): raise TypeError(f'{type(value).__name__} does not provide to_dict')
    result=method()
    if not isinstance(result,dict): raise TypeError('to_dict must return a dictionary')
    return result

def _enum(value: Any) -> Any: return getattr(value,'value',value)
def _approval_state(response: Any) -> str:
    request = response.execution_result.request
    if not response.governance_bundle.recommendation.requires_approval:
        return "not_required"
    if request.approval_decision_id is None:
        return "required_not_supplied"
    return "decision_recorded"


def _execution_state(result: Any) -> str:
    raw = _dict(result)
    execution_receipt = raw["execution_receipt"]
    review_receipt = raw["review_queue_receipt"]
    if execution_receipt is not None:
        return str(execution_receipt["status"])
    if review_receipt is not None:
        return "review_queued"
    raise ValueError("ExecutionResult contains neither execution nor review receipt")

def _assessment(item: Any) -> dict[str,Any]:
    raw=_dict(item)
    return {'assessment_id':raw['assessment_id'],'assessor_id':raw.get('institution_id'),'mandate_id':raw['mandate_id'],'assessed_fact_ids':raw['assessed_fact_ids'],'confidence_status':raw['confidence_status'],'observations':raw['observations'],'unresolved_questions':raw['unresolved_questions'],'assessment_digest':raw['assessment_digest']}
def _conflict(item: Any) -> dict[str,Any]:
    raw=_dict(item)
    return {'conflict_id':raw['conflict_id'],'assessment_ids':raw['assessment_ids'],'conflict_type':raw['kind'],'resolution_status':'unresolved' if raw['preserved'] and not raw['resolved'] else 'invalid','institution_ids':raw['institution_ids'],'fact_ids':raw['fact_ids']}
def _response(response:Any)->dict[str,Any]:
    ev=response.thematic_evidence_context.to_dict(); trace=_dict(response.y3172_trace); audit=_dict(response.audit_block)
    return {'verified_evidence':{'passage_ids':ev['verified_passage_ids']},'derived_thematic_interpretation':[{'theme_id':x['theme_id'],'theme':x['theme'],'evidence_status':x['evidence_status']} for x in ev['thematic_views']],'evidence_gaps':ev['evidence_gaps'],'deterministic_governance':{'recommendation':_enum(response.governance_bundle.recommendation.recommended_action),'approval_state':_approval_state(response),'execution_state':_execution_state(response.execution_result),'distribution_effect':None if response.distribution_effect is None else _dict(response.distribution_effect)},'y3172_trace':{'nodes':trace.get('nodes',[]),'trace_id':trace.get('trace_id'),'trace_digest':trace.get('trace_digest')},'audit':{'block_id':audit['audit_event']['audit_event_id'],'block_index':audit['block_index'],'payload_hash':audit['audit_event']['payload_hash'],'previous_hash':audit['audit_event']['previous_hash'],'block_hash':audit['audit_event']['block_hash']},'limitations':list(response.limitations)}

def build_evidence_chain_report(result:Any)->dict[str,Any]:
    if not result.final_audit_verification.valid: raise ValueError('final audit verification failed')
    stages=[]
    for stage in result.stages:
        if not stage.invariant_report.valid: raise ValueError(f'invariant verification failed: {stage.stage.value}')
        released=sorted({fact_id for envelope in stage.release_envelopes for fact_id in envelope.fact_ids})
        projections=[]
        for item in stage.projections:
            raw=_dict(item); projections.append({'recipient_id':raw.get('institution_id') or raw.get('recipient_id'),'fact_ids':raw.get('fact_ids',[]),'projection_digest':raw.get('projection_digest'),'projection_id':raw.get('projection_id')})
        responses=[_response(x) for x in stage.policy_agent_responses]
        assessment_ids=[a.assessment_id for a in stage.coordination.assessments]
        conflict_ids=[c.conflict_id for c in stage.coordination.conflicts]
        stages.append({'stage_id':stage.stage.name.replace('_','-'),'released_fact_ids':released,'recipient_projections':projections,'institutional_observations':[_assessment(x) for x in stage.coordination.assessments],'preserved_conflicts':[_conflict(x) for x in stage.coordination.conflicts],'thematic_evidence_references':{'assessment_ids':assessment_ids,'conflict_ids':conflict_ids,'passage_ids':sorted({p for r in responses for p in r['verified_evidence']['passage_ids']}),'theme_ids':sorted({t['theme_id'] for r in responses for t in r['derived_thematic_interpretation']}),'gap_ids':sorted({g['gap_id'] for r in responses for g in r['evidence_gaps']})},'policy_agent_results':responses,'invariant_verification':_dict(stage.invariant_report),'stage_digest':stage.stage_digest})
    return {'schema_version':'1.0.0','artifact_type':'four_stage_evidence_chain','run_id':result.run_id,'scenario_id':result.scenario_id,'synthetic':result.synthetic,'legal_effect':result.legal_effect,'validation':_dict(result.validation),'stages':stages,'final_audit_verification':_dict(result.final_audit_verification),'run_digest':result.run_digest}

def to_json_value(value: Any) -> Any:
    """Convert runtime values to deterministic JSON-compatible structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [to_json_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if is_dataclass(value):
        return to_json_value(asdict(value))
    method = getattr(value, "to_dict", None)
    if callable(method):
        return to_json_value(method())
    raise TypeError(f"Unsupported evidence-chain value: {type(value).__module__}.{type(value).__qualname__}")


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        to_json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def write_evidence_chain_report(
    payload: dict[str, Any],
    output: Path,
    pretty_output: Path | None = None,
) -> str:
    normalized = to_json_value(payload)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\n")
    if pretty_output is not None:
        pretty_output.parent.mkdir(parents=True, exist_ok=True)
        pretty_output.write_text(
            json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return sha256(text.encode("utf-8")).hexdigest()
