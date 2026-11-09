# AMBA-GOV: Complete Reproduction and Evaluation Guide

## 1. Purpose

This guide allows an evaluator to reproduce the AMBA-GOV environment, launch the full prototype, run four diverse governance scenarios, inspect each bounded agent, demonstrate failure behavior, verify Y.3172-oriented traces and audit records, regenerate readiness artifacts, and verify submission integrity.

The guide is deliberately operational. It distinguishes three different activities:

1. **Artifact review**, which uses committed deterministic evidence without rerunning the model.
2. **Prototype execution**, which launches the integrated PySide6 application or focused judge dashboard.
3. **Full regeneration**, which rebuilds scenario, standards, agent, readiness, closure, SBOM, and manifest artifacts.

## 2. Scope and boundaries

- All scenarios are synthetic and have no legal effect.
- No production external destination is contacted.
- Recommendation, approval, execution, and distribution are separate authority boundaries.
- The Y.3172 mapping is an interpreted project-architecture mapping, not formal conformance testing or ITU certification.
- The readiness reflection is a project self-evaluation, not an official ITU score or national assessment.
- The overall readiness score remains withheld while evidenced metric coverage is below 80%.
- `F5-M01` and `D11-M01` remain pending until an owner-approved license and real representative-review evidence exist.

## 3. Prototype software and hardware configuration

### Software stack

| Layer | Verified configuration |
|---|---|
| Operating system | Windows 10 or Windows 11, 64-bit |
| Programming language | Python 3.11 |
| Desktop interface | PySide6 6.7.3 |
| Local database | SQLite |
| Vector search | FAISS CPU 1.7.4 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Transformer framework | Transformers 4.44.2 |
| Governance configuration | YAML and deterministic Python services |
| Evidence artifacts | JSON, JSONL, YAML, and Markdown |
| Testing | pytest 9.1.1 and pytest-qt 4.5.0 |
| Dependencies | 114 declared exact pins, 117 locked distributions |
| Report support | ReportLab, python-docx, pypdf, python-pptx |
| Version control | Git |
| GPU requirement | None |

### Hardware

| Profile | CPU | RAM | Free storage | Display | GPU |
|---|---:|---:|---:|---:|---|
| Minimum | 4 logical cores | 8 GB | 10 GB | 1366 × 768 | Not required |
| Recommended | 8 logical cores | 16 GB | 20 GB | 1920 × 1080 | Optional |

### Operational notes

- The first run can be slower while `sentence-transformers/all-MiniLM-L6-v2` downloads and initializes.
- After caching, the model is reused locally.
- FAISS search runs on the CPU.
- Committed evidence can be reviewed without model re-execution.
- Scenario outputs are deterministic under the committed configuration.

## 4. Verified baseline

```yaml
python: 3.11
declared_dependencies: 114
locked_distributions: 117
pip_check: passed
tests_passed: 1208
tests_failed: 0
expected_warnings: 3
approved_passages: 90
scenarios: 4
bounded_agents: 8
y3172_mappings: 13
applicable_proxy_metrics: 19
scored_proxy_metrics: 14
evidence_coverage: 0.736842
publication_threshold: 0.80
overall_project_score: null
```

The expected warnings are two FAISS/setuptools `distutils` deprecation warnings and one Transformers future warning about `clean_up_tokenization_spaces`.

## 5. Clone and select the submission revision

```cmd
git clone <repository-url>
cd amba_ai_project
git checkout <final-submission-tag>
git rev-parse HEAD
git status --short
```

A clean working tree is required.

## 6. Create and verify the environment

```cmd
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m pip check
```

Expected:

```text
No broken requirements found.
```

Verify the dependency contract:

```cmd
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe tools\dependencies\verify_requirements.py
```

Expected:

```text
PASS: 114 declared dependencies are contained in 117 exact locked distributions
PASS: critical UI, vector, transformer, YAML, report, Word, PDF, and charset imports resolve
```

## 7. Run the complete regression

```cmd
.venv\Scripts\python.exe -m pytest -q
```

Verified baseline:

```text
1229 passed, 3 warnings
```

A higher pass count is acceptable after later documentation tests. Zero failures is mandatory.

## 8. Launch the complete prototype

```cmd
run_amba.bat
```

`run_amba.bat` is path-portable, invokes `.venv\Scripts\python.exe` directly, sets `PYTHONPATH`, and clears inherited `QT_QPA_PLATFORM` values so an offscreen test configuration cannot hide the production interface.

Equivalent command:

```cmd
set "QT_QPA_PLATFORM="
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe -m amba_ai.main
```

Verify:

- Existing learning workspaces open.
- Governance and Readiness each appear once.
- Governance menu actions open both workspaces.
- The status bar shows synthetic, no-legal-effect, Y.3172 interpretation, and score-withheld boundaries.

## 9. Launch the focused judge dashboard

```cmd
run_submission_dashboard.bat
```

This interface exposes:

```text
Governance
  Overview
  Four Scenarios
  Agents
  Evidence and Gaps
  ITU-T Y.3172
  Audit and Integrity

Readiness
  Framework
  Project Proxy Metrics
  Evidence Coverage
  Closure Plan
  Pending Gates
  Claim Boundaries
```

## 10. Run the four-scenario chain

```cmd
run_evidence_chain_demo.bat
```

Equivalent:

```cmd
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe -m amba_ai.cli.evidence_chain_demo
```

Generated artifact:

```text
submission/artifacts/four_stage_evidence_chain.json
```

Required checks:

```yaml
stage_count: 4
all_stage_invariants_valid: true
final_audit_valid: true
required_outcomes:
  - succeeded
  - review_queued
  - not_attempted
```

Detailed live steps are in `submission/four_scenario_demo_guide.md`.

## 11. Agent roles and interactions

### Roles

| Agent or subsystem | Function | Cannot do |
|---|---|---|
| Evidence Agent | Resolve approved evidence and gaps | Invent authority or binding findings |
| Institutional Assessment Agents | Assess mandate-bounded projections | Approve, execute, or distribute |
| Coordination Agent | Preserve agreements, conflicts, unresolved questions | Manufacture consensus |
| Policy Governance Agent | Produce deterministic recommendations | Treat recommendation as permission |
| Human Approval Gate | Approve or queue sensitive operations | Infer approval from execution |
| Execution Agent | Enforce registration, authorization, approval, and idempotency | Bypass controls |
| Distribution Agent | Enforce destination eligibility | Deliver failed or refused operations |
| Trace and Audit Subsystem | Build component trace and hash-linked audit | Claim certification from trace presence |

### Interaction sequence

```text
Event
  -> Evidence Release
  -> Institutional Projection
  -> Institutional Assessment Agents
  -> Coordination Agent
  -> Evidence Agent
  -> Policy Governance Agent
  -> Human Approval Gate when required
  -> Execution Agent
  -> Distribution Agent
  -> Trace and Audit Subsystem
```

## 12. Failure and error scenario demonstration

### Approved evidence unavailable

Expected:

```yaml
approved_passage_found: false
evidence_gap_created: true
binding_finding_created: false
```

Show in **Evidence and Gaps**.

### Passage hash mismatch

Expected: passage rejected. Demonstrate through the passage-hash verifier or a controlled test, not by modifying committed evidence during the final presentation.

### Unknown theme or policy mapping

Expected: resolution fails without fabricating evidence.

### Approval missing

```yaml
approval_required: true
approval_decision: absent
execution_state: review_queued
distribution_effect: none
```

Show in **Four Scenarios**.

### Unregistered operation

Expected: execution is not attempted.

### Unregistered destination

```yaml
operation: targeted_ad_dispatch
destination: SYNTHETIC-AD-SINK
destination_registered: false
execution_state: not_attempted
distribution_effect: prevented
```

Show in the targeted-advertising stage.

### Idempotency conflict

Expected: the request is rejected when the same idempotency key is reused with a different digest.

### Audit hash changed

Expected: audit verification fails.

### Manifested artifact changed

Expected: manifest state becomes stale or invalid.

### Readiness evidence incomplete

```yaml
scored_metrics: 14
applicable_metrics: 19
coverage: 0.736842
required_coverage: 0.80
overall_project_score: null
```

Show in **Evidence Coverage** and **Pending Gates**.

## 13. Regenerate Y.3172 and agent artifacts

```cmd
.venv\Scripts\python.exe tools\standards\generate_y3172_mapping.py
.venv\Scripts\python.exe tools\submission\generate_agent_architecture.py
```

Expected:

```text
entry_count=13
agent_count=8
```

The Y.3172 artifact must preserve:

```yaml
formal_conformance: false
itu_certification: false
```

## 14. Regenerate readiness artifacts

```cmd
.venv\Scripts\python.exe tools\readiness\generate_readiness_reflection.py
.venv\Scripts\python.exe tools\readiness\generate_readiness_evidence_plan.py
```

Expected:

```yaml
scored_proxy_metrics: 14
applicable_proxy_metrics: 19
evidence_coverage: 0.736842
minimum_required_coverage: 0.80
overall_project_score: null
```

## 15. Regenerate SBOM and closure evidence

```cmd
.venv\Scripts\python.exe tools\evidence\generate_sbom.py
.venv\Scripts\python.exe tools\readiness\generate_closure_evidence.py
.venv\Scripts\python.exe tools\readiness\apply_verified_readiness_closure.py
```

Expected:

```text
accepted_metric_ids=
pending_metric_ids=D11-M01,F5-M01
updated_metric_ids=
refused_metric_ids=D11-M01,F5-M01
```

## 16. Verify passage provenance

```cmd
.venv\Scripts\python.exe tools\evidence\verify_passage_hashes.py
```

Expected: 90 approved passage hashes verify.

## 17. Regenerate the final manifest

Run after all required documents and final report files exist:

```cmd
.venv\Scripts\python.exe tools\submission\generate_submission_manifest.py
.venv\Scripts\python.exe tools\submission\verify_submission_manifest.py
```

A valid result includes:

```json
{"failures": [], "valid": true}
```

## 18. Reusability verification

Use `submission/artifacts/agent_architecture.json` to inspect each agent's:

```text
responsibility
inputs
outputs
interactions
fail_closed_behavior
reusable_core
domain_specific_configuration
education_example
agriculture_example
finance_example
```

The reusable architecture does not copy a conclusion from one domain into another. It reuses evidence verification, mandate projection, assessment, conflict preservation, approval, execution, destination control, trace, and audit contracts while replacing domain evidence, mandates, policies, operations, and destinations.

## 19. English and optional language support

English is the complete and authoritative prototype language. Additional languages should be additive, not substitutes. A limited Amharic orientation layer may cover navigation labels and demonstration summaries after review. Verified passages and standards language should remain in their source language unless a reviewed translation is available.

## 20. Known warnings

The verified suite emits three non-blocking warnings:

- FAISS uses a deprecated `distutils` version helper.
- setuptools exposes the corresponding deprecation warning.
- Transformers reports a future default change for `clean_up_tokenization_spaces`.

Do not suppress warnings by altering runtime behavior shortly before submission.

## 21. Troubleshooting

### UI starts but is not visible

Clear inherited offscreen mode:

```cmd
set "QT_QPA_PLATFORM="
run_amba.bat
```

The portable launcher already performs this safeguard.

### `No module named amba_ai`

```cmd
set "PYTHONPATH=%CD%\src"
```

### Missing model on first run

Ensure internet access during setup. Do not fabricate data if model download is unavailable. Review committed deterministic artifacts instead.

### Manifest reports stale

Regenerate dependent artifacts first and the manifest last. Never edit hashes manually.

### Score remains withheld

This is expected until evidence coverage reaches 80% under the project methodology. Do not fabricate `F5-M01` or `D11-M01` closure evidence.

## 22. Evaluation checklist

```text
[ ] Software stack explained
[ ] Minimum and recommended hardware explained
[ ] CPU-only execution stated
[ ] Complete application launches
[ ] Focused dashboard launches
[ ] Four scenarios execute
[ ] Each agent's function and boundary shown
[ ] Agent interactions shown
[ ] Approval-missing error demonstrated
[ ] Unregistered-destination prevention demonstrated
[ ] Evidence-gap behavior demonstrated
[ ] Audit or manifest failure behavior explained
[ ] Education, agriculture, and finance reuse shown
[ ] 13 Y.3172 mappings inspectable
[ ] 90 passage hashes verified
[ ] 14/19 readiness evidence state shown
[ ] Score-withheld boundary shown
[ ] D11-M01 and F5-M01 pending
[ ] Final manifest valid
```
