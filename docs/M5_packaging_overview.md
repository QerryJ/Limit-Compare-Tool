# M5 · 单文件离线 exe 打包落地概述

## 交付内容
按已沟通方案（PRD 里程碑 M1–M5），M1/M2/M3 已完成、M4（FV-5/FV-6 分析 GUI）在 M2 外壳已实现，
本次落地 **M5：把离线桌面软件打包为可分发单文件 exe**。

| 交付物 | 说明 |
|---|---|
| `dist/LimitCompare.exe` | **45.3 MB 单文件**，含 PySide6 + openpyxl + `tokens.css`，运行时零网络 |
| `build.spec` | PyInstaller 打包蓝图（已改为基于 `SPECPATH` 的绝对路径，任意 cwd 可打包） |

## 构建命令（用户侧复现）
```bat
:: 在仓库根目录执行（build.spec 已 cwd 无关，任意目录均可）
pyinstaller build.spec --noconfirm
:: 产物：dist\LimitCompare.exe
```
- `console=False` → 纯 GUI，无控制台窗口
- `datas` 已捆绑 `docs/design-system/tokens.css` → 设计令牌单一来源在打包后从 `sys._MEIPASS` 读取
- `excludes` 已剔除 `tkinter/PyQt5/PyQt6/pytest/notebook`，缩小体积

## 验证结果
- ✅ PyInstaller 6.22.3 构建端到端成功，产出单文件 exe
- ✅ 构建警告 18 条**全部良性**（POSIX 专属模块 + openpyxl 可选依赖），**无 Qt 平台插件缺失、无 tokens.css 缺失**
- ⚠ **真机启动冒烟未在本环境执行**：沙箱限制派生 GUI 进程（被 SIGTERM 拦截）。请在你本机 Windows 双击 `dist/LimitCompare.exe` 确认窗口正常弹出、各模式可用（PE↔程序 / datalog↔PE / Cpk·GU 分析 / GU↔FT / FT↔QA 覆盖率 / 变更前↔后）。

## PRD 同步
- 版本 v0.2.1 → **v0.2.2**；状态 M2/M3/M4/M5 全部完成
- §12.1「打包 exe」待做 → **通过**

## 已知限制（非阻塞，沿用 PRD §13/§14）
- CPTS 单侧文件提示（仅 FT 或仅 QA 时）未实现
- 跨机台 `.pds` vs `.cpts` 对比仅有告警设计，无真实数据验证
- FV-7 版本追溯已移出本期（O6/D12）

## 下一步建议（待你拍板）
- 若需对外发布可补：exe 数字签名（当前 `codesign_identity=None`）、版本号对齐 `v0.1.0`、CHANGELOG 发布条目
- 若要做安装包可加 InnoSetup/NSIS；当前单文件已满足「离线分发」目标
