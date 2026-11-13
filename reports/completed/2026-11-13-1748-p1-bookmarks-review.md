# 完工报告 · DSH P1 快捷键与书签撤销复核

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1748 |
| 开始 | 2026-11-13 17:48 |
| 结束 | 2026-11-13 17:50 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |


## 1 任务

复核 [DSH 17:26 的 P1 快捷键面板与书签状态](2026-11-13-1726-p1-shortcuts-bookmark-status.md)。范围包括面板焦点、键盘和触控入口、批量书签状态、慢保存及撤销安全性。完成代码、隔离前后端验证和文档交接。

## 2 做了什么

- 原浏览器脚本在固定样本环境复跑时，Esc 归还焦点断言失败。移除延时抢焦点，改由原生 `dialog` 归还到打开前的实际焦点。打开时暂停背景快捷键，键盘、按钮和遮罩都能关闭。窄屏保留触控入口，兼容不支持 `closedby` 的浏览器。
- 批量状态接口复用书签 URL 校验，忽略非法或过长输入并返回每个匹配的原始网址。同一书签的多个跟踪链接可共享 ID。状态响应禁止缓存，前端撤销或重收藏时废弃旧查询并重新同步。
- 保存进行中保持乐观提示，待拿到确认 ID 才允许撤销。失败后保留实际状态并提示重试。撤销成功后同步同 ID 的卡片并刷新快捷栏，键盘焦点移回收藏按钮。
- SQLite 可复用已删除记录的 ID。新增 `DELETE /api/bookmarks/{id}/result?url=...`，在同一条 SQL 中核对 ID 与规范化网址，状态变化返回 409。使用独立路径，避免旧进程忽略额外参数并误删别的书签。原管理页删除入口继续可用。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/api/app/db/repo.py`、`apps/api/app/routers/bookmarks.py` | 批量别名、URL 校验和带身份核对的撤销 |
| `apps/api/tests/test_bookmarks.py` | 覆盖别名、无效输入、缓存头与 ID 复用 |
| `apps/web/src/App.tsx`、`apps/web/src/api.ts` | 暂停背景快捷键、同步批量状态、撤销调用 |
| `apps/web/src/components/BookmarkButton.tsx`、`QuickBookmarks.tsx`、`ShortcutsDialog.tsx`、`styles.css`、`workspace.css` | 保存/撤销状态、焦点、快捷栏刷新、窄屏入口 |
| `scripts/audit-ui.cjs`、`reports/assets/p1-bookmarks-review/` | 受控慢响应、别名、焦点和遮罩回归及证据 |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md`、`docs/进展与欠账.md`、`reports/INDEX.md` | 更新契约、进度及台账 |

## 4 验证与证据

| 命令 | 输出摘要 |
| --- | --- |
| `python -m pytest apps/api -q` | 最终版退出 0、100%。前一轮 `python -m pytest apps/api -q -o addopts=''` 明示 465 passed；最终端点改动后已重跑全套。 |
| `npm --prefix apps/web run build` | 69 modules，JS 326.29 kB、CSS 53.42 kB。 |
| `node --test scripts/engine-query.test.cjs` | 18 通过。 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18187 --out reports/assets/p1-bookmarks-review/chromium` | `ALL PASS (148)`。Esc、按钮、原生及兼容遮罩、背景快捷键、慢保存和撤销回滚均通过。 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18187 --channel chrome --out reports/assets/p1-bookmarks-review/chrome` | 本机 Chrome 无头模式 `ALL PASS (148)`。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18187` | 固定样本 16/16，SSE 10 个引用。 |
| 隔离库用 `Invoke-RestMethod -Method Post` 保存合成书签，再用 `Invoke-WebRequest` 查询两个别名并按网址撤销 | 原网址和别名命中同一 ID，错误网址 409，正确别名 204，撤销后匹配数为 0。 |
| `Invoke-RestMethod http://127.0.0.1:8000/openapi.json` | 日常 fixture 服务仍运行旧版 API，书签结果撤销端点未加载。 |
| `git diff --check` | 退出 0。Git 有 LF/CRLF 提示。 |

[Chromium 证据](../assets/p1-bookmarks-review/chromium/p0-ui-audit.json) · [Chrome 证据](../assets/p1-bookmarks-review/chrome/p0-ui-audit.json)

## 5 关键决策

- 当前页面内以服务端确认 ID 为准，保存期间的乐观文案不能用于触发删除。撤销核对 ID 与 URL，避免 ID 复用误删。
- 快捷键面板交给浏览器管理焦点。用能力检测加遮罩坐标判断补充旧浏览器的轻触关闭。

## 6 遗留与风险

- 日常 8000 服务由此前的 fixture 进程启动，未确认其实际数据库、令牌路径和模型启动参数，故保留原进程。它会提供新的静态构建，但需要用原配置重载 API 才能完整试用撤销。新版前端在旧后端无法执行结果卡撤销，保留书签并显示失败。
- 8888 无监听，真实 SearXNG 未验；Android 真机返回手势和读屏未验。未提交或推送。

## 7 交接

沿用 8000 的现有数据库、令牌路径和启动配置重启 API，再检查 OpenAPI 出现 `/api/bookmarks/{bookmark_id}/result`。用合成书签复核保存、别名状态和撤销后，再继续 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §6。
