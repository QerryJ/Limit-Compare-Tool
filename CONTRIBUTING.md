# 贡献指南

## 1. 流程铁律（项目组规范）

**先对齐，再动手。** 任何需求编码前，须由 @Agent Harness 架构设计师 输出
《功能信息清单 + 产品规划方案》（`docs/PRD.md`）并经确认。这是**阻断式 Gate**。

**文档为单一事实来源。** 设计决策落 `docs/design-system/`，数据结构落 `docs/db/`，
代码不得与文档分叉。改模型必须先改 `docs/db/data-model.md`。

## 2. 角色分工

| 角色 | 职责 |
|---|---|
| @Git 工作流专家 | 仓库规范、分支与提交规范、CI、Issue/PR 模板 |
| @Agent Harness 架构设计师 | 需求澄清、功能清单、产品规划方案 |
| @高级开发工程师 | 代码实现 |
| @数据库专家 | 数据库设计与完善（本项目为本地 JSON 持久化） |
| @UI设计师 | 工具 UI，美观实用、符合工程师使用习惯 |

## 3. 分支策略

| 分支 | 用途 |
|---|---|
| `main` | 可发布状态，只接受 `release/*` 与 `hotfix/*` 合入 |
| `develop` | 集成分支，功能分支的目标分支 |
| `feature/<编号>-<简述>` | 新功能，如 `feature/FV-1-ft-qa-coverage` |
| `release/<版本>` | 发布准备 |
| `hotfix/<版本>` | 线上问题修复 |

## 4. 提交规范（Conventional Commits）

```
feat: 新增 FT/QA 覆盖检查引擎
fix: 修正浮点噪声导致的方向误判
docs: 补齐数据模型文档
refactor: 抽离导出层
test: 补充对齐引擎用例
chore: 升级 openpyxl
```

## 5. 开发环境

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
python -m pytest -q
```

真实素材端到端用例默认 skip，需要时指定素材目录：

```bash
set LIMIT_COMPARE_MATERIAL_DIR=D:\material
python -m pytest -q
```

## 6. 编码约束（源自踩过的坑）

1. **空值是 `None`，不是 `0`**：`parse_number` 对空单元格返回 `None`，
   禁止把 `0` 当缺失值，也禁止把缺失当 `0` 参与比较。
2. **浮点比较用容差**：`_close()`（相对 + 绝对 `1e-9`），禁止 `==` 判等。
3. **表头按文字定位**：PE 各文件的子表头不一致（`Test item` / `Item` / `ATE test #`、
   `LSL|HSL` / `FT Limit`），禁止写死列字母。
4. **伪歧义要放行**：程序里同一 `(function, test_item)` 会重复出现，
   多个候选 key 相同时视为已匹配，不算 AMBIGUOUS。
5. **判定与配色单一来源**：`N/A` / `ERROR` / 方向枚举由引擎层产出，
   UI 与导出只消费，不得自行判空或重算。
6. **离线约束**：导出的 HTML 必须内联 CSS/JS，零 CDN；运行时零网络请求。

## 7. 数据合规（公开仓库，硬性要求）

本仓库是**公开**的。提交前请确认：

1. **绝不提交真实素材**：`Material/` 已在 `.gitignore` 中排除，
   含料号的 PE 规格、测试程序、datalog 一律不得入库。
2. **文档与测试中不出现料号**：写文档 / 加夹具时用中性代号
   （`产品A` / `PRODUCT_A`），不要用真实编号。
3. **不提交本机状态**：`output/`、`results/`、`config/settings.json`、
   `config/recent.json`、`config/mapping_*.json` 均不入库 —— 它们带本机绝对路径。
4. **不许为了绕过忽略规则改 `.gitignore`**。确有例外，先在 PR 里说明理由。

MR 合入前建议自查：

```bash
git grep -nIE 'BPD[0-9]|[0-9]{5}AB|C:/Users|C:\\Users' -- . ':!Material'
```

## 8. Pull Request

- 关联 Issue，描述改动与验证方式
- 涉及数据模型的改动须同步更新 `docs/db/data-model.md`
- 涉及视觉的改动须遵循 `docs/design-system/tokens.css`
- CI 通过（pytest）后方可合入
