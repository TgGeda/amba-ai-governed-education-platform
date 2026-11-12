# AMBA-GOV: Final Scenario, Failure-Handling, and Agent-Reuse Demonstration Guide

## 1. Evaluation Purpose

This guide supports technical evaluation of the AMBA-GOV prototype. It explains the demonstrated environment, bounded agent responsibilities, end-to-end interactions, four core scenarios, failure behavior, cross-domain reuse, and the limits of the policy and standards mapping.

The central claim is not that AMBA-GOV always produces an answer. The central claim is that AMBA-GOV distinguishes among:

- actions supported by eligible evidence;
- actions requiring accountable human review;
- requests requiring abstention; and
- operations that must not be executed or distributed.

All quantitative results must be reproduced at the exact public Git commit used for evaluation.

---

## 2. Demonstration Boundaries

```yaml
synthetic_demonstration: true
legal_effect: none
real_learner_data: prohibited
production_external_destination: false
formal_y3172_conformance: not_assessed
itu_certification: not_claimed
official_itu_readiness_score: not_claimed
national_readiness_assessment: not_claimed
project_proxy_metrics: clearly_labelled
```

AMBA-GOV uses selected ITU-T Y.3172 concepts as an architectural reference. The prototype does not claim formal conformity, certification, statutory compliance, or regulatory authority.

---

## 3. Prototype Environment

### Software

```yaml
operating_system: Windows 10 or 11, 64-bit
python: "3.11"
ui: "PySide6 6.7.3"
database: SQLite
vector_search: "FAISS CPU 1.7.4"
lexical_search: BM25
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
embedding_dimensions: 384
transformers: "4.44.2"
inference: locally hosted quantized 3B-class instruction model
gpu_required_for_demonstrated_configuration: false
external_cloud_required_after_local_provisioning: false
dependency_integrity: verified with pip check
test_result: taken from final run at published commit
```

### Demonstration Hardware Target

```yaml
minimum:
  cpu: 4 logical cores
  ram: 8 GB
  free_storage: 10 GB
  display: 1366 x 768
recommended:
  cpu: 8 logical cores
  ram: 16 GB
  free_storage: 20 GB
  display: 1920 x 1080
```

These are project demonstration targets, not independently certified minimum requirements.

### Live Verification Commands

```cmd
.venv\Scripts\python.exe -m pip check
run_tests_clean.bat
git rev-parse HEAD
run_amba.bat
```

If `run_submission_dashboard.bat` exists and is verified at the published commit, it may also be demonstrated.

---

## 4. Agents and Authority Boundaries

| Agent or subsystem | Function | Authority boundary |
|---|---|---|
| **Evidence Agent** | Resolves approved passages, provenance, applicability, gaps, and limitations. | Cannot invent authority, approve, execute, or distribute. |
| **Education Assessment Agent** | Assesses curriculum grounding, learner suitability, and assessment integrity. | Cannot grant legal permission or deliver content. |
| **Child-Rights Agent** | Assesses child safety, developmental appropriateness, profiling, and exploitation. | Cannot impose sanctions or authorize release. |
| **Data-Protection Agent** | Assesses purpose limitation, minimization, sensitive data, redaction, retention, and disclosure. | Cannot declare legal compliance or authorize prohibited transfer. |
| **Consumer-Protection Agent** | Detects advertising, paid influence, deceptive recommendations, and purchase manipulation. | Cannot penalize vendors or terminate contracts. |
| **Coordination Agent** | Preserves agreements, conflicts, missing evidence, and unresolved questions. | Cannot manufacture consensus or erase dissent. |
| **Policy Governance Agent** | Produces `PROCEED`, `BLOCK`, `ABSTAIN`, or `HOLD_FOR_REVIEW`. | Recommendation is not execution permission. |
| **Human Review Gate** | Records approve, redact, reject, revoke, supersede, or regenerate decisions. | Cannot overwrite history, alter held content, or bypass integrity checks. |
| **Execution Agent** | Enforces registration, authorization, approval, integrity, and idempotency. | Cannot execute unknown, unauthorized, held, or changed requests. |
| **Distribution Agent** | Controls delivery to registered destinations. | Cannot distribute blocked, held, rejected, revoked, or failed material. |
| **Trace and Audit Subsystem** | Links evidence, findings, decisions, execution, delivery, revocation, and deletion through hashes. | Does not confer certification or legal validity. |

---

## 5. End-to-End Interaction

```text
1. A scenario event enters the governed pipeline.
2. Eligible facts and source evidence are released to bounded assessors.
3. Recipient-specific projections limit each assessor's view.
4. Assessment agents produce independent findings.
5. Coordination preserves agreement, dissent, and missing evidence.
6. The Evidence Agent resolves approved passages and explicit gaps.
7. The Policy Governance Agent creates a deterministic recommendation.
8. The Human Review Gate intervenes where approval is required.
9. The Execution Agent executes, queues, refuses, or records not attempted.
10. The Distribution Agent allows or prevents delivery.
11. The Y.3172-oriented trace records the component path.
12. The audit subsystem binds evidence, decisions, execution, and delivery through hashes.
```

---

## 6. Scenario 1: Successful Governed Educational Operation

### Purpose

Demonstrate the complete valid path from verified curriculum material to learner delivery.

### Input

A teacher ingests a synthetic Newton's Laws lesson and requests a grounded learner Summary.

### Expected State

```yaml
source_governance: present
chunk_allowlist: complete
retrieval_parity: true
approved_evidence: available
recommendation: PROCEED
execution_state: succeeded
distribution_effect: allowed
audit_valid: true
```

### Live Steps

1. Show the source digest and document-governance decision.
2. Show chunk digests, eligibility, and permitted learning operations.
3. Show the active corpus revision.
4. Compare FAISS, BM25, and governance-allowlist identifiers.
5. Generate the Summary.
6. Show the retrieved chunk IDs and output-validation evidence.
7. Show the `PROCEED` recommendation, execution record, and sink receipt.
8. Show the learner-visible Summary and audit trace.

### Evaluation Message

The operation succeeds because source integrity, retrieval eligibility, output governance, operation registration, and destination controls are satisfied—not merely because the model produced fluent text.

---

## 7. Scenario 2: Approval Required, Exact Review, and Controlled Release

### Purpose

Demonstrate that a recommendation cannot bypass human approval and that the exact reviewed candidate—not a regenerated substitute—is released.

### Initial State

```yaml
approval_required: true
approval_decision: absent
execution_state: review_queued
distribution_effect: none
held_output_status: pending_review
```

### Live Steps

1. Generate an approval-sensitive educational output.
2. Show the findings and `HOLD_FOR_REVIEW` recommendation.
3. Confirm that no learner-facing sink received the candidate.
4. Open **Teacher Review → Held Learning Outputs**.
5. Show the exact sanitized candidate, event ID, queue receipt, operation, and output hash.
6. Enter an authorized reviewer role and rationale.
7. Select **Approve and Release**.
8. Show material-hash and governed-envelope verification.
9. Show delivery to the registered sink and the resulting receipt.
10. Show the learner interface refresh.
11. Confirm that no second model call occurred.

### Final State

```yaml
review_decision: approved
held_output_status: released
output_hash_matches_reviewed_hash: true
second_model_call: false
distribution_effect: allowed
delivery_receipt_present: true
```

### Evaluation Message

AMBA-GOV converts missing authority into a durable review workflow and releases only the exact candidate inspected by the authorized reviewer.

---

## 8. Scenario 3: Multi-Institutional Assessment with Preserved Conflict

### Purpose

Demonstrate mandate separation, bounded evidence views, and preservation of disagreement.

### Input

A learning interaction raises curriculum, child-rights, privacy, and consumer-protection concerns requiring multiple institutional perspectives.

### Expected State

```yaml
institutional_assessments: multiple
recipient_views: separated
coordination: completed
conflicts: preserved_when_present
missing_evidence: explicit
governance_recommendation: deterministic
audit_valid: true
```

### Live Steps

1. Show recipient-specific evidence projections.
2. Compare independent findings from the Education, Child-Rights, Data-Protection, and Consumer-Protection Agents.
3. Show conflict IDs, evidence gaps, or unresolved questions.
4. Confirm that the Coordination Agent does not delete dissent.
5. Show how the Policy Governance Agent uses the complete coordinated bundle.
6. Show trace links from each assessment to the final recommendation.

### Evaluation Message

AMBA-GOV does not collapse institutional perspectives into an unexplained average. Material disagreement and missing evidence remain visible and auditable.

---

## 9. Scenario 4: Targeted Advertising Using Learner Data

### Purpose

Demonstrate prevention at the policy, execution, and distribution boundaries.

### Normal Deployment

AMBA-GOV operates on school-owned infrastructure. Curriculum sources are verified, retrieval is restricted to approved content, and learner-facing outputs pass governance checks before delivery.

### Controversy

After six months, an external plugin attempts to use query frequency, repeated mistakes, revision behaviour, or inferred learning difficulty to promote paid tutoring products to learners and parents.

### Attempted Effect

```yaml
operation: targeted_ad_dispatch
destination: SYNTHETIC-AD-SINK
declared_purpose: commercial promotion
input: inferred learner difficulty
destination_registered: false
```

### Automated Detection and Containment

1. The Data-Protection Agent identifies incompatible secondary use and profiling indicators.
2. The Child-Rights Agent identifies commercial influence involving learners.
3. The Consumer-Protection Agent identifies targeted solicitation and purchase manipulation.
4. The Evidence Agent resolves applicable approved policy records and explicit gaps.
5. The Coordination Agent preserves all findings and unresolved legal questions.
6. The Policy Governance Agent recommends `BLOCK`.
7. The Execution Agent records the operation as `NOT_ATTEMPTED` because the operation or authorization is invalid.
8. The Distribution Agent records delivery as `PREVENTED` because the destination is unregistered.

No learner profile, inferred learning difficulty, or advertisement leaves the governed environment.

### Audit and Human Oversight

AMBA-GOV stores an append-only, hash-linked incident record containing the requested operation, intended destination, evidence references, evaluator findings, recommendation, execution status, and prevention receipt.

Authorized school or public officials determine whether investigation, notification, contractual action, remediation, or referral is required. AMBA-GOV preserves evidence and prevents the technical effect but does not impose legal sanctions.

### Remediation and Controlled Reactivation

The external integration remains disabled until the provider:

1. removes targeted advertising and learner profiling;
2. addresses improperly derived learner data where required;
3. documents an authorized educational purpose and approved destination;
4. completes institutional privacy and safeguarding review; and
5. passes regression tests confirming that commercial content cannot reach learner-facing destinations.

Any reactivation creates a new configuration and policy revision. The original incident remains in the append-only audit history.

### Expected State

```yaml
execution_state: not_attempted
distribution_effect: prevented
learner_profile_sent_externally: false
advertisement_displayed: false
incident_evidence_retained: true
automatic_legal_sanction: false
```

### Evaluation Message

This is technical prevention at the execution and distribution boundary, not an interface warning added after harm occurs.

---

## 10. Failure and Error Laboratory

| Failure injection | Expected response | Evaluator evidence |
|---|---|---|
| Approved passage unavailable | Explicit evidence gap; no invented authority | Gap record and no fabricated citation |
| Passage or audit hash changed in controlled test | Verification fails | Integrity error and failed verification result |
| Unknown theme or mapping | Resolution fails without invention | Explicit unresolved mapping |
| Missing approval | Review queued; no execution | Queue receipt and no sink receipt |
| Unregistered operation | Execution not attempted | `NOT_ATTEMPTED` record |
| Unregistered destination | Distribution prevented | Prevention record |
| Idempotency collision with changed request | Conflicting request rejected | Existing key and mismatch evidence |
| FAISS/BM25/allowlist drift | Governed rebuild or stop | Three ID sets and rebuild result |
| Held material changed | Release blocked | Digest mismatch and no release timestamp |
| Unauthorized reviewer | No review mutation | Role error and unchanged record count |
| Sink delivery failure | `release_failed`, retryable | Last error and no delivery receipt |
| Chunk approval revoked | New review record; corpus refresh | Append-only chain and changed revision |
| Index removal fails during deletion | Deletion remains incomplete | Failure state and recovery evidence |
| Readiness evidence incomplete | Metric remains pending | Evidence-coverage dashboard |

For the live session, prioritize missing approval, unregistered destination, retrieval parity, held-output integrity, and evidence gaps. Demonstrate destructive tampering only in an isolated test database, never in committed submission evidence.

---

## 11. Reusable Multi-Agent Building Blocks

| Building block | Stable contract | Domain package changes |
|---|---|---|
| Evidence resolution | Provenance, verification, gaps, limitations | Sources, jurisdictions, themes, policies |
| Projection | Recipient-specific fact release | Mandates and disclosure rules |
| Assessment | Structured findings and provenance | Domain logic and severity taxonomy |
| Coordination | Aggregation and conflict preservation | Institutions and conflict taxonomy |
| Governance | Deterministic recommendation | Operations, evaluators, policies |
| Human review | Append-only decision and queue | Roles, thresholds, escalation |
| Execution | Registration, authorization, integrity, idempotency | Operation adapters |
| Distribution | Destination enforcement and acknowledgement | Channels and destinations |
| Trace | Component graph and evidence pointers | Domain mapping |
| Audit | Hash linking and verification | Domain payload schema |

### Education Package

```yaml
operation: classroom_learning_delivery
assessors:
  - education assessment
  - child-rights assessment
  - data-protection assessment
  - consumer-protection assessment
destinations:
  - learner interface
  - teacher interface
  - governed learning persistence
```

### Agriculture Package

```yaml
operation: farmer_advisory_distribution
assessors:
  - agronomy assessment
  - pesticide and crop-safety assessment
  - data-protection assessment
destinations:
  - extension service
  - farmer cooperative portal
```

### Finance Package

```yaml
operation: consumer_credit_recommendation
assessors:
  - affordability assessment
  - fair-lending assessment
  - consumer-protection assessment
destination:
  - governed customer-notification channel
```

### Health Package

```yaml
operation: governed_health_information_release
assessors:
  - clinical-validity assessment
  - patient-safety assessment
  - privacy assessment
destination:
  - registered clinical service
```

Safe reuse requires replacement or revalidation of domain evidence, mandates, severity rules, operations, destinations, reviewer roles, retention rules, and acceptance tests. Changing only the prompt is insufficient.

---

## 12. Standards and Policy Gaps

The mapping produces explicit gaps rather than treating missing evidence as compliance.

```yaml
formal_y3172_conformance:
  status: not_assessed
  claim: not_made
  next_step: independent conformity analysis if applicable

itu_certification:
  status: not_claimed

commercial_exploitation:
  technical_prevention: demonstrated
  legal_violation_determination: reserved_for_authorized_review

learner_telemetry:
  policy_gap: classification and permissible educational use require clarification

held_output_lifecycle:
  standards_gap: no common interoperable record and review-event schema

hybrid_retrieval_parity:
  standards_gap: no common manifest proving dense, lexical, and governance corpus equality
```

The system must not convert a policy gap, standards gap, unsupported passage, or pending metric into a positive finding.

---

## 13. Project Readiness Evidence Demonstration

If the submission dashboard contains the following metrics at the final public commit, present them strictly as an internal project proxy—not as an official ITU score or national readiness assessment.

```yaml
framework_reference:
  factors: 6
  dimensions: 13

project_proxy:
  applicable_metrics: 19
  evidenced_metrics: 14
  evidence_coverage: 73.6842%
  project_defined_publication_threshold: 80%
  aggregate_score_status: withheld
  official_itu_score: not_claimed
```

### Minimum Evidence-Closure Set

```yaml
pending_metrics:
  - F5-M01
  - D11-M01
projected_evidenced_metrics: 16
projected_coverage: 84.2105%
project_threshold_reached: true
official_score_guaranteed: false
```

The 80% threshold is an AMBA-GOV evidence-publication rule, not an ITU requirement. Remove the figures if the final dashboard does not reproduce them at the published commit.

---

## 14. Seven-Minute Live Demonstration

### 0:00–0:40 — Environment and Boundaries

Show the operating system, Python 3.11, local SQLite, FAISS CPU, `pip check`, exact final test result, Git commit, and no-certification boundaries.

### 0:40–1:25 — Agents and Authority Separation

Show evidence, assessments, coordination, policy, human review, execution, distribution, and audit. Emphasize that recommendation is not execution permission.

### 1:25–3:50 — Four Scenarios

Show:

1. successful governed educational operation;
2. approval-sensitive output, exact teacher review, and release;
3. multi-institutional assessment with preserved conflicts; and
4. targeted advertising prevented at execution and distribution.

### 3:50–4:40 — Failure Laboratory

Show one evidence gap, one missing approval, and one unregistered destination. Explain remaining failures using committed tests.

### 4:40–5:25 — Reuse

Show how education, agriculture, finance, and health replace evidence, mandates, operations, destinations, reviewers, and tests while retaining common governance contracts.

### 5:25–6:15 — Trace and Audit

Show Y.3172-oriented component mappings, evidence references, limitations, recommendation, execution state, delivery result, and audit verification.

### 6:15–7:00 — Readiness and Close

Show the project proxy only if reproduced at the final commit. Explain the project-defined threshold, withheld aggregate score, and pending evidence items.

> AMBA-GOV distinguishes when evidence supports a governed action, when accountable human authorization is required, and when an operation must not be executed or distributed.

---

## 15. Live Acceptance Checklist

```text
[ ] Git commit and final test summary recorded
[ ] Software and hardware explained
[ ] CPU-oriented demonstration stated accurately
[ ] Synthetic/no-legal-effect boundary shown
[ ] All configured agent roles visible
[ ] Authority separation explained
[ ] Successful governed operation visible
[ ] Held output and review queue visible
[ ] Exact reviewed output released without regeneration
[ ] Multi-institutional conflict preservation visible
[ ] Targeted advertising execution not attempted
[ ] Unauthorized distribution prevented
[ ] Evidence gap visible
[ ] Retrieval parity or rebuild evidence visible
[ ] Audit integrity visible
[ ] Education, agriculture, finance, and health reuse explained
[ ] Y.3172 mapping labelled project-oriented
[ ] Formal conformity not assessed
[ ] ITU certification not claimed
[ ] Readiness figures reproduced or omitted
[ ] Official ITU score not claimed
```

---

## 16. Final Evaluation Message

AMBA-GOV demonstrates that educational AI governance can be implemented as an enforceable system lifecycle rather than a post-hoc ethics statement. Evidence, assessment, coordination, policy recommendation, human authorization, execution, distribution, revocation, deletion, and audit remain separate and inspectable. The prototype succeeds when an authorized and evidenced learning effect is delivered—and also when an unsupported, unapproved, commercially manipulative, or integrity-failed effect is prevented.
