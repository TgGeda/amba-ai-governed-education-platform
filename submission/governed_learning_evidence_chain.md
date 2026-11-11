# Governed Learning Evidence Chain

- Synthetic demonstration only
- No legal effect
- Y.3172-oriented project mapping
- Not formal ITU conformance or certification

## Correlation context

- Correlation ID: `EDU-CORR-DEMO-001`
- Session ID: `SESSION-DEMO-001`
- Principal ID: `SYNTHETIC-LEARNER-01`
- Operation ID: `learning.tutor.answer`
- Document ID: `1`
- Runtime request ID: `EDU-REQUEST-DEMO-001`
- Trace ID: `EDU-TRACE-DEMO-001`

## Verified chain

1. `user_action`: details `11bada347d7a7f459834474d3bda31e4767e317b01884a516fde002d1dbd1ab9`, event `549376fa4cdb185d0629b52b3cf7081d16bca6337b07a964da5423dda4d5ac49`
2. `operation_authorization`: details `87747211282d13664302ee2055243d24644eb892635220ff5c9c6fb3a2983fac`, event `7229112b296b3dd7f085937e2d312f245097d66bf29d6c3b59d6613c1cbb87f1`
3. `source_digest_verified`: details `60f74390607ca8c2374bf555be0f7571afbb8b5ec7d1a4253bef94582ca92a95`, event `26cac84b4a3c3f10a587de919332f35b8db91513f993f8f22eee7ccf068e0409`
4. `chunk_decisions_recorded`: details `1bdb06edc6fa6c274dded3b66798c9bfd0fd1f9d9321f176d6593b1e3ac48eaa`, event `3027a4111a5ebe2a7d41da4b2ebf85802582da778ce7178eb7f7ee3dc64360dd`
5. `index_revision_published`: details `bb205a2468b498cd408b5215348a415119a298c2b4aafbda6d20a00c365a5cab`, event `b1d66f3deae5325025f85e4fef3e3854f305ed6cdc7ea3789054f2c45100a866`
6. `retrieval_receipt_created`: details `a04d8875cfb8ea7bf999cc613396639cdd5fb866c14f9082b069ef299d8c1dca`, event `9b6d6e277c74598b8e078fb93f651f452e271f8f7f3bb3cd10f8bab549060a29`
7. `generation_requested`: details `a1abfba7e4c8d04ad3a323bbdc17368dfe213c0104f8c37f8d7ee95f6c8cb9c1`, event `4583cc1f010d389519c9ab3305cc80d19a8a9ddd3a278e63b956784b1ec61663`
8. `output_validated`: details `1cd836e27f3af011a392ad41283d7d2d52b3c872d69b788b56046f7490c3bc03`, event `24c80b57dc8df7d37118c225ef25b10b1019ccb993446f58bcd8a3ba00cd3537`
9. `sink_receipt_created`: details `6de7a2d92a0f0e6f2f345f9aae9dd91ec9a7f9982e531074ecd33c039e8f740e`, event `3b84a970ff4a45bd9b1cbe355b2339ef84afef8fb4760a6d171f8c53a93c7b93`
10. `distribution_completed_or_prevented`: details `a1a3980c2d1c354c5ec961daa1345700cf86a26d0da4a1a7c076231624254aa2`, event `0f2c00f558e4312c0fa6532a81f815a892a3cedc995aaf224d6c3245819383b8`
11. `trace_completed`: details `37d860027e11f87d4c9a35cd4368f422d0631369c0033cc3f8d5250296420f58`, event `d51f1d5a65d512e0a840f611397f9cc2268eb160d2ac1191215753f17f019afd`
12. `audit_block_verified`: details `9ee67e4a987e061e55c37f56d5e2b6b4da35d24f50a575bdae6b1d13296bd794`, event `3caf81f1a331523cf0a5b4ae5a72049a70b0d1d4037418ef1c8c1aa585a6b193`

## Evidence status

- Audit verified: `True`
- Missing required events: `[]`
- Evidence-chain SHA-256: `1feb3376461575c975ff6d383edf94e0d152a9a7567a7e9aeb38e66420cb384e`
- Source-inventory SHA-256: `640174ff62da335b9bd3568154625f23a12bfc957ed8b59137af08f957fffeff`

## Test matrix

- `test_application_composition.py`: One shared service graph
- `test_governed_document_ingestion.py`: Upload through governed indexed corpus
- `test_governed_index_rebuild.py`: Recovery preserves exclusions
- `test_governed_hybrid_retrieval.py`: FAISS and BM25 use one allowlist
- `test_governed_tutor_answer.py`: Tutor request through governed delivery
- `test_governance_review_lifecycle.py`: Approve, redact, reject, and revoke
- `test_governed_document_deletion.py`: Deletion and tombstone
- `test_policy_evidence_pipeline.py`: Policy authority and provenance
- `test_learning_governance_scenarios.py`: Real product learning scenarios
- `test_complete_governed_learning_chain.py`: Full user-action-to-audit chain