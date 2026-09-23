"""v0.3.0 UX additions: drag & drop upload, export default dir, GU sigma k, clear files.

Headless (``QT_QPA_PLATFORM=offscreen``). Skipped where PySide6 is absent.
The drop routing is exercised through ``_accept_dropped_paths`` so the tests do
not need a synthetic ``QDropEvent``; the widget-level ``dropEvent`` only does
the URL extraction around it.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6", reason="PySide6 not installed in this environment")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.ui.main_window import (  # noqa: E402
    APP_VERSION,
    MODE_ANALYSIS,
    MODE_COVERAGE,
    MODE_PE,
    MainWindow,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------- drag & drop
def test_dnd_routes_by_extension(app, tmp_path):
    window = MainWindow()
    pds = str(tmp_path / "PRODUCT_A_FT.pds")
    pe = str(tmp_path / "PE_spec.xlsx")
    log = str(tmp_path / "datalog.csv")
    placed, rejected = window._accept_dropped_paths([pds, pe, log])
    assert window.program_edit.text() == pds
    assert window.pe_edit.text() == pe
    assert window.datalog_edit.text() == log
    assert rejected == []
    assert len(placed) == 3


def test_dnd_two_programs_split_into_both_fields(app, tmp_path):
    """拖入 FT+QA 两个程序时，应自动分居主/副字段，而不是互相覆盖。"""
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_COVERAGE)
    ft = str(tmp_path / "PRODUCT_C_FT.cpts")
    qa = str(tmp_path / "PRODUCT_C_QA.cpts")
    window._accept_dropped_paths([ft, qa])
    assert window.program_edit.text() == ft
    assert window.gu_program_edit.text() == qa


def test_dnd_appends_multiple_pe_files(app, tmp_path):
    window = MainWindow()
    a = str(tmp_path / "a.xlsx")
    b = str(tmp_path / "b.xlsx")
    window._accept_dropped_paths([a])
    window._accept_dropped_paths([b])
    assert window.pe_edit.text() == f"{a};{b}"


def test_dnd_rejects_unknown_extension(app, tmp_path):
    window = MainWindow()
    placed, rejected = window._accept_dropped_paths([str(tmp_path / "note.txt")])
    assert placed == []
    assert len(rejected) == 1


# --------------------------------------------------------------- GU sigma k
def test_gu_sigma_k_defaults_to_three_and_persists(app):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_ANALYSIS)
    original = window.gu_k_spin.value()
    try:
        assert original == pytest.approx(3.0)
        window.gu_k_spin.setValue(4.5)
        assert window.settings["gu_sigma_k"] == pytest.approx(4.5)
    finally:
        window.gu_k_spin.setValue(original)


def test_gu_sigma_k_hidden_outside_analysis_mode(app):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_PE)
    assert not window.gu_k_spin.isVisible()


# --------------------------------------------------------------- clear files
def test_clear_files_resets_inputs_and_results(app, tmp_path):
    window = MainWindow()
    window.program_edit.setText(str(tmp_path / "p.pds"))
    window.pe_edit.setText(str(tmp_path / "pe.xlsx"))
    window.datalog_edit.setText(str(tmp_path / "d.csv"))
    window.gu_program_edit.setText(str(tmp_path / "g.pds"))
    window.summary_label.setText("已完成")
    window.table.setRowCount(2)

    window.clear_btn.click()

    assert window.program_edit.text() == ""
    assert window.pe_edit.text() == ""
    assert window.datalog_edit.text() == ""
    assert window.gu_program_edit.text() == ""
    assert window.summary_label.text() == "尚未执行"
    assert window.stage_label.text() == "—"
    assert window.table.rowCount() == 0
    assert window.result is None
    assert window.result_kind == ""
    # 模式 / 温区 / σ 倍数应保留，便于第二轮对比
    assert window.mode_combo.currentText() == MODE_PE
    assert window.gu_k_spin.value() == pytest.approx(3.0)


# ------------------------------------------------------------- export dir
def test_export_dir_opens_at_upload_location(app, tmp_path):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_PE)
    window.program_edit.setText(str(tmp_path / "sub" / "program.pds"))
    assert window._default_export_dir() == str(tmp_path / "sub")


def test_export_dir_prefers_datalog_in_analysis_mode(app, tmp_path):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_ANALYSIS)
    window.program_edit.setText(str(tmp_path / "p.pds"))
    window.datalog_edit.setText(str(tmp_path / "logs" / "d.csv"))
    assert window._default_export_dir() == str(tmp_path / "logs")


def test_author_label_shows_current_version(app):
    window = MainWindow()
    text = window.author_label.text()
    assert "Quincy" in text
    assert f"v{APP_VERSION}" in text
