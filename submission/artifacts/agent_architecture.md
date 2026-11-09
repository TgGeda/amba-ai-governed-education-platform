# AMBA-GOV Agent Architecture

> Bounded multi-agent governance architecture. Assessment and evidence agents cannot approve, execute, or distribute actions.

## Evidence Agent · `EVIDENCE-AGENT`

Resolve academically approved passage-level evidence, thematic interpretations, explicit gaps, and limitations without inventing authority.

- Inputs: event facts, scenario stage, policy query, approved passage catalog
- Outputs: approved passage IDs, thematic views, evidence gaps, limitations
- Consumes from: scenario runner, verified passage catalog
- Produces for: policy governance agent, trace and audit subsystem
- Fail closed: No approved support produces an evidence gap; No gap becomes a citation; No passage becomes a binding finding
- Reusable core: passage resolution, source provenance, citation eligibility, evidence-gap generation
- Domain configuration: approved sources, themes, policy mappings
- Education: Student-data governance
- Agriculture: Farmer-data sharing
- Finance: Consumer-credit governance

## Institutional Assessment Agents · `INSTITUTIONAL-ASSESSMENT-AGENTS`

Produce independent observations from mandate-bounded recipient projections without recommendation, approval, execution, or distribution authority.

- Inputs: recipient projection, institutional mandate, scenario context
- Outputs: assessment IDs, assessed fact IDs, observations, unresolved questions
- Consumes from: evidence release, projection service
- Produces for: coordination agent
- Fail closed: Out-of-mandate facts are not assessed; Missing eligible facts produce unresolved questions; Assessors cannot execute or recommend
- Reusable core: mandate isolation, observation model, assessment provenance
- Domain configuration: institutional mandates, assessor rules
- Education: Education authority and child-rights assessment
- Agriculture: Agriculture ministry and cooperative assessment
- Finance: Central bank and consumer-protection assessment

## Coordination Agent · `COORDINATION-AGENT`

Coordinate institutional assessments while preserving conflicts and unresolved questions as auditable objects.

- Inputs: institutional assessments, mandates, confidence states
- Outputs: coordinated observations, preserved conflicts, unresolved questions
- Consumes from: institutional assessment agents
- Produces for: policy governance agent, trace and audit subsystem
- Fail closed: Material disagreement is preserved; Unsupported consensus is not manufactured
- Reusable core: assessment aggregation, conflict preservation, provenance
- Domain configuration: conflict taxonomy, institutional composition
- Education: Reconcile school, rights, and data-protection views
- Agriculture: Reconcile ministry, cooperative, and privacy views
- Finance: Reconcile regulator, lender, and consumer views

## Policy Governance Agent · `POLICY-GOVERNANCE-AGENT`

Produce deterministic recommendations from facts, coordination, approved evidence, operations, and destinations.

- Inputs: event, coordinated assessments, approved passages, evidence gaps, operation, destination
- Outputs: recommendation, approval requirement, execution request, limitations
- Consumes from: coordination agent, evidence agent
- Produces for: human approval gate, execution agent, trace and audit subsystem
- Fail closed: Insufficient evidence remains unresolved; Recommendation does not authorize execution; Invalid operation or destination is rejected
- Reusable core: evaluator registry, recommendation model, deterministic governance bundle
- Domain configuration: operations, evaluators, authorization rules, destinations
- Education: Classroom exercise governance
- Agriculture: Farmer advisory governance
- Finance: Credit recommendation governance

## Human Approval Gate · `HUMAN-APPROVAL-GATE`

Gate approval-sensitive operations using explicit decision identities or a review queue.

- Inputs: recommendation, approval requirement, approval decision ID
- Outputs: decision reference, review queue receipt, execution eligibility
- Consumes from: policy governance agent, authorized reviewer
- Produces for: execution agent
- Fail closed: Required approval without a decision is queued; Execution state is not used to infer approval
- Reusable core: approval requirement, decision reference, review queue
- Domain configuration: review roles, thresholds, escalation policy
- Education: Sensitive student-data approval
- Agriculture: Farmer-data sharing approval
- Finance: High-impact credit exception review

## Execution Agent · `EXECUTION-AGENT`

Execute only registered, authorized, idempotent operations or produce a review or refusal result.

- Inputs: execution request, recommendation, approval decision, operation registry, destination registry
- Outputs: execution receipt, review queue receipt, not-attempted result
- Consumes from: human approval gate, policy governance agent
- Produces for: distribution agent, trace and audit subsystem
- Fail closed: Conflicting idempotency digest is rejected; Unregistered operation or destination does not execute; Missing approval does not execute
- Reusable core: idempotency, authorization enforcement, receipt model
- Domain configuration: operation adapters, destination adapters
- Education: Deliver classroom exercise
- Agriculture: Deliver farmer advisory
- Finance: Issue governed consumer notice

## Distribution Agent · `DISTRIBUTION-AGENT`

Control whether an execution result may be delivered to a registered destination and record prevented delivery.

- Inputs: execution result, destination identity, distribution policy
- Outputs: distribution effect, acknowledgment when eligible, prevention record
- Consumes from: execution agent
- Produces for: trace and audit subsystem
- Fail closed: Unregistered destination is prevented; Failed or not-attempted execution is not distributed
- Reusable core: destination enforcement, delivery effect, acknowledgment model
- Domain configuration: registered destinations, channel adapters
- Education: Teacher or learner interface delivery
- Agriculture: Cooperative or extension-service delivery
- Finance: Consumer notification delivery

## Trace and Audit Subsystem · `TRACE-AUDIT-SUBSYSTEM`

Bind component activity, evidence identities, decisions, execution outcomes, and prior audit state into verifiable traces and hashes.

- Inputs: facts, assessments, conflicts, passages, gaps, recommendation, execution, distribution
- Outputs: Y.3172-oriented trace, audit event, payload hash, previous hash, block hash, verification result
- Consumes from: all runtime agents
- Produces for: UI, submission artifacts, integrity verifier
- Fail closed: Hash mismatch invalidates verification; Missing runtime identity prevents complete trace claims
- Reusable core: trace graph, hash-linked audit, integrity verification
- Domain configuration: component mapping, event payload schema
- Education: Trace student-data governance decision
- Agriculture: Trace advisory and data-sharing decision
- Finance: Trace consumer-credit governance decision
