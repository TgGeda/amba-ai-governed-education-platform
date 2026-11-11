from __future__ import annotations

from amba_ai.ui.features.ingest.ingest_manager import IngestManager
from amba_ai.ui.workers import WorkerResult


class Jobs:
    pass


def test_one_task_failure_emits_one_ingestion_failure(qtbot):
    manager=IngestManager(Jobs())
    failures=[]
    manager.ingestionFailed.connect(failures.append)
    error={"error_message":"failed closed","error_type":"IngestionError"}
    manager._on_worker_error(error)
    manager._on_ingest_finished(
        WorkerResult(
            success=False,
            result=None,
            error_message="failed closed",
            task_name="Ingest File",
            metadata=error,
        )
    )
    assert len(failures) == 1
