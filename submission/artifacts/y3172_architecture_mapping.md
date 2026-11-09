# AMBA-GOV ITU-T Y.3172 Architecture Mapping

> Interpreted project-architecture mapping; not formal ITU-T Y.3172 conformance testing or ITU certification.

Source artifact SHA-256: `469792ed9f9fd574d51c67b5d7298c6755bbe959772b16978ac69c10fe758c06`

## Y3172-MAP-001 · Scenario event input

**Y.3172 interpretation:** ML pipeline input and orchestration trigger

Supplies deterministic event and stage context to the governance pipeline.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS
- Approved passages: Y3172-8.1-PIPELINE
- Implementation: src/amba_ai/scenarios/models.py, src/amba_ai/scenarios/runner.py
- Runtime evidence: /stages/*/stage_id, /stages/*/released_fact_ids
- Limitations: Project interpretation only; no formal interface conformance test performed.

## Y3172-MAP-002 · Evidence release

**Y.3172 interpretation:** Controlled data acquisition and release function

Releases only stage-eligible facts into recipient-specific processing.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS
- Approved passages: Y3172-8.1-PIPELINE
- Implementation: src/amba_ai/scenarios/evidence_release.py, src/amba_ai/scenarios/runner.py
- Runtime evidence: /stages/*/released_fact_ids
- Limitations: Evidence release is governance-specific and not an ITU-defined API.

## Y3172-MAP-003 · Institutional projection

**Y.3172 interpretation:** Context shaping and preprocessing function

Shapes released facts into mandate-bounded recipient views.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS
- Approved passages: Y3172-8.1-PIPELINE
- Implementation: src/amba_ai/institutional/context_projection.py
- Runtime evidence: /stages/*/recipient_projections
- Limitations: Projection semantics are AMBA-GOV domain controls.

## Y3172-MAP-004 · Institutional assessment agents

**Y.3172 interpretation:** Domain-specific analysis functions within an ML pipeline

Produce independent mandate-bounded observations without decision or execution authority.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS
- Approved passages: Y3172-8.1-PIPELINE
- Implementation: src/amba_ai/institutional/assessors/base.py, src/amba_ai/institutional/assessors/consumer_protection_assessor.py, src/amba_ai/institutional/assessors/data_protection_assessor.py, src/amba_ai/institutional/assessors/education_assessor.py, src/amba_ai/institutional/registry.py
- Runtime evidence: /stages/*/institutional_observations
- Limitations: Assessors are deterministic governance components; not trained ML models.

## Y3172-MAP-005 · Coordination service

**Y.3172 interpretation:** Cross-component coordination and pipeline control

Coordinates assessments while preserving material conflicts and unresolved questions.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS
- Approved passages: Y3172-8.1-PIPELINE
- Implementation: src/amba_ai/institutional/coordination.py
- Runtime evidence: /stages/*/preserved_conflicts
- Limitations: Conflict preservation is an AMBA-GOV governance extension.

## Y3172-MAP-006 · Verified policy evidence service

**Y.3172 interpretation:** Policy and knowledge support function

Resolves approved passages, thematic views, evidence gaps, and limitations.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS
- Approved passages: Y3172-8.1-PIPELINE
- Implementation: src/amba_ai/services/policy_kb_service.py, src/amba_ai/governance/thematic_evidence.py, src/amba_ai/services/thematic_evidence_service.py, src/amba_ai/governance/verified_stme_context_evidence.py
- Runtime evidence: /stages/*/policy_agent_results/*/verified_evidence, /stages/*/policy_agent_results/*/evidence_gaps
- Limitations: Semantic relevance does not establish legal applicability or binding authority.

## Y3172-MAP-007 · Policy governance agent

**Y.3172 interpretation:** Policy control and orchestration function

Produces deterministic recommendations from facts, assessments, approved evidence, operations, and destinations.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS, ITU-Y3172-SECURITY-CONSIDERATIONS
- Approved passages: Y3172-8.1-PIPELINE, Y3172-9-SECURITY
- Implementation: src/amba_ai/services/policy_agent_service.py, src/amba_ai/governance/evaluators.py
- Runtime evidence: /stages/*/policy_agent_results/*/deterministic_governance/recommendation
- Limitations: Recommendation is not permission to execute and has no independent legal effect.

## Y3172-MAP-008 · Human approval gate

**Y.3172 interpretation:** Human governance intervention in pipeline control

Prevents approval-sensitive operations from executing without a recorded decision.

- Verified records: ITU-Y3172-SECURITY-CONSIDERATIONS
- Approved passages: Y3172-9-SECURITY
- Implementation: src/amba_ai/governance/approvals.py, src/amba_ai/services/execution_service.py
- Runtime evidence: /stages/*/policy_agent_results/*/deterministic_governance/approval_state
- Limitations: Approval policy and roles are project governance controls.

## Y3172-MAP-009 · Execution service

**Y.3172 interpretation:** Action execution function

Executes only registered, authorized, idempotent operations or returns a review receipt.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS, ITU-Y3172-SECURITY-CONSIDERATIONS
- Approved passages: Y3172-8.1-PIPELINE, Y3172-9-SECURITY
- Implementation: src/amba_ai/services/execution_service.py, src/amba_ai/governance/execution.py
- Runtime evidence: /stages/*/policy_agent_results/*/deterministic_governance/execution_state
- Limitations: Demonstration operations are synthetic and legally non-effective.

## Y3172-MAP-010 · Distribution service

**Y.3172 interpretation:** Pipeline output and delivery-control function

Controls delivery to registered destinations and records prevented distribution.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS, ITU-Y3172-SECURITY-CONSIDERATIONS
- Approved passages: Y3172-8.1-PIPELINE, Y3172-9-SECURITY
- Implementation: src/amba_ai/services/distribution_service.py, src/amba_ai/governance/distribution.py
- Runtime evidence: /stages/*/policy_agent_results/*/deterministic_governance/distribution_effect
- Limitations: No production external destination is contacted by the synthetic demonstration.

## Y3172-MAP-011 · Y.3172 trace coordinator

**Y.3172 interpretation:** ML pipeline trace representation

Records pipeline nodes, component relationships, trace identity, and digest.

- Verified records: ITU-Y3172-ML-PIPELINE-COMPONENTS
- Approved passages: Y3172-8.1-PIPELINE
- Implementation: src/amba_ai/standards/y3172_trace_coordinator.py, src/amba_ai/standards/y3172_models.py
- Runtime evidence: /stages/*/policy_agent_results/*/y3172_trace
- Limitations: Trace presence is not formal conformance certification.

## Y3172-MAP-012 · Hash-linked audit service

**Y.3172 interpretation:** Security, accountability, and integrity support

Binds evidence, decisions, execution outcomes, and prior audit state through hashes.

- Verified records: ITU-Y3172-SECURITY-CONSIDERATIONS
- Approved passages: Y3172-9-SECURITY
- Implementation: src/amba_ai/services/audit_service.py, src/amba_ai/governance/audit.py
- Runtime evidence: /stages/*/policy_agent_results/*/audit, /final_audit_verification/valid
- Limitations: Application audit validity does not substitute for external certification or legal review.

## Y3172-MAP-013 · Synthetic demonstration environment

**Y.3172 interpretation:** ML sandbox environment

Runs deterministic, legally non-effective scenarios with isolated state and invariant checks.

- Verified records: ITU-Y3172-ML-SANDBOX-DEFINITION, ITU-Y3172-ARCHITECTURE-SANDBOX-COMPONENTS
- Approved passages: Y3172-3.2.6
- Implementation: src/amba_ai/scenarios/clock.py, src/amba_ai/cli/evidence_chain_demo.py
- Runtime evidence: /synthetic, /legal_effect, /stages/*/invariant_verification/valid
- Limitations: Synthetic sandbox results do not establish production readiness or national deployment fitness.
