# 完工报告 · 商用兜底与 CI 真跑

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1407 |
| 开始 | 2026-11-07 14:07 |
| 结束 | 2026-11-07 14:08 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

执行上一轮明确的下一个动作：接商用搜索兜底（Brave / Serper），并用 Docker 里的 act 真跑一遍 CI 工作流。

**验收标准**

- 兜底有真实代码路径：无 key 不发请求、有 key 合并去重、失败不影响主链路。
- 契约测试覆盖 Brave、Serper、错误与无 key 四种情况。
- act 在 Docker 里执行 ci.yml 并给出成功/失败结论。

**不做**

- 伪造 key 或声称已连真实付费接口（没有凭据）。
- 推 GitHub（无远端与凭据）。

## 2 做了什么

1. 新增 core/paid.py：Brave（GET api.search.brave.com）与 Serper（POST google.serper.dev）两个适配器，统一归一化成 Result。
2. 聚合器集成：仅第 1 页且未指定引擎时调用；按 URL 去重合并；失败写 meta.unresponsive 并记引擎熔断，成功来源进 meta.engines。
3. 配置项 BRAVE_API_KEY / SERPER_API_KEY / PAID_FALLBACK；无 key 时 build_paid_search 返回 None，一行请求都不发。
4. 6 个契约测试（无 key、Brave、Serper、429、合并去重、失败不影响主链路），全部用 MockTransport。
5. 安装 act，发现工作流冒烟步骤用 shell: pwsh，在 Linux runner 上 command not found；改写为 bash + 新增 scripts/ci-smoke.py（15 项检查）与 scripts/ci-wait.py。
6. act 实跑 ci.yml：Install、API tests（290 passed）、Build web、Smoke 全绿，Job succeeded。
7. 文档：README 增「商用检索兜底」与「CI 本地执行」；决策 M14-D1…D5；进展与欠账更新 P1-1 与未做清单第 1、7 条。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [apps/api/app/core/paid.py](../../apps/api/app/core/paid.py) | 新增 | Brave/Serper 适配器 |
| [apps/api/app/core/aggregator.py](../../apps/api/app/core/aggregator.py) | 修改 | 兜底合并与熔断接入 |
| [apps/api/app/config.py](../../apps/api/app/config.py) | 修改 | API key 与 PAID_FALLBACK |
| [apps/api/tests/test_paid.py](../../apps/api/tests/test_paid.py) | 新增 | 6 个契约测试 |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | 修改 | 冒烟步骤改为 bash + 两个脚本 |
| [scripts/ci-smoke.py](../../scripts/ci-smoke.py)、[scripts/ci-wait.py](../../scripts/ci-wait.py) | 新增 | 跨平台冒烟与就绪等待 |
| [README.md](../../README.md)、[docs/决策与接口变更.md](../../docs/决策与接口变更.md)、[docs/进展与欠账.md](../../docs/进展与欠账.md) | 修改 | 兜底与 CI 说明 |
| 本报告与 [INDEX.md](../INDEX.md) | 新增/更新 | 登记 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| python -m pytest apps/api -q -o addopts= | 通过 | 290 passed |
| python -m pytest apps/api/tests/test_paid.py -q | 通过 | 6 例：无 key 不发请求、Brave、Serper、429、合并去重、失败不拖垮 |
| python scripts/ci-smoke.py http://127.0.0.1:18106 | 通过 | 15 项：health/有结果/分档/缓存/后缀/C g/黑名单/零结果/503/SSE/404/书签/SSRF/跨域/首页 |
| act -j verify -P ubuntu-24.04=ghcr.io/catthehacker/ubuntu:act-latest | 通过 | Job succeeded；API tests 290 passed；Build web 809ms；Smoke 4.35s |
| npm --prefix apps/web run build | 通过 | 42 modules |

未验证：真实 Brave/Serper 接口（无 key）；GitHub Actions 托管运行（无远端）；act 与 GitHub runner 的差异（缓存、权限模型）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 兜底只打第 1 页 | 每页都打 | 翻页时重复付费没意义 |
| 无 key 返回 None | 空 key 也调接口 | 隐性调用会让「为什么变慢/超额度」难以解释 |
| 冒烟改写为 bash + python | 在 runner 装 pwsh | 工作流要跑在标准 Linux runner 上，不能依赖 Windows 工具链 |
| act 记为「本地等价」 | 当作 GitHub 结果 | runner 镜像与权限不同，不能混为一谈 |

## 6 遗留与风险

- 没有真实 key，兜底的真实返回结构、配额与延迟都未验；上线前必须用标注集复测。
- act 用的是 ghcr 镜像（Docker Hub 的 catthehacker 镜像会要求登录），与 GitHub 托管 runner 有差异。
- 兜底结果与主上游的分工没有打分区分：同一 URL 只保留主上游那条，可能丢掉付费源的更好摘要。
- 仓库仍无远端；首个提交之后的新改动尚未提交。

## 7 交接

**下一个人第一件事**

拿到 Brave 或 Serper key 后：设 key → 用 scripts/eval-expansion.py 的 18 条标注集复测命中与延迟 → 对比「兜底开/关」的 Top10 命中率与 P95。

**相关文件**

- [README 兜底章节](../../README.md)
- [决策 M14-D1…D5](../../docs/决策与接口变更.md)
- [兜底实现](../../apps/api/app/core/paid.py)
- [CI 冒烟脚本](../../scripts/ci-smoke.py)

---

> 注：头部「耗时」由 `close-report.ps1` 按报告起草时间计算；本轮实际约 70 分钟（含 act 安装、两次 CI 失败修复与一次完整重跑）。
