# 完工报告 · P1 结果高亮与卡片降噪

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1604 |
| 开始 | 2026-11-13 16:04 |
| 结束 | 2026-11-13 16:05 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §6 落地 P1 第 3、4 条：结果标题/摘要高亮查询词并 clamp 摘要；卡片降噪（引擎标签 2+N、域名面包屑、日期与风险一行、操作收进右上角菜单）。

**验收标准**

- 标题/摘要命中查询词并高亮，高亮词与查询一致（不区分大小写），底色可见且对比度达标（axe serious/critical=0）。
- 引擎标签每张卡 ≤2 个 + `+N`，`+N` 与引擎总数一致。
- 域名以面包屑显示（无协议头，`›` 分段）。
- 发布时间与风险提示处于同一行。
- 操作菜单默认收起、含收藏/复制链接/打开链接，点外部收起，复制写入剪贴板。
- 长摘要默认 3 行且可展开/收起；行内次要按钮 ≥24×24，主要控件 ≥44×44。
- 既有 82 项浏览器断言不回归；pytest 与前端构建通过。

**不做**

- P1 剩余条目（分页信息、搜索建议、快捷键面板、已收藏状态、错误态产品化、空态、主题细节、书签快捷栏刷新、AI 工具流控制、设置页增强、旧页面移动端）。
- 不改官方入口卡片的结构（仍保留行内收藏按钮）；不改后端接口。

## 2 做了什么

1. **高亮工具**：新增 `apps/web/src/highlight.ts`——`searchTerms()` 去掉末尾引擎后缀与引号、按空白/标点切词、去重后取最多 3 个；`splitHighlight()` 把文本切成命中/未命中片段，中文整段匹配、英文加字母数字边界；`breadcrumb()` 解百分号编码并截断段落。
2. **卡片重写**：`ResultCard.tsx` 用 `<Marked>` 渲染标题与摘要；长摘要（>120 字）给「展开摘要/收起摘要」；引擎标签只留 2 个 + `+N`（`title` 给全量）；发布时间、风险、品牌提示、中转确认合并到 `.card__flags` 不换行。
3. **操作菜单**：卡片右上角 `<details class="card__actions">`，含收藏（复用 `BookmarkButton`）、复制链接（写入剪贴板后显示「已复制链接」）、分享（`navigator.share` 可用时）、打开链接。
4. **交互收口**：`App.tsx` 的外部 `pointerdown` 现在同时收起卡片菜单；Esc 收起并把焦点还给触发钮；`b` 快捷键先展开菜单再点收藏，结果可见。
5. **透传查询**：`ResultList` 与 `ContentModules` 新增 `query` 参数，`App` 把 `data.parsed.q` 传下去。
6. **配色修正**：首版高亮用 `color-mix` 半透明底，axe 在结果页抓出 29 处 color-contrast；改成 `--accent-soft` 实色底 + `color: var(--text)` 后归零。
7. **验收脚本**：`scripts/audit-ui.cjs` 新增 14 项（高亮命中/一致性/底色、2+N 与总数、面包屑、同日显示、菜单默认态/四项操作/外部收起/剪贴板、3 行 clamp 与展开、行内按钮 24×24），并给桌面上下文加剪贴板权限。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/web/src/highlight.ts` | 新增 | 取词、切片高亮、域名面包屑 |
| `apps/web/src/components/ResultCard.tsx` | 重写 | 高亮、2+N、flags、操作菜单、摘要 clamp |
| `apps/web/src/components/ResultList.tsx` | 修改 | 新增并透传 `query` |
| `apps/web/src/components/ContentModules.tsx` | 修改 | 新增并透传 `query` |
| `apps/web/src/App.tsx` | 修改 | 透传查询、卡片菜单的外部收起与 Esc、`b` 展开菜单 |
| `apps/web/src/styles.css` | 修改 | 卡片定位与 padding、菜单、flags/tags、mark、摘要 clamp |
| `apps/web/src/workspace.css` | 修改 | 粗指针下菜单触发钮与菜单项 44px |
| `scripts/audit-ui.cjs` | 修改 | 新增 14 项断言（共 96 项）与剪贴板权限 |
| `reports/assets/ui-p1/` | 修改 | 新增卡片/菜单截图与最新审计 JSON |
| `docs/决策与接口变更.md` | 修改 | 新增 P1 高亮与降噪决策 |
| `docs/浏览器与UI优化方案.md` | 修改 | §6 第 3、4 条标注已完成 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `node scripts/audit-ui.cjs --out reports/assets/ui-p1` | 通过 | `ALL PASS (96)`；高亮 titles=23 snippets=34、`+1` 与引擎总数一致、剪贴板拿到 `https://en.wikipedia.org/wiki/Python`、clamp=3 且展开全文、axe 两页 0 严重项 |
| `npm --prefix apps/web run build` | 通过 | `tsc --noEmit` 无错误；66 modules，JS 315.79 kB，CSS 49.07 kB |
| `python -m pytest apps/api -q` | 通过 | 462 项，`[100%]` 无 F/E |
| 8000 日常实例 | 通过 | 提供本轮构建 `index-BiEHdU4Q.js` / `index-Br2bVaDG.css` |

**证据文件**

- 审计结果：`reports/assets/ui-p1/p0-ui-audit.json`
- 截图：`desktop-cards-highlight.png`、`desktop-card-menu.png`、`mobile-card-menu.png`

**未验证**

- AI 检索、AI 对话里的结果卡片没有传 `query`，不参与高亮（按需再接）。
- 768/1024 断点仍无断言；未做真机与读屏确认菜单焦点归还。
- 未跑本轮 smoke：改动全在前端渲染层，冒烟只打 `/api/*`。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 高亮用 `<mark>` + 实色底 | 加粗 / 仅换颜色 | 只换颜色会和链接色冲突；实色底还能满足对比度 |
| 英文加字母数字边界，中文不加 | 统一 `\b` | `\b` 对中文无效，而且会把 `pythonic` 当成 `python` |
| 摘要用 `-webkit-line-clamp` | 按字符截断 | 截断会切在句子中间；clamp 保持行宽自适应 |
| 操作收进 `<details>` 菜单 | 悬停浮层 | 原生可键盘、可读屏；点外部由统一的 pointerdown 收起 |
| `b` 快捷键先展开菜单 | 静默点击隐藏按钮 | 否则用户按 `b` 看不到「已收藏」反馈 |
| 只给结果卡加菜单，官方入口保留行内收藏 | 全部统一 | 官方入口是目录直达，行内收藏点得更快 |

## 6 遗留与风险

- 卡片菜单在窄屏会盖住下方卡片（浮层正常行为），但同一时间只应有一个打开；已由外部点击收起保证，若出现多个可再加互斥。
- 引擎标签仍占一行，移动端元信息可能排到第二行；如果继续压缩，可把引擎标签收进菜单。
- `+N` 依赖后端返回全量 `engine` 数组，若上游只回单个引擎则不显示。
- P1 剩余 10 条未动，下一轮建议「分页信息 + 搜索建议」。

## 7 交接

**下一个人第一件事**

跑 `node scripts/audit-ui.cjs --out reports/assets/ui-p1`（需 8000 在跑）确认 96 项仍全绿，然后做 P1 第 5、6 条：分页信息（`第 2/10 页 · 21–40 条`、`[`/`]` 翻页、翻页后滚动到结果标题）+ 搜索建议（历史/引擎后缀/品牌，`Ctrl/Cmd+K`）。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§6 第 3、4 条已标注完成）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P1 结果高亮与卡片降噪）
- 实现：`apps/web/src/highlight.ts`、`apps/web/src/components/ResultCard.tsx`
- 验收：`scripts/audit-ui.cjs`、`reports/assets/ui-p1/`