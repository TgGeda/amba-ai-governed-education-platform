from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Slot, QThreadPool
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QSplitter,
    QHeaderView,
    QMessageBox,
    QCheckBox,
)

from amba_ai.config import EXPORTS_DIR
from amba_ai.core.ocr_loader import WindowsOcrLoader
from amba_ai.logger import logger
from amba_ai.ui.workers import FunctionWorker


def _get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    Case/schema tolerant getter.

    Supports both:
    - C# PascalCase: Engine, Lines, Words, Box
    - JSON camelCase: engine, lines, words, box
    - older schema names: EngineName, ExecutionTimeMs, BoundingBox
    """
    for key in keys:
        if key in data:
            return data[key]

    lowered = {str(k).lower(): v for k, v in data.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None:
            return value

    return default


def _as_ocr_result_list(payload: Any) -> list[dict[str, Any]]:
    """
    Normalize OCR loader output into a list of OCR result dictionaries.

    Accepts:
    - [OcrResult, OcrResult]
    - {"legacy": {...}, "modern": {...}}
    - {"Legacy": {...}, "Modern": {...}}
    - {"results": [...]}
    - {"Results": [...]}
    - single OcrResult dict
    """
    if payload is None:
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    results = _get(payload, "results", "Results")
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict)]

    extracted: list[dict[str, Any]] = []

    legacy = _get(payload, "legacy", "Legacy")
    modern = _get(payload, "modern", "Modern")

    if isinstance(legacy, dict):
        extracted.append(legacy)

    if isinstance(modern, dict):
        extracted.append(modern)

    if extracted:
        return extracted

    if _get(payload, "engine", "Engine", "EngineName"):
        return [payload]

    return []


class ImageOverlayWidget(QLabel):
    """QLabel that draws OCR bounding boxes or confidence heatmaps over an image."""

    def __init__(self) -> None:
        super().__init__()

        self._pixmap: QPixmap | None = None
        self._ocr_data: dict[str, Any] | None = None
        self._show_heatmap = False

        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(360, 320)

    def set_image(self, path: str) -> None:
        pixmap = QPixmap(path)

        if pixmap.isNull():
            self._pixmap = None
            self.clear()
            return

        self._pixmap = pixmap
        self.update_overlay()

    def clear_ocr_data(self) -> None:
        self._ocr_data = None
        self.update_overlay()

    def set_ocr_data(
        self,
        data: dict[str, Any] | None,
        show_heatmap: bool,
    ) -> None:
        self._ocr_data = data
        self._show_heatmap = show_heatmap
        self.update_overlay()

    def update_overlay(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return

        canvas = self._pixmap.copy()
        painter = QPainter(canvas)

        try:
            if self._ocr_data:
                image_width = canvas.width()
                image_height = canvas.height()

                lines = _get(self._ocr_data, "lines", "Lines", default=[]) or []

                for line in lines:
                    if not isinstance(line, dict):
                        continue

                    words = _get(line, "words", "Words", default=[]) or []

                    for word in words:
                        if not isinstance(word, dict):
                            continue

                        box = _get(word, "box", "Box", "boundingBox", "BoundingBox")
                        if not isinstance(box, dict):
                            continue

                        confidence = float(
                            _get(word, "confidence", "Confidence", default=1.0) or 0
                        )
                        confidence = max(0.0, min(1.0, confidence))

                        x, y, w, h = self._box_to_pixels(
                            box,
                            image_width,
                            image_height,
                        )

                        if w <= 0 or h <= 0:
                            continue

                        if self._show_heatmap:
                            red = int(255 * (1.0 - confidence))
                            green = int(255 * confidence)
                            painter.setBrush(QColor(red, green, 0, 95))
                            painter.setPen(Qt.NoPen)
                        else:
                            painter.setBrush(Qt.NoBrush)
                            painter.setPen(QPen(QColor(0, 120, 255), 2))

                        painter.drawRect(x, y, w, h)

        finally:
            painter.end()

        self.setPixmap(
            canvas.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    @staticmethod
    def _box_to_pixels(
        box: dict[str, Any],
        image_width: int,
        image_height: int,
    ) -> tuple[int, int, int, int]:
        x = float(_get(box, "x", "X", default=0) or 0)
        y = float(_get(box, "y", "Y", default=0) or 0)
        width = float(_get(box, "width", "Width", default=0) or 0)
        height = float(_get(box, "height", "Height", default=0) or 0)

        # Final C# OCR models export normalized coordinates 0.0–1.0.
        # This also supports older pixel-coordinate outputs.
        if 0 <= x <= 1 and 0 <= y <= 1 and 0 <= width <= 1 and 0 <= height <= 1:
            return (
                int(x * image_width),
                int(y * image_height),
                int(width * image_width),
                int(height * image_height),
            )

        return int(x), int(y), int(width), int(height)

    def resizeEvent(self, event) -> None:
        self.update_overlay()
        super().resizeEvent(event)


class ViewOcr(QWidget):
    """Enterprise OCR benchmarking and visualization dashboard."""

    def __init__(self) -> None:
        super().__init__()

        self.ocr_loader = WindowsOcrLoader()
        self.thread_pool = QThreadPool.globalInstance()

        self.current_image_path: str | None = None
        self.ocr_results: list[dict[str, Any]] = []
        self._active_worker: FunctionWorker | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()

        self.btn_load = QPushButton("Load Image")
        self.btn_run = QPushButton("Run OCR Benchmark")
        self.chk_heatmap = QCheckBox("Confidence Heatmap")
        self.btn_export = QPushButton("Export Reports")

        self.btn_load.clicked.connect(self.load_image)
        self.btn_run.clicked.connect(self.run_ocr)
        self.chk_heatmap.stateChanged.connect(self.toggle_heatmap)
        self.btn_export.clicked.connect(self.export_reports)

        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)

        toolbar.addWidget(self.btn_load)
        toolbar.addWidget(self.btn_run)
        toolbar.addWidget(self.chk_heatmap)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_export)

        splitter = QSplitter(Qt.Horizontal)

        self.legacy_view = ImageOverlayWidget()
        self.modern_view = ImageOverlayWidget()

        splitter.addWidget(self._wrap_view("Legacy OCR", self.legacy_view))
        splitter.addWidget(self._wrap_view("Modern OCR", self.modern_view))

        self.dashboard = QTableWidget(0, 7)
        self.dashboard.setHorizontalHeaderLabels(
            [
                "Engine",
                "Status",
                "Time (ms)",
                "Avg Conf",
                "Median",
                "Low Conf",
                "Words",
            ]
        )
        self.dashboard.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.dashboard.setFixedHeight(150)

        root.addLayout(toolbar)
        root.addWidget(splitter)
        root.addWidget(QLabel("<b>Benchmark Dashboard</b>"))
        root.addWidget(self.dashboard)

    def _wrap_view(self, title: str, widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel(f"<b>{title}</b>"))
        layout.addWidget(widget)
        return container

    def load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select OCR Test Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)",
        )

        if not path:
            return

        self.current_image_path = path
        self.ocr_results = []

        self.legacy_view.set_image(path)
        self.modern_view.set_image(path)
        self.legacy_view.clear_ocr_data()
        self.modern_view.clear_ocr_data()

        self.dashboard.setRowCount(0)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(False)

    def run_ocr(self) -> None:
        if not self.current_image_path:
            return

        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)

        try:
            worker = FunctionWorker(
                self.ocr_loader.recognize,
                image_path=self.current_image_path,
                lang_code="en-US",
                mode="both",
            )

            worker.signals.finished.connect(self.on_ocr_finished)
            self._active_worker = worker
            self.thread_pool.start(worker)

        except Exception as exc:
            logger.exception("Failed to start OCR worker")
            self.btn_run.setEnabled(True)
            QMessageBox.critical(self, "OCR Error", str(exc))

    @Slot(object)
    def on_ocr_finished(self, result) -> None:
        self.btn_run.setEnabled(True)

        if not getattr(result, "success", False):
            error = getattr(result, "error", "Unknown OCR worker error")
            QMessageBox.critical(self, "OCR Error", str(error))
            return

        self.ocr_results = _as_ocr_result_list(getattr(result, "result", None))

        if not self.ocr_results:
            QMessageBox.warning(
                self,
                "OCR Result",
                "OCR completed but returned no engine results.",
            )
            return

        self.btn_export.setEnabled(True)
        self._refresh_dashboard()
        self._refresh_overlays()

    def _refresh_dashboard(self) -> None:
        self.dashboard.setRowCount(len(self.ocr_results))

        for row, data in enumerate(self.ocr_results):
            engine = str(_get(data, "engine", "Engine", "EngineName", default="Unknown"))
            status = str(_get(data, "status", "Status", default="Unknown"))
            elapsed = _get(data, "elapsedMs", "ElapsedMs", "executionTimeMs", "ExecutionTimeMs", default=0)
            avg_conf = float(_get(data, "averageConfidence", "AverageConfidence", default=0) or 0)
            median = float(_get(data, "medianConfidence", "MedianConfidence", default=0) or 0)
            low_count = int(_get(data, "lowConfidenceCount", "LowConfidenceCount", default=0) or 0)

            lines = _get(data, "lines", "Lines", default=[]) or []
            word_count = sum(
                len(_get(line, "words", "Words", default=[]) or [])
                for line in lines
                if isinstance(line, dict)
            )

            values = [
                engine,
                status,
                str(elapsed),
                f"{avg_conf:.3f}",
                f"{median:.3f}",
                str(low_count),
                str(word_count),
            ]

            for col, value in enumerate(values):
                self.dashboard.setItem(row, col, QTableWidgetItem(value))

    def _refresh_overlays(self) -> None:
        self.legacy_view.clear_ocr_data()
        self.modern_view.clear_ocr_data()

        heatmap = self.chk_heatmap.isChecked()

        for data in self.ocr_results:
            engine = str(_get(data, "engine", "Engine", "EngineName", default=""))

            if engine.lower() == "legacyocr":
                self.legacy_view.set_ocr_data(data, heatmap)
            elif engine.lower() == "modernocr":
                self.modern_view.set_ocr_data(data, heatmap)

    def toggle_heatmap(self) -> None:
        self._refresh_overlays()

    def export_reports(self) -> None:
        if not self.ocr_results:
            return

        try:
            export_dir = Path(EXPORTS_DIR)
            export_dir.mkdir(parents=True, exist_ok=True)

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = export_dir / f"ocr_benchmark_{stamp}.json"
            csv_path = export_dir / f"ocr_words_{stamp}.csv"

            with json_path.open("w", encoding="utf-8") as handle:
                json.dump(self.ocr_results, handle, indent=2, ensure_ascii=False)

            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "engine",
                        "language",
                        "line_index",
                        "word_index",
                        "text",
                        "confidence",
                        "x",
                        "y",
                        "width",
                        "height",
                    ]
                )

                for data in self.ocr_results:
                    engine = _get(data, "engine", "Engine", "EngineName", default="")
                    language = _get(data, "language", "Language", default="")
                    lines = _get(data, "lines", "Lines", default=[]) or []

                    for line_index, line in enumerate(lines):
                        if not isinstance(line, dict):
                            continue

                        words = _get(line, "words", "Words", default=[]) or []

                        for word_index, word in enumerate(words):
                            if not isinstance(word, dict):
                                continue

                            box = _get(word, "box", "Box", "boundingBox", "BoundingBox")
                            if not isinstance(box, dict):
                                continue

                            writer.writerow(
                                [
                                    engine,
                                    language,
                                    line_index,
                                    word_index,
                                    _get(word, "text", "Text", default=""),
                                    _get(word, "confidence", "Confidence", default=0),
                                    _get(box, "x", "X", default=0),
                                    _get(box, "y", "Y", default=0),
                                    _get(box, "width", "Width", default=0),
                                    _get(box, "height", "Height", default=0),
                                ]
                            )

            QMessageBox.information(
                self,
                "Export Complete",
                f"Saved:\n{json_path}\n{csv_path}",
            )

        except Exception as exc:
            logger.exception("Failed to export OCR reports")
            QMessageBox.critical(self, "Export Error", str(exc))