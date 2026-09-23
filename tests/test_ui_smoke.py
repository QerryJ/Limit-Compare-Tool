"""GUI smoke test.

Runs headless (``QT_QPA_PLATFORM=offscreen``) so it never opens a window and
never blocks. Skipped automatically where PySide6 is not installed (CI), and
the end-to-end case is skipped when the sample material is absent.

Covers: construction, mode switching, table filling, theme tokens bridging to
Qt, and one real PE-vs-program run through the GUI code path.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6", reason="PySide6 not installed in this environment")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.export.html_report import export_html_report  # noqa: E402
from src.ui.main_window import MODE_ANALYSIS, MODE_PE, MainWindow  # noqa: E402
from src.ui.theme import hex_color, row_height, verdict_color  # noqa: E402

from real_material import has, real_pe_dir, real_pds

PE_DIR = real_pe_dir()
REAL_PDS = real_pds()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_theme_tokens_bridge_to_qt():
    assert hex_color("--lc-pass").startswith("#")
    assert hex_color("--lc-fail").startswith("#")
    assert verdict_color("过紧") != verdict_color("覆盖")
    assert row_height("compact") < row_height("comfortable")


def test_window_constructs_and_switches_mode(app):
    window = MainWindow()
    assert "Limit Compare" in window.windowTitle()

    # NOTE: the window is never shown, so child isVisible() is always False --
    # assert on isHidden(), which reflects the explicit setVisible() state.
    window.mode_combo.setCurrentText(MODE_PE)
    assert window.program_edit.isEnabled()
    assert window.view_combo.isHidden()

    window.mode_combo.setCurrentText(MODE_ANALYSIS)
    assert not window.program_edit.isEnabled()
    assert not window.view_combo.isHidden()


def test_table_filling_and_verdict_colour(app):
    window = MainWindow()
    window._fill_table(["A", "判定"], [["x", "过紧"], ["y", "覆盖"]], verdict_col=1)
    assert window.table.rowCount() == 2
    assert window.table.item(0, 1).text() == "过紧"
    # Colour is auxiliary -- the text label is always present.
    assert window.table.item(1, 1).text() == "覆盖"


def test_density_toggle_persists(app, tmp_path):
    window = MainWindow()
    before = window.settings.get("density")
    window._toggle_density()
    assert window.settings.get("density") != before
    window._toggle_density()
    assert window.settings.get("density") == before


@pytest.mark.skipif(not has(PE_DIR, REAL_PDS),
                    reason="sample material not available")
def test_end_to_end_pe_compare_through_gui(app):
    import glob

    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_PE)
    window.program_edit.setText(REAL_PDS)
    pe_files = sorted(glob.glob(os.path.join(PE_DIR, "*.xlsx")))
    window.pe_edit.setText(";".join(pe_files))

    window._run_pe()
    assert window.result is not None
    assert window.result.summary["已对齐"] > 0
    assert window.result.summary["需更新"] > 0

    window._refresh_table()
    assert window.table.rowCount() > 0
    assert window.table.columnCount() == 13


def test_html_export_is_self_contained(app, tmp_path):
    out = tmp_path / "report.html"
    export_html_report(
        str(out), "冒烟", ["Test item", "判定"],
        [["A", "过紧"], ["B", "覆盖"]],
        summary="摘要",
    )
    text = out.read_text(encoding="utf-8")
    assert "<style>" in text          # inline CSS
    assert "http" not in text.lower().replace("http-equiv", "")  # zero CDN
    assert "过紧" in text
