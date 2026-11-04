from __future__ import annotations

from .domain_plugin import DomainPlugin
from .domain_registry import DomainRegistry, domain_registry

from .multimodal import (
    FigureType,
    LearningContentBundle,
    LearningFigure,
    LearningTable,
    MULTIMODAL_SCHEMA_VERSION,
    SourceRegion,
)
from .multimodal_parser import MultimodalLearningParser
from .multimodal_validator import (
    MultimodalIssue,
    MultimodalLearningValidator,
    MultimodalValidationReport,
)
from .parser import DocumentAgnosticLearningParser
from .schemas import (
    LearningConcept,
    LearningDocument,
    LearningSection,
    SCHEMA_VERSION,
    SourceCitation,
    TechnicalBlock,
    ValidationIssue,
    ValidationReport,
)
from .source_resolver import resolve_source_name
from .validator import LearningDocumentValidator

__all__ = [
    "DocumentAgnosticLearningParser",
    "DomainPlugin",
    "DomainRegistry",
    "FigureType",
    "LearningConcept",
    "LearningContentBundle",
    "LearningDocument",
    "LearningDocumentValidator",
    "LearningFigure",
    "LearningSection",
    "LearningTable",
    "MULTIMODAL_SCHEMA_VERSION",
    "MultimodalIssue",
    "MultimodalLearningParser",
    "MultimodalLearningValidator",
    "MultimodalValidationReport",
    "SCHEMA_VERSION",
    "SourceCitation",
    "SourceRegion",
    "TechnicalBlock",
    "ValidationIssue",
    "ValidationReport",
    "domain_registry",
    "resolve_source_name",
]