# 完工报告 · P2 可观测性与设计系统清理

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2215 |
| 开始 | 2026-11-13 22:15 |
| 结束 | 2026-11-13 22:15 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §7 落地 P2 第 8、9 条：前端上报 Web Vitals 与搜索/面板耗时到本机；清理 M2/M7 遗留死样式、token 化间距/圆角/字号，并加 Playwright 截图视觉回归。

**验收标准**

- `POST /api/metrics/vitals` 合法样本返回 204 并出现在 `GET /api/metrics.vitals`；非法值 422。
- 搜索与面板耗时在页面隐藏时通过 `sendBeacon` 上报一次。
- 样式表里不再出现 `.summary-toggle`/`.layout*`/`.ai-search-controls`/`.metabar__route`/`.engines__dot*` 等死选择器；token 已定义并被引用。
- `scripts/visual-regression.cjs` 能建立并比对 12 张基线截图（0 变化）。
- 既有 239 项浏览器断言不回归；pytest 与构建通过。

**不做**

- 第 7 条筛选能力（时间/语言/站点）：方案标注「单独立项」，需要后端 `opts` 扩展与缓存键升级，本轮不动。
- 不引入 `@playwright/test` 的 `toHaveScreenshot`（当前依赖只有 `playwright`），视觉回归用哈希比对。

## 2 做了什么

1. **后端**：新增 `apps/api/app/core/vitals.py`（200 条环形缓冲）与 `POST /api/metrics/vitals`（Pydantic 校验范围），`GET /api/metrics` 增加 `vitals:{count,recent}`；新增 1 个用例覆盖合法/非法输入。
2. **前端采样**：新增 `perf.ts`：`PerformanceObserver` 采集 LCP/CLS/INP/TTFB；`cs:search-start/end` 测搜索端到端；面板打开到渲染完成记 `panel_ms`；`visibilitychange`/`pagehide` 用 `sendBeacon` 上报，开发环境同时打 console。
3. **埋点接线**：`runSearch` 开始/响应处埋点；`togglePanel` 开面板时打点、`useEffect([sidePanel])` 渲染完成收尾。
4. **死样式清理**：删除 `.header`/`.brand*`/`.main`/`.layout*`/`.ai-search-controls`/`.summary-toggle` 与其 1080 媒体块（保留 `.shortcuts{display:none}`）、`.metabar__route`、`.state__error`、`.engines__dot*`、`.engines__label`、`.main--wide`、`.header__links`、`.header__link--active`；保留 `.header__link`（主题按钮仍在用）。
5. **设计 token**：新增 `--space-1..6`、`--radius-sm/md/lg`、`--font-xs/sm/md/base`，并把 `.card` 内边距、`.state__actions`、`.settings-actions`、`.suggest__item`、`.workspace-brand__mark`、`.card__actions-menu` 改为引用 token。
6. **视觉回归**：新增 `scripts/visual-regression.cjs`：6 路由 × 桌面浅色/移动深色，截图前注入「禁用动画」样式并遮罩 `.metabar`/`.quick-bookmarks`/`.summary__sid` 等易变区域，对 PNG 取 sha256 与基线比对；`--update` 重建基线。
7. **静态检查**：新增 `scripts/css-audit.test.cjs`，断言死选择器不再出现、token 已定义且至少被引用若干次。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/api/app/core/vitals.py` | 新增 | 环形缓冲与快照 |
| `apps/api/app/main.py` | 修改 | `VitalsSample` + POST 端点 + metrics 合并 |
| `apps/api/tests/test_search.py` | 修改 | vitals 上传/快照/校验用例 |
| `apps/web/src/perf.ts` | 新增 | Web Vitals 采集与上报 |
| `apps/web/src/main.tsx` | 修改 | `initPerf()` |
| `apps/web/src/App.tsx` | 修改 | 搜索/面板埋点 |
| `apps/web/src/styles.css`、`workspace.css` | 修改 | 删死样式、加 token、少量规则改用 token |
| `scripts/visual-regression.cjs` | 新增 | 截图基线与比对 |
| `scripts/css-audit.test.cjs` | 新增 | 死样式与 token 静态检查 |
| `reports/assets/visual-baseline/` | 新增 | 12 张基线截图 + manifest.json |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md` | 修改 | 新接口与完成标注 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -q` | 通过 | 475 项（474 + vitals 用例），`[100%]` 无 F/E |
| `node --test scripts/css-audit.test.cjs` | 通过 | 3 项：死样式清零、token 定义齐全、token 已被引用 |
| `node scripts/visual-regression.cjs --base http://127.0.0.1:18196` | 通过 | 12 张基线对比「变化 0，缺基线 0」 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18196 --out reports/assets/ui-p2` | 通过 | `ALL PASS (239)`，样式清理未破坏布局 |
| `npm --prefix apps/web run build` | 通过 | 73 modules，JS 230.58 kB 主包 + 页面分包 |
| 环境 | — | 验收用独立 `serve.ps1 -Provider fixture -Port 18196`，验完已停 |

**证据文件**

- 视觉基线：`reports/assets/visual-baseline/`（12 张 + `manifest.json`）
- 审计结果：`reports/assets/ui-p2/p0-ui-audit.json`

**未验证**

- Web Vitals 在真实浏览器里的数值未做长期观察；`INP` 用 `event` 条目近似，Safari 不支持该 Observer（会静默跳过）。
- 视觉回归依赖同一环境（字体、DPR）才能稳定，跨机器会误报；仅作为本机回归信号。
- 死样式判定基于「类名在 TSX 中是否出现」，动态拼接类（如 `badge--${provider}`）靠人工确认保留。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| vitals 只留内存环形缓冲 | 写数据库/日志 | 本地单用户调试用，落盘会带来清理与隐私问题 |
| 上报用 `sendBeacon` | 普通 fetch | 页面隐藏时 fetch 可能被取消，beacon 更可靠 |
| 视觉回归用哈希而非像素 diff | 引入 pixelmatch/sharp | 依赖最小化；哈希能稳定发现「是否变了」，变化定位靠人工看基线图 |
| 截图遮罩易变区域 | 固定 fixture 时间戳 | `.metabar` 的缓存/耗时本就随运行变化，遮罩比造数据更稳 |
| token 只替换等值处 | 全量重排间距 | 避免改变视觉，先建立刻度再逐步收敛 |

## 6 遗留与风险

- 第 7 条筛选能力未做，方案已标「单独立项」；需要后端 `opts` 扩展（时间范围/语言/站点）与缓存键升级。
- CSS 仍有未 token 化的魔法数字（如 `font-size: 13px` 多处），本轮只替换了等值点，后续可批量收敛。
- 视觉基线随构建产物变化（哈希 chunk 文件名不影响截图；但真实 UI 改动会失败），更新基线需显式 `--update`。
- 另一会话仍在同一工作区修改构建配置与 SW；本轮只动 `styles.css`/`workspace.css`/`App.tsx` 的局部与新增文件。

## 7 交接

**下一个人第一件事**

P2 只剩第 7 条（筛选能力，需单独立项）。建议先补齐后端 `opts`（时间范围、语言/地区、站点限定）与缓存键版本，再做前端筛选条；同时把剩余魔法数字收敛到 token，并在真实 Chrome 观察一轮 Web Vitals。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§7 第 8、9 条已标注）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P2 可观测性与设计系统）
- 实现：`apps/api/app/core/vitals.py`、`apps/web/src/perf.ts`、`scripts/visual-regression.cjs`
- 验收：`scripts/audit-ui.cjs`、`scripts/css-audit.test.cjs`、`reports/assets/visual-baseline/`