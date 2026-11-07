# 完工报告 · RDAP 域名年龄信号

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261107-1447 |
| 开始 | 2026-11-07 14:47 |
| 结束 | 2026-11-07 14:47 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | feat |
| 状态 | 完成 |

## 1 任务

**目标**

补上 RDAP 域名年龄信号：让风险公式里「新注册域名」这一项真正有数据，同时不让它拖慢首屏。

**验收标准**

- 能查到真实域名的注册时间，并有 SQLite 缓存与负缓存。
- 只有可疑结果触发查询；失败静默跳过。
- 新注册（<30 天）提升风险分并在 reasons 里可见。
- 契约测试覆盖缓存、解析、404、加分四种情况。

**不做**

- 语义分（需 embedding 模型，另开一轮）；GSB/URLhaus（无 key）。

## 2 做了什么

1. 新增 core/rdap.py：rdap.org 引导查询 + SQLite domain_age 表（正常 30 天、负缓存 1 天）+ 并发与总预算控制。
2. 搜索链路接入：安全过滤后对 risk > 0 的结果补年龄，命中 <30 天加 0.15 并追加 reason；越过 0.6 的按拦截处理。
3. 修 SafeFetcher 的放行规则：原来只对 IPv4 bench 段生效，本机代理解析到 2001:2::/48 时一律被拦；改为「显式放行只对 bench 段生效」，并保留 0.0.0.0/0 不能放开内网的保证。
4. 配置 RDAP_ENABLED / RDAP_TTL_DAYS；.env 的 FETCH_EXTRA_CIDRS 同时列 IPv4 与 IPv6 bench 段。
5. 3 个契约测试（缓存过期、注册时间解析与负缓存、加风险分），测试环境默认 RDAP_ENABLED=false 避免联网。
6. 实测宿主机与容器内的真实查询，记录延迟与注册时间。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [apps/api/app/core/rdap.py](../apps/api/app/core/rdap.py) | 新增 | 查询、缓存、并发控制 |
| [apps/api/app/core/fetch.py](../apps/api/app/core/fetch.py) | 修改 | 放行网段限定为 bench 段（含 IPv6） |
| [apps/api/app/routers/search.py](../apps/api/app/routers/search.py) | 修改 | 接入年龄信号与拦截统计 |
| [apps/api/app/config.py](../apps/api/app/config.py) | 修改 | RDAP_ENABLED / RDAP_TTL_DAYS |
| [apps/api/tests/test_rdap.py](../apps/api/tests/test_rdap.py) | 新增 | 3 个用例 |
| [apps/api/tests/conftest.py](../apps/api/tests/conftest.py) | 修改 | 测试默认关 RDAP |
| [.env](../.env) | 修改（本地） | FETCH_EXTRA_CIDRS 加 IPv6 bench 段 |
| [README.md](../README.md)、[docs/决策与接口变更.md](../docs/决策与接口变更.md)、[docs/进展与欠账.md](../docs/进展与欠账.md) | 修改 | 说明与状态 |
| 本报告与 [INDEX.md](INDEX.md) | 新增/更新 | 登记 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| python -m pytest apps/api -q -o addopts= | 通过 | 305 passed |
| python -m pytest apps/api/tests/test_rdap.py -q | 通过 | 3 例：缓存过期、解析+负缓存、加风险分 |
| 宿主机实时查询 | 通过 | python.org 1995-03-27（3096ms）、github.com 2007-10-10（6698ms）、anthropic.com 2001-10-03（3556ms） |
| 容器内查询 | 通过 | docker compose exec api 查 python.org → 1995-03-27 |
| 搜索延迟 | 观察 | HTTP 缓存 查询 8107ms（冷缓存 + 引擎慢）；RDAP 只对 1 条可疑结果触发，最多 +4s 预算 |
| /api/health | 通过 | blocklist_rules=301，provider=searxng |

未验证：真实钓鱼域名的新注册判定（没有样本）；不同 ccTLD 的 RDAP 覆盖情况；负载下 4 秒预算是否够。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 只查 risk > 0 的结果 | 全部结果都查 | 首次 3–7 秒，全量查等于把首屏拖到十秒 |
| 30 天 / 1 天双层缓存 | 只做正缓存 | 查不到的域名也会被反复重试，负缓存能止血 |
| 年龄只加 0.15 不拦截 | 新域名直接丢 | 新域名不必然恶意，需叠加其他信号 |
| 放行网段限定为 bench 段 | 允许任意 CIDR | 否则 0.0.0.0/0 会顺带放开内网，SSRF 防线失效 |

## 6 遗留与风险

- 首次查询 3–7 秒，虽然只对可疑结果触发，仍可能让个别查询慢 4 秒。
- 只有注册时间；到期时间、注册商、隐私代理信息都没有。
- 部分 ccTLD 无 RDAP，会退化成「查不到」并负缓存一天。
- 阈值 30 天与权重 0.15 没有真实样本校准，属于经验值。

## 7 交接

**下一个人第一件事**

用一批已知钓鱼/正常域名（各 20 条）校准 30 天阈值与 0.15 权重，并观察 RDAP 在负载下是否需要把预算从 4s 调小。

**相关文件**

- [RDAP 实现](../apps/api/app/core/rdap.py)
- [决策 M15-D1…D4](../docs/决策与接口变更.md)
- [README RDAP 章节](../README.md)

---

> 注：头部「耗时」由 `close-report.ps1` 按报告起草时间计算；本轮实际约 40 分钟（含 IPv6 放行规则的返工）。
