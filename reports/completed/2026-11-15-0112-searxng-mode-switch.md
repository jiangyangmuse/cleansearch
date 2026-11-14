# 完工报告 · 日常 8000 切回真实搜索

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261115-0112 |
| 开始 | 2026-11-15 01:12 |
| 结束 | 2026-11-15 01:12 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

**目标**

用户反馈「搜什么都返回同一个界面」。找出原因并修好日常 `127.0.0.1:8000`，让不同查询返回不同结果。

**验收标准**

- 日常实例 `/api/health` 的 `provider` 不是 `fixture`，不同查询返回不同标题集合。
- 侧栏总结能出正文与引用（不再是 `LLM_BAD_RESPONSE`）。
- 冒烟恢复通过；改动写进决策文档。

**不做**

- 不改搜索排序、去重、官方入口表。
- 不动别人的报告与台账行。

## 2 做了什么

1. **定位**：截图里「展示 8 条 · 缓存」+ 固定的一批 Python/HTTP 结果，正是 `fixture` 固定样本。`curl` 三个不同查询，`provider=fixture` 且标题集合完全相同——不是搜索坏了，是模式问题。
2. **切换**：`serve.ps1 -Provider searxng -SkipBuild` 重启日常 8000，指向运行中的 `cs-searxng`（`127.0.0.1:8888`），沿用 `data/cs.db` 与原模型设置。
3. **顺带发现并修掉**：`.env` 的 `LLM_BASE_URL=http://127.0.0.1:1`（死地址）与 `LLM_REASONING_EFFORT=none` 让云端接口返回 HTTP 400；数据库模型条目 `deepseek-f` 也调不通。把 `.env` 指回本机 Ollama（`http://127.0.0.1:11434/v1`），并通过 `PUT /api/settings/models`（revision 3 → 4）把 search/summary/translate 指派切换成本机千问 `qwen3.5-4b-local:latest`。
4. **冒烟口径**：`smoke.ps1` 原先要求 SSE `meta.model` 等于 `/api/health.llm_model`；用设置页指定的模型后两者天然不同（meta 给标签）。改为「`meta.model` 属于当前配置的模型之一」，引用/结束/错误校验保持严格。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `.env` | 修改（本机配置，不入库） | `LLM_BASE_URL` 指回 `http://127.0.0.1:11434/v1`；`LLM_REASONING_EFFORT` 置空 |
| 模型设置（SQLite） | 修改 | 新增本机模型条目并指派 search/summary/translate（revision 4） |
| `scripts/smoke.ps1` | 修改 | SSE 模型校验改为「属于已配置模型之一」 |
| `docs/决策与接口变更.md` | 修改 | 记录模式切换与冒烟口径 |
| `127.0.0.1:8000` | 重启 | provider 由 fixture 改为 searxng |
| `reports/assets/mode-switch-searxng/` | 新增 | 冒烟日志与审计守卫输出 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `curl /api/health`（切换前） | `provider=fixture` | 三个查询标题完全相同：`asyncio — 异步 I/O…` / `FastAPI 官方文档…` |
| `curl /api/health`（切换后） | 通过 | `provider=searxng`、`searxng_url=http://127.0.0.1:8888`、`api_version=2` |
| 三个查询对比（切换后） | 通过 | `python asyncio` 17 条、`北京天气` 25 条、`rust 教程` 16 条、`2026 世界杯` 25 条，标题集合互不相同 |
| `GET /api/summarize?sid=…&mode=fast` | 通过 | 本地千问返回真实正文：`asyncio 是 Python 标准库…`，引用 10 处，`done` 正常结束 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8000` | 通过 | `冒烟通过 13/13，跳过 3`（跳过项为固定样本专用；切换前为 12/13，失败项是总结 SSE） |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:8000` | 预期拒绝 | `完整浏览器审计需要 fixture，当前 provider=searxng。真实 SearXNG 请运行 verify-filters.cjs`——上一轮加的守卫 |

未验证：真实上游引擎可用性随网络/限流波动（Google 与 CSE 近期多次 503）；移动端未测。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 日常实例切到 `searxng` 模式 | 继续 fixture、只改文档说明 | 用户要的是真搜索；fixture 的固定样本本来就是给离线验收用的演示数据 |
| 模型指派切本机千问 | 修 `deepseek-f` 条目 | 云端条目模型名与密钥都不确定，本机模型已验证可用且不花钱 |
| 放宽冒烟的模型名比对 | 让 health 报实际模型 | 让 health 读数据库设置会把健康检查变成有状态操作；校验「属于已配置模型」同样能挡住乱报 |

## 6 遗留与风险

- 日常实例现在依赖两个外部件：`cs-searxng` 容器（8888）与本机 Ollama（11434）。任一没起，搜索或总结会降级/报错；health 能看出 provider 与模型名。
- `.env` 与模型设置都是本机状态，不在仓库里；换机器要重配。
- 固定样本模式仍是 CI 与离线验收的主力（`audit-ui` 只跑 fixture），真实上游的问题靠 `verify-filters.cjs` 覆盖。

## 7 交接

**下一个人第一件事**

若再次出现「搜什么都一样」：先看页面统计条是否写着「固定样本」，或 `curl /api/health` 看 `provider`；`fixture` 就是演示模式，换 `searxng` 即可。

**相关文件**

- 启动：`scripts/serve.ps1`、`.env`、`data/logs/serve-8000.*.log`
- 冒烟：`scripts/smoke.ps1`
- 决策：`docs/决策与接口变更.md`（2026-11-15 日常 8000 切回真实搜索）
