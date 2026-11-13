# 完工报告 · 官方入口混杂原因与分区方案

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1530 |
| 开始 | 2026-11-08 15:30 |
| 结束 | 2026-11-08 15:31 |
| 耗时 | 2 分钟 |
| 执行者 | Codex |
| 任务类型 | docs |
| 状态 | 完成 |

## 1 任务

目标：诊断官方入口混杂，并给出可实施方案。验收：有代码依据、离线验证和建议边界。本轮不修改业务代码、不发布或提交推送。

## 2 做了什么

读取台账最近三份报告、决策、共享交接、打分、响应模型和结果展示代码。上一轮已验证 DeepSeek 根入口与聊天入口保留，十三引擎首屏 11/13；Mojeek 与完整 Compose 仍有欠账。

当前只按相关性分档，没有品牌官方身份与入口角色。百科、代码托管等通用权威站点有加分，未在名单内的品牌官网没有该项加分。NAV 修复防止入口被误去重，尚未处理身份识别和独立展示。

建议方案（尚未实现）：

1. 建可维护的品牌入口表：品牌别名、精确主机、允许路径、入口角色、核验来源与日期。共享托管域名须限定组织/路径，不整域认证。
2. 品牌导航查询在首屏单独显示“官方入口”，按官网、聊天/产品、文档、控制台等角色组织；同角色语言版本可折叠。教程、百科、新闻继续按现有相关性展示；教程或新闻查询不无条件置顶全部品牌入口。
3. 官方身份与相关性分开。标题写官网、docs 前缀、多引擎共识或模型判断均不足以独立认证。未知品牌保持普通结果；主机匹配拒绝 brand.com.example.org 之类伪装。
4. 第一版只识别上游返回的候选，不推造缺失链接。若后续从核验目录补充入口，须标注目录来源和复核日期，并新增决策说明对 NAV-D4 范围的扩展。
5. 提取官方候选应在三档容量截断前完成。契约变更须同步计数、缓存版本、总结引用、键盘导航和去重，避免卡片重复或引用错位。

## 3 改动清单

| 路径 | 说明 |
| --- | --- |
| 本报告 | 原因、证据和建议 |
| reports/INDEX.md | 仅新增本任务登记，维护本行状态与链接 |

工作区既有 breaker、engines、probe、README、决策、进度和上一轮报告等改动未在本轮改写。没有新增已定产品决策。

## 4 验证与证据

实际命令，退出码 0：

```powershell
$env:PYTHONPATH='apps/api'; @'
from app.core.scoring import authority_score
from app.schemas import Result, Groups
for host in ['www.deepseek.com','chat.deepseek.com','en.wikipedia.org','github.com','docs.unverified-example.com']:
    print(host, authority_score(host))
print('Result fields:', ','.join(Result.model_fields))
print('Groups fields:', ','.join(Groups.model_fields))
```

以上 Python 内容通过 PowerShell here-string 管道送给 `python -` 执行（此处省略结束分隔符以便阅读）。输出：www.deepseek.com=0.0；chat.deepseek.com=0.0；en.wikipedia.org=1.0；github.com=1.0；docs.unverified-example.com=0.9。最后一项仅为离线字符串输入，未访问该主机，不代表其存在或属于官方站点。权威项最终权重 0.15，不能据此断言某次搜索的最终名次。

Result 字段没有官方身份或入口角色；Groups 只有 strong、related、weak。

`rg -n -C 2 'title="(强相关|相关|弱相关)|groups\.(strong|related|weak)' apps/web/src/App.tsx`：退出 0，第 330–346 行仅渲染三档结果。

文档验证使用 `scripts/close-report.ps1` 与 `scripts/check-report.ps1`，字数以最终计数输出为准。未运行 pytest、冒烟或浏览器：本轮仅诊断与文档，无业务实现；探针验证机制，没有复现用户本次具体查询。

一次报告写入命令因嵌套 here-string 解析失败，退出 1，未写入正文；随后调整写法补齐，不影响离线探针证据。

## 5 关键决策

建议优先实现“核验入口表 + 品牌导航识别 + 独立展示”。来源身份、页面用途和相关性分别表达。此为待实施建议，不更改既有决策。

## 6 遗留与风险

混杂现象尚未修复，本次只完成诊断咨询。用户未提供具体查询，不能确认其现场名次。入口表需要维护，不能用品牌词或模型自动猜测认证。官方身份也不保证页面始终可访问或内容准确。

后续验收覆盖多个品牌/别名、多个官方角色、教程新闻意图、未知品牌、伪装域名、共享托管路径、语言页、候选缺失不造链接、容量截断、缓存和总结引用。

## 7 交接

下一步实现小范围核验品牌表与官方入口区，再做真实查询验收；变更接口或 NAV-D4 范围须追加决策。相关代码：apps/api/app/core/scoring.py、apps/api/app/schemas.py、apps/api/app/routers/search.py、apps/web/src/App.tsx。

本报告完成状态只表示诊断完成，不表示分区已上线。原 M19 欠账保留；归档后从 INDEX 链接查找。