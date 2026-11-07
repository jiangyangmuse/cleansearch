# 完工报告 · P1 收口：CI 基线、浏览器验收与模型实测

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1056 |
| 开始 | 2026-11-07 10:56 |
| 结束 | 2026-11-07 10:56 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | ops |
| 状态 | 部分完成 |

## 1 任务

**目标**

1) 完成交接里的下一个动作：容器搜索接宿主机千问；2) 推进 P1 三项（CI 基线、浏览器/移动端验收、安全与模型实测）。

**验收标准**

- 容器内 fast/full 总结可用，引用绑定，降级有标记。
- 有首个提交；CI 配置可校验，CI 同款命令本地跑通。
- 真实浏览器（Edge/Chrome）加载未打包扩展并完成收藏。
- feed 可拉取并热加载；多主题 fast/full 有耗时与降级数据。
- 做不到的写明原因（远端 CI、Android、GSB/URLhaus）。

**不做**

- 推远端（无地址与凭据）、Android 真机（无设备）、GSB/URLhaus（无 key）。

## 2 做了什么

1. 容器接模型：.env 设 LLM_PROVIDER=openai、LLM_MODEL=qwen3.5-4b-local:latest、LLM_TIMEOUT=120、LLM_REASONING_EFFORT=none、COMPOSE_LLM_BASE_URL=http://host.docker.internal:11434/v1，重建 api 后 /api/health 显示 openai。
2. 容器 full 模式先失败（fetched=0）：容器 DNS 把 docs.python.org 解析到 198.18.1.131（代理网段），被 SSRF 白名单拦下；加 FETCH_EXTRA_CIDRS=198.18.0.0/15 后抓到 2/5。
3. P1-1：git 首次提交 2cbc632（176 文件，工作树干净）；CI 配置用 PyYAML 校验（api 5 步 / web 3 步）；按 CI 形式跑 pytest -o addopts= 268 passed。无远端，CI 未在平台运行。
4. P1-2：给 verify-extension.cjs 加 CS_BROWSER_CHANNEL；Edge 157 通道 12 项 ALL PASS；Chrome 156 通道等待 service worker 超时——该版本已移除 --load-extension（137 起），只能手动加载。
5. P1-3 feed：URLhaus 文本端点返回 410，改用 OpenPhish；首次刷新在容器里 2.5s 超时，改为 feed 专用 clone_with_timeout(≥10s) 并重建镜像后成功：298 条并入，health.blocklist_rules 3→301，容器内样本 URL 命中黑名单。
6. P1-3 模型：3 个主题 fast（首字 6.8–10.9s，总 13.4–23.0s，引用全绑定），2 个主题 full（抓取 2/5 与 0/5，partial=true）。
7. 文档：README 增容器接模型与 feed 实测表；决策 M11-D1…D5；进展与欠账 P1-1/P1-2/P1-3 标部分完成并注明缺口。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [apps/api/app/core/fetch.py](../apps/api/app/core/fetch.py) | 修改 | 新增 clone_with_timeout（feed 专用超时） |
| [apps/api/app/routers/tools.py](../apps/api/app/routers/tools.py) | 修改 | feed 刷新用更长超时的抓取器 |
| [apps/api/app/main.py](../apps/api/app/main.py) | 修改 | blocklist_rules 统计基础文件 + feed 文件 |
| [scripts/verify-extension.cjs](../scripts/verify-extension.cjs) | 修改 | 支持 CS_BROWSER_CHANNEL |
| [.env](../.env) | 修改（本地） | 容器模型、OpenPhish、FETCH_EXTRA_CIDRS |
| [README.md](../README.md)、[docs/决策与接口变更.md](../docs/决策与接口变更.md)、[docs/进展与欠账.md](../docs/进展与欠账.md) | 修改 | 实测数据与 P1 状态 |
| 本报告与 [INDEX.md](INDEX.md) | 新增/更新 | 登记 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| GET /api/health（容器） | 通过 | provider=searxng、llm_provider=openai、model=qwen3.5-4b-local:latest |
| fast 总结 ×3（asyncio / Rust / 量子计算） | 通过 | 首字 10.9 / 6.8 / 7.2 s；总 19.3 / 13.4 / 23.0 s；引用 10 条全绑定 |
| full 总结 ×2 | 通过 | 首字 5.1 / 7.8 s；fetched=2/5 与 0/5；partial=true；无 error 事件 |
| git log --oneline -1 | 通过 | 2cbc632 init: CleanSearch M0-M9 …；tracked=176；status 0 |
| PyYAML 校验 ci.yml | 通过 | jobs=[api, web]，api 5 步 |
| python -m pytest apps/api -q -o addopts= | 通过 | 268 passed |
| Edge 157 通道 verify-extension | 通过 | 12 项 ALL PASS（含 popup 收藏、后台保存、PWA 清单） |
| Chrome 156 通道 verify-extension | 失败 | 等待 serviceworker 超时：该版本已移除 --load-extension |
| POST /api/tools/refresh-feeds（OpenPhish） | 通过 | entries=298，blocklist_rules 3→301；容器内 Blocklist.match 样本 URL 返回「URL 命中黑名单」 |
| URLhaus text 端点 | 失败 | HTTP 410（需认证） |

未验证：远端 CI（无仓库）、Android 安装与系统分享（无设备）、原生书签管理器双向导入导出（需人工操作）、容器内 full 抓取成功率（2/5、0/5，受真实站点 403/超时影响）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| feed 用更长的独立超时 | 全局调大 FETCH_TIMEOUT | 网页 2.5s 是刻意的；feed 文件慢但一次拉取用很久 |
| health 统计 feed 条数 | 只看基础文件 | 没有可观测值就无法证明热加载生效 |
| Chrome 失败不隐藏 | 只报 Edge 通过 | 版本限制是事实，写清楚才能让用户手动加载 |
| 首次提交只做本地 | 等远端再提交 | 用户要求做 P1，P1-1 的完成标准就是首个提交；推远端缺凭据 |

## 6 遗留与风险

- 无远端仓库：CI 未在托管平台跑过；提交只在本机。
- Chrome 156 无法用 CLI 加载扩展；用户需在 chrome://extensions 手动加载。
- full 模式抓取成功率低（0–2/5），受目标站 403/超时影响；模型侧正常出结果并标 partial。
- GSB/URLhaus 无 key；URLhaus 公开文本端点返回 410，需改用 API 或换源。
- RDAP 域名年龄只做评估（bootstrap 服务可用，但需缓存与批量策略），未接入。
- fast 首字 6.8–10.9s，明显高于设计的 2.5–4s；模型冷启动与 4B 模型在 CPU 上是主因。

## 7 交接

**下一个人第一件事**

给仓库配远端并推送首个提交，拿到 CI 的真实运行结果；同时评估把 fast 首字压到 4s 内（预热模型或换更小模型）。

**相关文件**

- [README 容器实测](../README.md)
- [决策 M11-D1…D5](../docs/决策与接口变更.md)
- [进展与欠账 P1](../docs/进展与欠账.md)
- [扩展验收脚本](../scripts/verify-extension.cjs)

---

> 注：头部「耗时」由 `close-report.ps1` 按报告起草时间计算；本轮实际约 55 分钟。
> P1-1 缺远端 CI、P1-2 缺 Android 与 Chrome、P1-3 缺 GSB/URLhaus 与 RDAP，故状态为「部分完成」。
