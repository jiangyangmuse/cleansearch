# 完工报告 · 托管 CI 收口与 AI 贡献署名

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-0212 |
| 开始 | 2026-11-08 02:12 |
| 结束 | 2026-11-08 02:20 |
| 耗时 | 8 分钟 |
| 执行者 | Codex |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

核对 GitHub 托管 CI，将上轮已验收修复与本次署名/CI 文档发布，记录 Codex 与 DeepSeek Harness（DSH）的实际协作。

验收：托管运行与发布 SHA 对应，测试/判断器/构建/冒烟成功；贡献说明在 GitHub 可读；工作区进度与证据一致。不改写历史、不伪造账号邮箱或 Contributors 数据。

用户当轮明确授权“提交并推送上轮已验收修复＋本次文档，验证新版本 CI”。GitHub 自动 Contributors 列表的身份统计由平台决定；本轮采用项目文件记录 AI 协作署名。

## 2 做了什么

1. 独立核对原 ci #1/#2：均 success。#2 对应 4032535，日志确认 315 项测试、构建和冒烟；它没有覆盖未提交的 M17 修复。
2. 新增 CONTRIBUTORS.md，列明项目维护者、Codex、DSH 的角色及实际贡献；README 加入口与 CI badge。使用工具名称署名，不冒用官方或其他账号。
3. 按 AGENTS.md 取得当轮明确发布授权。发布前再跑 323 项本地测试、生产构建及判断器负例，检查待发布范围与已配置凭据。
4. 正常新增 `43ea950930bc05076f2742597137e78e94db68cd` 并推送 main，共 44 个文件，包含上轮修复、证据与署名；保持已有 Git 作者配置和历史。
5. 等待并核对 ci #3，9 个主要步骤及收尾步骤均成功。下载 job 日志确认 323 项、判断器 1/1、构建 42 模块和 15 项冒烟成功；远端 CONTRIBUTOR 文件可读。
6. 将 P1-1 从待办移出，分别保留 315 基线和 323 修复版本证据。补 M18 决策与贡献统计规则；其余真机、新站和事实质量欠账继续保留。

## 3 改动清单

| 产物 | 说明 |
| --- | --- |
| `CONTRIBUTORS.md` | 维护者及 Codex/DSH 的 AI 协作署名、贡献与平台统计的区别 |
| `README.md` | badge/贡献入口、三次 CI 的 SHA/时间/结果、当前下一步 |
| `docs/进展与欠账.md` | P1-1 收口，保留其它未验项 |
| `docs/决策与接口变更.md` | M18：按 SHA 验收、AI 工具署名、明确授权及发布结果 |
| `reports/assets/hosted-ci-credit/hosted-ci.json` | 脱敏后的运行/步骤与日志摘要，不存完整 job 日志或账号邮箱 |
| `reports/assets/hosted-ci-credit/publish-manifest.json` | 首次源码发布范围与本地文件哈希；Git 可能按属性规范行尾 |
| `reports/assets/hosted-ci-credit/prepublish-api-tests.xml` | 发布前完整 API 回归 |
| `reports/assets/hosted-ci-credit/verify.py`、`document-check.json` | 链接、台账、源码范围、署名和证据核对 |
| 上轮修复及证据 | 具体内容见原 2026-11-07-1659 报告，本轮只收口发布与 CI |
| 本报告、`reports/INDEX.md` | 登记完成并归档，不改他人历史报告或状态行 |

## 4 验证与证据

| 命令原文 / API 操作 | 退出码 / 实际结果 |
| --- | --- |
| `git remote -v`、`git log -5 --format="%h %an <%ae> %s" --decorate` | 0；origin 已为 GitHub SSH，开工 HEAD=4032535，现有历史作者保持 |
| GitHub `fetch` runs #1/#2、`fetch_workflow_run_jobs`、`fetch_workflow_job_logs(job_id=128466069623)` | success；#2 completed/success，日志 `315 passed, 1 warning in 7.67s` |
| `python -m pytest apps/api -q -o addopts= --junitxml=reports/assets/hosted-ci-credit/prepublish-api-tests.xml`，TEMP/TMP 指向工作区隔离目录 | 0；`323 passed in 10.50s` |
| `npm --prefix apps/web run build` | 0；TypeScript 通过、42 modules、Vite 构建成功 |
| `node --test scripts/browser-check.test.cjs` | 0；1 test、pass 1、fail 0 |
| 发布清单与已配置凭据扫描（Python） | 0；44 个文件含清单自身；无额外路径、密钥配置或 data 目录纳入 |
| `git fetch origin main` | 0；FETCH_HEAD 与开工 HEAD 一致，无并发远端提交 |
| `git diff --cached --check` | 初次 2，发现一份冒烟日志 EOF 多余空行；规范末尾并更新哈希后 0 |
| `git commit -m "fix: publish acceptance hardening and AI collaboration credits"` | 0；43ea950，44 files，正常新增提交 |
| `git push origin main` | 0；4032535..43ea950，main -> main |
| GitHub run `42395082507` / job `128470595808` 的状态、步骤、日志 | completed/success，323 passed in 8.13s；判断器 1/1；42 模块；冒烟通过；全部步骤成功 |
| GitHub raw `43ea950/CONTRIBUTORS.md` | success；远端文本含 Codex 与 DeepSeek Harness，README 入口已发布 |
| `python reports/assets/hosted-ci-credit/verify.py` | 0；100 个相对链接/锚点有效；38 份报告与台账一致；37 份历史报告/状态行保持；当前产品代码与已托管验证的 43ea950 一致 |
| `.\scripts\close-report.ps1 -Path reports/2026-11-08-0212-hosted-ci-credits.md`，归档后 `.\scripts\check-report.ps1 -Path reports/completed/2026-11-08-0212-hosted-ci-credits.md` | 均 0；报告结构 PASS、完成状态登记并归档 |

托管 CI #3：2026-11-08 **02:11:33–02:12:17 JST**（44 秒），event=push，branch=main，SHA=`43ea950930bc05076f2742597137e78e94db68cd`。[运行链接](https://github.com/jiangyangmuse/cleansearch/actions/runs/42395082507)

托管 fixture 冒烟为项目 `scripts/ci-smoke.py` 的 15 项；PowerShell 冒烟 16 项已有上轮证据，本轮没有重复调用真实搜索/总结或设备验收。公开日志的脱敏摘要、文档字数/行数与链接检查见 hosted-ci.json 和 document-check.json。

未验证：正式 Chrome 手动加载/原生书签互迁、Android 真机、新注册正常对照、总结全量事实准确率、分支保护/矩阵等。本轮未将这些写成已完成；CI 绿色仅覆盖该源码版本的工作流检查。

## 5 关键决策

按 M18 执行。GitHub Contributors 根据提交及账号邮箱关联等条件统计，当前没有可用的 Codex/DSH 账号映射；使用项目贡献文件记录真实工具协作。不填写虚构邮箱或 `Co-authored-by`，也不恢复/改写历史作者。

[GitHub 贡献者规则](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-a-projects-contributors) · [共同作者规则](https://docs.github.com/en/pull-requests/how-tos/commit-changes/creating-a-commit-with-multiple-authors)

## 6 遗留与风险

- AI 协作署名文件已公开，但它不向 GitHub 自动 Contributors 列表手工插入账号。如后续使用专用机器人身份，需提供真实获授权的账号邮箱，并用于其实际贡献的新提交。
- 上轮成果的正式浏览器/Android、新站对照和事实质检仍需完成，原部分完成报告保留根目录。
- CI #3 验证的是源码提交 43ea950。收口提交仅更新文档、报告与证据；发布后继续确认其 Actions，避免把旧基线状态误记为新源码通过。

## 7 交接

托管 CI 欠账已收口。下一步继续逐事实盲标与有出处的新注册正常域名对照，再补正式浏览器和 Android；按真实需要另行配置分支保护。

- [当前进度](../../docs/进展与欠账.md)
- [公开贡献说明](https://github.com/jiangyangmuse/cleansearch/blob/main/CONTRIBUTORS.md)
- [本地贡献说明](../../CONTRIBUTORS.md)
- [托管验收证据](../assets/hosted-ci-credit/hosted-ci.json)
- [文档与源码范围核对](../assets/hosted-ci-credit/document-check.json)

归档本报告后提交验收文档；本轮不启停用户服务、不修改本机模型配置或正式书签数据。
