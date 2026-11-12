# AI for Good Sandbox Hackathon – AMBA-GOV – Governed AI for Education

**Team Leader:** Birhan Abuhay Jemere  
**Team Members:** AMBA-GOV Project Team(Prof.Asrat Mulat,Birhan Abuhay)
**Contact Details:** burahabtam@gmail.com | +251-918-288-845 ||asrat.mulatu@aastu.edu.et|+251-911-538-342
**GitHub Link:** https://github.com/TgGeda/amba-ai-governed-education-platform  

> **Prototype Boundary:** AMBA-GOV is a synthetic, offline-capable
educational AI governance prototype. The project demonstrates
enforceable controls, reproducible scenarios, and hash-linked audit
evidence. The project does not claim formal ITU-T Y.3172 conformity,
ITU certification, legal advice, or regulatory authority.

<div style="text-align:justify;">

<h2>1. Introduction</h2>

<p>
Educational AI can improve access to summaries, notes, quizzes, flashcards, and tutoring. However, conventional deployments often leave document ingestion, retrieval, generation, memory, export, and deletion outside the governance path. This creates risks including unsupported instructional content, learner-data disclosure, confidential assessment leakage, commercial manipulation, and dependence on external cloud services.
</p>

<p>
AMBA-GOV is a local-first governed education platform that combines FAISS dense retrieval and BM25 lexical retrieval with executable policy controls, bounded evaluators, human review, controlled destinations, and append-only audit records. Every learning effect is linked to an authorized purpose, eligible source, registered operation, approved destination, and defined review rule.
</p>

<p>
The central principle is operational: when evidence or safety is insufficient, the platform does not guess. The request is blocked, abstained from, or placed in a durable teacher-review queue. A reviewed candidate is released without regeneration only after its content and governed-envelope hashes are verified.
</p>

<p>
This submission maps the prototype to selected ITU-T Y.3172 architectural concepts, Ethiopia's Personal Data Protection Proclamation No. 1321/2024, national education and cybersecurity evidence, UNESCO AI ethics principles, and UNICEF child-centred AI guidance. The mapping is a project interpretation rather than a formal conformity assessment or an official readiness score.
</p>

</div>
<div style="text-align:justify;">

## 2. Description of the Use Case

The use case is the safe and equitable application of generative AI in
primary and secondary education under limited connectivity,
institutional capacity, and computing resources.
</div>
AMBA-GOV implements the following governed workflow:

```text
Verified source and learner request
→ source and chunk integrity assessment
→ operation-specific eligibility decisions
→ synchronized FAISS and BM25 retrieval
→ local grounded generation
→ output sanitization and bounded assessment
→ PROCEED, BLOCK, ABSTAIN, or HOLD_FOR_REVIEW
→ registered destination or teacher-review queue
→ execution, delivery, and audit receipts
```

### How the Solution Addresses Existing Gaps

| Existing gap | AMBA-GOV invariant |
|---|---|
| Unverified ingestion | A document without integrity and governance records cannot enter the governed corpus. |
| Retrieval-policy drift | FAISS, BM25, and the operation allowlist must contain the same eligible chunk identifiers. |
| Direct-to-learner generation | Candidate output cannot reach approved UI or persistence destinations before governance clearance. |
| Non-actionable oversight | The exact sanitized candidate survives restart and can be reviewed and released without another model call. |
| Uncontrolled distribution | Unknown or prohibited destinations fail closed, and every registered sink verifies the governed envelope. |
| Ineffective revocation | Revocation creates an append-only decision and triggers a governed corpus refresh. |
<div style="text-align:justify;">

AMBA-GOV uses bounded software agents rather than unrestricted autonomy. Evidence and domain assessment agents produce findings; coordination preserves agreements and disagreements; policy produces a recommendation; human review authorizes consequential release; and execution and distribution enforce registered operations and destinations.
</div>

## 3. Use Case Requirements

### Pipeline Requirements

| Node | Requirement |
|---|---|
| **SRC** | Accept authenticated educational input, record source identity and SHA-256 digest, and prohibit unnecessary learner tracking. |
| **C** | Support local workstation or school-LAN collection, bounded sessions, and offline-capable operation. |
| **PP** | Apply configured PII checks, semantic chunking, canonical operations, chunk hashes, and complete operation-specific allowlists. |
| **M** | Keep governed FAISS and BM25 retrieval synchronized; excluded chunks cannot ground learner output. |
| **P** | Produce bounded education, child-rights, privacy, and consumer-protection findings; preserve disagreements; require review where necessary. |
| **D** | Verify operation, destination, approval, idempotency, held-output integrity, and governed envelopes before execution. |
| **SINK** | Deliver only through verified learner, teacher, persistence, export, memory, and audit destinations. |

## 4. Mapping with ITU-T Y.3172 Readiness 2.0 Report and Domain-Specific Policies

| Node | AMBA-GOV Functional Component | AI Readiness Emphasis | Policy and Technical Evidence |
| :--- | :--- | :--- | :--- |
| **SRC** | Authenticated curriculum upload, learner request, role metadata, source identity, and SHA-256 digest. | Provenance, safeguarded intake, purpose definition, and data quality. | Ethiopia’s Personal Data Protection Proclamation No. 1321/2024 supports lawful, purpose-bounded, and accountable personal-data processing. Education-policy evidence supports curriculum alignment. UNICEF child-centred AI guidance supports safety, privacy, transparency, fairness, and children’s best interests. Exact article applicability requires authorized legal review. |
| **C** | Local workstation or school-LAN intake, bounded sessions, offline-capable operation, and connected-mode monitoring. | Edge AI, infrastructure resilience, inclusion, and continuity under constrained connectivity. | ESDP VI identifies education-sector infrastructure and digital-technology challenges. UNICEF’s inclusion and enabling-environment requirements support accessible deployment but do not specifically mandate offline AI. Applicable Ethiopian communications quality-of-service requirements should be assessed separately for connected operation. |
| **PP** | Configured PII detection, semantic chunking, canonical operation identifiers, chunk hashes, operation-specific allowlists, and corpus-revision control. | Data harmonization, minimization, privacy by design, retention control, and secure preprocessing. | AMBA-GOV maps preprocessing controls to applicable purpose-limitation, minimization, security, privacy-by-design, retention, and deletion duties under Ethiopia’s data-protection framework. The prototype does not claim cryptographic proof of RAM erasure or absolute zero retention. |
| **M** | Local quantized language-model inference with governed FAISS and BM25 retrieval over the same eligible corpus revision. | Model and data provenance, sandboxing, robustness, and bounded inference. | ITU-T Y.3172 provides an architectural framework for machine-learning pipelines and related components in future networks. AMBA-GOV uses its specification and sandbox concepts as architectural references rather than as formal conformity claims. UNESCO ethics principles support lifecycle safety, robustness, data quality, and human responsibility. |
| **P** | Education, Child-Rights, Data-Protection, and Consumer-Protection evaluators; conflict-preserving coordination; deterministic recommendation; and teacher review. | Trustworthiness, human oversight, transparency, contestability, and child protection. | UNICEF’s child-centred requirements address safety, privacy, fairness, transparency, explainability, accountability, inclusion, and children’s best interests. UNESCO supports human oversight and accountability. Applicable Ethiopian automated-decision safeguards should be mapped at passage level rather than presented as unqualified legal conclusions. |
| **D** | Execution authorization, idempotency, immutable held-output storage, destination allowlist, governed-envelope verification, and revocation-triggered corpus refresh. | Controlled action, secure interfaces, local processing, and prevention of unauthorized egress. | AMBA-GOV maps these controls to applicable data-security, transfer, accountability, and institutional-authorization requirements. ITU-T Y.3172 security considerations inform the execution boundary but do not prescribe AMBA-GOV’s education-specific destination rules. |
| **SINK** | Learner and teacher interfaces, summary and notes persistence, study assets, tutor logs, controlled export, and append-only hash-linked audit records. | Accountability, auditability, usability, monitoring, and human-AI collaboration. | AMBA-GOV maps sink records to applicable processing-record, accountability, incident-management, transparency, and auditability principles. Audit records are described as hash-linked and tamper-detectable rather than blockchain-based. Exact breach-notification timelines and legal article assignments require passage-level legal confirmation. |

## 5. Error Scenario: Targeted Advertising Using Learner Data

### Step 1: Normal Deployment

<div style="text-align:justify;">

AMBA-GOV is deployed on school-owned infrastructure to provide governed summaries, quizzes, and tutoring. Curriculum sources are verified, retrieval is restricted to approved content, and learner-facing outputs pass governance checks before delivery.
</div>

### Step 2: Controversy Detected
<div style="text-align:justify;">

After six months, monitoring reveals that an external learning plugin is using query frequency, repeated mistakes, and inferred learning difficulties to target learners and parents with paid tutoring advertisements. This creates child-data protection, purpose-limitation, profiling, consumer-protection, and unauthorized-egress concerns.
</div>

### Step 3: Automated Detection and Containment
<div style="text-align:justify;">

The Data-Protection, Child-Rights, and Consumer-Protection Agents identify unauthorized profiling, commercial influence, and an unregistered destination. The Policy Governance Agent recommends `BLOCK`, the Execution Agent records the operation as `NOT_ATTEMPTED`, and the Distribution Agent records delivery as `PREVENTED`.

No learner profile, inferred learning difficulty, or advertisement leaves the governed environment.
</div>

### Step 4: Audit and Human Oversight
<div style="text-align:justify;">

AMBA-GOV creates a hash-linked incident record containing the evidence, findings, requested operation, destination, policy recommendation, execution status, and prevention receipt. Authorized school officials review the incident and determine whether notification, investigation, remediation, or referral is required under applicable procedures.

### Step 5: Remediation and Controlled Reactivation
<div style="text-align:justify;">

The external integration remains disabled until the provider removes profiling and targeted advertising, deletes improperly derived learner data where required, completes institutional review, and passes regression tests confirming that commercial content cannot reach learner-facing destinations.
<div style="text-align:justify;">

**The anticipated results of this intervention are fourfold:** The advertisement is prevented before reaching the learner, the attempted profiling remains auditable, no unauthorized data leaves the school environment, and the external integration cannot resume without formal review and verified remediation.
### Additional Fail-Closed Scenarios
<br>

<table style="width:100%; border-collapse:collapse;" border="1">
    <tr>
        <th>Failure</th>
        <th>Deterministic Response</th>
    </tr>
    <tr>
        <td>Missing approved evidence</td>
        <td>Returns an evidence-gap notice; no fabricated conclusions.</td>
    </tr>
    <tr>
        <td>Protected assessment or prompt injection</td>
        <td>Content is excluded and the request is blocked or abstained.</td>
    </tr>
    <tr>
        <td>FAISS/BM25 mismatch</td>
        <td>Corpus is rebuilt or processing is stopped.</td>
    </tr>
    <tr>
        <td>Digest mismatch</td>
        <td>Output release is blocked.</td>
    </tr>
    <tr>
        <td>Missing approval or destination</td>
        <td>No execution or distribution occurs.</td>
    </tr>
    <tr>
        <td>Duplicate release request</td>
        <td>Existing released record is returned.</td>
    </tr>
    <tr>
        <td>Deletion failure</td>
        <td>Deletion remains incomplete and recoverable.</td>
    </tr>
</table>

## 6. Policy Gaps and Standards Gaps Derived from the Mapping Exercise

<div style="text-align:justify;">

Mapping AMBA-GOV across the nine policy and standards sources revealed that the sources provide important principles but do not collectively define an executable governance framework for school-based generative AI.
</div>

| Mapped source | Gap identified through AMBA-GOV implementation |
|---|---|
| **ITU-T Y.3172** | Provides a useful machine-learning pipeline architecture, but does not define education-specific requirements for curriculum grounding, child protection, teacher authorization, held outputs, or learner-facing delivery. |
| **ITU AI Readiness 2.0** | Identifies readiness dimensions, but does not provide technical acceptance tests for retrieval parity, governed output release, revocation, or destination control. |
| **Ethiopia Personal Data Protection Proclamation No. 1321/2024** | Establishes data-protection duties, but requires education-sector guidance on learner telemetry, inferred learning difficulties, AI personalization, and temporary retention of outputs awaiting teacher review. |
| **Ethiopia ESDP VI and curriculum-policy evidence** | Support digital education and curriculum alignment, but do not specify how generative outputs should be grounded, cited, validated, or blocked when evidence is insufficient. |
| **National cybersecurity policy evidence** | Supports security, accountability, and audit, but does not define integrity records for AI prompts, retrieved chunks, model outputs, human overrides, or controlled delivery. |
| **Ethiopian communications QoS requirements** | Address connected-service quality, but do not establish minimum offline-AI performance, recovery, update, or school-edge deployment requirements. |
| **Consumer-protection evidence** | Addresses unfair commercial conduct, but does not specifically regulate advertisements or paid recommendations derived from learner behaviour and inferred academic difficulty. |
| **UNESCO Recommendation on the Ethics of Artificial Intelligence** | Defines human oversight, accountability, fairness, and safety principles, but does not prescribe executable controls, review states, destination restrictions, or technical audit formats for educational AI. |
| **UNICEF Guidance on AI and Children** | Provides child-centred requirements for safety, privacy, fairness, transparency, inclusion, and best interests, but does not define a technical implementation profile for governed retrieval, teacher release, revocation, and deletion. |

### Cross-Cutting Research Gaps
<div style="text-align:justify;">
The mapping therefore identified four cross-cutting gaps:

1. **No unified educational-AI governance profile** connecting architecture, child rights, privacy, curriculum, cybersecurity, consumer protection, and human oversight.

2. **No clear protection framework for learner telemetry**, including response latency, repeated errors, revision behaviour, and inferred learning difficulties.

3. **No standardized held-output lifecycle** defining how unreleased AI content is stored, inspected, redacted, approved, rejected, revoked, released, and deleted.

4. **No end-to-end technical assurance standard** for proving FAISS/BM25/governance parity, preserving multi-agent findings and dissent, and controlling UI, memory, clipboard, export, and external destinations.

These findings support the development of a **child-centred educational AI implementation profile** comprising an operation-risk register, a Governed Retrieval Manifest, an immutable Held Output Record, append-only human-review events, and verified destination-delivery receipts.
</div>