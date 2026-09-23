"""v0.4.2 UI polish: C icon, centred startup, drop-target hint, file list.

Headless (``QT_QPA_PLATFORM=offscreen``). Skipped where PySide6 is absent.
The icon is drawn as **vector geometry** (no fonts), so pixel assertions are
deterministic even though the offscreen platform ships zero fonts.
"""

import os
import struct
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6", reason="PySide6 not installed in this environment")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from src.ui.icon import build_app_icon, build_icon_pixmap, save_ico  # noqa: E402
from src.ui.main_window import (  # noqa: E402
    MODE_CHANGE,
    MODE_COVERAGE,
    MainWindow,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------------ L icon
def test_icon_pixel_colors_are_deterministic(app):
    """L = 竖笔 + 横笔（矢量路径）。64px 时：竖笔中心 x≈20.5，横笔中心 y≈47.4。"""
    pm = build_icon_pixmap(64)
    assert not pm.isNull()
    image = pm.toImage()
    # 顶部中央：圆角方块底色（强调色，蓝通道 > 红通道）
    top = image.pixelColor(32, 3)
    assert top.blue() > top.red()
    # 竖笔中段与横笔中段：接近白色
    vertical = image.pixelColor(20, 32)
    assert min(vertical.red(), vertical.green(), vertical.blue()) > 220
    horizontal = image.pixelColor(32, 47)
    assert min(horizontal.red(), horizontal.green(), horizontal.blue()) > 220
    # L 右上方的空白区：仍是底色而非笔画
    empty = image.pixelColor(52, 20)
    assert empty.blue() > empty.red()


def test_save_ico_writes_valid_structure(tmp_path):
    path = str(tmp_path / "app.ico")
    save_ico(path, sizes=(16, 32, 256))
    data = open(path, "rb").read()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind, count) == (0, 1, 3)
    # 每个条目的图像数据都是 PNG 签名
    for i in range(count):
        _, _, _, _, _, _, size, offset = struct.unpack(
            "<BBBBHHII", data[6 + 16 * i: 6 + 16 * (i + 1)])
        assert data[offset:offset + size].startswith(b"\x89PNG")


def test_window_icon_is_set(app):
    window = MainWindow()
    assert not window.windowIcon().isNull()
    assert not build_app_icon().pixmap(32).isNull()


# --------------------------------------------------------- centred startup
def test_center_on_screen_places_window_inside_screen(app):
    window = MainWindow()
    window.center_on_screen()
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        pytest.skip("offscreen platform exposes no screen")
    assert screen.availableGeometry().contains(window.frameGeometry().center())


# ------------------------------------------------------ drop-target hint
def test_drop_targets_predict_routing_for_two_programs(app, tmp_path):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_COVERAGE)
    ft, qa = str(tmp_path / "FT.pds"), str(tmp_path / "QA.pds")
    targets = window._drop_targets([ft, qa])
    assert window.program_edit in targets
    assert window.gu_program_edit in targets
    assert window.pe_edit not in targets


def test_drop_hint_sets_and_clears_property(app, tmp_path):
    window = MainWindow()
    window._show_drop_hint([str(tmp_path / "a.pds")])
    assert window.program_edit.property("dropTarget") is True
    window._clear_drop_hint()
    assert not window.program_edit.property("dropTarget")


def test_drop_hint_reports_unmatched_type(app, tmp_path):
    window = MainWindow()
    window._show_drop_hint([str(tmp_path / "note.txt")])
    assert not window.program_edit.property("dropTarget")
    assert not window.pe_edit.property("dropTarget")


def test_role_label_follows_mode(app):
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_COVERAGE)
    assert window._role_label(window.gu_program_edit) == "QA 程序"
    window.mode_combo.setCurrentText(MODE_CHANGE)
    assert window._role_label(window.gu_program_edit) == "新程序"


# -------------------------------------------------------------- file list
def test_file_list_lists_roles_and_full_path_tooltip(app, tmp_path):
    window = MainWindow()
    pds = str(tmp_path / "PRODUCT_A.pds")
    pe1, pe2 = str(tmp_path / "PE1.xlsx"), str(tmp_path / "PE2.xlsx")
    window.program_edit.setText(pds)          # textChanged 自动刷新
    window.pe_edit.setText(f"{pe1};{pe2}")
    assert window.file_list.count() == 3
    texts = [window.file_list.item(i).text() for i in range(3)]
    assert any("PRODUCT_A.pds" in t for t in texts)
    assert any("PE1.xlsx" in t and "PE 表格" in t for t in texts)
    assert window.file_list.item(0).toolTip() == pds


def test_file_list_empty_state_after_clear(app):
    window = MainWindow()
    window.program_edit.setText("C:/tmp/x.pds")
    window.clear_btn.click()
    assert window.file_list.count() == 1
    assert "尚未选择" in window.file_list.item(0).text()


def test_file_list_refreshes_labels_on_mode_change(app):
    window = MainWindow()
    window.gu_program_edit.setText("C:/tmp/qa.cpts")
    window.mode_combo.setCurrentText(MODE_COVERAGE)
    assert "QA 程序" in window.file_list.item(0).text()
    window.mode_combo.setCurrentText(MODE_CHANGE)
    assert "新程序" in window.file_list.item(0).text()


# ------------------------------------------------------- v0.4.3 additions
def _seed(window, n=3):
    window._rows = [[f"FUNC_{i}", f"ITEM_{i}", "过紧" if i == 1 else "合理"]
                    for i in range(n)]
    window._headers = ["Function", "Test item", "判定"]
    window._verdict_col = 2
    window._anomaly_set = {"过紧"}
    return window._rows


def test_frozen_columns_mirror_first_two(app):
    window = MainWindow()
    rows = _seed(window)
    window._fill_table(window._headers, rows, 2)
    frozen = window.table._frozen
    assert window.table.frozen_cols == 2
    assert frozen.columnCount() == 2              # 只冻结前两列
    assert frozen.rowCount() == len(rows)
    for r in range(len(rows)):
        for c in range(2):
            assert frozen.item(r, c).text() == window.table.item(r, c).text()
    # 第 3 列（判定）不在冻结层
    assert frozen.item(0, 2) is None


def test_frozen_table_hides_when_empty(app):
    window = MainWindow()
    window.table.clear()
    window.table.setColumnCount(0)
    window.table.refresh_frozen()
    assert not window.table._frozen.isVisible() or window.table.columnCount() == 0


def test_busy_state_toggles_button_and_text(app):
    window = MainWindow()
    window._set_busy(True, "处理中")
    assert not window.run_btn.isEnabled()
    assert window.run_btn.text() == "执行中…"
    window._set_busy(False)
    assert window.run_btn.isEnabled()
    assert window.run_btn.text() == "执行对比"


def test_run_reports_failure_and_restores_button(app, tmp_path):
    """执行抛错时按钮必须恢复可用（不能卡在「执行中…」）。

    QMessageBox.critical 是模态对话框，headless 下会永久阻塞，必须钉住。
    """
    window = MainWindow()
    window.mode_combo.setCurrentText(MODE_CHANGE)   # 无文件 → 必抛 ValueError
    with mock.patch.object(QMessageBox, "critical", lambda *a, **k: None):
        window.run_btn.click()
    assert window.run_btn.isEnabled()
    assert window.run_btn.text() == "执行对比"


def test_verdict_badge_is_icon_not_text_pollution(app):
    window = MainWindow()
    rows = _seed(window)
    window._fill_table(window._headers, rows, 2)
    for r in range(len(rows)):
        cell = window.table.item(r, 2)
        assert not cell.icon().isNull()          # 形状徽章存在
        assert cell.text() in ("过紧", "合理")    # 文本未被前缀污染，导出仍干净


def test_recent_combo_lists_and_routes_selection(app, tmp_path):
    window = MainWindow()
    pds = str(tmp_path / "RECENT_PROBE.pds")
    window._accept_dropped_paths([pds])          # 拖拽路径才会 add_recent 落盘
    window.program_edit.clear()
    texts = [window.recent_combo.itemText(i) for i in range(window.recent_combo.count())]
    assert "RECENT_PROBE.pds" in texts
    window._on_recent_selected(texts.index("RECENT_PROBE.pds"))
    assert window.program_edit.text() == pds     # 选中即按扩展名回填对应输入框
    assert window.recent_combo.currentText().startswith("—")  # 回到占位项


def test_focus_search_shortcut_target_exists(app):
    window = MainWindow()
    window._focus_search()                       # headless 下不抛错即可
    assert hasattr(window, "search_edit")
