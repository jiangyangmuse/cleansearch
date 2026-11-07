# 完工报告 · DeepSeek 总结接入与当前成果复验

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1136 |
| 开始 | 2026-11-07 11:36 |
| 结束 | 2026-11-07 11:37 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

复验当前搜索、总结与发布产物。将用户提供的 DeepSeek 凭据保存在工作区本地，交付可显式选择的云端总结，并用固定样本核对真实 SSE、引用与结束事件。

## 2 做了什么

1. 增加 `serve.ps1 -DeepSeek`，使用 DeepSeek 官方 API 的 `deepseek-flash` 和现有 OpenAI 兼容客户端。按请求关闭推理模式。本机 Ollama 仍可通过 `-OllamaModel` 选择。
2. 凭据单独保存在 Git 忽略的本地文件。启动脚本结束后恢复父 shell 的模型环境。固定样本测试使用临时数据库。
3. 模型端 HTTP 401/402 分别返回 `LLM_AUTH_FAILED`、`LLM_INSUFFICIENT_BALANCE`，均标记为不可原样重试。未知异常返回固定 SSE 消息，避免暴露上游请求详情。
4. 对照 P0–P3 近期报告，更新当前进展摘要中的真实引擎、缓存、模型、Edge 和 CI 口径。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `scripts/serve.ps1` | 更新 | DeepSeek 启动参数、模型环境恢复，与 Ollama 参数互斥 |
| `apps/api/app/core/llm.py`、`apps/api/app/routers/summarize.py` | 更新 | 认证/余额分类和通用错误消息 |
| `apps/api/tests/test_summarize.py` | 回归 | 401、402 及未知异常去除内部详情 |
| `README.md`、`docs/进展与欠账.md`、`docs/决策与接口变更.md` | 更新 | 启动、当前验收证据、云端数据范围与接口约定 |
| `data/deepseek-api-key.txt` | 本地配置 | Git 忽略的凭据文件，未纳入报告或示例 |

## 4 验证与证据

| 命令 | 结果 | 输出摘要 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `278 passed in 7.47s`，含模型认证/余额与异常信息回归 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 通过，Vite 转换 42 个模块并生成发布产物 |
| `.\scripts\serve.ps1 -Provider fixture -Port 18121 -SkipBuild`（测试 shell 置 `LLM_PROVIDER=stub`），另起 shell 执行 `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18121` | 通过 | `冒烟通过`，16/16，覆盖三态、缓存、风控、总结引用、书签与同源托管 |
| `.\scripts\serve.ps1 -Provider fixture -Port 18122 -SkipBuild -DeepSeek`，对该服务 `POST /api/search` 查询固定样本「Python 文档」，再 `GET /api/summarize?sid=<测试快照>&mode=fast` | 通过 | `health_provider=openai model=deepseek-flash`，10 条结果、10 条引用、160 段正文、10 个有效引用编号、0 个无效绑定、正常 `done`。首段正文 742 ms，总耗时 1,628 ms |
| `.\scripts\serve.ps1 -DeepSeek -OllamaModel 'qwen3.5-4b-local:latest' -SkipBuild` | 通过 | PowerShell 参数绑定拒绝同时使用两个开关 |
| `git check-ignore -v -- data/deepseek-api-key.txt`、`git grep --cached -F -l -f data/deepseek-api-key.txt`、`git grep -F -l -f data/deepseek-api-key.txt` | 通过 | 文件被 `data/` 规则忽略，暂存区和跟踪文件扫描均无匹配 |
| 以替身 `python` 执行 `.\scripts\serve.ps1 -Provider fixture -Port 18123 -SkipBuild -DeepSeek` | 通过 | `cloud_environment_restoration=pass`，启动前的五项模型环境变量均恢复 |

本轮真实模型只发出一条固定样本 fast 总结。真实 SearXNG 与 DeepSeek 组合、full 网页抓取和多主题稳定性未在本轮验证。两个临时验收服务已关闭。

## 5 关键决策

- 云端总结由启动参数显式选择，以便用户决定何时发送查询及总结材料。沿用既有兼容客户端和应用接口。 [DeepSeek 首次调用](https://api-docs.deepseek.com/quick_start/agent_integrations/)
- 认证和余额按不同状态提示。服务端返回安全提示，避免将上游请求或响应的细节转发到前端。 [DeepSeek 错误码](https://api-docs.deepseek.com/zh-cn/quick_start/error_codes/)

## 6 遗留与风险

- 首段延迟为单次固定样本的测量。真实检索、多主题及 full 模式的延迟和引用质量待独立验收。
- 启用云端模型后，总结请求会把查询及选用的摘要或正文发送给 DeepSeek。
- 远端 CI、Android 分享与原生书签互迁的既有待办见 `docs/进展与欠账.md`。

## 7 交接

在工作区运行 `.\scripts\serve.ps1 -Provider fixture -DeepSeek`，从首页生成一次总结。验真实上游时改用 `-Provider searxng`，分别记录 fast/full 的首段正文、引用绑定与降级状态。保持离线冒烟使用抽取式桩。
