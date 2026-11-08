from __future__ import annotations
from typing import Any

def present_evidence_chain(response: Any) -> dict[str, Any]:
    evidence=response.thematic_evidence_context.to_dict()
    return {'verified_evidence':evidence['verified_passage_ids'],'derived_thematic_interpretation':[{'theme_id':v['theme_id'],'theme':v['theme'],'evidence_status':v['evidence_status']} for v in evidence['thematic_views']],'unresolved_evidence_gaps':evidence['evidence_gaps'],'deterministic_governance_result':{'recommended_action':response.governance_bundle.recommendation.recommended_action.value,'execution_state':response.execution_result.state.value,'distribution_effect':None if response.distribution_effect is None else response.distribution_effect.to_dict(),'y3172_trace':response.y3172_trace.to_dict(),'audit_block':response.audit_block.to_dict()},'limitations':list(response.limitations)}
