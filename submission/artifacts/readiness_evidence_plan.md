# AMBA-GOV Readiness Evidence-Coverage Closure Plan

> This plan identifies evidence needed to increase defensible project-level coverage. It does not change statuses, lower thresholds, guarantee a score, claim an official ITU score, or establish national AI readiness.

## Current state

- Scored applicable metrics: `14/19`
- Coverage ratio: `0.736842`
- Required ratio: `0.8`
- Overall project score: `None`
- Score status: `withheld_insufficient_evidence_coverage`

## Minimum threshold-closure plan

- Selected metrics: `D11-M01, F5-M01`
- Projected scored metrics: `16`
- Projected coverage: `0.842105`
- Threshold reached: `true`
- Selection basis: minimum metric count, then delivery risk, external dependency, preferred closure, and metric ID

## Metric evidence gaps

### D1-M01 · Data and model marketplace evidence
- Current status: `not_assessed`
- Delivery risk: `high`
- External dependency: `medium`
- Projected coverage if resolved alone: `0.789474`
- Threshold reached alone: `false`
- Missing evidence:
  - governed data or model catalog
  - licensing and permitted-use metadata
  - provenance and version controls
  - marketplace access and revocation controls
- Recommended actions:
  - define a synthetic governed catalog schema
  - register at least one versioned synthetic asset
  - test access, licensing, provenance, and revocation controls
- Acceptance criteria:
  - no personal or restricted production data is used
  - asset identity, version, license, provenance, and owner are explicit
  - access and revocation tests pass

### D11-M01 · Inclusion outcome evidence
- Current status: `insufficient_evidence`
- Delivery risk: `low`
- External dependency: `medium`
- Projected coverage if resolved alone: `0.789474`
- Threshold reached alone: `false`
- Missing evidence:
  - accessibility evaluation
  - affected-user participation
  - measured inclusion outcome
  - low-bandwidth or offline operation result
- Recommended actions:
  - run a WCAG 2.2 AA-oriented accessibility test protocol
  - capture low-bandwidth and offline-mode execution results
  - record an affected-user or representative review
  - publish measurable inclusion findings with limitations
- Acceptance criteria:
  - test protocol and results have immutable identifiers and SHA-256
  - accessibility findings distinguish tested from untested criteria
  - participation evidence documents scope and limitations
  - outcome measures are linked to the verified execution artifact

### D2-M01 · Generated-content marketplace evidence
- Current status: `not_assessed`
- Delivery risk: `high`
- External dependency: `medium`
- Projected coverage if resolved alone: `0.789474`
- Threshold reached alone: `false`
- Missing evidence:
  - generated-content provenance model
  - labeling and rights metadata
  - content review and withdrawal controls
- Recommended actions:
  - define a synthetic generated-content registry
  - record generation provenance and rights metadata
  - test review, withdrawal, and audit behavior
- Acceptance criteria:
  - generated content is synthetic and clearly labeled
  - provenance and rights metadata are mandatory
  - withdrawal and audit tests pass

### F2-M01 · Research capability evidence
- Current status: `not_assessed`
- Delivery risk: `medium`
- External dependency: `medium`
- Projected coverage if resolved alone: `0.789474`
- Threshold reached alone: `false`
- Missing evidence:
  - documented research question and evaluation protocol
  - reproducible experiment or comparative evaluation results
  - reviewed findings linked to project decisions
- Recommended actions:
  - publish an experiment protocol under docs/research
  - execute and archive a reproducible comparative evaluation
  - link reviewed findings to the evidence-chain artifact
- Acceptance criteria:
  - protocol has immutable identifier and SHA-256
  - results include dataset, configuration, and execution provenance
  - finding is reviewed and referenced by an approved evidence record

### F5-M01 · Open-source governance evidence
- Current status: `not_assessed`
- Delivery risk: `low`
- External dependency: `low`
- Projected coverage if resolved alone: `0.789474`
- Threshold reached alone: `false`
- Missing evidence:
  - explicit software license
  - contribution governance policy
  - security vulnerability disclosure policy
  - dependency inventory or software bill of materials
- Recommended actions:
  - add an approved LICENSE file
  - add CONTRIBUTING.md and CODE_OF_CONDUCT.md
  - add SECURITY.md with coordinated disclosure instructions
  - generate and verify a CycloneDX SBOM from requirements.txt
- Acceptance criteria:
  - license identity is explicit and repository-tracked
  - contribution and security policies are repository-tracked
  - SBOM is reproducibly generated and hash-verified
