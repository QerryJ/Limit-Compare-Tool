"""FV-1 (FT↔QA coverage) and FV-4 (before↔after) GUI modes.

Headless (``QT_QPA_PLATFORM=offscreen``). Skipped where PySide6 is absent.
The end-to-end runs use a real .pds that carries both FT and QA sides
in one file, so FV-1 needs no second program field.
"""

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6", reason="PySide6 not installed in this environment")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.ui.main_window import MODE_CHANGE, MODE_COVERAGE, APP_VERSION, MainWindow  # noqa: E402

from real_material import real_pds

REAL_PDS = real_pds()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_modes_present(app):
    window = MainWindow()
    texts = [window.mode_combo.itemText(i) for i in range(window.mode_combo.count())]
    assert MODE_COVERAGE in texts
    assert MODE_CHANGE in texts


def test_coverage_mode_relabels_and_enables_fields(app):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_COVERAGE)
    assert window.program_label.text() == "FT 程序:"
    assert window.gu_label.text() == "QA 程序:"
    assert window.program_edit.isEnabled()
    assert window.gu_program_edit.isEnabled()
    assert not window.pe_edit.isEnabled()


def test_change_mode_relabels_fields(app):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_CHANGE)
    assert window.program_label.text() == "基准程序:"
    assert window.gu_label.text() == "新程序:"
    assert window.program_edit.isEnabled()
    assert window.gu_program_edit.isEnabled()


@pytest.mark.skipif(not REAL_PDS, reason="sample material not available")
def test_run_coverage_through_gui(app):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_COVERAGE)
    window.program_edit.setText(REAL_PDS)
    window._run_coverage()
    assert window.result_kind == "coverage"
    assert "覆盖率" in window.coverage_report.summary
    window._refresh_table()
    assert window.table.columnCount() == 11


@pytest.mark.skipif(not REAL_PDS, reason="sample material not available")
def test_run_change_identical_programs(app):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_CHANGE)
    window.program_edit.setText(REAL_PDS)
    window.gu_program_edit.setText(REAL_PDS)
    window._run_change()
    assert window.result_kind == "change"
    assert window.compare_report.summary.get("放宽风险", 0) == 0
    window._refresh_table()
    assert window.table.columnCount() == 5


@pytest.mark.skipif(not REAL_PDS, reason="sample material not available")
def test_export_xlsx_coverage_via_gui(app, tmp_path):
    """GUI XLSX export for FV-1 must dispatch to export_coverage_report."""
    from openpyxl import load_workbook

    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_COVERAGE)
    window.program_edit.setText(REAL_PDS)
    window._run_coverage()
    window._refresh_table()
    assert window.result_kind == "coverage"

    out = str(tmp_path / "coverage.xlsx")
    with mock.patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(out, "Excel (*.xlsx)"),
    ):
        window._export_xlsx()
    assert os.path.exists(out)
    wb = load_workbook(out)
    assert "摘要" in wb.sheetnames
    assert "未覆盖(需处理)" in wb.sheetnames
    assert "全部明细" in wb.sheetnames


@pytest.mark.skipif(not REAL_PDS, reason="sample material not available")
def test_export_xlsx_change_via_gui(app, tmp_path):
    """GUI XLSX export for FV-4 must dispatch to export_compare_report."""
    from openpyxl import load_workbook

    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_CHANGE)
    window.program_edit.setText(REAL_PDS)
    window.gu_program_edit.setText(REAL_PDS)
    window._run_change()
    window._refresh_table()
    assert window.result_kind == "change"

    out = str(tmp_path / "change.xlsx")
    with mock.patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(out, "Excel (*.xlsx)"),
    ):
        window._export_xlsx()
    assert os.path.exists(out)
    wb = load_workbook(out)
    assert "摘要" in wb.sheetnames
    assert "放宽风险" in wb.sheetnames
    assert "全部明细" in wb.sheetnames


@pytest.mark.skipif(not REAL_PDS, reason="sample material not available")
def test_export_html_change_via_gui(app, tmp_path):
    """GUI HTML export for FV-4 must dispatch to export_html_report (offline)."""
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_CHANGE)
    window.program_edit.setText(REAL_PDS)
    window.gu_program_edit.setText(REAL_PDS)
    window._run_change()
    window._refresh_table()
    assert window.result_kind == "change"

    out = str(tmp_path / "change.html")
    with mock.patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(out, "HTML (*.html)"),
    ):
        window._export_html()
    assert os.path.exists(out)
    content = open(out, encoding="utf-8").read()
    # Offline single-file contract: inline CSS, no CDN <link>/script src.
    assert "<style" in content
    assert "<link" not in content
    assert "cdn" not in content.lower()


@pytest.mark.skipif(not REAL_PDS, reason="sample material not available")
def test_filter_coverage_all_then_anomaly(app):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_COVERAGE)
    window.program_edit.setText(REAL_PDS)
    window._run_coverage()
    window._refresh_table()
    total = window.table.rowCount()
    assert total > 0
    opts = [window.filter_combo.itemText(i) for i in range(window.filter_combo.count())]
    assert "全部" in opts and "仅异常" in opts
    # 仅异常：行数应少于全量且大于 0（原始数据保留，仅视图收窄）
    window.filter_combo.setCurrentText("仅异常")
    anomalous = window.table.rowCount()
    assert 0 < anomalous < total
    window.filter_combo.setCurrentText("全部")
    assert window.table.rowCount() == total


def test_author_label_present(app):
    window = MainWindow()
    assert "Quincy" in window.author_label.text()
    assert f"v{APP_VERSION}" in window.author_label.text()
