# 完工报告 · DSH 扩展、性能指标与设计系统两轮复核

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2227 |
| 开始 | 2026-11-13 22:27 |
| 结束 | 2026-11-13 22:32 |
| 耗时 | 6 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

复核 [DSH 22:07 扩展与性能](2026-11-13-2207-p2-extension-perf.md) 和 [DSH 22:15 指标与设计系统](2026-11-13-2215-p2-vitals-design-system.md)。验收覆盖未打包扩展、分享载荷、离线分包、指标隐私及可重复视觉比较。

## 2 做了什么

- 扩展三个入口复用本机地址与请求约束。连接探测区分无效 token 和服务故障，收藏拒绝重定向、错误响应和非本机设置。快捷命令使用触发标签，右键结果按标签反馈，地址栏入口遵循浏览器指定的打开方式。
- 恢复按完整构建内容生成缓存版本与资源清单，保留懒加载、完整离线壳和动态 OpenSearch 路由。验证分享内容和结果卡菜单取消裁剪。
- 使用 `web-vitals` 5.3.0 采集标准指标。采样只记录固定路由，前后端均过滤搜索词、总结 URL 和片段。成功搜索的计时归属于对应请求，移动抽屉和后台查看也能计时。
- 视觉脚本固定样本和就绪状态，遮罩令牌尾号、API 地址等易变内容，普通比对另存截图，缺基线时失败。保留原基线并新增固定样本基线。

## 3 改动清单

| 路径 | 变更 |
| --- | --- |
| `apps/extension/connection.js`、`background.js`、`popup.*`、`options.*` | 共用网络约束、探测、命令与地址栏回调 |
| `apps/web/vite.config.ts`、`apps/web/src/main.tsx` | 完整构建指纹，恢复开发代理与首屏主题单一入口 |
| `apps/web/src/perf.ts`、`App.tsx`、`package.json`、`package-lock.json` | 指标和计时，新增 `web-vitals` 及视觉测试依赖 `pngjs` |
| `apps/api/app/main.py`、`apps/api/tests/test_search.py`、`test_tools.py` | 上报路径约束、空样本与扩展脚本契约 |
| `scripts/audit-ui.cjs`、`verify-extension.cjs`、`extension.test.cjs`、`visual-regression.cjs` | 真浏览器、回调与视觉回归 |
| `reports/assets/p2-extension-vitals-review/` | 测试证据与新视觉基线 |
| `docs/决策与接口变更.md`、`docs/进展与欠账.md` | 新口径和部署边界 |

## 4 验证与证据

| 命令 | 实际结果 |
| --- | --- |
| `python -m pytest apps/api -q`；`python -m pytest apps/api -q -o 'addopts='` | 两次退出 0，475 passed。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18202` | 16/16，SSE 10 个引用。 |
| `npm.cmd --prefix apps/web run build` | 76 modules，入口 JS 236.35 kB，离线预缓存 18 个文件。 |
| `node --test scripts/extension.test.cjs scripts/css-audit.test.cjs scripts/engine-query.test.cjs` | 28 项通过。快捷键、右键和 omnibox 额外执行回调单测。 |
| `node scripts/verify-extension.cjs http://127.0.0.1:18202 reports/assets/p2-extension-vitals-review/extension` | `CS_HEADLESS=true`、`CS_BROWSER_CHANNEL=chromium`，实际加载扩展，`ALL PASS (14)`。设置页通过实际服务确认有效和无效 token，模拟 500 也正确报错。弹窗和后台收藏均真实入库，测试记录清除。[扩展证据](../assets/p2-extension-vitals-review/extension/extension.json) |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18202 --test-bookmark-writes --out reports/assets/p2-extension-vitals-review/chromium` | `ALL PASS (245)`。[Chromium](../assets/p2-extension-vitals-review/chromium/p0-ui-audit.json) |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18202 --channel chrome --test-bookmark-writes --out reports/assets/p2-extension-vitals-review/chrome` | `ALL PASS (245)`。[Chrome](../assets/p2-extension-vitals-review/chrome/p0-ui-audit.json) |
| `node scripts/visual-regression.cjs --base http://127.0.0.1:18202 --actual reports/assets/p2-extension-vitals-review/visual-repeat` | 固定样本 12 张，变化 0，缺基线 0。用空基线目录复跑返回 1，缺基线 12。[新基线](../assets/p2-extension-vitals-review/visual-baseline/manifest.json) |
| 定向 Chrome 执行原生 `fetchLater` 并观察队列 | 已排入只含路由和耗时的样本；浏览器套件另强制 beacon 返回 false，实际 keepalive POST 返回 204。[队列证据](../assets/p2-extension-vitals-review/chrome/fetch-later.json) |
| `node --check`；`git -c core.safecrlf=false diff --check` | 退出 0。 |

旧基线比对有五张不同，人工查看定位到现存书签、工具页端口和令牌尾号等易变样本。固定样本复验发现个别抗锯齿像素每通道差至 2 个色阶。新规则先核对基线文件哈希，像素比较透明度要求相同，RGB 仅放行 0–2 个色阶。

## 5 关键决策

- 性能上报使用标准指标库和固定路由。支持 `fetchLater` 时合并更新排队中的快照，其他浏览器在隐藏时走 beacon 或 keepalive。[Chrome 会话遥测指南](https://developer.chrome.com/docs/modern-web-guidance/guides/performance/full-session-analytics) · [web-vitals](https://github.com/GoogleChrome/web-vitals)
- 收藏保留直接用户动作授予的标签权限，并验证运行时真实的扩展服务工作线程。快捷键、地址栏和菜单的系统交互与回调单测分别记证据。

## 6 遗留与风险

- 正式 Chrome/Edge 工具栏弹窗的当前标签自动预填、系统快捷键、地址栏和右键实际点击待人工验收。已验证独立 Chromium 中打开扩展页面、命令注册、后台回调及真实收藏。Android/iOS 系统分享待真机。
- 日常 `8000` 读到的 `/api/metrics` 仍无 `vitals` 字段。隔离服务已验收新后端，日常后端需沿用现有数据库、令牌和启动参数重新加载。
- 性能样本来自隔离 fixture，尚无真实上游和长期数据。视觉基线以本机字体、分辨率和浏览器环境复跑。

## 7 交接

先在日常服务加载后端并确认 `GET /api/metrics` 含 `vitals`，再用正式浏览器的独立配置补验工具栏、快捷键、地址栏和右键菜单。P2 第 7 条筛选维持原计划单独立项。
