# 完工报告 · 桌面搜索布局与独立设置页

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261112-1959 |
| 开始 | 2026-11-12 19:59 |
| 结束 | 2026-11-12 20:00 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

把 CleanSearch 搜索页按手绘电脑版布局改版，并在右上角提供独立设置页。验收覆盖搜索、分类、折叠、书签跳转和主题与 AI 偏好保存。书签管理沿用现有页面。

## 2 做了什么

1. 左侧固定首页、百科、视频、下载导航，中间保留搜索与结果。分类切换使用当前结果及地址栏状态。
2. 右上角提供主题切换、书签和设置。右侧快捷栏显示最近六项收藏，记录折叠状态，搜索页收藏后即时刷新。
3. AI 检索和 AI 总结由右侧按钮分别展开。日常开关和 ds 后缀沿用原行为。保留键盘选结果、总结和引用跳转。
4. 新增可直接访问的设置页面。主题与日常 AI 设置共用浏览器偏好，工具区提供单页总结和一键添加书签。
5. 前端产物已更新至日常 8000。使用现有同源静态托管，日常 API 进程持续服务。

## 3 改动清单

| 文件 | 内容 |
| --- | --- |
| `apps/web/src/App.tsx`、`workspace.css`、`components/SearchBar.tsx` | 桌面布局、分类视图、窄屏重排、引擎和 AI 入口 |
| `apps/web/src/SettingsPage.tsx`、`main.tsx`、`searchPreferences.ts` | 独立路由及共同偏好 |
| `apps/web/src/components/WorkspaceHeader.tsx`、`components/QuickBookmarks.tsx`、`components/BookmarkButton.tsx` | 顶栏和书签快捷栏 |
| `apps/web/src/theme.ts`、`components/ThemeToggle.tsx`、`components/SummaryPanel.tsx` | 主题联动和引用定位 |
| `docs/决策与接口变更.md` | 布局、分类参数和设置路由 |
| [浏览器脚本与截图](../assets/desktop-workspace/) | Chromium 验收、4 张截图及 JSON |

## 4 验证与证据

| 命令 | 实测输出 |
| --- | --- |
| `python -m pytest apps/api -q` | 退出码 0，447 项全部到达 100% |
| `node --test scripts/engine-query.test.cjs` | 16 项通过，0 失败 |
| `npm --prefix apps/web run build -- --outDir ../../data/workspace-preview-dist` | TypeScript 与 Vite 成功，54 个模块 |
| `npm --prefix apps/web run build` | 发布产物成功，54 个模块，Vite 783 ms |
| `./scripts/smoke.ps1 -BaseUrl http://127.0.0.1:18181` | 16/16，包含路由、错误、书签、固定样本总结 SSE、主页同源 |
| `node reports/assets/desktop-workspace/verify-browser.cjs` | 退出码 0。桌面三列，折叠和收藏更新，三类结果筛选与刷新，AI 展开、ds、引用跳转，设置持久化，320/390/920px 无横向溢出 |
| `node -` 本机日常 Chromium 验证 | 首页、设置、书签三路 HTTP 200。明日方舟从 Bing 菜单发起，实际来源 bing，显示官网，AI 请求 0，页面异常 0 |
| `git -c core.safecrlf=false diff --check` | 退出码 0，无空白错误 |
| `git diff --name-only -- apps/web/src/BookmarkPage.tsx` | 输出为空 |

证据为[桌面首页](../assets/desktop-workspace/desktop.png)、[搜索结果](../assets/desktop-workspace/results.png)、[设置页](../assets/desktop-workspace/settings.png)、[窄屏](../assets/desktop-workspace/mobile.png)、[交互验收](../assets/desktop-workspace/browser.json)和[日常验证](../assets/desktop-workspace/daily.json)。截图使用独立测试库中的示例书签。浏览器 AI 检索使用固定响应，总结引用使用隔离服务的实际 SSE。

## 5 关键决策

- 分类基于当前搜索结果页的既有分类字段，切换无需额外上游请求。分页保持当前类别。
- 书签快捷栏使用最近收藏；完整管理由独立书签页提供。
- 草图右侧的第二个工具入口放入现有 AI 总结。窄屏把导航横排并把工具放在搜索框下方。

## 6 遗留与风险

- 分类显示当前结果页中已有的内容，实际覆盖取决于现有搜索结果和分类规则。
- 本轮新界面测试使用固定 AI 检索响应。日常 Bing 链路使用真实查询。
- 核对桌面 Chromium 和三个窄屏视口。原生移动设备未在本轮测试范围。

## 7 交接

直接打开 [日常搜索](http://127.0.0.1:8000/) 体验，右上角省略号进入[独立设置页](http://127.0.0.1:8000/settings)。想核对分类或右侧结果，可先提交普通查询或用 ds 后缀。

