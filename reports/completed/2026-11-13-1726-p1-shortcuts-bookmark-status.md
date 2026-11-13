# 完工报告 · P1 快捷键面板与书签状态

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1726 |
| 开始 | 2026-11-13 17:26 |
| 结束 | 2026-11-13 17:26 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §6 落地 P1 第 7、8 条：`?` 打开快捷键面板并补齐 `g h`/`g b`；新增批量书签状态接口，让结果卡启动即显示「已在书签」，保存乐观更新并支持撤销。

**验收标准**

- `?` 打开模态快捷键面板，列出全部快捷键；Esc/遮罩关闭并把焦点还给触发按钮；`g b` 打开书签页。
- `GET /api/bookmarks/status?urls=...` 支持重复参数、最多 50 个、只收 http(s)、按 canonical URL 归一、超限 422。
- 结果加载后批量查询一次（≤40 个），命中卡片显示「已在书签」并禁用；撤销后回到「收藏」，撤销入口消失。
- 点击收藏先乐观更新，接口完成后保持已收藏。
- 既有 132 项断言不回归；pytest 与前端构建通过。

**不做**

- P1 余下条目（错误态产品化、空态、主题细节、书签快捷栏刷新细项、AI 工具流控制、设置页增强、旧页面移动端）。
- 不改收藏写入语义（仍走 `POST /api/bookmarks` + 去重规则）。

## 2 做了什么

1. **后端**：`BookmarkRepo.ids_for_urls()` 用 `canonical_url` 归一后批量查 `url_key`；新增 `GET /api/bookmarks/status`（重复 `urls` 参数、`max_length=50`、只收 http(s)、单词截断 2048），返回 `{原始网址: 书签 id}`。
2. **测试**：新增 `test_status_batch_lookup`（带 utm 的同一网址只回一条、非 http 忽略、缺失不报错）与 `test_status_empty_and_cap`（空参数返回 `{}`、51 个返回 422）。
3. **前端数据流**：`api.bookmarkStatus()`；`App` 在结果到达后收集结果 + 官方入口网址（去重、最多 40）查一次，存进 `savedUrls`，并通过 `ResultList`/`ContentModules`/`OfficialPanel` 透传给 `BookmarkButton`。
4. **BookmarkButton**：初始为「已在书签」并禁用；保存走乐观更新（先显示已收藏，失败回滚「收藏失败」）；已收藏时额外渲染「撤销收藏」，调用 `DELETE` 并派发 `cs:bookmark-removed`。响应缺 `item` 时容错为已收藏（只缺 id）。
5. **快捷键面板**：新增 `ShortcutsDialog`（原生 `<dialog>`、`closedby="any"`、进入动画遵循 reduced-motion），分「搜索 / 浏览结果 / 结果操作」三组列出全部键位；结果区底部的 `?` 按钮也能打开。关闭时把焦点还给触发按钮——浏览器关闭 dialog 时会再恢复一次焦点，因此延后一拍执行。
6. **键位**：`?`（Shift+/，输入框内不拦截）、`g h`/`g s` 回首页、`g b` 打开书签页；Esc 在面板打开时交给原生 dialog 处理。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/db/repo.py` | 修改 | 新增 `ids_for_urls()` 批量查询 |
| `apps/api/app/routers/bookmarks.py` | 修改 | 新增 `GET /api/bookmarks/status` |
| `apps/api/tests/test_bookmarks.py` | 修改 | 新增 2 个用例 |
| `apps/web/src/api.ts` | 修改 | 新增 `bookmarkStatus()` |
| `apps/web/src/components/BookmarkButton.tsx` | 重写 | 初始已收藏、乐观更新、撤销、容错 |
| `apps/web/src/components/ShortcutsDialog.tsx` | 新增 | 快捷键速查表 dialog |
| `apps/web/src/components/ResultCard.tsx`、`ResultList.tsx`、`ContentModules.tsx`、`OfficialPanel.tsx` | 修改 | 透传 `saved` 与变更回调 |
| `apps/web/src/App.tsx` | 修改 | 批量状态查询、`savedUrls`、`?`/`g h`/`g b`、面板挂载 |
| `apps/web/src/styles.css`、`workspace.css` | 修改 | 面板样式、撤销按钮、粗指针尺寸 |
| `scripts/audit-ui.cjs` | 修改 | 新增 10 项断言（共 142 项） |
| `reports/assets/ui-p1/` | 修改 | 新增面板与已收藏卡片截图、最新审计 JSON |
| `docs/决策与接口变更.md` | 修改 | 新接口契约与交互规则 |
| `docs/浏览器与UI优化方案.md` | 修改 | §6 第 7、8 条标注已完成 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -q` | 通过 | 464 项（原 462 + 新增 2），`[100%]` 无 F/E |
| `npm --prefix apps/web run build` | 通过 | 69 modules，JS 325.07 kB，CSS 52.99 kB |
| `node scripts/audit-ui.cjs --out reports/assets/ui-p1` | 通过 | `ALL PASS (142)`：`?` 模态面板 3 组、快捷键清单、Esc 焦点归还、`g b` 跳转、状态只带 http(s) ≤40、启动即「已在书签」+禁用、撤销回滚、乐观更新 + 保存计数 1 |
| 环境 | — | 8000 现为固定样本实例（SearXNG 8888 仍不可用），前端为本次构建 `index-Ge6F1gM_.js` |

**证据文件**

- 审计结果：`reports/assets/ui-p1/p0-ui-audit.json`
- 截图：`desktop-shortcuts.png`、`desktop-saved-card.png`

**未验证**

- 真实 SearXNG 未复跑；状态接口对真实上游返回的 20 条/页也要跑一次（当前固定样本 10 条）。
- Android 真机、读屏朗读 dialog 与「已在书签」状态未验。
- 撤销只覆盖单条；批量撤销、撤销后快速重收藏的竞态未测。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 返回扁平对象 `{url: id}` | 数组 `[{url, id}]` | 前端直接 `savedUrls[url]` 查，少一层 map；id 也够撤销用 |
| canonical 归一再比对 | 字符串精确匹配 | 结果卡网址常带跟踪参数，精确匹配会漏掉已收藏 |
| 批量查询合并官方入口 | 只查三档结果 | 官方入口卡片同样有收藏按钮，状态要一致 |
| 乐观更新 + 失败回滚 | 等接口再改文案 | 本机写库很快，但视觉上先给反馈更稳；失败有明确文案 |
| 面板用原生 dialog | 自绘弹层 | 焦点圈定、Esc、遮罩、返回手势都由浏览器负责 |
| 关闭后延后一拍还焦点 | 立即 focus | 浏览器关闭 dialog 时自身也会恢复焦点，立即设置会被覆盖 |

## 6 遗留与风险

- 批量状态每次结果到达都请求一次；翻页会重复查（结果不同），属预期，但如果要做“跨页已知状态”可加本地缓存。
- 已收藏卡片按钮禁用后只能从菜单撤销；如果要“点一下就取消”，需要再改交互。
- 撤销没有确认步骤（本机单人使用，误点代价小）。
- 面板里 `g h`/`g b` 在输入框聚焦时不生效，与现有前缀键一致。

## 7 交接

**下一个人第一件事**

在真实 SearXNG 环境跑 `node scripts/audit-ui.cjs` 复核 20 条/页下的状态批量查询与分页文案，然后做 P1 第 9、10 条：错误态产品化（“本机搜索服务未连接” + 重试/打开设置，诊断命令仅在 debug/fixture 显示）+ 空态与分类提示（换关键词、取消引擎后缀、本页 N 条 / 全部 M 条）。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§6 第 7、8 条已标注完成）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P1 快捷键面板与书签状态）
- 实现：`apps/api/app/routers/bookmarks.py`、`apps/web/src/components/BookmarkButton.tsx`、`ShortcutsDialog.tsx`
- 验收：`scripts/audit-ui.cjs`、`reports/assets/ui-p1/`