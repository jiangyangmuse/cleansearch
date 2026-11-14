# 完工报告 · 收口并行改动并推送

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1437 |
| 开始 | 2026-11-08 14:37 |
| 结束 | 2026-11-08 14:38 |
| 耗时 | 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

**目标**

把工作区里并行执行体留下的改动收口、验证、提交并推送到 GitHub，确认托管 CI 通过；然后加分支保护。

**验收标准**

- 工作区干净，改动已推送；CI 结果为 passing。
- 推送前有本地验证证据（测试、构建、脚本用例、冒烟）。
- 分支保护若无法完成，写明卡点与具体命令。

**不做**

- 不改写并行执行体的实现，不动他们的报告正文。

## 2 做了什么

1. 读 M19 引擎目录/回退、导航去重两份报告，确认改动自带验收与证据。
2. 本地全量验证：362 项 API 测试、前端构建、engine-query 14 例、browser-check 1 例、fixture 冒烟 16/16。
3. 扫密钥：命中项全部是测试里的占位 key（test-key / serper-key），reports/assets 无凭据；资产合计 1.1MB。
4. 提交 31764ad 并推送（第一次 push 遇瞬断，重试成功 5af2daf..31764ad）。
5. GitHub 匿名 API 额度用尽后改用 workflow badge 判定：`ci - passing`。
6. 分支保护无法在无 token 情况下设置，写入报告与 README（网页步骤 + gh 命令）。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| 工作区并行改动（apps/api、apps/web、scripts、reports、searxng） | 提交 | 31764ad |
| [README.md](../../README.md) | 修改 | 收口记录、分支保护步骤、API 限制 |
| [docs/决策与接口变更.md](../../docs/决策与接口变更.md) | 修改 | M18-D1…D3 |
| 本报告与 [INDEX.md](../INDEX.md) | 新增/更新 | 登记 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| python -m pytest apps/api -q -o addopts= | 通过 | 362 passed |
| npm --prefix apps/web run build | 通过 | 42 modules，dist 266KB |
| node --test scripts/engine-query.test.cjs | 通过 | 14 pass / 0 fail |
| node --test scripts/browser-check.test.cjs | 通过 | 1 pass / 0 fail |
| pwsh -File scripts/smoke.ps1 -BaseUrl http://127.0.0.1:18110 | 通过 | 16/16 |
| git push origin main | 通过 | 5af2daf..31764ad |
| badge.svg | 通过 | `ci - passing` |
| git status --short | 通过 | 0（提交后） |

未验证：分支保护（无 token）；本次推送的 job 级步骤明细（匿名 API 限流，只能读 badge）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 按原样收口并行改动 | 逐文件重审改写 | 改动自带报告与回归，重写会制造语义冲突 |
| badge 判 CI | 等一小时再查 API | badge 不耗额度且直接反映默认分支最新结果 |
| 分支保护留待用户 | 硬塞 token | 没有写权限就设置不了，也不该索要凭据 |

## 6 遗留与风险

- 分支保护未设置：main 仍可直接推送，`verify` 未设为必需检查。
- 匿名 API 限流期间拿不到 job 明细；如需日志要 `gh run view`。
- 公开仓库新增了并行执行体的报告与证据图（1.1MB），后续提交仍需自查是否含敏感信息。
- 本次推送内容较多（引擎目录、回退、导航去重），但本地与 CI 均绿。

## 7 交接

**下一个人第一件事**

登录 gh 后执行 README 里的分支保护命令（或网页设置），把 `verify` 设为必需检查；随后补一次 PR 流程演练，确认保护真的拦住红灯提交。

**相关文件**

- [README 收口章节](../../README.md)
- [决策 M18-D1…D3](../../docs/决策与接口变更.md)
- [M19 报告](../incomplete/2026-11-08-1137-m19-engine-suffix-repair.md)

---

> 注：头部「耗时」由 close-report.ps1 按报告起草时间计算；本轮实际约 30 分钟（含一次 push 瞬断重试与 API 限流绕行）。
