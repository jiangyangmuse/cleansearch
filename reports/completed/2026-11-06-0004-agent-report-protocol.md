# 完工报告 · 开工完工协议与报告自动化

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261106-0004 |
| 开始 | 2026-11-06 00:04 |
| 结束 | 2026-11-06 00:05 |
| 耗时 | 2 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | docs |
| 状态 | 完成 |

## 1 任务

**目标**

让每次开工先读上下文、每次完工自动产出可校验的报告：把"读协议"绑到自动加载机制上，把"写报告"压成一条命令加一道机器校验。

**验收标准**

- [x] 工作区根目录存在 `AGENTS.md`，DSH 会话第一轮自动加载（本次会话已验证：系统提示出现 `Instructions from: AGENTS.md` 并带全文）
- [x] 三个脚本可执行：`new-report` / `check-report` / `close-report`
- [x] 空模板被 lint 拒绝（exit 1），填满后通过（exit 0）
- [x] 台账 `reports/INDEX.md` 自动登记新行，close 时同步状态

**不做**

- 不做全局安装（`~/.dsh/AGENTS.md`），只在 §8 写明移植方法
- 不做 git hook / CI 强制
- 不动 M0 业务代码

## 2 做了什么

1. 新增 `AGENTS.md`：SOP-OPEN 五步 + SOP-CLOSE 五步 + 报告规范 + 7 条红线 + 本项目命令表 → DSH 与 Codex 均自动加载
2. 新增 `reports/_TEMPLATE.md`：7 段式模板，所有待填项统一写成 `〔待填〕`，为机器校验留锚点
3. 新增 `reports/INDEX.md`：台账表格，新行插在表头分隔线之后（新的在上）
4. 新增 `scripts/new-report.ps1`：校验 slug → 生成 `YYYY-MM-DD-HHmm-<slug>.md` → 自动填编号/开始时间/执行者/改动文件 → 台账插入一行（状态=进行中）
5. 新增 `scripts/check-report.ps1`：6 项校验（命名、`{{}}` 残留、`〔待填〕` 残留、状态字段、260 行上限、6 个必填段非空），另有 2 条 warning（状态未落定、证据无命令）
6. 新增 `scripts/close-report.ps1`：先调 check，通过后写结束时间与耗时、状态置完成态、把台账对应行的「进行中」改掉；校验失败不改任何内容
7. 修 bug：改动扫描的正则尾反斜杠导致 `Invalid pattern ... Illegal \ at end of pattern`，改成字符类 `[\\/](node_modules|...)[\\/]` 后正常
8. 收紧 lint：初版对未填模板判 PASS（占位行被当成正文）→ 引入 `〔待填〕` 哨兵后正确判 FAIL
9. 修误伤：报告中只要用行内代码引用了哨兵本身就会被判未填 → 校验前先剥离围栏代码块与行内代码再比对

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `AGENTS.md` | 新增 | 协议本体，自动加载 |
| `reports/_TEMPLATE.md` | 新增 | 报告模板 |
| `reports/INDEX.md` | 新增 | 台账 |
| `scripts/new-report.ps1` | 新增 | 起草脚本 |
| `scripts/check-report.ps1` | 新增 | 校验脚本 |
| `scripts/close-report.ps1` | 新增 | 落定脚本 |
| `reports/2026-11-06-0004-agent-report-protocol.md` | 新增 | 本报告 |
| `docs/决策与接口变更.md` | 修改 | 追加 P1–P4 流程决策（协议红线 4：改了决策要同步） |

> 自动采集把 M0 的近 6 小时改动也扫了进来（本工作区无 git 仓库，按 mtime 粗采），已按实际改动收窄。

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `.\scripts\new-report.ps1 -Slug agent-report-protocol -Type docs -Title "开工完工协议与报告自动化"` | 通过 | 生成 `reports\2026-11-06-0004-agent-report-protocol.md`，台账插入 1 行且状态=进行中 |
| `.\scripts\check-report.ps1`（对刚生成的空模板） | 失败（符合预期） | `[check] FAIL` / `× 还有未填写的〔待填〕占位` / `! 状态仍是「进行中」`，exit=1 |
| `.\scripts\new-report.ps1`（首版，正则 bug） | 失败 | `Invalid pattern '\\(node_modules|dist|...)\' at offset 71. Illegal \ at end of pattern`，exit=1 → 已修为字符类写法 |
| `.\scripts\check-report.ps1`（填满后首跑） | 失败（误伤） | 正文在普通段落里提到了哨兵字面量（引号内、非代码），被判为未填，exit=1 → 改为剥离代码块后比对 |
| `.\scripts\check-report.ps1`（修复后） | 通过 | `[check] PASS`，仅剩「状态仍是进行中」提示，exit=0 |
| `.\scripts\close-report.ps1 -Path reports\2026-11-06-0004-agent-report-protocol.md` | 通过 | 校验 PASS → 写入结束时间与耗时 → 状态改为「完成」→ 台账行同步 |
| AGENTS.md 自动加载 | 通过 | 本次会话系统提示中出现 `Instructions from: AGENTS.md` 并附协议全文，证明"每次开工必读"由机制保证，不靠自觉 |

证据文件：`reports/INDEX.md`（台账行）、本报告 §4 上表命令输出

未验证：Windows PowerShell 5.1 下的执行（脚本已加 UTF-8 BOM 兜底，未实测）；`new-report.ps1` 的 git 采集分支（本工作区无 `.git`，走的是 mtime 兜底）

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 协议放 `AGENTS.md` | 独立 `PROTOCOL.md` + 靠提示词要求"先读" | `dsh-agent-instructions` 与 Codex 都自动加载 AGENTS.md，是唯一能让"每次开工必读"不依赖自觉的机制 |
| 报告放 `reports/` | 混进 `docs/` | `docs/` 是产品文档（长期有效），`reports/` 是过程记录（按时间检索），生命周期与检索方式不同 |
| 用 `〔待填〕` 哨兵 | 靠人 review 或正则猜占位 | 只有可 grep 的显式哨兵能让 lint 真的失败；否则空模板会 PASS，校验形同虚设 |
| 报告生成与校验脚本化 | 只写一份文字规范 | 一条命令生成骨架 + 一道退出码，把合规成本压到最低，比写十页规范有效 |
| 状态值用中文（完成/部分完成/阻塞） | 英文 status | 台账是给人扫的，中文一眼可读，机器只需匹配字符串 |

## 6 遗留与风险

- `close-report.ps1` 靠文件名匹配台账行，报告一旦重命名就断链
- 无 git 仓库时改动清单按 mtime 粗采（近 6 小时、前 25 个），会把同期其它 agent 的改动算进来，需要人工收窄
- 没有 hook / CI 兜底，强制力仍来自 AGENTS.md 的约束
- 全局复用需手动复制到 `~/.dsh/AGENTS.md` 或 `~/.codex/AGENTS.md`
- 脚本仅在 PowerShell 7 实测；5.1 已写入 BOM，但中文参数与 `[ordered]` 行为未实测

## 7 交接

**下一个人第一件事**

跑 `.\scripts\new-report.ps1 -Slug <任务名> -Type <类型>` 起草，填满 §1–§7 后 `.\scripts\close-report.ps1 -Path reports\<文件名>.md`。

**相关文件**

- `AGENTS.md`
- `reports/_TEMPLATE.md`
- `reports/INDEX.md`
- `scripts/new-report.ps1` / `scripts/check-report.ps1` / `scripts/close-report.ps1`
