# 完工报告 · P1 统计条折叠与加载骨架

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1540 |
| 开始 | 2026-11-13 15:40 |
| 结束 | 2026-11-13 15:40 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §6 落地 P1 第 1、2 条：统计条折叠成一行、其余进「检索详情」；结果区加载骨架 + 翻页保留旧列表。

**验收标准**

- 结果页统计条高度 ≤44px 且只有一行；`sid` 默认不可见、展开「检索详情」后可见。
- 新查询渲染 3 张骨架卡并显示已用时间；骨架区高度 ≥280px（不塌陷）。
- 翻页时旧列表保留、整块降透明（opacity 0.45）、显示「正在加载第 N 页」，完成后退回不透明。
- 390×844 统计条同样只占一行，首条结果仍在首屏。
- 既有 42 项 P0/复核断言不回归。
- `python -m pytest apps/api -q` 与 `npm --prefix apps/web run build` 通过。

**不做**

- P1 其余条目（结果高亮、卡片降噪、分页信息、搜索建议、快捷键面板、已收藏状态、错误态产品化、空态、主题细节、书签快捷栏刷新、AI 工具流控制、设置页增强、旧页面移动端）。
- 不改后端接口、检索排序与缓存；不改 P0 已定的 URL 语义。

## 2 做了什么

1. **统计条两级结构**：`MetaBar.tsx` 拆成 `.metabar__summary`（展示条数 / 缓存 / ms / 官方入口 / 拦截）与 `<details class="metabar__more">`「检索详情」（上游、去重、拦截、官方入口明细、路由、引擎、不可用引擎、sid）。`.metabar` 改两列网格：主行在左、详情入口右对齐，展开后详情独占下一行。
2. **窄屏再收一层**：≤520px 把主行的上游/官方入口/拦截隐去，主行恒为「徽标 · 展示 N 条 · 缓存 · ms · 检索详情」。
3. **骨架组件**：新增 `components/ResultSkeleton.tsx`，3 张骨架卡 + `正在检索「q」… X.Xs`；卡片区 `aria-hidden`，避免读屏把占位块念出来。
4. **两种加载态**：`App.tsx` 里新查询（`!paging`）清空旧结果走骨架；翻页保留 `data`，把结果区包进 `.results-body`，加 `aria-busy`、透明度 0.45、`pointer-events:none`，并在顶部显示「正在加载第 N 页…」。
5. **计时**：`elapsed` 状态 + 100ms 定时器，只在 `loading` 期间走，切换查询/页码或返回时清零。
6. **播报统一**：`main` 的 `role=status` 增加「正在检索 X」，与「找到 N 条结果」共用同一 live region，避免骨架文案再起一个播报源。
7. **验收脚本**：`scripts/audit-ui.cjs` 新增 13 项（统计条单行、sid 收起/展开、详情含关键字段、骨架 3 卡、计时递增、骨架高度、骨架移除、翻页降透明与进度、恢复不透明、移动端统计条单行）。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/web/src/components/ResultSkeleton.tsx` | 新增 | 3 张骨架卡 + 已用时间 |
| `apps/web/src/components/MetaBar.tsx` | 修改 | 主行 + 「检索详情」`<dl>` |
| `apps/web/src/App.tsx` | 修改 | 骨架/旧列表分支、`elapsed` 计时、新查询清旧结果、播报文案 |
| `apps/web/src/styles.css` | 修改 | 统计条两列网格与详情样式、骨架样式、`.results-body[aria-busy]`、reduced-motion |
| `apps/web/src/workspace.css` | 修改 | 窄屏统计条隐去次要字段、粗指针下详情入口触控高度 |
| `scripts/audit-ui.cjs` | 修改 | 新增 13 项断言（共 74 项） |
| `reports/assets/ui-p1/` | 新增 | 审计 JSON、骨架/详情/移动端截图 |
| `docs/决策与接口变更.md` | 修改 | 新增「P1 首屏效率」决策 |
| `docs/浏览器与UI优化方案.md` | 修改 | §6 第 1、2 条标注已完成 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `node scripts/audit-ui.cjs --out reports/assets/ui-p1` | 通过 | `ALL PASS (74)`；统计条 h=34（桌面）、43（390，含徽标换行余量），骨架 3 卡 h=323，翻页 opacity=0.45，恢复后 1 |
| `npm --prefix apps/web run build` | 通过 | `tsc --noEmit` 无错误；65 modules，JS 312.04 kB，CSS 47.02 kB |
| `python -m pytest apps/api -q` | 通过 | 462 项，`[100%]` 无 F/E |
| 移动端首条结果位置 | 通过 | 390×844 首卡 y=381.8（P0 复核时为 580.6，P0 初版 1017） |

**证据文件**

- 审计结果：`reports/assets/ui-p1/p0-ui-audit.json`
- 截图：`desktop-skeleton.png`、`desktop-metabar-details.png`、`mobile-metabar.png`，以及脚本自带的 `desktop-light-search.png`、`mobile-dark-search.png`、`mobile-drawer.png`

**未验证**

- 未跑本轮 smoke：改动全在前端渲染层，`smoke.ps1` 只打 `/api/*` 与首页字节数；真实上游 smoke 的两项既有失败仍按上轮记录待复跑。
- 768/1024 断点未加断言，只做 1440/390/320 自动检查。
- 骨架动画在 `prefers-reduced-motion: reduce` 下停用，但未做真机确认。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 统计条用 `<details>` 而不是弹出层 | 自绘下拉 / 抽屉 | 原生可键盘、可读屏，零 JS，关闭态不占高度 |
| 新查询清空旧结果，翻页保留 | 一律保留旧列表 | 换查询时留着旧列表会误导（用户以为新结果就是这些）；翻页保留才不会高度塌陷 |
| 骨架用 `aria-hidden` + 复用主 live region | 骨架自带 role=status | 一个页面只留一个播报源，避免重复朗读 |
| 透明度 0.45 + `pointer-events:none` | 只改透明度 | 半透明的旧卡片仍可点会打开过期链接 |

## 6 遗留与风险

- 移动端统计条 h=43，接近 44 上限；若后续再加字段会换行，需同步收窄。
- `.metabar__details` 里引擎列表可能很长（11 个引擎名），展开后会把结果下推；如果需要固定高度可再加 `max-height` + 滚动。
- P1 余下 12 条未动，其中「结果高亮」「卡片降噪」「分页信息」与本次改动同区域，下一轮优先。
- 骨架只在首次查询出现；缓存命中时几乎看不到，属于预期。

## 7 交接

**下一个人第一件事**

跑 `node scripts/audit-ui.cjs --out reports/assets/ui-p1`（需 8000 在跑）确认 74 项仍全绿，然后做 P1 第 3、4 条：结果关键词高亮 + 卡片降噪（引擎标签最多 2 个、域名面包屑、操作收进菜单）。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§6 第 1、2 条已标注完成）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P1 首屏效率）
- 实现：`apps/web/src/components/MetaBar.tsx`、`ResultSkeleton.tsx`、`apps/web/src/App.tsx`
- 验收：`scripts/audit-ui.cjs`、`reports/assets/ui-p1/`