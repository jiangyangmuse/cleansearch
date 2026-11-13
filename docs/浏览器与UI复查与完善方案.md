# 浏览器与 UI 复查与完善方案

> 复查对象：2026-11-13 22:38 构建的 `apps/web/dist` 与当前工作区后端代码。为不触碰日常 `8000` 进程，实测在隔离实例 `127.0.0.1:18400`（真实 SearXNG + 临时数据库 + stub 模型）进行，另保留 `18401` fixture 实例做固定样本断言。
> 方式：读实现与决策、独立 Playwright/Chromium 复跑、端点对照、离线/断点/焦点/axe 实验。未改任何产品代码、配置、数据或 `dist`。
> 证据截图：`reports/assets/browser-ui-recheck/`。复查报告：`reports/completed/2026-11-13-2316-browser-ui-recheck.md`。

## 0 结论

这一轮 P0–P2 的代码交付是扎实的：fixture 浏览器断言 253 项全绿，pytest 全绿，离线壳、OpenSearch、扩展静态检查、主题、触控、结果卡和抽屉都能在隔离实例复现。问题已经从“功能没做”转到“边界状态和交付一致性”：

1. **筛选状态与浏览器历史脱节**：地址栏回到无筛选的 URL 后，界面仍显示“已筛选：一周内”，结果仍是 13 条，且不再发请求；再翻页又把 `range=week` 写回 URL。
2. **筛选浮层没有退出路径**：点外部和按 Esc 都不关闭，面板覆盖官方入口与分页；在 390px 下从 x=96 展开 358px，右侧被视口裁掉。
3. **交付实例混版**：日常 `8000` 是旧 fixture 后端，前端却是新 dist。新前端请求 `/api/bookmarks/status` 得到 404、`/api/metrics/vitals` 得到 405，模型测试 405，筛选参数被旧 schema 忽略（base/site/week 都返回同一批 10 条）。这会让用户以为新功能坏了。
4. **手机 PWA 缺少可用路径**：服务只接受回环 Host；用电脑局域网 IP 访问会 403。PWA 安装/系统分享在手机上缺少完成路径，除非额外做允许主机或反代。
5. **断点与方案不一致**：方案写“900–1179 两栏、右栏变抽屉”，实现仍是三栏；901px 主列只有 478px，1024px 为 601px。
6. **移动首屏仍然偏工具化**：首条自然结果 y=766（390×844），只露出标题顶部；官方入口 3 条占据大部分首屏。

建议下一轮只做 4 个 P0：筛选状态/浮层、版本对齐、手机 PWA 范围决策、断点；其余作为 P1/P2 打磨。

## 1 复查基线

| 项 | 命令/方式 | 结果 |
| --- | --- | --- |
| API 测试 | `python -m pytest apps/api -q -p no:cacheprovider` | 全绿（100%，无 F/E；项目口径 482 项） |
| 静态检查 | `node --test scripts/extension.test.cjs scripts/css-audit.test.cjs scripts/engine-query.test.cjs` | 28/28 通过 |
| fixture 浏览器断言 | `node scripts/audit-ui.cjs --base http://127.0.0.1:18401` | `ALL PASS (253)` |
| 真实上游浏览器断言 | `node scripts/audit-ui.cjs --base http://127.0.0.1:18400` | 在筛选刷新步骤超时（等待 `.results-body`，见 §3 R-12），未完成 253 |
| 离线壳 | 18400 注册 SW 后 `setOffline` 打开 `/settings` | 壳与设置页可加载；引擎设置显示英文 `Failed to fetch` |
| OpenSearch | `GET /opensearch.xml` | 200、`application/opensearchdescription+xml`、绝对模板 |
| 主题 | light/dark context | `data-theme`、`color-scheme`、`theme-color` 分别 `#ffffff`/`#1b2320` |
| 扩展 | manifest/图标/commands/omnibox/options | 静态检查通过，图标像素尺寸正确 |
| 日常 8000 | `/api/health` | `provider=fixture`，无 `db_path`；旧后端 |

对照实验（同一请求体）：

| 端口 | base | site=example.com | time_range=week | `meta.filters` |
| --- | --- | --- | --- | --- |
| 8000（旧后端） | 10 条 | 10 条 | 10 条 | 不存在 |
| 18400（当前代码） | 15 条 | 5 条 | 10 条 | 正常回显 |

旧后端把新参数静默忽略，这比报错更危险：界面看起来支持筛选，实际没有生效。

## 2 已经确认修好的

- URL/标题/页码：搜 A→搜 B→后退回 A；第 2 页刷新仍第 2 页；标题为 `q · CleanSearch`。
- 移动抽屉：打开后 `.workspace-results` top 保持 243；Esc 关闭并把焦点还给 FAB；遮罩关闭正常。
- 引擎分组：设置页为“中国大陆可直连 4 / 其他引擎 16”；禁用开关 20/20，checked=0，opacity=0.4。
- 旧页面：书签品牌与正文 x 差 0；工具页 `pre` 不再横向溢出；移动书签工具栏分行。
- 触控：390 下主要控件 ≥44；粗指针下页头、分页、收藏、开关均放大。
- 标题层级/播报：结果页 h1=1、卡片 h3、skip link 与 live region 存在；axe 在结果、抽屉、筛选状态均为 0 violation。
- 离线/PWA：SW 注册、壳缓存、未访问路由离线打开、OpenSearch、manifest shortcuts 均可用。

## 3 新发现问题

| ID | 严重度 | 问题 | 证据 | 影响 |
| --- | --- | --- | --- | --- |
| R-01 | P0 | 筛选变化未参与 `popstate` 比较 | 选中一周后 URL `?q=python&range=week`；后退到 `?q=python` 后 badge=1、note=已筛选：一周内、meta=13 条、无新请求；再翻页 URL 变 `?q=python&page=2&range=week` | URL 与界面/结果不一致；分享、刷新、后退全部失真 |
| R-02 | P0 | 筛选浮层点外部/Esc 不关闭，遮挡结果 | 桌面打开后点侧栏/按 Esc，`.filters[open]` 仍在；Playwright 点击结果被 `.filters__body` 拦截 | 用户选完筛选后点不到结果，必须先找回“筛选”按钮 |
| R-03 | P0 | 移动筛选面板超出视口 | 390 下面板 x=96、w=358，右边 454 > 390；截图右侧被裁 | “一月内/一年内”、站点输入和去重下拉不可完整操作 |
| R-04 | P0（ops） | 8000 前后端混版 | 新 dist + 旧 API；`/api/bookmarks/status` 404、`/api/metrics/vitals` 405、模型测试 405、`/opensearch.xml` 返回 text/html；筛选参数被忽略 | 新功能在日常实例上表现为“坏了”，验收与用户反馈会错位 |
| R-05 | P1（范围） | 手机 PWA 没有可用部署路径 | `Host: 192.168.1.10:18400` 返回 403 HOST_FORBIDDEN；服务只允许回环 | Android 安装/系统分享没有真机完成路径；要么加允许主机/HTTPS，要么明确只支持同机 |
| R-06 | P1 | 900–1179 仍是三栏 | 901 主列 478、1024 主列 601，右栏常驻 285；与方案 §3.7/§4 的“两栏 + 抽屉”不符 | 小笔记本/分屏统计与卡片折行；1024 断言反而固定了三栏 |
| R-07 | P1 | 移动首屏仍以工具/官方入口为主 | 390 首条结果 y=766，仅露出标题；官方入口 3 条未按方案 §4.2 收敛到 2 条 | 用户需要滚动才能确认“搜到了什么” |
| R-08 | P2 | 快捷键面板关闭后焦点落到 body | 键盘 `?` 打开，Esc 关闭后 activeElement=BODY，不是触发按钮 | 读屏/键盘用户丢失位置；与决策中“归还触发按钮”不符 |
| R-09 | P2 | 安装按钮不可用时仍是可聚焦的主按钮 | `aria-disabled=true`，`disabled=false`，tabIndex=0，绿色主按钮样式 | 点击无反应，像坏按钮；应 disabled 或改为说明文字 |
| R-10 | P2 | 空首页仍是一整屏空白 | 390 空首页文本只有搜索/后缀/筛选/日常 AI；无最近搜索、示例或快捷入口 | 首次使用缺少起点，搜索历史能力不可见 |
| R-11 | P2 | 离线时设置页出现英文 `Failed to fetch` | 断网打开 /settings，引擎设置直接显示原始错误 | 离线壳有，但错误不是产品化文案；应给全局离线条与禁用网络操作 |
| R-12 | P2（验证） | 253 项断言与真实结果强耦合 | 18400 真实上游在 `range=week&site=example.com` 刷新后无结果，脚本等待 `.results-body` 超时；fixture 253 全绿 | “真实模式 253 全绿”不可稳定复现；筛选回退/关闭也没断言 |

## 4 完善方案

### 4.1 P0-1：把筛选纳入 URL 状态机

- 在 `urlState.ts` 增加筛选比较/规范化函数；`App.onPopState` 同时比较 `q/literal/page/category/range/lang/site/dedupe`。
- 若筛选不同：先 `setFilters(restored)`、`filtersRef.current = restored`，再调用 `runSearch`，并给 `runSearch` 增加 `filtersOverride`（或把筛选作为显式参数），避免读旧 ref。
- 不要因为 `sameQuery && samePage && sameView` 早退；空首页回退也要把筛选重置为 URL 值。
- 翻页、重试、历史词点击都必须沿用“当前 URL 的筛选”，不要把上一轮 ref 又写回 URL。
- 验收：选 week→back，badge=0、note 为空、请求不带 `time_range`、结果数回到 base；week→day→back 回到 week；选 site→back 后 site 输入框清空；翻页 URL 不再带已回退的筛选。

### 4.2 P0-2：筛选浮层的关闭与定位

- 在 `SearchFilters` 内用 ref + `pointerdown` 监听外部关闭；Esc 关闭并把焦点还给 `summary`；路由/查询变化时关闭。
- 或把 App 现有的“引擎菜单/卡片菜单外部关闭”统一到一个 popover 管理器，避免每个浮层各写一套。
- 桌面加 `max-height: min(70vh, 520px); overflow:auto`，避免小高度视口裁切。
- ≤900px 改成视口对齐的固定面板：`position:fixed; inset-inline:16px; top: calc(var(--header-height) + 96px); width:auto; max-height:70vh; overflow:auto`；或直接复用底部抽屉。
- 验收：点结果、点侧栏、按 Esc 都能关闭；390/320 面板完整在视口内；关闭后结果区可点击。

### 4.3 P0-3：消除混版

- `/api/health` 增加 `api_version` / `capabilities`（至少 `filters`、`bookmark_status`、`vitals`、`model_test`、`opensearch`）。
- 前端启动时读取 health，能力缺失就显示“服务版本过旧，请重启本机服务”横幅，并禁用对应 UI（筛选、模型测试、批量收藏状态），不要静默失败。
- 运行手册写成一条可执行步骤：停旧进程 → `serve.ps1 -Provider searxng -SkipBuild`（或明确的端口/环境变量）→ 用 `/api/health` 核对 capability；禁止“新 dist + 旧 API”长时间并存。
- 验收：8000 health 含 `db_path` 与 capabilities；筛选在 8000 与 18400 行为一致；`/opensearch.xml` 返回 XML MIME；批量状态与 vitals 不再是 404/405。

### 4.4 P0-4：断点与手机范围二选一

**断点**

- 把抽屉断点从 900 提到 1180（或至少 1100），`useMediaQuery`、`workspace.css`、`audit-ui.cjs`、视觉基线同步；1024 断言改为“抽屉可用、主列 ≥560”，不再固定三栏。
- 1440 仍三栏；≥1660 保持 1920 右栏 360。

**手机 PWA**

- 如果手机/系统分享是产品目标：增加受控 `ALLOWED_HOSTS`（回环 + 显式局域网域名/IP）或要求 HTTPS 反代，并同步扩展 host 权限、README 和验收；不要让 `LOOPBACK_HOST` 一边写“手机可装”一边 403。
- 如果只支持同机：从 PWA 分享/Android 验收项和产品文案中降级为“同机桌面 PWA”，不要保留会失败的手机步骤。

### 4.5 P1：移动首屏与空态

- 移动端官方入口最多展示 2 条，折叠为“查看全部 N 条”；或把官方入口移到前 3 条结果之后。
- 结果数/检索详情压成一行 sticky；目标首条结果标题在 390×844 的 y ≤ 700。
- 空首页加“最近搜索”（历史最多 8 条，可单条删除）、3 个示例查询、“书签/单页总结/AI 对话”快捷入口；无历史时只显示示例与快捷键提示。
- 首条结果在 320 下至少露出标题和摘要首行；必要时把官方入口默认折叠。

### 4.6 P2：焦点、安装态、离线文案

- 快捷键面板记录打开前的焦点，关闭后恢复到“全部快捷键”按钮或 `?` 触发器；读屏测试补一条。
- 安装按钮在 `!installable && !standalone` 时使用 `disabled`，或改为纯说明文本 + “浏览器菜单安装”步骤。
- 离线时在 AppShell 显示全局“本机服务未连接/离线壳”条；网络面板统一用中文产品文案，禁用重试以外的写操作。
- 扩展/设置页 token 轮换仍缺后端接口，继续保持待办。

### 4.7 验证补强

- `scripts/audit-ui.cjs` 新增：筛选外部点击/Esc/路由关闭；筛选 back/forward/刷新；翻页不带回退筛选；390/320 筛选面板 right ≤ viewport；1024 抽屉而非三栏；快捷键焦点归还；安装按钮 disabled。
- 把筛选断言与真实结果解耦：用 `page.route` 固定 `/api/search` 响应，或把“结果存在”断言放到 fixture 套件；真实上游只断言请求体、URL、meta.filters 与过滤规则。
- 增加 `urlState` 单元测试（node --test）：`readUrlState/searchUrl` 往返、非法 page/range/dedupe、筛选差异比较。
- 终验报告分两列：fixture 253 项（确定性）与真实上游检查（请求体/过滤/延迟，不承诺条数）。不要把真实上游的结果数当作断言前提。
- 文档：现有 `docs/浏览器与UI优化方案.md` 的 §0/§1 仍是 14:22 的历史审计口吻，建议在顶部加“已落地/最新复查见…”或把本文件作为新的现状入口，避免读者以为问题仍在。

## 5 建议顺序与估时

| 顺序 | 内容 | 估时 | 验收 |
| --- | --- | --- | --- |
| 1 | 筛选 URL 状态 + 浮层关闭/定位 | 1–1.5d | R-01/R-02/R-03 的断言全绿 |
| 2 | 版本 capability 与 8000 重启手册 | 0.5d | 8000/18400 行为一致；旧后端有明确横幅 |
| 3 | 断点 1180 + 1024 断言/基线 | 1d | 901/1024 抽屉；主列 ≥560 |
| 4 | 手机 PWA 范围决策与实施/降级 | 0.5–2d（取决于是否加反代） | 手机安装/分享可复现，或文档明确不支持 |
| 5 | 移动首屏/空首页/焦点/安装态/离线文案 | 1–2d | 390 首条 y≤700；焦点/离线/安装断言 |
| 6 | 审计脚本解耦与文档收口 | 0.5–1d | fixture/真实两套口径稳定，报告可复现 |

## 6 非目标

- 不改搜索排序、评分、官方入口表、付费/免费回退策略。
- 不做多用户、云同步、桌面壳、扩展商店上架。
- 不为了“过测试”放宽真实上游的条数断言，也不把 fixture 结果冒充真实上游。

## 7 关键文件

- 筛选/URL：`apps/web/src/App.tsx`、`urlState.ts`、`components/SearchFilters.tsx`、`styles.css`
- 断点/抽屉：`apps/web/src/workspace.css`、`useMediaQuery.ts`、`components/ToolDrawer.tsx`
- 版本/主机：`apps/api/app/main.py`、`apps/api/app/config.py`、`scripts/serve.ps1`
- 焦点/安装/离线：`components/ShortcutsDialog.tsx`、`SettingsPage.tsx`、`sw.js`、`offline.html`
- 验收：`scripts/audit-ui.cjs`、`scripts/visual-regression.cjs`、`reports/assets/browser-ui-recheck/`
