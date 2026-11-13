# 完工报告 · 浏览器与 UI 复查与完善方案

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2316 |
| 开始 | 2026-11-13 23:16 |
| 结束 | 2026-11-13 23:17 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | research |
| 状态 | 完成 |

## 1 任务

**目标**

在不改动现有产品代码、配置、数据和 `dist` 的前提下，复查已交付的浏览器/UI 构建：验证上一轮 P0–P2 的结论，找出仍未覆盖的状态问题，并把下一轮完善方案写成可执行清单。

**验收标准**

- 用当前构建与当前后端在隔离实例复跑核心断言，不依赖日常 8000 的旧进程。
- 至少验证一遍 fixture 253 项、pytest、静态检查与离线/PWA 关键路径。
- 新问题有可复现的命令、截图或端点对照，不把猜测写成结论。
- 产出按 P0/P1/P2 排序、含文件落点与验收口径的方案。
- 不修改 `apps/`、`data/`、`dist/`。

**不做**

- 不修代码、不重启用户的 8000 进程、不改视觉基线、不提交 git。
- Android/iOS 真机、NVDA/VoiceOver、正式 Chrome/Edge 手动加载扩展仍留待设备/条件。
- 不重新评估搜索排序、评分、正文质量或付费兜底策略。

## 2 做了什么

1. 读当前 `App.tsx`、`urlState.ts`、`SearchFilters`、`AppShell`、`ToolDrawer`、`SummaryPanel`、PWA/SW/扩展实现，以及 2026-11-13 的 P0–P2 决策和终验/真实上游报告。
2. 启动两个隔离实例：`18400`（真实 SearXNG、临时 DB、stub 模型）与 `18401`（fixture、临时 DB），避免触碰 8000 与用户数据库。
3. 复跑：pytest、node 静态检查、fixture `audit-ui.cjs`、真实上游 `audit-ui.cjs`、离线 SW、OpenSearch、主题、axe、移动断点、筛选历史/浮层/焦点/安装态。
4. 对照旧 8000 与新 18400 的端点能力与筛选请求结果，确认是否存在前后端混版。
5. 截取 8 张证据图到 `reports/assets/browser-ui-recheck/`，把新问题与下一轮方案写入 `docs/浏览器与UI复查与完善方案.md`。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `docs/浏览器与UI复查与完善方案.md` | 新增 | 复查结论、R-01…R-12、修订后的 P0/P1/P2 与验收补强 |
| `reports/2026-11-13-2316-browser-ui-recheck.md` | 新增 | 本报告 |
| `reports/assets/browser-ui-recheck/*.png` | 新增 | 8 张复查截图与索引 |
| `reports/INDEX.md` | 修改 | 按流程登记本报告一行 |
| `apps/**`、`data/**`、`dist/**` | 未改 | 用户要求不动现有产物 |

工作区在本轮开始前已有大量未提交改动，不属于本次产出；本轮没有 `git add/commit/push`。

## 4 验证与证据

| 命令/动作 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -q -p no:cacheprovider` | 通过 | 全绿，100%，无 F/E |
| `node --test scripts/extension.test.cjs scripts/css-audit.test.cjs scripts/engine-query.test.cjs` | 通过 | 28/28 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18401` | 通过 | `ALL PASS (253)`，fixture |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18400` | 未通过 | 真实上游在筛选刷新步骤等待 `.results-body` 超时；见 R-12 |
| `curl /api/health` 8000 | 旧版 | provider=fixture，无 `db_path`；新前端跑旧 API |
| 8000 `/api/bookmarks/status` | 404 | 新前端批量状态请求不可用 |
| 8000 `POST /api/metrics/vitals` | 405 | 新前端性能上报不可用 |
| 8000 `POST /api/settings/models/test` | 405 | 设置页模型测试不可用 |
| 8000 `/opensearch.xml` | 200，text/html | 新 `<link rel=search>` 指向 HTML，不是 XML |
| 8000 筛选对照 | base/site/week 均 10 条，`meta.filters` 缺失 | 新参数被旧 schema 静默忽略 |
| 18400 筛选对照 | base 15、site 5、week 10，`meta.filters` 正常 | 当前后端筛选生效 |
| 筛选后退 | URL 无 range，badge=1，note=已筛选：一周内，meta=13，无新请求 | R-01；再翻页 URL 出现 `page=2&range=week` |
| 筛选浮层关闭 | 点外部、按 Esc 均 `.filters[open]` 仍在；只有再点“筛选”关闭 | R-02；点击结果被 `.filters__body` 拦截 |
| 390 筛选面板 | x=96、w=358，右边界 454 > 390 | R-03；截图右侧被裁 |
| 390 首条结果 | y=766；320 下 y=793 | R-07；仅露出标题顶部 |
| 901/1024 布局 | 主列 478/601，右栏 285 常驻 | R-06；与方案“900–1179 两栏”不符 |
| `Host: 192.168.1.10:18400` | 403 HOST_FORBIDDEN | R-05；手机 PWA 无可用路径 |
| 离线 /settings | 壳可加载，引擎设置显示 `Failed to fetch` | 离线可用但错误文案未产品化 |
| 快捷键 Esc 焦点 | 关闭后 activeElement=BODY | R-08；未回到触发按钮 |
| 安装按钮 | `aria-disabled=true`、`disabled=false`、tabIndex=0 | R-09；可聚焦的无效主按钮 |

**截图**：`01-filter-popover-desktop.png`、`02-filter-popover-mobile.png`、`03-mobile-first-screen.png`、`04-desktop-901.png`、`05-desktop-1024.png`、`06-mobile-home.png`、`07-offline-settings.png`、`08-mobile-drawer.png`。

**未验证**

- 真实上游 `audit-ui` 的 253 项因筛选刷新无结果而中断；本轮只确认 fixture 253 全绿与真实请求/端点行为，未把它写成“真实全绿”。
- Android/iOS 安装与系统分享、NVDA/VoiceOver 朗读、正式 Chrome/Edge 手动加载扩展仍缺设备。
- 8000 的旧后端未重启；本轮只报告混版事实，不擅自替换用户进程。
- 真实上游筛选条数会随网络变化，本报告只对照同次请求的 base/site/week 行为。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 用 18400/18401 隔离实例复查 | 直接在 8000 上测 | 8000 是旧后端且连着用户数据；隔离实例才能验证当前代码 |
| 把筛选状态/浮层列为 P0 | 先做视觉打磨 | URL/结果/界面不一致会误导分享、刷新和回退；浮层直接挡住结果 |
| 把 8000 混版列为 P0（ops） | 只写“需重启”备注 | 新前端请求 404/405，用户会以为功能坏了；必须有版本握手或明确告警 |
| 手机 PWA 先做范围决策 | 直接加允许主机 | 涉及权限边界与 HTTPS，不应在未确认产品范围时擅自放开 |
| 不修改产品代码/基线 | 顺手修 P0 | 用户明确要求不动现有产物；且工作区已有大量未提交改动 |
| 审计脚本分 fixture/真实两套 | 继续一套 253 | 真实上游结果不可控，强耦合结果数的断言不可复现 |

## 6 遗留与风险

- 筛选修复会触及 `popstate`、`runSearch`、`writeUrl` 和筛选组件，需补回退/刷新/翻页三类回归，避免把筛选写回旧 URL。
- 浮层关闭若统一成全局 popover 管理器，注意不要影响引擎菜单、卡片菜单和原生 `<details>` 的键盘行为。
- 断点从 900 提到 1180 会改变 12 张视觉基线与 1024 断言，需要同步更新并人工复核 1024/1100。
- 手机 PWA 若增加允许主机，需同时考虑 HTTPS、Origin/CORS、token 与局域网暴露面；不要只改 Host 正则。
- 混版状态在用户重启 8000 前仍存在；复查报告不替代部署动作。
- 工作区原有未提交改动较多，提交时只挑本轮新增的 docs/report/assets 路径。

## 7 交接

**下一个人第一件事**

先做 R-01/R-02/R-03：把筛选加入 URL 状态机、让浮层点外部/Esc/路由变化关闭、把 390/320 面板限制在视口内；随后补 `audit-ui` 的筛选回退/关闭/面板边界断言。完成后再处理 8000 的 capability 握手与断点。

**相关文件**

- 方案：[docs/浏览器与UI复查与完善方案.md](../../docs/浏览器与UI复查与完善方案.md)
- 截图：`reports/assets/browser-ui-recheck/`
- 筛选/URL：`apps/web/src/App.tsx`、`urlState.ts`、`components/SearchFilters.tsx`、`styles.css`
- 断点/抽屉：`apps/web/src/workspace.css`、`useMediaQuery.ts`、`components/ToolDrawer.tsx`
- 版本/主机：`apps/api/app/main.py`、`scripts/serve.ps1`
- 验收：`scripts/audit-ui.cjs`、`reports/assets/browser-ui-recheck/`