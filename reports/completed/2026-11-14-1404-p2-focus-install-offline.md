# 完工报告 · 焦点归还、安装态与离线文案（P2）

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261114-1404 |
| 开始 | 2026-11-14 14:04 |
| 结束 | 2026-11-14 14:05 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 复查与完善方案](../../docs/浏览器与UI复查与完善方案.md) §4.6 收尾 P2：快捷键面板关闭后的焦点归还（R-08）、安装按钮不可用态的语义（R-09）、离线时的产品化文案与只读约束（R-11）。

**验收标准**

- 从无焦点状态（`activeElement=body`）按 `?` 打开、Esc 关闭后，焦点落在「? 全部快捷键」按钮上，不再是 body。
- 浏览器没提供安装入口时，安装按钮是 `disabled` 且有「可从浏览器菜单安装」的提示，而不是可聚焦的绿色主按钮。
- 断网时页头出现「连不上本机服务」，设置页/引擎设置显示中文文案，不出现 `Failed to fetch`；引擎设置只剩读取类操作可点。
- 网络恢复（`online` 事件）后自动重新核对 health，不需要刷新页面。
- pytest / 冒烟 / 浏览器断言 / 视觉基线全绿。

**不做**

- 不新建工作树；不改搜索/筛选/断点行为。
- 不做 §4.7 的审计脚本解耦与文档收口（下一轮）。
- 扩展与设置页的 token 轮换仍缺后端接口，继续保持待办。

## 2 做了什么

1. **焦点兜底**：`App` 增加 `closeShortcuts`，在 `requestAnimationFrame` + `setTimeout(0)` 后检查 `activeElement`：仍是 body 就把焦点交给 `.shortcuts__open`（不在 DOM 时退到 `#main`）。首轮实现只在 rAF 里聚焦，被原生 dialog 的异步焦点恢复覆盖，实测仍是 body——改成等它跑完再兜底。
2. **安装按钮**：`SettingsPage` 把 `aria-disabled` 换成真 `disabled`，加 `title` 说明浏览器菜单路径，保留“浏览器未提供安装入口”的说明文字与状态播报。
3. **统一网络错误文案**：`api.ts` 的 `jsonRequest` 捕获 fetch 失败（AbortError 除外）后抛 `ApiError(..., "NETWORK_ERROR", 0)`，引擎设置、设置页数据卡等不再透出 `Failed to fetch`。
4. **离线自愈**：`capabilities.useServerState` 首次读缓存 promise（多组件挂载仍只探一次 health），`online`/`offline` 事件触发 `refreshServerState()` 重探；首轮实现让每个组件挂载都重探，被既有“health 只探一次”的断言抓到（health=3），已修回 health=1。
5. **离线只读**：`EngineSettingsPanel` 用 `useServerState()` 判定 offline，禁用「保存引擎设置」，保留「重新读取 / 刷新状态」。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `apps/web/src/App.tsx` | 修改 | `shortcutsTrigger` ref + `closeShortcuts` 焦点兜底 |
| `apps/web/src/SettingsPage.tsx` | 修改 | 安装按钮 `disabled` + `title` |
| `apps/web/src/api.ts` | 修改 | `jsonRequest` 网络失败中文文案 |
| `apps/web/src/capabilities.ts` | 修改 | `refreshServerState`、`online/offline` 重探、首次仍用缓存 |
| `apps/web/src/components/EngineSettingsPanel.tsx` | 修改 | 离线禁用保存 |
| `scripts/audit-ui.cjs` | 修改 | 4 项新断言 + 修正 health 探测计数断言 |
| `docs/决策与接口变更.md`、`docs/浏览器与UI复查与完善方案.md` | 修改 | P2 决策与落地状态 |
| `reports/assets/p2-focus-install-offline/` | 新增 | 审计日志（300 项）、截图、`pytest.log`、`actual/` |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `npm --prefix apps/web run build` | 通过 | `tsc --noEmit` + Vite |
| `python -m pytest apps/api -q -o addopts=` | 通过 | `489 passed in 11.07s`（[日志](../assets/p2-focus-install-offline/pytest.log)） |
| `node --test (Get-ChildItem scripts -Filter '*.test.cjs').FullName` | 通过 | 36 passed / 0 failed |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:8000 --out reports/assets/p2-focus-install-offline/audit` | 通过 | **`ALL PASS (300)`**（[明细](../assets/p2-focus-install-offline/audit.log)） |
| `node scripts/visual-regression.cjs --base http://127.0.0.1:8000 --out …/visual-baseline --actual …/actual` | 通过 | `对比 12 张：变化 0，缺基线 0` |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8000` | 通过 | `冒烟通过 16/16，跳过 0` |

关键断言原文（`audit.log`）：

- `PASS 无焦点时关闭面板把焦点交还「全部快捷键」 · {"tag":"BUTTON","text":"? 全部快捷键","isBody":false}`
- `PASS 未提供安装入口时按钮真禁用并给菜单指引 · {"text":"浏览器未提供安装入口","disabled":true,"title":"浏览器未提供安装入口，可从浏览器菜单安装"}`
- `PASS 断网时页头显示连不上本机服务 · 连不上本机服务 确认 FastAPI 已启动（默认 http://127.0.0.1:8000）…`
- `PASS 断网时引擎设置用中文文案且没有可写的保存 · {"engineError":"连不上本机服务，确认 FastA…`
- `PASS 探测与旧后端均无未确认的收藏状态和性能请求 · {"health":1,"status":0,"vitals":0}`（修复后回到 1 次探测）

首轮失败证据（已修）：`FAIL 无焦点时关闭面板把焦点交还「全部快捷键」 · {"isBody":true}`、`FAIL 探测… · {"health":3}`。

未验证：iOS Safari 的原生 dialog 焦点行为；离线壳内点击写操作的真实失败提示（本轮只保证按钮禁用）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 焦点兜底放在 App 而不是 dialog 内 | 在 `ShortcutsDialog` 内 `onClose` 里 `focus()` | 需要知道“哪个按钮是触发器”，App 持有该 ref；dialog 只负责对话框语义 |
| 等 rAF + `setTimeout(0)` 再聚焦 | 只在 rAF 聚焦 | 原生 dialog 的焦点恢复在关闭后异步执行，抢在前面会被覆盖 |
| 首次探测用缓存 promise，只在网络事件重探 | 每次挂载都重探 | 多组件同时挂载会打出多次 health；既有断言（health 只探一次）正是为了防止这种放大 |
| 安装按钮 `disabled` 而不是纯文本 | 保留按钮 + `aria-disabled` | R-09 的根因就是“可聚焦但点了没反应”，纯文本会丢掉状态播报路径 |
| 网络错误在 `jsonRequest` 统一翻译 | 每个面板各自 catch | 一处翻译覆盖全部调用方，避免以后新增面板又漏出英文原文 |

## 6 遗留与风险

- 离线判定来自一次 `/api/health` 探测（5s 超时），服务“能连但不健康”（如 500）不会被判成离线，只会走各自的错误态。
- `online` 事件由浏览器决定何时触发，个别浏览器在网卡切换时可能不触发；此时仍需手动刷新。
- 离线时只禁用了引擎设置保存；书签页、单页总结的写操作仍可点，会得到中文网络错误而不是被禁用——按方案“禁用重试以外的写操作”只覆盖了网络面板。

## 7 交接

**下一个人第一件事**

做 §4.7 验证补强与文档收口：把 `audit-ui.cjs` 里依赖真实结果的断言与 fixture 解耦（`page.route` 固定 `/api/search`），补 `urlState` 之外的纯函数单测，并把 `docs/浏览器与UI优化方案.md` 顶部标成历史审计、指向最新复查。

**相关文件**

- 焦点：`apps/web/src/App.tsx`（`closeShortcuts`）、`apps/web/src/components/ShortcutsDialog.tsx`
- 离线：`apps/web/src/capabilities.ts`、`apps/web/src/api.ts`、`apps/web/src/components/EngineSettingsPanel.tsx`、`apps/web/src/components/ServerBanner.tsx`
- 断言：`scripts/audit-ui.cjs`（文件末尾 P2 段）
- 证据：`reports/assets/p2-focus-install-offline/`
