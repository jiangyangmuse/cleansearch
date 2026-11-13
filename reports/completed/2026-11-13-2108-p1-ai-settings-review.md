# 完工报告 · DSH P1 AI 流控制与设置页复核

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2108 |
| 开始 | 2026-11-13 21:08 |
| 结束 | 2026-11-13 21:11 |
| 耗时 | 3 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

复核 [DSH 20:51 交付](2026-11-13-2051-p1-ai-stream-settings.md) 的 P1 第 13、14 条。验收后台任务查看与停止、设置模型连接、引擎状态和导出行为，覆盖桌面与窄屏。

原始脚本在隔离服务的一次复跑，于既有 `g b` 快捷键断言等待导航超时。测试现在明确将焦点移到结果区再输入组合键。原交付报告状态保留。

## 2 做了什么

- 分别显示后台 AI 总结和 AI 检索。移动端「查看」打开抽屉，焦点移到对应入口。停止后将焦点交给仍在页面的控制项。切换到 AI 对话时可继续操作后台任务。
- 停止会取消对应的浏览器请求。AI 检索服务端检测客户端断开，取消上游等待和关联任务。总结停止清除模型元数据、错误和部分内容。
- 模型连接测试与已保存的配置版本绑定。修改连接字段后清除旧结果，保存后可重新测试。总超时六秒，重定向和无效模型列表返回失败，成功时说明所填模型是否出现在列表中。
- 引擎筛选支持带感叹号的后缀和别名。状态统计只计聚合引擎，按已保存的上游匹配，刷新失败清除旧标记。
- 导出设置清单默认省略历史、数据库绝对路径和直达网址模板。用户可选导出历史及字面模式。清空历史仅在浏览器写入成功后更新计数，设置页也监听其他同源标签页的历史变化。

## 3 改动清单

| 路径 | 变更 |
| --- | --- |
| `apps/web/src/App.tsx`、`apps/web/src/components/SummaryPanel.tsx`、`apps/web/src/styles.css` | 后台任务、抽屉、焦点、触控大小、状态播报 |
| `apps/api/app/routers/search.py`、`apps/api/app/routers/ai_tools.py`、`apps/web/src/api.ts` | 断开取消、模型版本和列表校验、实时状态读取 |
| `apps/web/src/SettingsPage.tsx`、`apps/web/src/searchHistory.ts` | 数据管理和设置导出 |
| `apps/web/src/components/EngineSettingsPanel.tsx`、`apps/web/src/components/ModelSettingsPanel.tsx` | 筛选、状态、测试入口 |
| `apps/api/tests/test_ai_search.py`、`apps/api/tests/test_model_tools.py`、`scripts/audit-ui.cjs` | 断开、模型响应、窄屏并发后台任务与实际导出 JSON 回归 |
| `docs/决策与接口变更.md`、`docs/浏览器与UI优化方案.md`、`docs/进展与欠账.md` | 接口和产品口径 |

## 4 验证与证据

| 命令 | 实际结果 |
| --- | --- |
| `python -m pytest apps/api -q`；`python -m pytest apps/api -q -o 'addopts='` | 两次均退出 0，473 passed（9.59s）。Windows 沙箱卡在 asyncio 初始化回环 socket，使用允许本机回环的执行环境完成。 |
| `python -m pytest apps/api/tests/test_ai_search.py::test_ai_search_disconnect_cancels_running_provider apps/api/tests/test_model_tools.py -q -o 'addopts='` | 12 passed。ASGI 请求在上游已开始后发送真实语义的 `http.disconnect`，等待中的 provider 进入取消清理。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18196` | 固定样本 16/16，SSE 10 个引用。 |
| `npm.cmd --prefix apps/web run build` | TypeScript、Vite 通过，70 modules，`index-B01IAsE1.js`。 |
| `node --test scripts/engine-query.test.cjs` | 18 通过。 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18196 --test-bookmark-writes --out reports/assets/p1-ai-settings-review/chromium` | `ALL PASS (212)`。[Chromium JSON](../assets/p1-ai-settings-review/chromium/p0-ui-audit.json) |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18196 --channel chrome --test-bookmark-writes --out reports/assets/p1-ai-settings-review/chrome` | `ALL PASS (212)`。[Chrome JSON](../assets/p1-ai-settings-review/chrome/p0-ui-audit.json) |
| `Invoke-RestMethod http://127.0.0.1:11434/v1/models`；将其一条模型写入隔离注册表后 `POST /api/settings/models/test` | 实际 Ollama 返回 `{"ok":true,"status":200,"models":3,"model_listed":true}`，随后清理测试注册项。 |
| `Invoke-RestMethod http://127.0.0.1:8000/api/health` 和 `Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/` | 日常 fixture 进程可用，健康响应缺新版 `db_path`，静态首页读取新构建。 |
| `Invoke-RestMethod http://127.0.0.1:18196/api/settings/models` 和 `Invoke-RestMethod 'http://127.0.0.1:18196/api/bookmarks?limit=6'` | 验收结束后隔离模型和书签均为 0 条。 |
| `node --check scripts/audit-ui.cjs`、`git -c core.safecrlf=false diff --check` | 退出 0。 |

## 5 关键决策

- 保留后台继续生成能力，分别显示任务控制。把非可见的播报合并进现有主状态区。参考 [Chrome 可访问性指南](https://developer.chrome.com/docs/modern-web-guidance/guides/accessibility/accessibility)。
- 连接测试使用已保存版本并检查模型列表。结果中的模型存在性只来自列表，本次只请求 `/models`。
- 导出仍为 JSON 清单，历史改为主动选择，直达模板省略，避免分享文件时附带本机路径和潜在访问参数。

## 6 遗留与风险

- 日常 8000 的后端需在沿用当前数据库、令牌和启动参数的前提下重新加载。新接口、取消和数据路径行为已在隔离服务验收。
- 手机交互使用 Playwright 的窄屏和触控模拟，移动端读屏尚未实机验证。远端 DeepSeek 连接和取消后上游是否继续推理未实测。客户端与服务端已验证各自的取消边界。

## 7 交接

日常服务加载新版后，复验设置页显示本机数据库及模型测试连接，再执行 [方案 §6 第 15 条](../../docs/浏览器与UI优化方案.md) 的旧页面移动端优化。
