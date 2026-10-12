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

from src.ui.main_window import (  # noqa: E402
    APP_VERSION, MODE_CHANGE, MODE_COVERAGE, MainWindow, _CHANGE_HEADERS,
)
from src.model import (  # noqa: E402
    CellDiff, ChangeDirection, CompareReport, ItemDiff, SourceType, TempZone,
)

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


def test_change_table_carries_original_values(app, tmp_path):
    """FV-4 GUI table must expand per CellDiff and keep old/new LSL/HSL + Δ.

    Regression guard for the missing-original-data bug: the table used to
    show only Function/Test item/Unit/方向/变更说明 and dropped the raw
    before/after limits. This test does NOT need real material.
    """
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_CHANGE)

    cell_ft = CellDiff(
        zone=TempZone.ROOM, side=SourceType.FT,
        a_lo=1.0, a_hi=10.0, b_lo=0.5, b_hi=12.0,
        delta_lo=-0.5, delta_hi=2.0,
    )
    cell_gu = CellDiff(
        zone=TempZone.HOT, side=SourceType.GU,
        a_lo=2.0, a_hi=20.0, b_lo=2.0, b_hi=18.0,
        delta_lo=0.0, delta_hi=-2.0,
    )
    item = ItemDiff(
        function="F1", test_item="T1", unit="uA",
        direction=ChangeDirection.LOOSER,
        zones=[cell_ft, cell_gu],
        change_detail="FT 低边放宽",
    )
    window.result = CompareReport(items=[item])
    window.result_kind = "change"
    window._refresh_table()

    # 13 列：Function/Test item/Unit/温区/侧别/旧LSL/旧HSL/新LSL/新HSL/ΔLSL/ΔHSL/方向/变更说明
    assert window.table.columnCount() == 13
    assert [window.table.horizontalHeaderItem(c).text()
            for c in range(window.table.columnCount())] == _CHANGE_HEADERS
    # 逐 CellDiff 展开：2 个温区/侧别 → 2 行（而非合并成 1 行）
    assert window.table.rowCount() == 2

    def row_text(r: int) -> str:
        return " | ".join(
            window.table.item(r, c).text() if window.table.item(r, c) else ""
            for c in range(window.table.columnCount())
        )

    ft_row = row_text(0)
    assert "旧 LSL" not in ft_row  # header, not a value row
    assert "1" in ft_row and "10" in ft_row       # 旧 LSL/HSL
    assert "0.5" in ft_row and "12" in ft_row     # 新 LSL/HSL
    assert "-0.5" in ft_row and "2" in ft_row      # Δ LSL/HSL
    assert "放宽" in ft_row                          # 方向

    # HTML 导出也必须自动带上原始数据（复用当前表格行）
    out = str(tmp_path / "change.html")
    with mock.patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(out, "HTML (*.html)"),
    ):
        window._export_html()
    content = open(out, encoding="utf-8").read()
    assert "旧 LSL" in content and "新 LSL" in content and "Δ LSL" in content
    assert "1" in content and "10" in content and "0.5" in content
    # 离线单文件契约
    assert "<style" in content and "<link" not in content
