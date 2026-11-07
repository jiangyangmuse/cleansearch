# 完工报告 · GitHub 远端与托管 CI

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-0153 |
| 开始 | 2026-11-08 01:53 |
| 结束 | 2026-11-08 01:53 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

**目标**

按用户提供的地址与方式接入 GitHub 远端：SSH 认证、公开仓库、提交身份改为 jyms_rue <jyme_rue@qq.com>，并确认托管 CI 能跑通。

**验收标准**

- 推送成功，远端 main 与本地一致。
- GitHub Actions 运行完成并有结论。
- 作者信息已按用户要求改好。
- 仓库中不含密钥。

**不做**

- 不打包工作区里另一位执行体未完成的 20 个文件改动。

## 2 做了什么

1. 设置仓库级提交身份 jyms_rue <jyme_rue@qq.com>；确认已有 ed25519 密钥，ssh -T 返回 Hi jiangyangmuse。
2. 暂存工作区未完成改动 → 用 filter-branch 把 4 个提交的作者/提交者重写为新身份 → 恢复工作区。
3. 远端切到 git@github.com:jiangyangmuse/cleansearch.git，推送 main。
4. 用公开 API 轮询 Actions：ci #1 从 queued → in_progress → success，33 秒。
5. 拉取 job 明细：8 个步骤全部 success（含 fixture 冒烟）。
6. 文档：README 增「GitHub 远端与托管 CI」与 act 差异表；决策 M17-D1…D4；进展与欠账把 P1-1 与缺口 1 关闭。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [README.md](../README.md) | 修改 | GitHub 远端、Actions 结果、与 act 的差异 |
| [docs/决策与接口变更.md](../docs/决策与接口变更.md) | 修改 | M17-D1…D4 |
| [docs/进展与欠账.md](../docs/进展与欠账.md) | 修改 | P1-1 完成、缺口 1 关闭 |
| 仓库历史 | 重写 | 4 个提交作者改为 jyms_rue |
| 本报告与 [INDEX.md](INDEX.md) | 新增/更新 | 登记 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| ssh -T git@github.com | 通过 | Hi jiangyangmuse! You've successfully authenticated |
| git log --format='%h %an <%ae> %s' -4 | 通过 | 4 个提交均为 jyms_rue <jyme_rue@qq.com> |
| git push -u origin main | 通过 | [new branch] main -> main |
| GitHub Actions api（run 42393430557） | 通过 | status=completed conclusion=success，33 秒，event=push |
| Actions job 明细 | 通过 | 8 步 success：checkout/setup-python/setup-node/Install/API tests/Build web/Smoke |
| git ls-files 敏感文件检查 | 通过 | 无 .env / token / pem 被跟踪 |

未验证：私有仓库场景（当前 public）、矩阵构建、tag 触发；Actions 日志正文需要 token 才能下载，本轮只取了步骤结论。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| SSH 认证 | PAT 写进脚本或 URL | 密钥已在且 ssh -T 通过，token 不必落地 |
| 推送前重写历史作者 | 保留 DSH/lead 或事后改 | 公开仓库不该出现工具身份；推送前改不影响任何人 |
| 只提交本轮文档 | 把工作区 20 个改动一并打包 | 那些是另一位执行体未收口的改动，打包会制造半成品提交 |
| 公开仓库 | private | 用户明确 public；公开仓库 Actions 不限额度，也能直接读 run 状态 |

## 6 遗留与风险

- 仓库现在是公开的：代码、报告、证据图都对外可见；已确认无密钥，但后续新增文件仍需自查。
- Actions 日志正文未下载（需要 token），只有步骤级结论。
- 工作区仍有 20 个未提交改动（另一执行体的 eval-rdap/eval-summary/browser-check 等），未纳入本次推送。
- 本地 bare 远端 D:\agent\llq-remote.git 仍在，可作离线备份。

## 7 交接

**下一个人第一件事**

把那 20 个未完成改动收口后单独提交并推送，观察 Actions 是否仍为绿色；同时给仓库加分支保护（要求 ci 通过才能合并）。

**相关文件**

- [README GitHub 章节](../README.md)
- [决策 M17-D1…D4](../docs/决策与接口变更.md)
- [Actions 运行](https://github.com/jiangyangmuse/cleansearch/actions/runs/42393430557)

---

> 注：头部「耗时」由 close-report.ps1 按报告起草时间计算；本轮实际约 20 分钟。
