# 完工报告 · 浏览器功能与 UI 优化审计

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1432 |
| 开始 | 2026-11-13 14:22 |
| 结束 | 2026-11-13 14:32 |
| 耗时 | 10 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | research |
| 状态 | 完成 |

## 1 任务

**目标**

在不改动现有产品代码、配置和数据的前提下，实测本机运行实例的浏览器功能与 UI，找出结构性问题，给出按优先级排序、可直接执行的优化与完善方案。

**验收标准**

- 覆盖搜索页、书签、工具、单页总结、设置、AI 工具、扩展与 PWA 清单。
- 关键结论有可复现命令或截图证据，不用“感觉不好用”代替判断。
- 产出至少一份可执行的方案，含问题、改动点、文件、验收口径与估时。
- 不修改 `apps/` 下的产品代码与配置。

**不做**

- 不实现方案、不改 UI、不改接口、不重建 `dist`。
- 不做 Android 真机、正式 Chrome/Edge 手动加载扩展、商店上架。
- 不评估搜索排序/正文质量本身；只评估浏览器行为与界面。

## 2 做了什么

1. 读 `AGENTS.md`、`reports/INDEX.md` 最近条目、`docs/决策与接口变更.md` 的 2026-11-12/13 决策，确认当前范围与“大陆分组只含 Bing/搜狗/360/百度”的口径。
2. 通读前端 `App.tsx`、页面组件、`components/*`、`api.ts`、`styles.css`、`workspace.css`，以及 `apps/extension/`、`manifest.webmanifest`、`index.html`。
3. 用 Playwright 自带的 Chromium 对 `http://127.0.0.1:8000` 做真实浏览器实测：1440×900、1024、901、768、390×844、320、1920；浅色/深色；缓存与未缓存查询；搜索、翻页、后退、刷新、引擎菜单、AI 面板、错误/加载态、设置页、书签、工具、单页总结、对话页。
4. 用 DOM/ComputedStyle/CDP 量化：可交互元素尺寸、标题层级、aria-live、对比度、Service Worker 注册数、PWA 清单、请求数、断点列宽。
5. 截取 17 张证据图存入 `reports/assets/browser-ui-audit/`，把结论与方案写入 `docs/浏览器与UI优化方案.md`。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `docs/浏览器与UI优化方案.md` | 新增 | 现状地图、实测证据、P0/P1/P2 清单、布局方案、实施与验收 |
| `reports/2026-11-13-1432-browser-ui-audit.md` | 新增 | 本报告 |
| `reports/assets/browser-ui-audit/*.png` | 新增 | 17 张实测截图与说明 |
| `reports/INDEX.md` | 修改 | 按流程登记本报告一行 |
| `apps/**`、`data/**`、`dist/**` | 未改 | 用户要求不动现有产物 |

说明：工作区在本轮开始前已有大量未提交改动（见 `git status`），不属于本次产出；本轮没有 `git add/commit/push`。

## 4 验证与证据

| 命令/动作 | 结果 | 说明 |
| --- | --- | --- |
| `curl.exe -s http://127.0.0.1:8000/api/health` | 通过 | `provider=searxng`、`web_built=true`、`llm_model=qwen3.5-4b-local:latest` |
| `curl.exe -s http://127.0.0.1:8000/api/engines` | 4 mainland + 16 null | 证明“中国大陆可直连”标题下的 16 个引擎没有分组 |
| Playwright 搜索 `python 文档` | 22 条展示 / 上游 84 | 1440×900 与 390×844 均复现 |
| 后退测试 | `afterBack=about:blank` | 连续两次搜索后后退离开应用；`replaceState` 导致 |
| 第 2 页刷新 | URL 不变；刷新回第 1 页 | 页码未进 URL |
| 结果页标题 | `CleanSearch` | 未随查询更新 |
| 390×844 首条结果 | `y=1017` | 首屏 844px 内没有自然结果 |
| 打开 AI 总结 | 结果 top 372 → 793（+421） | 面板把结果推下 |
| 触控尺寸扫描 | 75/81 个可交互元素任一边 <44px | 开关 31×18、收藏 42×21、分页 58×24 |
| 引擎菜单外部点击 | `open=true` | 点外部/结果不关闭；Esc 才关 |
| 设置页引擎开关 | 20/20 disabled，12 checked，opacity=1 | 禁用态与启用态不可区分 |
| `/bookmarks` header | 品牌 x=300，正文 x=160 | 差 140px；390px 下链接竖排 |
| `/tools` 代码块 | scrollWidth 4956 / clientWidth 314 | 横向溢出 |
| 标题层级 | h1=0，h2=28 | 读屏无法按标题导航 |
| aria-live | 0 个 | 搜索完成不播报 |
| Service Worker | registrations=0 | 无离线/缓存/更新控制 |
| 对比度抽样 | 5.44–8.84:1 | 通过；问题是 11px 字号 |
| CDP `Page.getInstallabilityErrors` | `[]` | Chrome 112+ 菜单安装不强制 SW；但无 SW 仍无离线/POST 分享 |
| 320/768 宽度 | scrollWidth = viewport | 无横向溢出 |
| 901px 主列 | 478px | 三栏断点过窄 |
| 1920 布局 | 主列 391–1361，右栏 1560 起 | 199px 空隙，右栏脱节 |
| `Get-Item dist/assets/*.js` | 304,623 B，14:02 构建 | 先于 14:05 启动的服务，审计对应当前构建 |

**截图证据**（`reports/assets/browser-ui-audit/`）：`01-desktop-idle.png`、`02-desktop-results.png`、`03-desktop-engine-menu.png`、`04-desktop-summary-rail.png`、`05-desktop-dark.png`、`06-desktop-901.png`、`07-desktop-1920.png`、`08-mobile-idle.png`、`09-mobile-first-screen.png`、`10-mobile-summary-push.png`、`11-mobile-engine-menu.png`、`12-mobile-bookmarks.png`、`13-mobile-tools.png`、`14-settings-engines.png`、`15-error-state.png`、`16-mobile-320.png`、`17-loading-state.png`。

**未验证**

- Android 真机安装/系统分享、正式 Chrome/Edge 手动加载扩展（沿用项目既有欠账）。
- Lighthouse/axe 自动评分未跑；本轮是自写 DOM 检查，建议方案落地后补 `@axe-core/playwright`。
- PWA GET 分享在无 SW 时是否由浏览器直接导航到 `/bookmarks`，未在真机确认；报告只主张“无离线/POST 分享/更新控制”，不主张“完全不可分享”。
- 真实 Chrome 版本差异：本机 Playwright Chromium 与稳定版 Chrome 的触控/安装 UI 可能有差异。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 只出方案，不动产品代码 | 直接改 P0 | 用户明确“不要动现在的产物”；且工作区已有未提交改动，贸然改会混淆责任边界 |
| 以 390×844 与 1440×900 为主证据 | 只看桌面截图 | 移动端首屏无结果、面板推挤是结构性问题，桌面看不出来 |
| P0 先修浏览器语义/移动端/状态 bug | 先做视觉重设计 | 这三类直接影响可用性与信任；视觉风格本身可保留 |
| 保留现有绿色系与卡片语言 | 全面换视觉 | 当前对比度合格、品牌一致；问题在密度、层级、断点与状态 |
| 方案写入 docs，报告只做摘要 | 全塞进报告 | 报告 ≤260 行，方案需要表格、线框图和分阶段清单 |

## 6 遗留与风险

- 审计基于当前 `dist`（14:02）与真实 SearXNG 实例；上游状态（DuckDuckGo 冷却等）会影响耗时/条数，不影响布局结论。
- 引擎“中国大陆可直连”误标是前端分组渲染问题（`section:null` 无标题、无分隔），不是数据问题；修复时需同时改菜单和设置页，避免只修一处。
- 移动端抽屉若用 `<dialog>`，需验证焦点圈定、Esc、iOS 滚动锁；不要复用旧 `.layout__side` 的 transform 方案而不做焦点管理。
- URL 历史改造会影响分享链接、搜索历史、AI 面板自动打开逻辑；需补 Playwright 回归，避免 `popstate` 重复请求。
- Service Worker 必须只缓存同源静态资源，不能缓存 `/api/*` 的搜索结果；否则会破坏“每次检索可复现”的预期。
- 扩展无图标/快捷键/omnibox 属于可用性缺口，不影响现有收藏链路；但加 `commands` 后要在正式 Chrome 手动加载验证。
- 工作区 `git status` 已有大量未提交改动；本报告与截图是新增文件，未触碰 `apps/` 与 `data/`。提交时请只挑本报告相关路径。

## 7 交接

**下一个人第一件事**

按 `docs/浏览器与UI优化方案.md` 的 P0 顺序先做 B-01（URL/历史/标题）和 B-02（移动端工具抽屉）；两者改完后用 390×844 复测“首条结果 y<844、打开总结不推挤结果、后退回上一次搜索”三条断言。

**相关文件**

- 方案：[docs/浏览器与UI优化方案.md](../../docs/浏览器与UI优化方案.md)
- 截图：`reports/assets/browser-ui-audit/`
- 搜索页/历史：`apps/web/src/App.tsx`、`searchHistory.ts`
- 移动端布局：`apps/web/src/workspace.css`
- 引擎分组：`apps/web/src/engineQuery.ts`、`components/EngineBar.tsx`、`components/EngineSettingsPanel.tsx`
- 旧页面 header：`styles.css`、`BookmarkPage.tsx`、`ToolsPage.tsx`、`PageSummaryPage.tsx`
- PWA/扩展：`apps/web/index.html`、`public/manifest.webmanifest`、`apps/extension/`