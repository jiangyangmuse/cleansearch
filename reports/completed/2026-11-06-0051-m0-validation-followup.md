# 完工报告 · M0 验收复查与边界修复

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-0051 |
| 开始 | 2026-11-06 00:51 |
| 结束 | 2026-11-06 00:52 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | fix |
| 状态 | 完成 |

## 1 任务

复查 M0 独立验收报告和上一轮加固，处理仍可复现的缺陷。

验收覆盖外链校验、评分异常降级、固定样本三态与同源发布。

## 2 做了什么

1. 复核 SearXNG 回环绑定和上游响应形状校验已落地。
2. 复现了带凭证的 URL 被写入显示地址、带反斜杠的 URL 被后端和浏览器解析成不同主机，以及超大上游评分引起 `OverflowError`。
3. 在归一化入口及渲染层收紧外链校验，将评分溢出按无效分数回退到 0。更新 README 中的验收状态和错误码说明。

## 3 改动清单

| 路径 | 内容 |
| --- | --- |
| [normalize.py](../../apps/api/app/core/normalize.py) | 拒绝带凭证、反斜杠、控制字符和不明确主机的结果 URL，处理评分溢出 |
| [url.ts](../../apps/web/src/url.ts) | 浏览器渲染前复查协议、主机、凭证、反斜杠和控制字符 |
| [test_guards.py](../../apps/api/tests/test_guards.py) | 增加外链边界与正常 IPv6 链接回归 |
| [test_searxng_client.py](../../apps/api/tests/test_searxng_client.py) | 验证混合响应中丢弃带凭证结果并保留超大评分的合法结果 |
| [README.md](../../README.md) 和 [决策与接口变更](../../docs/决策与接口变更.md) | 同步链接规则、状态码和验收范围 |
| 本报告及 [INDEX.md](../INDEX.md) | 登记本次复查结果 |

## 4 验证与证据

| 命令或操作 | 结果 | 输出摘要 |
| --- | --- | --- |
| `python -m pytest apps/api -q -o 'addopts='` | 通过 | `54 passed in 0.28s` |
| `npm --prefix apps/web run build` | 通过 | 类型检查完成，36 个模块构建成功 |
| `node -`，用现有 TypeScript 编译器转译 `safeHref` 后运行 `node:assert/strict` | 通过 | 12 条断言，含凭证、反斜杠、编码主机、控制字符、普通 HTTPS 和 IPv6 |
| `python -m uvicorn app.main:app --host 127.0.0.1 --port 18084`（`SEARCH_PROVIDER=fixture`），随后 `./scripts/smoke.ps1 -BaseUrl http://127.0.0.1:18084` | 通过 | 5/5。健康检查与首页通过，有结果 10 条且去重 1 条，空结果 0 条，故障码正确 |
| `curl.exe -sS --max-time 2 'http://127.0.0.1:8888/search?q=test&format=json'` | 真实上游未验证 | curl 退出码 28。Docker/Podman 命令不可用，未取得真实引擎数据 |

## 5 关键决策

继续采用 M0 的既有 URL 契约和错误响应格式。异常评分影响排序值，结果是否可展示仍由标题和 URL 校验决定。

## 6 遗留与风险

真实 SearXNG 及 2–3 个引擎的可用性、成功率和延迟仍需部署环境实测。固定样本通过范围与真实上游的待验证项已在 README 顶部分开说明。

## 7 交接

在可运行 SearXNG 的部署环境执行首版实施计划中的真实引擎验收，记录中英文和短关键词查询的成功率与延迟。

参考 [独立验收报告](../incomplete/2026-11-06-0014-m0-acceptance.md)、[上一轮加固](2026-11-06-0043-m0-hardening.md) 和 [首版实施计划](../../docs/搜索聚合器-首版实施计划.md)。
