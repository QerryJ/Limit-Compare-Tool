# FV-1 / FV-4 桌面模式接入 · 实现概览

> 日期：2026-09-24 ｜ 范围：M3 收尾（V 层）｜ 关联：PRD v0.2.1 §4 FV-1/FV-4、§11 M3
> 用户指令：**「需要 FV-1 和 FV-4 都接入」**
> 作者：@Agent Harness 架构设计师

## 1. 背景

FV-1（程序内部 FT↔QA 覆盖）与 FV-4（变更前↔后复核）的**引擎层早已实现**
（`engine.coverage.evaluate_coverage` / `engine.compare.compare_programs`），且跑通真实数据。
本次缺的是 **V 层（桌面模式）**——把两个引擎接进 `main_window` 并提供 XLSX/HTML 导出。

## 2. 设计决策（复用既有外壳，未新增独立控件）

| 项 | 决策 | 理由 / 可推翻点 |
|---|---|---|
| 输入框 | 复用 `program_edit` + `gu_program_edit`，按模式动态改标签 | FV-1：`FT 程序`/`QA 程序`；FV-4：`基准程序`/`新程序`；GU↔FT：`FT 程序`/`GU 程序` 同构 |
| FV-1 的 .cpts 单侧 | 检测到无 QA 侧时，要求另选 QA 文件并 `merge_sides` 合并 | `.pds` 自带双侧则直接比对；若用户想单文件自动按文件名分边，可改 |
| 表呈现 | 默认**只列风险/异常项**（覆盖项折叠） | 全量明细在 XLSX；GUI 若想看全量可调 |
| 摘要领先 | FV-4 摘要首行即「放宽风险」 | 放宽=漏放真风险，复核时最该先看到 |

## 3. 改动文件

- `src/ui/main_window.py`
  - 模式下拉新增 `FT ↔ QA 覆盖率 (FV-1)`、`变更前 ↔ 后 (FV-4)`
  - `_on_mode_changed`：按模式改 `program_label`/`gu_label` 文本并启用对应字段
  - 新增 `_run_coverage()`：`.pds` 双侧直接比；`.cpts` 缺 QA 侧则要求选 QA 并 `merge_sides`
  - 新增 `_run_change()`：基准+新程序 → `compare_programs`，摘要领先展示「放宽风险」
  - `_refresh_table`：coverage / change 两种渲染（判定列=状态 / 方向）
  - `_export_xlsx` / `_export_html`：新增 coverage / change 分支
- `src/export/report.py`
  - `export_coverage_report`：摘要 / 未覆盖(需处理) / 局部缺失 / 整体缺失 / 全部明细
  - `export_compare_report`：摘要 / 放宽风险 / 新增与移除 / 变更明细(逐格) / 全部明细
- `tests/test_fv1_fv4_gui.py`（新增）：headless 冒烟——模式出现、字段改标签、真实 `.pds` 走 FV-1、相同 `.pds` 走 FV-4
- `tests/test_coverage_compare.py`：新增 `export_coverage_report` / `export_compare_report` 单测

## 4. 验证

- **全量 57 passed**（原 50 + 新 7），零回归
- FV-1 经真实 产品A `.pds` 走 GUI：summary 含「覆盖率」；表列未覆盖/缺失项
- FV-4 相同 `.pds` 作基准+新：方向全「相同」、放宽风险 0、表 5 列
- PRD 同步：v0.2.1，M3 标记 FV-1/FV-4 GUI ✅，单元测试数 43→57

## 5. 仍待做（非阻塞，已记入 PRD §14）

- CPTS 单侧文件提示（只拿到 FT 或只拿到 QA 时如何提示用户）尚未实现
- 跨机台 `.pds` vs `.cpts` 对比仅有告警设计，无真实数据验证

## 6. 层间铁律复核

`V` 只消费 `L` 的结果：覆盖率状态、`ERROR`/`未覆盖`/方向枚举全部由 engine 产出，
GUI 与导出**不自行判空、不重算方向**，延续单一真值原则。
