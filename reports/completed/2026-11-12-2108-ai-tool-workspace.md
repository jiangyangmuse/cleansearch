# 完工报告 · 侧栏工具、搜索历史与模型分配

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261112-2108 |
| 开始 | 2026-11-12 21:08 |
| 结束 | 2026-11-12 21:09 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

把单页总结、一键添加移回顶栏，设置独立入口，更多菜单加入搜索历史。右侧加入多网页总结、翻译和译文搜索。设置的日常 AI 检索下提供模型导入、按功能分配和备选授权。

## 2 做了什么

- 顶栏使用独立的设置链接和可扩展的更多菜单。历史保存在浏览器，支持重搜和清空。
- 侧栏 AI 总结可填写最多 5 个链接，复用受控抓取，显示各来源及抓取失败原因。翻译支持 8 种目标语言，译文可一键填入搜索框并提交。
- 添加「模型填写」，可逐个填写或批量导入 JSON，为检索、总结和翻译各设默认和备选，并对每个模型单独勾选功能。模型设置以版本控制的 SQLite 写入本机服务端，API 读取不回传密钥。
- 自定义 AI 检索使用免费引擎真实候选和模型重排；生成链接来自原候选。模型分配应用于 AI 检索、搜索结果总结、网页总结、单页总结和翻译。
- 日常 8000 已加载后端与前端新版。重启复核运行环境、书签库、令牌和 SearXNG 保持一致。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/web/src/App.tsx`、`SettingsPage.tsx`、`searchHistory.ts`、`workspace.css` | 布局、历史和配置入口 |
| `apps/web/src/components/WorkspaceHeader.tsx`、`ModelSettingsPanel.tsx`、`PageBatchSummary.tsx`、`TranslationPanel.tsx`、`api.ts` | 顶栏、模型填写、总结、翻译和契约调用 |
| `apps/api/app/core/model_settings.py`、`model_routing.py`、`llm.py`、`fetch.py` | 模型存储、权限与回退、兼容端点连接 |
| `apps/api/app/core/ai_search.py`、`aggregator.py`、`summarize.py` | 免费候选筛选和总结模型 |
| `apps/api/app/routers/ai_tools.py`、`search.py`、`page.py`、`summarize.py`、`main.py` | 设置、翻译、多页抓取和现有入口接入 |
| `apps/api/tests/test_model_tools.py`、`docs/决策与接口变更.md` | 回归测试和接口决策 |
| [验收与部署记录](../assets/ai-tool-workspace/) | 脚本、验证数据、截图 |

## 4 验证与证据

| 命令 | 输出 |
| --- | --- |
| `python -m pytest apps/api -q` 与 `python -m pytest apps/api -o addopts= -q` | 退出码 0，451 passed in 8.78s。新增覆盖密钥隐藏、跨域写保护、版本冲突、禁用与启用备选、候选编号拒绝及部分网页抓取失败 |
| `node --test scripts/engine-query.test.cjs` | 16 项通过，0 失败 |
| `npm --prefix apps/web run build` | 退出码 0，TypeScript 和 Vite 构建成功，58 个模块 |
| `./scripts/smoke.ps1 -BaseUrl http://127.0.0.1:18183` | 16/16。首轮隔离环境关闭缓存，缓存命中项失败；按日常配置启用缓存后复跑全部通过 |
| `node reports/assets/ai-tool-workspace/verify-browser.cjs` | 退出码 0。历史重搜、两模型批量导入和设置持久化、备选禁用提示、开启后真实千问翻译、译文搜索、2 篇公开网页抓取并真实千问总结、320px 无横向溢出 |
| `python -` 隔离真实 SearXNG + 本机千问 | Godot 免费上游 503 UPSTREAM_TIMEOUT；Python HTTP 200，真实千问筛出 5 条上游候选 |
| `python reports/assets/ai-tool-workspace/restart-native.py` | 退出码 0，原生 8000 进程 33148 → 20408，新端点可见，环境、书签库、令牌和 8888 进程校验一致 |
| `node -` 日常 Chromium | 首页、设置、模型读取与实际本机翻译均 HTTP 200，模型 qwen3.5-4b-local:latest，浏览器异常 0 |
| `git -c core.safecrlf=false diff --check` | 退出码 0 |

证据为[浏览器验证](../assets/ai-tool-workspace/browser.json)、[真实检索](../assets/ai-tool-workspace/live-search.json)、[日常验证](../assets/ai-tool-workspace/daily.json)、[重启记录](../assets/ai-tool-workspace/restart.json)、[翻译截图](../assets/ai-tool-workspace/translate.png)、[模型设置截图](../assets/ai-tool-workspace/models.png)、[多网页总结截图](../assets/ai-tool-workspace/summary.png)。截图中的模型配置来自隔离测试。

## 5 关键决策

- 每项功能独立分配默认和备选。默认失败且备选未启用当前功能时显示「当前模型不可用，备选模型未开启此功能」。
- 模型协议为流式 OpenAI 兼容 Chat Completions。公网端点经过 HTTPS 和 DNS 校验，本机 Ollama 通过环回地址接入。[Ollama 兼容接口](https://docs.ollama.com/api/openai-compatibility)
- 多网页总结显示成功和失败项，材料按成功网页编号。搜索结果总结的已配置路由在确定实际输出模型后发出 SSE 正文。

## 6 遗留与风险

- 免费搜索引擎可能超时，本轮 Godot 超时已按实记录。真实模型测试使用本机千问，云端兼容接口的路由和错误用模拟端点覆盖。
- 网页抓取覆盖公开可提取正文的页面，登录、反爬或纯图片内容会报告失败。一次最多 5 个网址，过长正文使用节选。
- 日常服务使用现有系统模型配置，用户导入并分配后生效。测试模型仅写入隔离库，隔离服务已停止。

## 7 交接

打开 [CleanSearch](http://127.0.0.1:8000/) 查看顶栏和右侧工具。[设置](http://127.0.0.1:8000/settings) 的日常 AI 检索下展开「模型填写」，填好模型、勾选允许的功能并保存分配。本机 Ollama 可填写基址 `http://127.0.0.1:11434/v1` 和模型名 `qwen3.5-4b-local:latest`。

