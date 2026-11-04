from __future__ import annotations

from dataclasses import dataclass
import hashlib

import pytest

from amba_ai.governance.distribution import DistributionDisposition, DistributionEffect
from amba_ai.governance.execution import (
    DistributionAcknowledgment,
    ExecutionReceipt,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ReviewQueueReceipt,
)
from amba_ai.governance.models import EnforcementAction, PipelineEvent
from amba_ai.services.distribution_service import DistributionService

NOW = "2026-11-04T12:00:00Z"

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

@dataclass
class Executor:
    disposition: DistributionDisposition
    calls: list | None = None
    def __post_init__(self): self.calls=[]
    def execute(self, destination_id, payload):
        self.calls.append((destination_id,payload))
        return DistributionEffect("EXEC", destination_id, self.disposition, self.disposition.value, {"synthetic":True})

def event(destination="DEST"):
    return PipelineEvent("EVT",NOW,"OP","SRC",destination,"test",{},None,True)

def request(action, destination="DEST"):
    return ExecutionRequest.create("REQ","EVT","OP",action,destination,digest("p"),digest("r"),None,"KEY",NOW)

def receipt(req, action, status=ExecutionStatus.SUCCEEDED):
    return ExecutionReceipt("RCPT",req.request_id,req.event_id,req.operation_id,action,status,"EXEC","effect",NOW,digest("x"),{},True,False)

def service():
    return DistributionService(permit_executor=Executor(DistributionDisposition.DELIVERED),block_executor=Executor(DistributionDisposition.PREVENTED),review_executor=Executor(DistributionDisposition.QUEUED_FOR_REVIEW))

def test_routes_delivery():
    req=request(EnforcementAction.PROCEED); rcpt=receipt(req,EnforcementAction.PROCEED)
    ack=DistributionAcknowledgment("ACK",rcpt.receipt_id,"DEST","DELIVERED",NOW,digest("a"))
    result=ExecutionResult(req,rcpt,None,ack,False)
    effect=service().distribute(event=event(),execution_result=result,payload={"x":1})
    assert effect.disposition is DistributionDisposition.DELIVERED

def test_routes_prevention():
    req=request(EnforcementAction.BLOCK); result=ExecutionResult(req,receipt(req,EnforcementAction.BLOCK),None,None,False)
    effect=service().distribute(event=event(),execution_result=result,payload={})
    assert effect.disposition is DistributionDisposition.PREVENTED

def test_routes_review_to_queue():
    req=request(EnforcementAction.HOLD_FOR_REVIEW)
    review=ReviewQueueReceipt("Q",req.request_id,req.event_id,"QUEUE",NOW,digest("q"),"HOLD",{})
    result=ExecutionResult(req,None,review,None,False)
    effect=service().distribute(event=event(),execution_result=result,payload={})
    assert effect.destination_id == "QUEUE"
    assert effect.disposition is DistributionDisposition.QUEUED_FOR_REVIEW

def test_not_attempted_has_no_distribution():
    req=request(EnforcementAction.MODIFY)
    result=ExecutionResult(req,receipt(req,EnforcementAction.MODIFY,ExecutionStatus.NOT_ATTEMPTED),None,None,False)
    assert service().distribute(event=event(),execution_result=result,payload={}) is None

def test_event_identity_mismatch_fails_closed():
    req=request(EnforcementAction.BLOCK)
    result=ExecutionResult(req,receipt(req,EnforcementAction.BLOCK),None,None,False)
    with pytest.raises(Exception,match="event identifier"):
        service().distribute(event=PipelineEvent("OTHER",NOW,"OP","SRC","DEST","test",{},None,True),execution_result=result,payload={})


def test_proceed_without_acknowledgment_fails_closed():
    req = request(
        EnforcementAction.PROCEED
    )
    rcpt = receipt(
        req,
        EnforcementAction.PROCEED,
    )
    acknowledgment = DistributionAcknowledgment(
        "ACK",
        rcpt.receipt_id,
        "DEST",
        "DELIVERED",
        NOW,
        digest("a"),
    )
    result = ExecutionResult(
        req,
        rcpt,
        None,
        acknowledgment,
        False,
    )

    object.__setattr__(
        result,
        "distribution_acknowledgment",
        None,
    )

    with pytest.raises(
        Exception,
        match="acknowledgment",
    ):
        service().distribute(
            event=event(),
            execution_result=result,
            payload={},
        )


def test_prevention_with_acknowledgment_fails_closed():
    req=request(EnforcementAction.BLOCK); rcpt=receipt(req,EnforcementAction.BLOCK)
    with pytest.raises(ValueError):
        ExecutionResult(req,rcpt,None,DistributionAcknowledgment("ACK",rcpt.receipt_id,"DEST","DELIVERED",NOW,digest("a")),False)


def test_payload_must_be_mapping():
    req=request(EnforcementAction.BLOCK)
    result=ExecutionResult(req,receipt(req,EnforcementAction.BLOCK),None,None,False)
    with pytest.raises(TypeError,match="payload"):
        service().distribute(event=event(),execution_result=result,payload=[])
