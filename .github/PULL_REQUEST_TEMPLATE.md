## 关联 Issue
<!-- Closes #123 -->

## 改动说明
<!-- 做了什么，为什么 -->

## 类型
- [ ] feat 新功能
- [ ] fix 修复
- [ ] docs 文档
- [ ] refactor 重构
- [ ] test 测试
- [ ] chore 杂项

## 自查清单
- [ ] 关联了 Issue，且已确认 `docs/PRD.md` 中有对应功能定义
- [ ] 涉及数据模型的改动已同步 `docs/db/data-model.md`
- [ ] 涉及视觉的改动遵循 `docs/design-system/tokens.css`
- [ ] 空值按 `None` 处理，未把 `0` 当缺失
- [ ] 浮点比较使用容差，未用 `==`
- [ ] 判定与配色由引擎层产出，UI/导出未自行重算
- [ ] 离线可用（无网络调用、无 CDN 依赖）
- [ ] 本地 `pytest -q` 通过

## 验证方式
<!-- 用哪些真实文件跑过，关键数字 -->
