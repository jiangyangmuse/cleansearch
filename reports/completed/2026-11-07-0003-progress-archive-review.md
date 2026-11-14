# 完工报告 · 当前成果复核、归档与进度对齐

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-0003 |
| 开始 | 2026-11-07 00:03 |
| 结束 | 2026-11-07 00:06 |
| 耗时 | 3 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

核对已有全部 20 份完工报告与当前实现，归档各自范围已经全部完成的报告，重写当前进展与待办，并修复验收中复现的问题。

- 复测 API、生产构建、发布形态冒烟、真实搜索及本机千问链路。
- 保留历史台账状态与正文，将报告链接更新到实际位置。
- 本轮范围为复核与修复。容器、正式浏览器和移动设备的验收继续按进度文档追踪。

## 2 做了什么

1. 逐份核对原有 20 份报告的任务范围、验证结果和遗留。15 份历史报告迁入 `reports/completed/`，4 份原「部分完成」及 1 份六阶段报告留在根目录。六阶段正文 §8.1 的真实上游仍为部分达成，台账保留其历史「完成」状态并注明差异。
2. 修复 `/go` 签名与 URL 验证。响应按当前本地 token 生成签名，命中已有缓存也重新签名。非法签名及无法作为结果渲染的 URL 均返回 403。
3. 更新真实上游验收脚本。指定路由按既定字段比较，允许响应包含扩展词。质量测量区分返回可展示结果与空响应，打印缓存标记。
4. 汇总各阶段已经交付、已经实测和等待真实环境验收的内容，写入 [进展与欠账](../../docs/进展与欠账.md)。同步 README 和决策台账。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `reports/completed/`、`reports/INDEX.md` | 归档 / 更新 | 迁移报告并重算 Markdown 相对链接，保留历史状态 |
| `AGENTS.md`、`scripts/check-report.ps1`、`scripts/close-report.ps1` | 更新 | 记录归档规则，两个脚本默认在根目录与归档中选择最新报告 |
| `docs/进展与欠账.md`、`docs/决策与接口变更.md`、`README.md` | 更新 | 汇总进展与分级待办，登记当前修复 |
| `apps/api/app/routers/search.py`、`apps/api/app/routers/go.py`、`apps/api/app/core/redirect.py` | 修复 | 风险中转链接的生成、验证和缓存交互 |
| `apps/api/tests/test_cache.py`、`apps/api/tests/test_feeds_go.py` | 回归 | token 轮换、非 ASCII 签名、非法目标 |
| `scripts/verify-searxng.py`、`scripts/measure-search-quality.py` | 修复 | 真实验收字段匹配和质量指标 |

## 4 验证与证据

| 命令 | 结果 | 输出摘要 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | 262 passed in 4.84s。修复前复现了缓存仍返回旧签名及畸形目标触发 URL 解析异常。 |
| `npm --prefix apps/web run build` | 通过 | TypeScript 检查通过，Vite 转换 42 个模块并生成 `dist`。 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18112` | 通过 | 临时 DB 的发布形态 16/16。补充 HTTP 探测 `go_valid=200 go_invalid_signature=403`。 |
| `python scripts/verify-searxng.py --base-url http://127.0.0.1:18111 --engines g b sc` | 2/12 | 地区 `jp` 和 `C g` 护栏通过。Google access denied 并进入冷却，Bing 返回空结果，Scholar 超时。退出码 1。 |
| `python scripts/measure-search-quality.py --base-url http://127.0.0.1:18111 --rounds 2` | 8/8 有结果 | 中位 1,192 ms，最大 3,323 ms。8 次有 `google cse`，其中 4 次也有 Brave；后续 Brave 限流。每次有引擎失败，`cached=False`。 |
| `Invoke-RestMethod http://127.0.0.1:18111/api/search -Method Post -ContentType 'application/json' -Body '{"q":"Python documentation"}'`，随后 `Invoke-WebRequest "http://127.0.0.1:18111/api/summarize?sid=$($hit.meta.sid)&mode=fast" -UseBasicParsing -TimeoutSec 90` | 通过 | 真 SearXNG 19 条结果接 `qwen3.5-4b-local:latest`，10 条引用均绑定本次结果、67 段正文、5 处有效正文引用、0 错误、正常 `done`。端到端总结 14,343 ms。 |
| 两个报告目录中逐份执行 `.\scripts\check-report.ps1 -Path $report.FullName -Quiet` | 通过 | 原有 20 份均通过结构校验，20 条历史状态保留。 |

历史截图和 JSON 证据见 [m9-evidence](../../docs/m9-evidence)。本轮探测使用临时数据库与本机已有服务。Docker/Podman 未在本机找到，未执行 Compose 启动与卷重建。正式 Chrome/Edge、Android、完整上游响应的缓存对照以及千问 full 路径待按进度文档执行。

## 5 关键决策

- 按报告自身的任务范围判断是否已全部完成，按最新证据判断项目验收状态。六阶段报告保留在待核对区并在台账注明原因。
- 签名在响应边界生成。缓存内容与 token 生命周期解耦，已签发的旧链接在 token 轮换后按签名规则失效。
- 验收脚本分别核对「真实默认搜索出结果」与「指定引擎来源正确」。两项各自保留结果与退出状态。

## 6 遗留与风险

- 指定引擎及完整上游结果的冷热对照尚未通过。默认模式主要依赖 `google cse`，Brave 来源受限流影响。
- Ollama 总结仅完成一条真实搜索的 fast 联测。首段正文时延与多主题质量还需复测。
- Git 已初始化并有暂存区，尚无首个提交和远端 CI 运行证据。容器持久化、正式浏览器与手机仍需目标环境验收。

## 7 交接

先在可重复部署环境稳定至少两个显式搜索引擎，再重跑 `verify-searxng.py` 与 `measure-search-quality.py`，记录指定来源、延迟和冷热缓存差异。

- [当前进展与优先级](../../docs/进展与欠账.md)
- [报告台账](../INDEX.md)
- [六阶段报告](../incomplete/2026-11-06-2342-roadmap-six-phases.md)
