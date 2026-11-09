# AMBA-GOV Technical Report Source

> **Publication source only. Do not generate the PDF until the official five-page template, example winning report, typography rules, citation requirements, and figure restrictions are supplied.**

## Working title

**AMBA-GOV: Evidence-Grounded Multi-Agent Governance with Controlled Execution, Reusable Institutional Agents, ITU-T Y.3172-Oriented Traceability, and Fail-Closed Project Readiness**

## Author

Birhan Abuhay Jemere

## Publication boundaries

```yaml
primary_language: English
synthetic_demonstration: true
legal_effect: false
formal_y3172_conformance: false
itu_certification: false
official_itu_score: false
national_readiness_assessment: false
technical_report_pdf_generated: false
```

## Verified evidence inventory

```yaml
approved_passages: 90
scenarios: 4
bounded_agents: 8
y3172_mappings: 13
readiness_factors: 6
readiness_dimensions: 13
applicable_proxy_metrics: 19
scored_proxy_metrics: 14
evidence_coverage: 0.736842
publication_threshold: 0.80
overall_project_score: null
pending_gates:
  - D11-M01
  - F5-M01
declared_dependencies: 114
locked_distributions: 117
tests_passed: 1208
tests_failed: 0
```

# Page 1 source: problem, solution, novelty, and architecture

## Problem

AI-enabled institutional services can produce recommendations that appear authoritative even when the supporting evidence, institutional mandate, approval authority, operation registration, or destination permission is incomplete. Retrieval can identify relevant text, but relevance alone does not establish that a passage is approved, applicable, binding, or sufficient to authorize an action. A warning shown by a user interface also does not prevent an external side effect.

## Solution

AMBA-GOV is an evidence-grounded multi-agent governance prototype. It transforms synthetic scenario events into recipient-specific institutional assessments, conflict-preserving coordination, verified policy evidence, deterministic governance recommendations, human approval decisions when required, controlled execution or refusal, distribution effects, ITU-T Y.3172-oriented traces, and hash-linked audit records.

## Novelty

The contribution is the complete evidence-to-effect chain:

```text
Event
  -> controlled fact release
  -> institution-specific interpretation
  -> conflict-preserving coordination
  -> verified evidence and explicit gaps
  -> deterministic recommendation
  -> human approval
  -> controlled execution
  -> controlled distribution
  -> component trace
  -> hash-linked audit
```

AMBA-GOV treats abstention, review, or prevention as legitimate governance outcomes. It separates recommendation from authorization and separates execution from distribution.

## Proposed architecture figure

The final figure should show the 12-step interaction sequence, eight agent boundaries, evidence and approval gates, execution and destination controls, trace, and audit. It must visibly state **Synthetic demonstration** and **No legal effect**.

# Page 2 source: agents, interactions, and reusability

## Agent roles

### Evidence Agent

Resolves approved passages, thematic interpretations, explicit evidence gaps, and limitations. It cannot invent authority or issue a binding finding.

### Institutional Assessment Agents

Assess only recipient-specific fact projections within an institutional mandate. They cannot approve, execute, or distribute.

### Coordination Agent

Coordinates institutional observations while preserving material disagreement and unresolved questions. It cannot manufacture consensus.

### Policy Governance Agent

Produces deterministic recommendations from event facts, coordinated assessments, approved evidence, gaps, operation identity, and destination identity. A recommendation is not execution permission.

### Human Approval Gate

Records an authorized decision or queues the request. It cannot infer approval from execution state.

### Execution Agent

Executes only registered, authorized, approved, idempotent operations. It returns success, review, refusal, or not-attempted receipts.

### Distribution Agent

Delivers only eligible execution results to registered destinations. It records prevention when delivery is prohibited.

### Trace and Audit Subsystem

Builds the Y.3172-oriented component path and hash-linked audit. Trace presence does not establish certification.

## Interaction contract

| Producer | Artifact | Consumer |
|---|---|---|
| Evidence Release | Released facts | Projection |
| Projection | Recipient views | Assessment Agents |
| Assessment Agents | Assessments | Coordination Agent |
| Coordination Agent | Coordinated result and conflicts | Governance Agent |
| Evidence Agent | Passages, gaps, limitations | Governance Agent |
| Governance Agent | Recommendation and approval requirement | Approval Gate and Execution Agent |
| Approval Gate | Decision or review receipt | Execution Agent |
| Execution Agent | Execution result | Distribution Agent |
| Distribution Agent | Distribution effect | Trace and Audit |

## Reusability

AMBA-GOV reuses governance contracts, not domain conclusions. Stable building blocks include passage verification, projection, assessment provenance, conflict preservation, approval gating, idempotent execution, destination enforcement, trace construction, and audit verification. Domain packages replace sources, mandates, assessment rules, operations, destinations, and approval policy.

Education, agriculture, finance, and health examples should be included in a compact reusability matrix.

# Page 3 source: prototype setup, scenarios, and error handling

## Software and hardware

Verified software includes Windows 10/11, Python 3.11, PySide6 6.7.3, SQLite, FAISS CPU 1.7.4, `all-MiniLM-L6-v2`, Transformers 4.44.2, and 117 exact locked distributions. A GPU is not required. Minimum hardware is four logical cores, 8 GB RAM, and 10 GB free storage. Eight logical cores, 16 GB RAM, 20 GB storage, and a 1920 × 1080 display are recommended.

## Four scenarios

| Scenario | Outcome | Primary property |
|---|---|---|
| Governed education operation | Succeeded and distributed | Valid evidence-to-effect path |
| Approval-sensitive operation | Review queued | Human approval cannot be bypassed |
| Multi-institutional workflow | Coordinated with preserved conflict | Mandate separation |
| Targeted advertising | Not attempted and prevented | Hard execution and destination control |

## Error handling

The report should present at least four concrete errors:

1. Missing approved passage creates an evidence gap, not a citation.
2. Missing approval queues review, not execution.
3. Unregistered destination prevents targeted-advertising execution and distribution.
4. Incomplete readiness evidence withholds the overall project score.

Additional error table entries should cover passage hash mismatch, unknown mapping, unregistered operation, idempotency conflict, changed audit hash, and changed manifested artifact.

## Proposed visual

Use a screenshot showing the four scenario rows and one selected scenario detail panel. If space permits, include one compact failure matrix.

# Page 4 source: standards mapping, policy gaps, and readiness

## ITU-T Y.3172

AMBA-GOV contains 13 evidence-backed mappings from implemented components to selected Y.3172 concepts. Every entry includes implementation files, verified record IDs, approved passage IDs, runtime evidence pointers, and limitations.

Required wording:

> AMBA-GOV provides an interpreted project-architecture mapping to selected ITU-T Y.3172 concepts. The mapping is evidence-backed but does not constitute formal Y.3172 conformance testing or ITU certification.

## Standards and policy gaps

Gaps are first-class outputs:

- formal Y.3172 conformance is not established;
- ITU certification is not claimed;
- unresolved commercial-exploitation evidence does not become a legal conclusion;
- `F5-M01` remains pending without an owner-approved license;
- `D11-M01` remains pending without real representative-review evidence.

## Readiness reflection

AMBA-GOV maps six factors and 13 dimensions through 19 project proxy metrics. Fourteen metrics are scored, producing 73.6842% evidence coverage against an 80% threshold. The overall project score is withheld.

The minimum deterministic closure set contains `F5-M01` and `D11-M01`. If accepted evidence were available for both, projected coverage would be 16 of 19, or 84.2105%. Passing the threshold would permit publication under the project methodology but would not guarantee a score.

# Page 5 source: verification, reproducibility, limitations, and conclusion

## Verification

The reviewed dependency set contains 114 exact pins and the lock contains 117 distributions. A clean Python 3.11 environment installed successfully from the lock. `pip check` passed, critical imports resolved, and the complete clean-environment suite passed 1,229 tests with zero failures.

## Reproduction

```cmd
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m pip check
run_amba.bat
```

The detailed procedure is in `submission/HOW_TO_REPRODUCE.md`.

## Limitations

- synthetic demonstration and no legal effect;
- no formal Y.3172 conformance assessment;
- no ITU certification;
- no official ITU or national readiness score;
- readiness score withheld below the evidence threshold;
- license and representative-review gates pending;
- production infrastructure and national deployment not evaluated.

## Conclusion

AMBA-GOV demonstrates a governance architecture in which evidence, institutional mandate, human authority, execution permission, destination permission, traceability, and audit are explicit and separable. Its principal capability is not unconditional automation. It is controlled progression from evidence to effect, with review, abstention, and prevention when support or authority is insufficient.

## Final PDF assembly checklist

```text
[ ] Official five-page template received
[ ] Winning example reviewed without copying language
[ ] Page-limit interpretation confirmed
[ ] Font, margin, column, citation, and figure rules confirmed
[ ] Architecture figure finalized
[ ] Four-scenario visual finalized
[ ] Agent-reuse visual finalized
[ ] Y.3172 and readiness visual finalized
[ ] All values refreshed from final artifacts
[ ] Final test count refreshed
[ ] English proofread by a human
[ ] Optional Amharic orientation text reviewed
[ ] Exactly five pages verified
[ ] Selectable text and accessibility checked
```
