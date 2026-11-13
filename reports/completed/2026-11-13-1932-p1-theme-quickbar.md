# 完工报告 · P1 主题细节与书签快捷栏刷新

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-1932 |
| 开始 | 2026-11-13 19:32 |
| 结束 | 2026-11-13 19:32 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §6 落地 P1 第 11、12 条：`color-scheme` 与 `theme-color` 跟随最终主题、`prefers-reduced-motion` 关掉 spinner/闪烁/平滑滚动；书签快捷栏在 `visibilitychange`/`pageshow`/删除事件后刷新，保持 6 条 + 管理入口、移动端在抽屉内。

**验收标准**

- 浅色/深色主题下根元素 `color-scheme` 分别为 `light`/`dark`，`meta[name="theme-color"]` 与主题表面色一致，`auto` 下跟随系统。
- `prefers-reduced-motion: reduce` 时 spinner 不旋转、页面不平滑滚动、骨架不脉冲。
- 快捷栏在 `visibilitychange`/`pageshow` 后重新拉取；请求带 `limit=6`；「全部书签」入口存在。
- 既有 170 项断言不回归；pytest 与前端构建通过。

**不做**

- P1 余下条目（AI 工具流控制、设置页增强、旧页面移动端）。
- 不改主题配色，只补 `color-scheme` 与 `theme-color` 这类浏览器 UI 同步。

## 2 做了什么

1. **theme.ts**：`applyTheme()` 在写 `data-theme` 的同时调用 `syncThemeColor()`，把 `meta[name="theme-color"]` 设为 `#ffffff`（浅）/ `#1b2320`（深），缺 meta 时动态补；`auto` 下系统主题变化仍走 `applyTheme("auto")`，颜色随之更新。
2. **styles.css**：`:root` 默认 `color-scheme: light`，并新增 `:root[data-theme="light"|"dark"]` 两个显式声明，替换原来的 `light dark`；新增 reduce 块关掉 `.spinner` 旋转、`.summary__cursor` 闪烁、`.card--flash` 与平滑滚动。
3. **踩坑**：第一版把 `.spinner { animation: none }` 放在 `.spinner` 自身定义之前，被后面的 `animation: spin …` 覆盖，实测算到 `animationName=spin`；改为紧随 `@keyframes spin` 之后。
4. **QuickBookmarks**：在已有 `cs:bookmark-saved`/`cs:bookmark-removed` 之外，新增 `pageshow`、`storage`、`visibilitychange`（仅 visible 时刷新）三类触发，卸载时一起清理。
5. **验收脚本**：新增 10 项断言（三态主题色与 `color-scheme`、reduce 下 spinner/滚动、快捷栏三种刷新与 `limit=6`）。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/web/src/theme.ts` | 修改 | `syncThemeColor` 与 `applyTheme` 同步 meta |
| `apps/web/src/styles.css` | 修改 | `color-scheme` 显式声明、reduce 动画块 |
| `apps/web/src/components/QuickBookmarks.tsx` | 修改 | pageshow/storage/visibilitychange 刷新 |
| `scripts/audit-ui.cjs` | 修改 | 新增 10 项断言（共 180 项） |
| `reports/assets/ui-p1/` | 修改 | 最新审计 JSON 与既有截图 |
| `docs/决策与接口变更.md` | 修改 | 记录 color-scheme/theme-color/reduce/刷新触发 |
| `docs/浏览器与UI优化方案.md` | 修改 | §6 第 11、12 条标注已完成 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18191 --out reports/assets/ui-p1` | 通过 | `ALL PASS (180)`：浅 `scheme=light meta=#ffffff`、深 `scheme=dark meta=#1b2320`、自动跟随系统、reduce 下 `spinner=none scroll=auto`、快捷栏 `条目 1 → 条目 2` 与 `calls 2 → 3`、`?limit=6` |
| `npm --prefix apps/web run build` | 通过 | 69 modules，JS 330.14 kB，CSS 54.27 kB |
| `python -m pytest apps/api -q` | 通过 | 465 项，`[100%]` 无 F/E（本轮未改后端） |
| 环境 | — | 验收用独立进程 `serve.ps1 -Provider fixture -SkipBuild -Port 18191`，验完已停 |

**证据文件**

- 审计结果：`reports/assets/ui-p1/p0-ui-audit.json`（180 项，含本轮 10 项）
- 截图：沿用 `mobile-dark-search.png`（深色）与 `desktop-light-search.png`（浅色）

**未验证**

- 真实浏览器地址栏颜色需要肉眼确认（无头环境只能读 meta 值）。
- 系统级切换深浅色（OS 设置变更）未在真机触发；`auto` 分支靠 `matchMedia` change 事件，代码路径未覆盖。
- 从书签页删除后返回搜索页（bfcache）的真实浏览器行为未验，只测了 `pageshow` 事件本身。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| `color-scheme` 写死在 `[data-theme]` | 保留 `light dark` 让浏览器猜 | 数据已明确最终主题，写死才能让滚动条/控件对齐 |
| `theme-color` 用 `--surface` 色值 | 用品牌绿 | 地址栏和页面顶部同色才不割裂；品牌绿只做强调色 |
| reduce 下只停动画，不改布局 | 全部动画归零 + 移除过渡 | 保留状态切换的可感知性，避免“点了没反应” |
| 快捷栏三种事件都刷新 | 只监听收藏事件 | 返回页面、后台切回、其它标签页改动都会让列表过期 |

## 6 遗留与风险

- `theme-color` 只在 `applyTheme` 时写；如果以后新增页面壳或被系统重设 meta，需要再走一次 `applyTheme`。
- `visibilitychange` 刷新在每次切回标签页都会请求一次 `/api/bookmarks?limit=6`，本机可忽略；如果将来加远端同步需要加节流。
- reduce 规则只覆盖已有动画，后续新增动画需记得放进 reduce 块。

## 7 交接

**下一个人第一件事**

在真机（Android Chrome / iOS Safari）确认地址栏颜色与 reduce 下的观感，然后做 P1 第 13、14 条：AI 工具合并后的流控制（关闭面板提示「后台生成中」或提供“停止”）+ 设置页增强（引擎搜索/筛选、测试连接、数据管理）。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§6 第 11、12 条已标注完成）
- 决策：`docs/决策与接口变更.md`（2026-11-13 · P1 主题细节与书签快捷栏刷新）
- 实现：`apps/web/src/theme.ts`、`apps/web/src/styles.css`、`apps/web/src/components/QuickBookmarks.tsx`
- 验收：`scripts/audit-ui.cjs`、`reports/assets/ui-p1/`