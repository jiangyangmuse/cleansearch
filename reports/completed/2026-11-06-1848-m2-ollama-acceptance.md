# 完工报告 · M2 本机千问验收与优化

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-1848 |
| 开始 | 2026-11-06 18:48 |
| 结束 | 2026-11-06 18:50 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

**目标**

使用本机已安装的千问小模型验收 M2 侧栏，修复流式等待、错误判定和引用定位问题。

**验收标准**

- 固定样本接真实 Ollama，测首段正文、总耗时、结束事件及引用来源绑定。验证模型错误不会影响搜索结果。
- 后端测试、前端构建、真实模型和抽取式桩的冒烟全部通过。缺失模型必须让冒烟失败。
- 浏览器能生成总结、展开引用所在分组，切换查询时移除旧总结。

**不做**

- 本轮聚焦 M2 的摘要模式。真实 SearXNG 联调仍按 M1 验收报告跟踪。

## 2 做了什么

1. 增加 `serve.ps1 -OllamaModel <模型名>`，用 `ollama list` 查到的名称连接本机兼容端点。该启动方式默认关闭额外思考，可通过 `LLM_REASONING_EFFORT` 覆盖。
2. 首段可见正文受 `LLM_TIMEOUT` 约束，避免持续到达的隐藏推理片段让侧栏一直等。空正文、上游流错误或缺结束信号会发 `error`，并在退出时关闭上游生成器。前端发现流没有结束事件时提示重试。
3. 提示词优先取与问题直接相关的摘要，并要求结论引用实际支持它的来源。点击引用会先展开所在组，再定位结果卡片。
4. 真实模式和桩统一检查 SSE 正文、引用编号与来源绑定、正常结束。模型错误会让冒烟以非零状态退出。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| `apps/api/app/config.py`、`apps/api/app/core/llm.py`、`apps/api/app/core/summarize.py`、`apps/api/app/routers/summarize.py` | 增加可选推理参数、首段期限、终止验证和生成器清理 |
| `apps/api/app/prompts/summary_system.txt` | 聚焦直接相关材料和短答 |
| `apps/web/src/api.ts`、`apps/web/src/components/SummaryPanel.tsx` | 流中断进入错误态，引用自动展开折叠组 |
| `apps/api/tests/conftest.py`、`apps/api/tests/test_summarize.py` | 测试固定走桩，覆盖首段超时、上游断流、空正文及错误 |
| `scripts/serve.ps1`、`scripts/smoke.ps1` | 本机模型入口和统一冒烟判定 |
| `README.md`、`.env.example`、`docs/决策与接口变更.md` | 本机启动示例、环境变量与变更说明 |
| `reports/2026-11-06-1848-m2-ollama-acceptance.md`、`reports/INDEX.md` | 验收证据与台账 |

## 4 验证与证据

| 命令或操作 | 结果 | 关键输出 |
| --- | --- | --- |
| `curl.exe -fsS --max-time 4 http://127.0.0.1:11434/api/tags`，`curl.exe -fsS --max-time 4 http://127.0.0.1:11434/api/version` | 通过 | Ollama `0.40.15`，已安装 `qwen3.5-4b-local:latest`，实测使用该标签 |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `151 passed in 0.41s`，包括 4 个新增回归用例 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 构建转换 37 个模块，714 ms |
| 修改前设置 `LLM_PROVIDER=openai`、`LLM_BASE_URL=http://127.0.0.1:11434/v1`、`LLM_MODEL=qwen3.5-4b-local:latest`、`LLM_TIMEOUT=30`，运行 `.\scripts\serve.ps1 -Provider fixture -Port 18086 -SkipBuild` | 复现问题 | Python urllib 对 `POST /api/search` 查询 `python 文档`，使用返回的 `sid` 读取 `GET /api/summarize?sid=<sid>`。收到元数据和来源后，正文读取等待 95 秒仍无数据，客户端 `TimeoutError` |
| `.\scripts\serve.ps1 -Provider fixture -Port 18089 -OllamaModel 'qwen3.5-4b-local:latest' -SkipBuild`，同一 urllib 探针 | 通过 | 首段正文 0.69 秒、`done.ms=8048`、126 个正文片段、10 个来源均绑定本次结果，正文引用 `[1][2][3][10]`；中间复测为 5.14 秒首段、12.476 秒结束。未控制模型与提示词缓存，耗时仅代表本机本轮样本 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18089` | 通过 | 真实千问 11/11，侧栏 10 个来源、123 个正文片段 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18090` | 通过 | 桩 11/11，`stub-extractive`、10 个来源、161 个正文片段 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18091`，该实例的模型名为 `cleansearch-acceptance-missing:latest` | 按预期失败 | 10 个搜索及页面检查通过，侧栏检查失败，`error=LLM_BAD_RESPONSE`、正文片段 0、退出码 1 |
| 内置浏览器打开 `http://127.0.0.1:18089/`，搜 `python 文档` 后点「生成总结」 | 通过 | 显示千问模型和「生成中」，完成 103 个片段、6708 ms；点击 `[10]` 打开弱相关组并显示 Octoverse 卡片；重新生成时切换「零结果」，旧侧栏消失 |
| 内置浏览器打开 `http://127.0.0.1:18091/`，搜索并生成 | 通过 | 显示「生成失败」「找不到模型」和「重试」，原有搜索链接仍可用 |
| `curl.exe -sS --max-time 3 'http://127.0.0.1:8888/search?q=test&format=json' -o NUL -w 'SearXNG HTTP %{http_code}\n'` | 真实搜索未验证 | `HTTP 000`、退出码 7，连接失败 |

证据记录为上述终端与浏览器无障碍树的输出摘要。验收后已停止本轮临时 FastAPI 实例。

## 5 关键决策

| 决策 | 依据 |
| --- | --- |
| Ollama 快速摘要默认请求 `reasoning_effort=none`，通用端点保持可选 | 本机小模型默认行为实测长时间未产生正文。使用 Ollama 已支持的兼容参数，避免为本机另写一套客户端。[Ollama 兼容接口](https://docs.ollama.com/api/openai-compatibility) |
| 首段按可见正文而非任意网络数据计时 | 隐藏推理片段会刷新 HTTP 读取超时，用户却看不到摘要 |
| 上游要求 `[DONE]` 和可见正文 | 防止只有推理、上游流内错误或连接提前结束被当作完成 |

## 6 遗留与风险

- 真实千问已验收，搜索使用固定样本。SearXNG 本机 8888 无服务，真实搜索与模型的整条链路尚未验证。
- 本轮仅测一种千问模型和一条固定样本。该样本结论有对应摘要，但仍引用了一条弱相关的语言流行度信息。引用有效只证明对应到本次结果，摘要相关性和准确性仍取决于材料与模型。

## 7 交接

在仓库根目录运行 `.\scripts\serve.ps1 -Provider fixture -OllamaModel 'qwen3.5-4b-local:latest'` 即可复现本机千问模式。SearXNG 可用后，用真实搜索结果补验总结与引用。

- `README.md` 记录本机模型启动和可选参数。
- `docs/决策与接口变更.md` 记录超时和结束事件语义。
- `reports/2026-11-06-1704-m1-acceptance-fixes.md` 跟踪真实搜索待验项。
