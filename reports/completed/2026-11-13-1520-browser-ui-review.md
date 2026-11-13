# 完工报告 · DSH 浏览器与 UI P0 复核修复

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1520 |
| 开始 | 2026-11-13 15:20 |
| 结束 | 2026-11-13 15:23 |
| 耗时 | 4 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |


## 1 任务

以 [DSH 14:58 的浏览器与 UI P0 交付](2026-11-13-1458-browser-ui-p0.md) 为范围，复核原有 42 项浏览器检查，修复实际交互和验收缺口。验收包括 API 全量、前端构建、两种 Chromium 渠道、固定样本冒烟及原真实上游冒烟失败项。P1/P2 功能、扩展及令牌轮换保留在原排期。

## 2 做了什么

- 修复分类页重搜或用译文转搜时多写一条浏览历史。`popstate` 按地址栏恢复查询、分类、页码和字面模式，分类切换复用已有结果。退回空首页时取消旧请求并清空 AI 结果。前进后退只恢复普通搜索，避免重复触发 AI 服务。普通提交和刷新沿用已有 AI 触发规则。
- 移动端按 `s` 打开工具抽屉并请求总结，引用可关闭抽屉并将焦点移到目标卡片。译文转搜收起抽屉并将焦点返回输入区。原生 dialog 负责 Esc、关闭时的焦点归还和支持 `closedby` 的浏览器中的遮罩关闭，旧浏览器有局部点击回退。抽屉打开时搜索页快捷键暂停。
- 用可展开按钮表达允许全部收起的工具组，保留 Enter/Space 操作。修正 AI 对话双主标题和标签页标题、结果状态重复播报及风险描述。引擎继承态显示上游启用数量，上游目录不可读时省略计数。默认收起含令牌的书签代码，保留复制代码、拖入书签栏和令牌操作。
- 扩展原有 Playwright 脚本，增加重搜历史、前进、AI 请求次数、对话标题、工具键盘操作、令牌初始展示、摘要引用、译文转搜、关闭兼容性和宽度断点的验证。标题层级在有卡片时检查，避免固定样本第二页为空而空通过。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/web/src/App.tsx`、`urlState.ts` | 地址栏恢复、工具按钮与各入口交互、标题与播报 |
| `apps/web/src/components/ToolDrawer.tsx`、`SummaryPanel.tsx`、`workspace.css` | 模态关闭与焦点、引用跳转、抽屉样式 |
| `apps/web/src/components/EngineSettingsPanel.tsx`、`ResultCard.tsx`、`apps/web/src/ToolsPage.tsx` | 引擎说明、风险描述、书签代码展示 |
| `scripts/audit-ui.cjs` | 新增浏览器回归，支持 `--channel chrome` |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md`、`docs/进展与欠账.md` | 补充复核后的交互规则和验收范围 |
| `reports/assets/browser-ui-review/`、`reports/INDEX.md` | 独立 JSON、截图证据和台账 |

## 4 验证与证据

| 命令 | 输出摘要 |
| --- | --- |
| `python -m pytest apps/api -q` | 退出 0，进度 100%。`python -m pytest apps/api --collect-only -q -o addopts=''` 收集 462 项。 |
| `npm --prefix apps/web run build` | 退出 0。TypeScript 与 Vite 完成，64 modules，JS 310.35 kB，CSS 44.94 kB。 |
| `node --test scripts/engine-query.test.cjs` | 18 通过，0 失败。 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18185 --out reports/assets/browser-ui-review/chromium` | `ALL PASS (61)`。结果页、设置页 axe 严重和危急为 0。390×844 首卡 y=580.55，打开抽屉前后结果区 y=351。 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18185 --channel chrome --out reports/assets/browser-ui-review/chrome` | 本机 Chrome 157.0.8103.51 无头模式，`ALL PASS (61)`。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18185` | 固定样本 16/16，候选 11、展示 10，分档 3/6/1，SSE 10 个引用、161 个文本块。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18186` | 真实本机 SearXNG、付费回退关闭、临时库、抽取式模型。13 项适用检查均通过，3 项固定样本检查 N/A。`python 文档` 上游 74、展示 18、分档 3/10/5，原失败的两个判据本次均通过。 |
| `Invoke-WebRequest http://127.0.0.1:8000/` | 日常实例健康且提供本次构建 `index-I_XXdBuJ.js`、`index-DqbAa516.css`。 |
| `git diff --check` | 退出 0。Git 输出已有 LF/CRLF 转换提示。 |

复核前原脚本在固定样本实例 42/42。新增回归在旧构建上确认分类重搜后一次后退落到 `?q=python`。修复后落到 `?q=python&category=encyclopedia`。旧构建扩展回归随后因 AI 分类定位选择器超时中止，已改用可访问名称定位。浏览器脚本对 AI 检索、总结引用及翻译注入固定响应，实际 SSE 链路另由两套冒烟验证。真实上游复跑结果仅对应本次查询和当时的上游状态。

证据：[Chromium JSON](../assets/browser-ui-review/chromium/p0-ui-audit.json)、[本机 Chrome JSON](../assets/browser-ui-review/chrome/p0-ui-audit.json)、[移动端抽屉截图](../assets/browser-ui-review/chromium/mobile-drawer.png)。

## 5 关键决策

- 地址栏保存搜索状态，浏览器历史复用同一还原路径，避免与自定义历史状态对象出现分歧。AI 检索可能计费，前进后退只重取普通结果。
- 工具组支持全部收起，采用原生按钮及 `aria-expanded`；保留单行布局。遮罩关闭优先使用原生机制，并在浏览器缺少 `closedBy` 时补交互。
- 书签代码是可复制的完整可执行载荷，默认收起可降低无意展示完整令牌的概率。

## 6 遗留与风险

- Android 真机返回手势、NVDA/VoiceOver 朗读未验证。当前证据为无头 Chrome 和 Chromium 的桌面与移动视口。
- DSH 原报告中的令牌轮换和总结面板隐藏后取消流仍在后续排期。
- 本轮没有提交或推送。日常 8000 已提供最新前端，真实冒烟使用隔离 18186 的免费检索和抽取式模型，日常模型质量与长时间上游稳定性未复测。

## 7 交接

日常入口 `http://127.0.0.1:8000/`。下一轮用 Android 真机复核抽屉返回手势，再用读屏检查焦点与播报。浏览器固定样本回归命令见 §4。P0 复核决策和 P1 清单见 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md)。
