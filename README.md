# AMBA-GOV

**Evidence-grounded multi-agent governance for bounded institutional assessment, controlled execution, ITU-T Y.3172-oriented traceability, and fail-closed project-readiness reflection.**

AMBA-GOV is a locally reproducible governance prototype that turns synthetic scenario events into institution-specific assessments, conflict-preserving coordination, verified policy evidence, deterministic recommendations, human approval when required, controlled execution or refusal, controlled distribution, component traces, and hash-linked audits.

The prototype is designed to answer a practical governance question:

> How can an AI-enabled system distinguish between an action supported by approved evidence, an action that requires human authorization, and an action that must not be attempted?

## Submission status

| Item | Verified state |
|---|---:|
| Python | 3.11 |
| Declared dependencies | 114 exact pins |
| Locked dependency closure | 117 distributions |
| Complete regression | 1,229 passed, 0 failed, 3 warnings |
| Approved passages | 90 |
| Demonstration scenarios | 4 |
| Bounded agents or subsystems | 8 |
| Y.3172 architecture mappings | 13 |
| Readiness factors and dimensions | 6 factors, 13 dimensions |
| Project proxy metrics | 19 applicable, 14 scored |
| Evidence coverage | 73.6842% |
| Publication threshold | 80% |
| Overall readiness score | Withheld |
| Pending evidence gates | D11-M01 and F5-M01 |

## Claim boundaries

AMBA-GOV is careful about what it claims.

- The four-scenario demonstration is synthetic and has no legal effect.
- The ITU-T Y.3172 work is an interpreted, evidence-backed project architecture mapping. It is not formal Y.3172 conformance testing and is not ITU certification.
- The readiness reflection is a project self-evaluation. It is not a national AI-readiness assessment and not an official ITU score.
- A recommendation does not authorize execution.
- Citation eligibility does not establish legal applicability or binding authority.
- The overall readiness score remains withheld because 14 of 19 applicable project proxy metrics are evidenced, below the configured 80% publication threshold.

## Why AMBA-GOV is different

Many prototypes stop at retrieval, classification, or recommendation. AMBA-GOV links evidence to operational governance:

```text
Scenario event
  -> controlled evidence release
  -> recipient-specific institutional projection
  -> bounded institutional assessments
  -> conflict-preserving coordination
  -> approved policy evidence and explicit gaps
  -> deterministic governance recommendation
  -> human approval when required
  -> execution, review queue, or refusal
  -> distribution control
  -> Y.3172-oriented trace
  -> hash-linked audit
```

The architecture treats a refusal, abstention, or review queue as a valid governed outcome rather than a system failure.

## Prototype software and hardware configuration

### Software

| Layer | Configuration |
|---|---|
| Operating system | Windows 10 or Windows 11, 64-bit |
| Programming language | Python 3.11 |
| Desktop interface | PySide6 6.7.3 |
| Local database | SQLite |
| Vector search | FAISS CPU 1.7.4 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Transformer framework | Transformers 4.44.2 |
| Governance configuration | YAML plus deterministic Python services |
| Evidence artifacts | JSON, JSONL, YAML, and Markdown |
| Tests | pytest 9.1.1 and pytest-qt 4.5.0 |
| Dependency reproduction | `requirements.txt` plus `requirements-lock.txt` |
| Report support | ReportLab, python-docx, pypdf, and python-pptx |
| GPU requirement | None |

### Hardware

| Profile | CPU | RAM | Free storage | Display | GPU |
|---|---:|---:|---:|---:|---|
| Minimum | 4 logical cores | 8 GB | 10 GB | 1366 × 768 | Not required |
| Recommended | 8 logical cores | 16 GB | 20 GB | 1920 × 1080 | Optional |

The first evidence-chain run may take longer while the embedding model is downloaded and initialized. After caching, the model can be reused locally. FAISS runs on the CPU, and committed evidence artifacts can be inspected without rerunning the embedding pipeline.

## Agent architecture

AMBA-GOV documents eight bounded agents or subsystems.

| Agent or subsystem | Role | Main outputs | Authority boundary |
|---|---|---|---|
| Evidence Agent | Resolves approved passages, themes, gaps, and limitations | Passage IDs, thematic views, evidence gaps | Cannot invent authority or issue a binding finding |
| Institutional Assessment Agents | Assess recipient-specific facts within one mandate | Assessment IDs, observations, unresolved questions | Cannot approve, execute, or distribute |
| Coordination Agent | Coordinates assessments while preserving disagreement | Coordinated observations, conflicts, unresolved issues | Cannot manufacture unsupported consensus |
| Policy Governance Agent | Produces a deterministic recommendation | Recommendation, approval requirement, execution request | Recommendation is not execution permission |
| Human Approval Gate | Controls approval-sensitive operations | Decision reference or review-queue receipt | Cannot infer approval from execution state |
| Execution Agent | Executes only registered, authorized, idempotent operations | Success, review, refusal, or not-attempted receipt | Cannot bypass approval, operation, or destination controls |
| Distribution Agent | Controls delivery to registered destinations | Acknowledgment or prevention record | Cannot deliver failed or not-attempted execution |
| Trace and Audit Subsystem | Constructs component traces and hash-linked audit | Trace nodes, payload hash, previous hash, block hash | Trace presence is not standards certification |

Full inputs, outputs, interactions, failure behavior, implementation files, and cross-domain examples are generated in:

```text
submission/artifacts/agent_architecture.json
submission/artifacts/agent_architecture.md
```

## Agent interaction contract

| Producer | Artifact | Consumer |
|---|---|---|
| Evidence Release | Released fact IDs | Institutional Projection |
| Institutional Projection | Recipient-specific views | Institutional Assessment Agents |
| Institutional Assessment Agents | Mandate-bounded assessments | Coordination Agent |
| Coordination Agent | Coordinated result and preserved conflicts | Policy Governance Agent |
| Evidence Agent | Passages, gaps, themes, and limitations | Policy Governance Agent |
| Policy Governance Agent | Recommendation and approval requirement | Human Approval Gate and Execution Agent |
| Human Approval Gate | Decision or review receipt | Execution Agent |
| Execution Agent | Execution result | Distribution Agent |
| Distribution Agent | Distribution effect | Trace and Audit Subsystem |
| Trace and Audit Subsystem | Trace and integrity evidence | UI, report, and manifest |

## Reusable governance building blocks

AMBA-GOV reuses the governance pipeline rather than reusing a domain conclusion. Domain packages change approved evidence, mandates, assessment rules, executable operations, registered destinations, and approval policies. The core contracts remain stable.

| Building block | Reusable core | Domain-specific configuration |
|---|---|---|
| Evidence Agent | Passage verification, provenance, gap generation | Approved sources, themes, policies |
| Institutional Projection | Recipient-specific fact selection | Mandates and disclosure rules |
| Assessment framework | Observation model, IDs, provenance | Domain assessment logic |
| Coordination Agent | Aggregation and conflict preservation | Conflict taxonomy and institutional composition |
| Policy Governance Agent | Recommendation model and deterministic evaluators | Operations, policies, authorization rules |
| Human Approval Gate | Approval requirement, decision reference, review queue | Reviewer roles and thresholds |
| Execution Agent | Registration, authorization, idempotency, receipts | Operation adapters |
| Distribution Agent | Destination registration and delivery effects | Channels and destination adapters |
| Trace Coordinator | Component graph and runtime pointers | Domain component mapping |
| Audit subsystem | Hash linking and verification | Event and decision payload schema |
| Readiness subsystem | Evidence mapping, scoring eligibility, threshold control | Framework mappings and requirements |

### Domain examples

- **Education:** classroom exercise delivery and student-data governance involving education, child-rights, and data-protection perspectives.
- **Agriculture:** farmer advisory distribution and farmer-data sharing involving an agriculture authority, cooperative, and data-protection perspective.
- **Finance:** consumer-credit recommendation involving a financial regulator, consumer-protection institution, and financial institution.
- **Health:** governed health-data release involving a health authority, clinical institution, and privacy authority.

## Four demonstration scenarios

| Scenario | Main outcome | Property demonstrated |
|---|---|---|
| 1. Governed education operation | Execution succeeds and distribution is allowed | Normal evidence-to-execution path |
| 2. Approval-sensitive operation | Review is queued | Human authorization cannot be bypassed |
| 3. Multi-institutional workflow | Assessments are coordinated and conflicts remain visible | Mandate separation and conflict preservation |
| 4. Targeted advertising prevention | Execution is not attempted and distribution is prevented | Hard operation and destination boundary |

Detailed steps are in `submission/four_scenario_demo_guide.md`.

## Failure and error handling

| Failure condition | Fail-closed behavior |
|---|---|
| No approved passage | Create an evidence gap, not a citation |
| Passage hash mismatch | Reject the evidence |
| Unknown theme or policy mapping | Fail resolution without invention |
| Approval required but absent | Queue human review |
| Unregistered operation | Do not execute |
| Unregistered destination | Do not execute or distribute |
| Conflicting idempotency digest | Reject the conflicting request |
| Audit hash changed | Fail audit verification |
| Manifested artifact changed | Mark manifest stale or invalid |
| Readiness evidence incomplete | Keep metric pending |
| Coverage below 80% | Withhold the overall score |
| License approval missing | Keep `F5-M01` pending |
| Representative review incomplete | Keep `D11-M01` pending |

## ITU-T Y.3172 mapping

AMBA-GOV contains 13 mappings from implemented components to selected Y.3172 concepts. Each entry contains implementation paths, verified record IDs, approved passage IDs, runtime evidence pointers, and limitations.

```yaml
mapping_type: interpreted_project_architecture_mapping
formal_conformance: false
itu_certification: false
```

Artifacts:

```text
config/y3172_architecture_mapping.yaml
submission/artifacts/y3172_architecture_mapping.json
submission/artifacts/y3172_architecture_mapping.md
```

## Project readiness reflection

AMBA-GOV maps six factors and 13 dimensions through 19 project proxy metrics. The current evidence state is:

```yaml
applicable_metrics: 19
scored_metrics: 14
evidence_coverage: 0.736842
publication_threshold: 0.80
overall_project_score: null
score_status: withheld_insufficient_evidence_coverage
```

The minimum two-metric closure set is `F5-M01` and `D11-M01`. Resolving both would project coverage to 16 of 19, or 84.2105%, but would not guarantee a particular score.

## Quick start

```cmd
git clone <repository-url>
cd amba_ai_project
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m pip check
run_amba.bat
```

Expected dependency check:

```text
No broken requirements found.
```

## Verification

```cmd
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe tools\dependencies\verify_requirements.py
.venv\Scripts\python.exe -m pytest -q
```

Verified baseline:

```text
1229 passed, 0 failed, 3 warnings
```

## Judge-oriented launchers

```cmd
run_submission_dashboard.bat
```

```cmd
run_evidence_chain_demo.bat
```

The complete reproduction procedure is in `submission/HOW_TO_REPRODUCE.md`.

## Language

The complete prototype, report sources, and reproduction materials are provided in English. English is the authoritative technical language. A limited Amharic orientation layer may be added for navigation and demonstration summaries only after review. Verified source passages and standards terminology remain in their source language to preserve accuracy.

## Submission timeline

| Date | Milestone |
|---|---|
| 10 November 2026, 23:59 UAE time | Final submission deadline |
| 11 to 18 November 2026 | First-round evaluation |
| 18 November 2026 | Shortlisted teams announced |
| 8 December 2026 | Final evaluation onsite in Dubai |
| 10 December 2026 | Award ceremony onsite in Dubai |

The final email must state **FINAL SUBMISSION** and supersede earlier submissions.

## Repository map

```text
src/amba_ai/                    product code
src/amba_ai/ui/features/        active feature workspaces
src/amba_ai/governance/         governance models and controls
src/amba_ai/institutional/      projections, assessors, coordination
src/amba_ai/standards/          Y.3172 registry, models, trace, mapping
src/amba_ai/services/           evidence, policy, execution, distribution, audit
config/                         deterministic policies and mappings
kb/                             verified records and approved passages
submission/artifacts/           generated evidence and integrity artifacts
tools/                          reproducible product generators and verifiers
tests/                          unit, integration, and adversarial coverage
submission/                     reproduction, demo, and report source documents
```

## Documentation

- `submission/HOW_TO_REPRODUCE.md`
- `submission/four_scenario_demo_guide.md`
- `submission/technical_report_source.md`
- `submission/artifacts/agent_architecture.md`
- `submission/artifacts/y3172_architecture_mapping.md`

## License and review gates

The project intentionally keeps the software-license readiness metric pending until an owner-approved license file is present. It also keeps the representative-review metric pending until a real representative review is completed and accepted. These boundaries must not be bypassed for presentation purposes.
