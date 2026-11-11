from __future__ import annotations
import pytest
from amba_ai.governance.models import AuthorizationBasisType
from amba_ai.ui.governance_context import DesktopGovernanceContextFactory

@pytest.mark.parametrize("method,operation,destination",(
("summarize_document","learning.summary.generate","desktop.summary"),
("generate_notes","learning.notes.generate","desktop.notes"),
("generate_study_assets","learning.flashcards.generate","desktop.study"),
("tutor_chat","learning.tutor.answer","desktop.tutor"),
("tutor_answer","learning.tutor.answer","desktop.tutor"),
("tutor_retrieve","learning.tutor.retrieve","internal.retrieval"),
))
def test_learner_context_is_operation_scoped(method,operation,destination):
 context=DesktopGovernanceContextFactory(session_id="desktop-test").for_operation(method,document_id=7)
 basis=context.authorization_basis
 assert context.destination_id==destination
 assert context.stage_id==f"{operation}:document-7"
 assert basis is not None
 assert basis.basis_type is AuthorizationBasisType.PROJECT_FIXTURE
 assert basis.authority_reference=="LEARNER-EDUCATIONAL-OPERATIONS-V1"
 assert basis.purposes==(operation,)
 assert basis.processing_operations==(operation,)
 assert basis.synthetic is True and basis.legal_effect is False
 assert len(basis.artifact_hash)==64

def test_learner_context_rejects_teacher_only_operation():
 factory=DesktopGovernanceContextFactory(session_id="desktop-test")
 with pytest.raises(ValueError,match="no authorized destination"):
  factory.for_operation("learning.document.delete",document_id=7)
