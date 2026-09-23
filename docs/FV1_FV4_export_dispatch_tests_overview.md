# FV-1 / FV-4 GUI 导出分支端到端验证（收尾补测）

## 背景
M3 已把 FV-1（FT↔QA 覆盖率）与 FV-4（变更前↔后）接入 GUI，全量 57 passed。
但 GUI `_export_xlsx` / `_export_html` 的 `coverage` / `change` 分支会弹
`QFileDialog`，headless 测试下没有走通 —— 这是唯一遗留的验证缺口。
底层 `export_coverage_report` / `export_compare_report` 已在 `tests/test_coverage_compare.py`
单测覆盖，但「GUI 派发 → 调对正确导出器」这一跳未被验证。

## 本次改动
**`tests/test_fv1_fv4_gui.py`** 新增 3 条测试，用
`mock.patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(tmp_path, ...))`
钉住文件对话框，直接验证派发分支：

| 测试 | 验证目标 | 断言 |
|---|---|---|
| `test_export_xlsx_coverage_via_gui` | FV-1 → `export_coverage_report` | 文件可 openpyxl 加载；含 `摘要`/`未覆盖(需处理)`/`全部明细` sheet |
| `test_export_xlsx_change_via_gui` | FV-4 → `export_compare_report` | 文件可 openpyxl 加载；含 `摘要`/`放宽风险`/`全部明细` sheet |
| `test_export_html_change_via_gui` | FV-4 → `export_html_report` | HTML 含内联 `<style>`，无 `<link>`、无 `cdn`（离线单文件契约） |

## 验证结果
- 全量 **60 passed**（原 57 + 新 3），零回归。
- 命令（仓库根目录执行）：
  ```bash
  QT_QPA_PLATFORM=offscreen python -m pytest -q
  ```

## 同步更新
- `docs/PRD.md` §12.1 单元测试数 57 → 60。
- `.workbuddy/memory/2026-09-23.md` 追加收尾补测段。

## 结论
至此 FV-1 / FV-4 的 **引擎 / GUI 模式 / GUI 导出（XLSX + HTML）** 全部端到端验证闭合。
