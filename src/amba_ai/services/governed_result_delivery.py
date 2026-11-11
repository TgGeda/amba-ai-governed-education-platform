from __future__ import annotations
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Mapping
from amba_ai.governance.runtime.output_guardrails import OutputDisposition, digest_material
from amba_ai.services.result_sinks import DEFAULT_SINKS, GovernedDeliveryError, SinkDeliveryReceipt

@dataclass(frozen=True, slots=True)
class GovernedResultEnvelope:
    output_id: str
    operation_id: str
    document_id: int | None
    sanitized_material: Mapping[str, Any]
    sanitized_sha256: str
    disposition: OutputDisposition
    trace_id: str
    audit_receipt: str
    def __post_init__(self):
        object.__setattr__(self,"sanitized_material",MappingProxyType(dict(self.sanitized_material)))
        if digest_material(self.sanitized_material)!=self.sanitized_sha256:
            raise GovernedDeliveryError("Envelope sanitized material digest mismatch.")
    def to_dict(self)->dict[str,Any]:
        return {"output_id":self.output_id,"operation_id":self.operation_id,"document_id":self.document_id,"sanitized_material":dict(self.sanitized_material),"sanitized_sha256":self.sanitized_sha256,"disposition":self.disposition.value,"trace_id":self.trace_id,"audit_receipt":self.audit_receipt}

class GovernedResultDeliveryService:
    def __init__(self,sinks:Mapping[str,Any]|None=None)->None:self.sinks=dict(sinks or DEFAULT_SINKS)
    def verify(self,envelope:GovernedResultEnvelope)->None:
        if not isinstance(envelope,GovernedResultEnvelope):raise TypeError("Sinks accept GovernedResultEnvelope only.")
        if digest_material(envelope.sanitized_material)!=envelope.sanitized_sha256:raise GovernedDeliveryError("Envelope digest verification failed.")
    def envelope_from_validation(self,validation:Any,*,operation_id:str)->GovernedResultEnvelope:
        return GovernedResultEnvelope(str(validation.output_id),str(operation_id),int(validation.document_id) if validation.document_id is not None else None,dict(validation.sanitized_material),str(validation.sanitized_output_sha256),getattr(validation, "decision", getattr(validation, "disposition", None)),str(validation.trace_id),str(validation.audit_receipt))
    def envelope_from_dict(self,data:Mapping[str,Any])->GovernedResultEnvelope:
        return GovernedResultEnvelope(str(data["output_id"]),str(data["operation_id"]),int(data["document_id"]) if data.get("document_id") is not None else None,dict(data["sanitized_material"]),str(data["sanitized_sha256"]),OutputDisposition(str(data["disposition"])),str(data["trace_id"]),str(data["audit_receipt"]))
    def envelope_from_result(self,result:Any)->GovernedResultEnvelope:
        meta=dict(getattr(result,"metadata",{}) or {}); data=meta.get("governed_result_envelope")
        if not isinstance(data,Mapping):raise GovernedDeliveryError("Result does not contain a governed delivery envelope.")
        return self.envelope_from_dict(data)
    def deliver(self,envelope:GovernedResultEnvelope,sink_name:str,**context:Any)->SinkDeliveryReceipt:
        self.verify(envelope)
        try:sink=self.sinks[sink_name]
        except KeyError as e:raise GovernedDeliveryError(f"Unknown governed result sink: {sink_name}") from e
        return sink.deliver(envelope,**context)
