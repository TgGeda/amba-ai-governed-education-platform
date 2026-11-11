from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QModelIndex, QSettings, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from amba_ai.logger import logger
from amba_ai.ui.common.qss_utils import apply_local_qss
from amba_ai.ui.common.ui_icons_utils import icon
from .data_classes import ReviewDecisionHistoryItem, ReviewItemViewModel
from .review_manager import GovernanceReviewManager


class GovernanceReviewWidget(QWidget):
    reviewDecided = Signal(dict)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    COL_CHUNK_ID = 0
    COL_STATUS = 1
    COL_FINDINGS = 2
    COL_PREVIEW = 3
    TOTAL_COLUMNS = 4

    def __init__(
        self,
        settings: QSettings,
        services: Any,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.services = services
        self.review_manager = GovernanceReviewManager(
            review_service=services.governance_review_service,
            services=services,
            parent=self,
        )
        self.document_id: int | None = None
        self._items: list[ReviewItemViewModel] = []
        self._selected_item: ReviewItemViewModel | None = None
        self.model = QStandardItemModel(0, self.TOTAL_COLUMNS, self)
        self.setObjectName("AmbaGovernanceReviewWidgetUI")
        self._setup_ui()
        self._connect_signals()
        self.apply_feature_style()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("reviewSplitter")

        left = QFrame()
        left.setObjectName("reviewSidebar")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)
        heading = QLabel(self.tr("Document Chunks Queue"))
        heading.setObjectName("reviewHeaderTitle")
        left_layout.addWidget(heading)
        self.refresh_btn = QPushButton(icon("refresh"), self.tr("Refresh Queue"))
        left_layout.addWidget(self.refresh_btn)
        self.tree_view = QTreeView()
        self.tree_view.setObjectName("chunkTreeView")
        self.tree_view.setModel(self.model)
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree_view.setUniformRowHeights(True)
        self.model.setHorizontalHeaderLabels(
            [self.tr("Chunk ID"), self.tr("Status"), self.tr("Findings"), self.tr("Preview")]
        )
        header = self.tree_view.header()
        header.setSectionResizeMode(self.COL_CHUNK_ID, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_FINDINGS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_PREVIEW, QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.tree_view, 1)
        splitter.addWidget(left)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        workspace = QFrame()
        workspace.setObjectName("reviewWorkspace")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title = QLabel(self.tr("Teacher & Administrator Review Desk"))
        title.setObjectName("reviewHeaderTitle")
        subtitle = QLabel(
            self.tr(
                "Examine findings, enforce redactions, approve, reject, or revoke governed chunks."
            )
        )
        subtitle.setObjectName("reviewHeaderSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("reviewCard")
        card_layout = QVBoxLayout(card)
        self.lbl_doc_title = QLabel(self.tr("Document: None"))
        self.lbl_doc_title.setObjectName("fieldValueLabel")
        self.lbl_doc_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_source_digest = QLabel(self.tr("Source Digest: None"))
        self.lbl_source_digest.setObjectName("fieldValueLabel")
        self.lbl_source_digest.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_status = QLabel(self.tr("Status: -"))
        self.lbl_status.setObjectName("statusBadgePending")
        self.lbl_findings = QLabel(self.tr("Risk Findings: None"))
        self.lbl_permitted_ops = QLabel(self.tr("Permitted Operations: None"))
        self.lbl_restricted_ops = QLabel(self.tr("Restricted Operations: None"))
        for widget in (
            self.lbl_findings,
            self.lbl_permitted_ops,
            self.lbl_restricted_ops,
        ):
            widget.setObjectName("fieldValueLabel")
        for widget in (
            self.lbl_doc_title,
            self.lbl_source_digest,
            self.lbl_status,
            self.lbl_findings,
            self.lbl_permitted_ops,
            self.lbl_restricted_ops,
        ):
            card_layout.addWidget(widget)
        layout.addWidget(card)

        layout.addWidget(self._tag("Effective Governed Text"))
        self.chunk_browser = QTextBrowser()
        self.chunk_browser.setObjectName("chunkTextBrowser")
        self.chunk_browser.setFixedHeight(145)
        layout.addWidget(self.chunk_browser)
        self.reveal_original = QCheckBox(self.tr("Reveal protected original source text"))
        self.reveal_original.setToolTip(
            self.tr("Available only to teacher and school-administrator reviewers.")
        )
        layout.addWidget(self.reveal_original)

        layout.addWidget(self._tag("Previous Review Decisions (Append-Only Audit)"))
        self.history_browser = QTextBrowser()
        self.history_browser.setObjectName("historyBrowser")
        self.history_browser.setFixedHeight(120)
        layout.addWidget(self.history_browser)

        form = QFrame()
        form.setObjectName("reviewCard")
        form_layout = QVBoxLayout(form)
        form_layout.addWidget(self._tag("Execute Governance Decision"))
        role_row = QHBoxLayout()
        role_row.addWidget(QLabel(self.tr("Reviewer Role:")))
        self.role_combo = QComboBox()
        self.role_combo.addItems(["teacher", "school_administrator"])
        role_row.addWidget(self.role_combo, 1)
        form_layout.addLayout(role_row)
        form_layout.addWidget(QLabel(self.tr("Proposed redactions, one exact string per line:")))
        self.redactions_edit = QPlainTextEdit()
        self.redactions_edit.setObjectName("redactionsEditor")
        self.redactions_edit.setMaximumHeight(78)
        self.redactions_edit.setPlaceholderText(
            self.tr("learner@example.com\nStudent ID: ABC-123")
        )
        form_layout.addWidget(self.redactions_edit)
        rationale_row = QHBoxLayout()
        rationale_row.addWidget(QLabel(self.tr("Rationale:")))
        self.rationale_edit = QLineEdit()
        self.rationale_edit.setPlaceholderText(
            self.tr("Mandatory reason for the governance decision")
        )
        rationale_row.addWidget(self.rationale_edit, 1)
        form_layout.addLayout(rationale_row)
        actions = QHBoxLayout()
        self.btn_approve = self._button("Approve", "btnApprove")
        self.btn_approve_redacted = self._button(
            "Approve with Redactions", "btnApproveRedacted"
        )
        self.btn_reject = self._button("Reject", "btnReject")
        self.btn_revoke = self._button("Revoke", "btnRevoke")
        for button in (
            self.btn_approve,
            self.btn_approve_redacted,
            self.btn_reject,
            self.btn_revoke,
        ):
            actions.addWidget(button)
        form_layout.addLayout(actions)
        layout.addWidget(form)

        self.receipt_banner = QFrame()
        self.receipt_banner.setObjectName("receiptBanner")
        self.receipt_banner.setVisible(False)
        receipt_layout = QHBoxLayout(self.receipt_banner)
        self.lbl_receipt = QLabel(self.tr("Receipt: None"))
        self.lbl_receipt.setObjectName("receiptText")
        self.lbl_receipt.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        receipt_layout.addWidget(self.lbl_receipt)
        layout.addWidget(self.receipt_banner)
        layout.addStretch(1)
        scroll.setWidget(workspace)
        splitter.addWidget(scroll)
        splitter.setSizes([380, 720])
        main_layout.addWidget(splitter)

    def _tag(self, text: str) -> QLabel:
        label = QLabel(self.tr(text))
        label.setObjectName("fieldTagLabel")
        return label

    def _button(self, text: str, object_name: str) -> QPushButton:
        button = QPushButton(self.tr(text))
        button.setObjectName(object_name)
        return button

    def _connect_signals(self) -> None:
        self.tree_view.selectionModel().currentChanged.connect(
            self._on_tree_selection_changed
        )
        self.refresh_btn.clicked.connect(self.reload_queue)
        self.reveal_original.toggled.connect(self._render_selected_item)
        self.btn_approve.clicked.connect(lambda: self._submit_disposition("approve"))
        self.btn_approve_redacted.clicked.connect(
            lambda: self._submit_disposition("approve_with_redactions")
        )
        self.btn_reject.clicked.connect(lambda: self._submit_disposition("reject"))
        self.btn_revoke.clicked.connect(lambda: self._submit_disposition("revoke"))
        self.review_manager.itemsLoaded.connect(self._on_items_loaded)
        self.review_manager.reviewStarted.connect(lambda _subject: self._set_buttons_enabled(False))
        self.review_manager.reviewCompleted.connect(self._on_review_completed)
        self.review_manager.reviewFailed.connect(self._on_review_failed)
        self.review_manager.statusMessage.connect(self.statusMessage.emit)
        self.review_manager.operationStarted.connect(self.operationStarted.emit)
        self.review_manager.operationFinished.connect(self.operationFinished.emit)

    def apply_feature_style(self) -> None:
        qss_path = Path(__file__).parent / "governance_review.qss"
        if qss_path.exists():
            apply_local_qss(self, qss_path)

    @Slot(int)
    def set_document(self, document_id: int) -> None:
        self.document_id = int(document_id)
        self.reload_queue()

    @Slot()
    def reload_queue(self) -> None:
        if self.document_id is None:
            self._render_empty_state()
            return
        self.review_manager.load_document_chunks(self.document_id)

    @Slot(list)
    def _on_items_loaded(self, payload: list[dict[str, Any]]) -> None:
        self._items = [
            ReviewItemViewModel(
                document_id=int(data["document_id"]),
                document_title=str(data["document_title"]),
                chunk_id=int(data["chunk_id"]),
                chunk_text=str(data["chunk_text"]),
                source_digest=str(data["source_digest"]),
                risk_findings=tuple(data.get("risk_findings") or ()),
                current_status=str(data.get("current_status") or "pending"),
                permitted_operations=tuple(data.get("permitted_operations") or ()),
                restricted_operations=tuple(data.get("restricted_operations") or ()),
                proposed_redactions=tuple(data.get("proposed_redactions") or ()),
                previous_reviews=tuple(
                    ReviewDecisionHistoryItem(**item)
                    for item in data.get("previous_reviews") or ()
                ),
                effective_review_id=data.get("effective_review_id"),
                effective_text=data.get("effective_text"),
            )
            for data in payload
        ]
        self.model.removeRows(0, self.model.rowCount())
        root = self.model.invisibleRootItem()
        for item in self._items:
            row = [
                QStandardItem(f"#{item.chunk_id}"),
                QStandardItem(item.current_status.upper()),
                QStandardItem(", ".join(item.risk_findings) or "-"),
                QStandardItem(item.chunk_text.replace("\n", " ")[:60]),
            ]
            row[0].setData(item.chunk_id, Qt.ItemDataRole.UserRole)
            row[1].setForeground(
                QColor(
                    "#34D399"
                    if item.current_status == "approved"
                    else "#FB7185"
                    if item.current_status in {"rejected", "revoked"}
                    else "#FCD34D"
                )
            )
            for cell in row:
                cell.setEditable(False)
            root.appendRow(row)
        if self._items:
            self.tree_view.setCurrentIndex(self.model.index(0, 0))
        else:
            self._render_empty_state()

    @Slot(QModelIndex, QModelIndex)
    def _on_tree_selection_changed(
        self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        if not current.isValid():
            self._selected_item = None
            return
        value = self.model.item(current.row(), self.COL_CHUNK_ID).data(
            Qt.ItemDataRole.UserRole
        )
        self._selected_item = next(
            (item for item in self._items if item.chunk_id == value), None
        )
        self.reveal_original.setChecked(False)
        self._render_selected_item()

    @Slot()
    def _render_selected_item(self) -> None:
        item = self._selected_item
        if item is None:
            self._render_empty_state()
            return
        self.lbl_doc_title.setText(
            f"Document: {item.document_title} (ID #{item.document_id})"
        )
        self.lbl_source_digest.setText(f"Source SHA-256: {item.source_digest}")
        self.lbl_status.setText(f"Status: {item.current_status.upper()}")
        status_objects = {
            "approved": "statusBadgeApproved",
            "rejected": "statusBadgeRejected",
            "revoked": "statusBadgeRevoked",
        }
        self.lbl_status.setObjectName(
            status_objects.get(item.current_status.lower(), "statusBadgePending")
        )
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self.lbl_findings.setText(
            "Risk Findings: " + (", ".join(item.risk_findings) or "None detected")
        )
        self.lbl_permitted_ops.setText(
            "Permitted Operations: "
            + (", ".join(item.permitted_operations) or "None")
        )
        self.lbl_restricted_ops.setText(
            "Restricted Operations: "
            + (", ".join(item.restricted_operations) or "None")
        )
        effective = item.effective_text or item.chunk_text
        if self.reveal_original.isChecked():
            self.chunk_browser.setHtml(
                "<b style='color:#F59E0B;'>Protected Original Source Text</b><br/>"
                + html.escape(item.chunk_text)
            )
        else:
            self.chunk_browser.setHtml(
                "<b style='color:#34D399;'>Effective Governed Text</b><br/>"
                + html.escape(effective)
            )
        self.redactions_edit.setPlainText("\n".join(item.proposed_redactions))
        if item.previous_reviews:
            lines = []
            for review in item.previous_reviews:
                redactions = (
                    f" | Redactions: {', '.join(review.redactions)}"
                    if review.redactions
                    else ""
                )
                supersedes = (
                    f" | Supersedes: {review.supersedes_review_id}"
                    if review.supersedes_review_id
                    else ""
                )
                lines.append(
                    f"• <b>[{review.disposition.upper()}]</b> by "
                    f"<i>{review.reviewer_role}</i> on {review.decided_at} — "
                    f"Rationale: {html.escape(review.rationale)}{redactions}{supersedes} "
                    f"<span style='color:#2DD4BF;'>"
                    f"(Receipt: {review.receipt_id})</span>"
                )
            self.history_browser.setHtml("<br/>".join(lines))
        else:
            self.history_browser.setHtml(
                "<i style='color:#64748B;'>No previous review decisions recorded.</i>"
            )
        self.btn_revoke.setEnabled(item.effective_review_id is not None)

    def _render_empty_state(self) -> None:
        self._selected_item = None
        self.lbl_doc_title.setText(self.tr("Document: None"))
        self.lbl_source_digest.setText(self.tr("Source Digest: None"))
        self.lbl_status.setText(self.tr("Status: -"))
        self.lbl_findings.setText(self.tr("Risk Findings: None"))
        self.lbl_permitted_ops.setText(self.tr("Permitted Operations: None"))
        self.lbl_restricted_ops.setText(self.tr("Restricted Operations: None"))
        self.chunk_browser.clear()
        self.history_browser.clear()
        self.redactions_edit.clear()
        self.rationale_edit.clear()
        self.receipt_banner.setVisible(False)

    def _submit_disposition(self, disposition: str) -> None:
        if self._selected_item is None:
            QMessageBox.warning(
                self, self.tr("No Selection"), self.tr("Select a chunk from the queue.")
            )
            return
        redactions = tuple(
            line.strip()
            for line in self.redactions_edit.toPlainText().splitlines()
            if line.strip()
        )
        payload = {
            "subject_id": str(self._selected_item.chunk_id),
            "document_id": self._selected_item.document_id,
            "disposition": disposition,
            "reviewer_role": self.role_combo.currentText(),
            "rationale": self.rationale_edit.text(),
            "redactions": redactions,
            "supersedes_review_id": (
                self._selected_item.effective_review_id
                if disposition == "revoke"
                else None
            ),
        }
        self.review_manager.submit_review(payload)

    @Slot(dict)
    def _on_review_completed(self, result: dict[str, Any]) -> None:
        self._set_buttons_enabled(True)
        self.lbl_receipt.setText(f"Receipt: {result.get('receipt_id', '')}")
        self.receipt_banner.setVisible(True)
        self.reviewDecided.emit(result)
        self.rationale_edit.clear()
        self.redactions_edit.clear()
        self.reload_queue()

    @Slot(dict)
    def _on_review_failed(self, error_context: dict[str, Any]) -> None:
        self._set_buttons_enabled(True)
        QMessageBox.critical(
            self,
            self.tr("Review Action Failed"),
            str(error_context.get("error_message") or "Governance review failed."),
        )

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.btn_approve.setEnabled(enabled)
        self.btn_approve_redacted.setEnabled(enabled)
        self.btn_reject.setEnabled(enabled)
        self.btn_revoke.setEnabled(
            enabled
            and bool(self._selected_item and self._selected_item.effective_review_id)
        )

    def cleanup_before_close(self) -> None:
        self.review_manager.cleanup_before_close()
        logger.info("GovernanceReviewWidget cleanup completed.")

    def retranslateUi(self) -> None:
        pass
