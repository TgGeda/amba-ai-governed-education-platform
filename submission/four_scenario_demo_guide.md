# AMBA-GOV: Four-Scenario, Failure-Handling, and Agent-Reuse Demonstration Guide

## 1. Evaluation purpose

This guide is designed for technical evaluators who will interact with the prototype. It explains the software and hardware environment, each agent's function, the complete interaction path, the four scenario inputs, error behavior, standards and policy gaps, and reuse across education, agriculture, finance, and health.

The central demonstration is not that the software always returns an answer. The central demonstration is that the software knows when evidence supports an action, when human approval is required, and when execution or distribution must be prevented.

## 2. Demonstration boundaries

```yaml
synthetic: true
legal_effect: false
production_external_destination: false
formal_y3172_conformance: false
itu_certification: false
official_itu_score: false
national_readiness_assessment: false
```

## 3. Prototype environment to explain first

### Software

```yaml
operating_system: Windows 10 or 11, 64-bit
python: 3.11
ui: PySide6 6.7.3
database: SQLite
vector_search: FAISS CPU 1.7.4
embedding_model: sentence-transformers/all-MiniLM-L6-v2
transformers: 4.44.2
dependencies:
  declared: 114
  exact_lock: 117
tests:
  passed: 1208
  failed: 0
gpu_required: false
```

### Hardware

```yaml
minimum:
  cpu: 4 logical cores
  ram: 8 GB
  free_storage: 10 GB
recommended:
  cpu: 8 logical cores
  ram: 16 GB
  free_storage: 20 GB
  display: 1920 x 1080
```

### Live commands

```cmd
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m pytest -q
run_amba.bat
run_submission_dashboard.bat
```

## 4. Agent roles, functions, and authority boundaries

### Evidence Agent

**Role:** Resolve approved passage-level evidence, thematic interpretations, explicit gaps, and limitations.

**Inputs:** event facts, stage, query, approved catalog.

**Outputs:** passage IDs, themes, gaps, and limitations.

**Cannot do:** invent authority, transform relevance into applicability, or issue a binding finding.

**Reuse:** the verification and gap logic stays the same; the approved catalog and domain themes change.

### Institutional Assessment Agents

**Role:** Assess recipient-specific facts from one institutional mandate.

**Inputs:** recipient fact projection, institutional mandate, scenario context.

**Outputs:** assessment ID, assessed fact IDs, observations, unresolved questions.

**Cannot do:** recommend, approve, execute, or distribute.

**Reuse:** replace mandates and assessment rules for education, agriculture, finance, or health.

### Coordination Agent

**Role:** Coordinate multiple assessments while preserving material conflict.

**Inputs:** assessment IDs, observations, mandates, confidence state.

**Outputs:** coordinated observations, conflict IDs, unresolved questions.

**Cannot do:** manufacture consensus or erase disagreement.

**Reuse:** the conflict-preservation contract stays stable; the institutional composition and conflict taxonomy change.

### Policy Governance Agent

**Role:** Produce a deterministic recommendation from facts, coordinated assessments, approved evidence, gaps, operation identity, and destination identity.

**Outputs:** recommendation, approval requirement, limitations, execution request.

**Cannot do:** treat recommendation as execution permission.

**Reuse:** evaluators, policies, operations, and authorization rules are configured per domain.

### Human Approval Gate

**Role:** Control approval-sensitive operations.

**Inputs:** recommendation, approval requirement, authorized reviewer decision.

**Outputs:** decision reference, review-queue receipt, execution eligibility.

**Cannot do:** infer approval from an execution result.

**Reuse:** reviewer roles, thresholds, escalation, and separation-of-duty rules change by domain.

### Execution Agent

**Role:** Execute only registered, authorized, idempotent operations.

**Inputs:** execution request, approval, operation registry, destination registry.

**Outputs:** success, review, refusal, or not-attempted receipt.

**Cannot do:** bypass approval, registration, destination, or idempotency controls.

**Reuse:** execution contract stays stable; operation adapters change.

### Distribution Agent

**Role:** Control delivery to registered destinations.

**Inputs:** execution result, destination, distribution policy.

**Outputs:** delivery acknowledgment or prevention record.

**Cannot do:** distribute a failed or unattempted operation.

**Reuse:** destination and channel adapters change while registration enforcement remains stable.

### Trace and Audit Subsystem

**Role:** Construct the Y.3172-oriented component path and hash-linked audit.

**Inputs:** facts, assessments, conflicts, passages, gaps, recommendation, execution, and distribution.

**Outputs:** trace ID, nodes, evidence references, payload hash, previous hash, block hash, verification result.

**Cannot do:** convert trace presence into formal standards certification.

## 5. End-to-end interaction

```text
1. Scenario event enters the pipeline.
2. Evidence Release selects eligible facts.
3. Institutional Projection creates mandate-bounded views.
4. Institutional Assessment Agents assess independently.
5. Coordination Agent preserves agreements and conflicts.
6. Evidence Agent resolves approved passages and gaps.
7. Policy Governance Agent creates a deterministic recommendation.
8. Human Approval Gate intervenes when required.
9. Execution Agent executes, queues, refuses, or does not attempt.
10. Distribution Agent controls delivery.
11. Y.3172 Trace Coordinator records the component path.
12. Audit binds evidence, decisions, execution, and distribution through hashes.
```

## 6. Scenario 1: successful governed operation

### Purpose

Show the valid path from event to successful execution and allowed distribution.

### Expected state

```yaml
approved_evidence: available
approval: not required or satisfied
execution_state: succeeded
distribution_effect: allowed
invariant_valid: true
audit_valid: true
```

### Live steps

1. Open **Four Scenarios**.
2. Select the first scenario.
3. Show released fact IDs and recipient projections.
4. Show institutional observations.
5. Show approved passages.
6. Show the recommendation.
7. Show successful execution and allowed distribution.
8. Show the trace and audit.

### Evaluation message

The operation succeeds because all governance boundaries are satisfied, not because the model produced a favorable answer.

## 7. Scenario 2: approval required and review queued

### Purpose

Show that recommendation cannot bypass human approval.

### Expected state

```yaml
approval_required: true
approval_decision: absent
execution_state: review_queued
distribution_effect: none
```

### Live steps

1. Select the approval-sensitive scenario.
2. Show the recommendation and approval requirement.
3. Open **Evidence and Gaps** and inspect the relevant gap.
4. Return to the scenario and show `review_queued`.
5. Confirm no distribution occurred.

### Evaluation message

The system converts missing authority into a review workflow, not unauthorized execution.

## 8. Scenario 3: multi-institutional governed workflow

### Purpose

Show mandate separation and conflict preservation.

### Expected state

```yaml
institutional_assessments: multiple
recipient_views: separated
coordination: completed
conflicts: preserved_when_present
governance: deterministic
invariant_valid: true
```

### Live steps

1. Select the multi-institutional scenario.
2. Compare recipient-specific projections.
3. Compare independent observations.
4. Show conflict IDs or unresolved questions.
5. Show how the final recommendation cites coordinated evidence.
6. Show the trace links from assessments to outcome.

### Evaluation message

The system does not collapse institutional perspectives into an unexplained average. Conflict remains visible and auditable.

## 9. Scenario 4: targeted advertising prevented

### Purpose

Show a hard execution and destination boundary.

### Input and expected state

```yaml
operation: targeted_ad_dispatch
destination: SYNTHETIC-AD-SINK
destination_registered: false
execution_state: not_attempted
distribution_effect: prevented
invariant_valid: true
audit_valid: true
```

### Live steps

1. Select the targeted-advertising scenario.
2. Show operation and destination identities.
3. Show that the destination is unregistered.
4. Show `not_attempted`.
5. Show `prevented`.
6. Inspect trace and audit evidence.

### Evaluation message

This is prevention at the execution and distribution boundary, not a warning added by the interface.

## 10. Failure and error laboratory

| Failure | Expected response | UI location |
|---|---|---|
| Approved passage unavailable | Explicit evidence gap | Evidence and Gaps |
| Passage hash mismatch | Evidence rejected | Audit and Integrity |
| Unknown theme or mapping | Resolution fails without invention | Evidence and Gaps |
| Missing approval | Review queued | Four Scenarios |
| Unregistered operation | Execution not attempted | Scenario details |
| Unregistered destination | Execution and distribution prevented | Scenario 4 |
| Idempotency collision | Conflicting request rejected | Execution details or test evidence |
| Changed audit hash | Audit verification fails | Audit and Integrity |
| Changed manifested artifact | Manifest stale or invalid | Audit and Integrity |
| Incomplete readiness evidence | Metric remains pending | Pending Gates |
| Coverage below 80% | Score withheld | Evidence Coverage |
| License unapproved | `F5-M01` pending | Pending Gates |
| Representative review incomplete | `D11-M01` pending | Pending Gates |

For the live session, prioritize missing approval, unregistered destination, evidence gap, and withheld readiness score. Explain the remaining errors with test and artifact evidence unless a controlled demonstration can be performed without changing committed submission files.

## 11. Reusable multi-agent building blocks

| Building block | Stable contract | Domain package changes |
|---|---|---|
| Evidence Agent | Provenance, verification, gaps | Sources, themes, policies |
| Projection | Recipient-specific release | Mandates and disclosure rules |
| Assessment framework | IDs, observations, provenance | Domain logic |
| Coordination | Aggregation and conflict preservation | Institutions and conflict taxonomy |
| Governance | Deterministic recommendation | Operations, evaluators, policies |
| Approval | Decision and queue | Roles, thresholds, escalation |
| Execution | Registration, authorization, idempotency | Operation adapters |
| Distribution | Destination enforcement | Channels and destinations |
| Trace | Component graph and pointers | Domain mapping |
| Audit | Hash linking and verification | Payload schema |
| Readiness | Evidence eligibility and threshold | Framework mapping |

### Education package

```yaml
operation: classroom_exercise_delivery
assessors:
  - education authority
  - child-rights institution
  - data protection authority
destinations:
  - teacher interface
  - learner interface
```

### Agriculture package

```yaml
operation: farmer_advisory_distribution
assessors:
  - agriculture authority
  - farmer cooperative
  - data protection authority
destinations:
  - extension service
  - cooperative portal
```

### Finance package

```yaml
operation: consumer_credit_recommendation
assessors:
  - financial regulator
  - consumer protection institution
  - financial institution
destination:
  - governed customer-notification channel
```

### Health package

```yaml
operation: governed_health_data_release
assessors:
  - health authority
  - clinical institution
  - privacy authority
destination:
  - registered clinical service
```

## 12. Standards and policy gaps

Show these as first-class outputs:

```yaml
formal_y3172_conformance:
  established: false
  action: external conformance assessment would be required

itu_certification:
  established: false

commercial_exploitation_evidence:
  status: unresolved where the scenario records a gap
  binding_violation_claimed: false

F5-M01:
  status: pending
  missing: owner-approved LICENSE

D11-M01:
  status: pending
  missing: real representative review and acceptance evidence
```

The system must not convert a standards or policy gap into a positive finding.

## 13. Readiness demonstration

Show:

```yaml
factors: 6
dimensions: 13
applicable_proxy_metrics: 19
scored_proxy_metrics: 14
evidence_coverage: 73.6842%
threshold: 80%
overall_project_score: withheld
```

Then show the minimum closure set:

```yaml
selected_metrics:
  - F5-M01
  - D11-M01
projected_scored_metrics: 16
projected_coverage: 84.2105%
threshold_reached: true
score_guaranteed: false
```

## 14. Seven-minute live script

### 0:00 to 0:45: setup

Show Windows, Python 3.11, PySide6, SQLite, FAISS CPU, locked dependencies, `pip check`, and the 1,229-test result.

### 0:45 to 1:45: architecture and agents

Show the agent workspace. Explain role, inputs, outputs, interactions, and authority boundaries.

### 1:45 to 4:15: four scenarios

Show success, review queue, multi-institutional coordination, and prevented advertising.

### 4:15 to 5:00: error behavior

Show one evidence gap and the missing-approval review queue.

### 5:00 to 5:40: reuse

Show education, agriculture, and finance adaptation packages.

### 5:40 to 6:20: Y.3172 and audit

Show 13 mappings, implementation paths, verified records, passage IDs, limitations, and audit validity.

### 6:20 to 7:00: readiness and close

Show 73.6842% coverage, 80% threshold, withheld score, and pending `F5-M01` and `D11-M01`.

Close with:

> AMBA-GOV distinguishes when evidence supports a governed action, when a human decision is required, and when an operation must not be attempted or distributed.

## 15. Live acceptance checklist

```text
[ ] Software and hardware explained
[ ] CPU-only execution stated
[ ] Four scenarios visible
[ ] Eight agent records visible
[ ] Agent interactions visible
[ ] Successful execution visible
[ ] Review queue visible
[ ] Multi-institutional conflict preservation visible
[ ] Prevented execution and distribution visible
[ ] Evidence gap visible
[ ] Manifest or audit integrity visible
[ ] Education, agriculture, and finance reuse explained
[ ] Thirteen Y.3172 mappings visible
[ ] Formal conformance false
[ ] ITU certification false
[ ] 14/19 readiness state visible
[ ] Score withheld
[ ] F5-M01 and D11-M01 pending
```
