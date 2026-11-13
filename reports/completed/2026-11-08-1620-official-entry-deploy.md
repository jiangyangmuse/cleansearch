# 完工报告 · 官方入口修复日常部署与真实验收

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261108-1620 |
| 开始 | 2026-11-08 16:20 |
| 结束 | 2026-11-08 16:29 |
| 耗时 | 10 分钟 |
| 执行者 | Codex |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

目标：执行上轮下一动作，让官方入口修复在日常 8000 服务生效，并核对真实搜索、缓存与引用。
验收：原生库/令牌/模型选择保留，API 加载新字段，品牌导航与教程行为正确，真实页面与总结引用可用。
不做：不切换部署方式，不合并原生与 Docker 数据，不提交推送，不重跑十三引擎矩阵或全部品牌网络核验。

上一轮已完成源码复核（427 API、构建与两套 fixture 冒烟通过），但日常进程尚无 official 字段。本轮按开工协议读取台账最近三份、决策与共享交接后执行部署。

## 2 做了什么

1. 构建前端，核对原生 API 13796 的 uvicorn 命令、cwd、环境与监听归属；确认当前日常 DB 是 data/review-temp/verify.db。备份 SQLite 与令牌，保存书签三表计数/摘要，不输出记录或凭据。
2. 第一次仅原样重启 8000：13796→8692，official 及完整结果字段加载成功。所有配置、库与令牌保持一致，8888 上游未动，CACHE_ENABLED=true。
3. 真实 SearXNG 默认搜索验证：deepseek 冷请求 10.59 秒，4 官方（官网/聊天/文档/控制台）+17 普通；重复请求约 0.02 秒命中缓存且官方分区完全一致。documentation 查询 3 官方+17 普通；how to use 查询 0 官方+15 普通。官方/普通 URL 不重复，条数与 ID 一致。
4. 首次总结虽完整返回，SSE 模型却是 stub-extractive；核对原进程环境和项目 .env，LLM_PROVIDER=openai、模型名为千问，但 LLM_BASE_URL 为空。保留此发现，没有把它算成千问实测。
5. 只读确认本机 Ollama 已安装所选模型后，备份 .env，将唯一空端点补成 http://127.0.0.1:11434/v1；8692→592 再启 API。进程环境逐项比较，仅 LLM_BASE_URL 改变；模型、推理参数、超时、数据库和令牌路径全部保留。
6. 实际千问 fast 总结完成：10 来源，296 字符，约 20.11 秒，SSE 的模型名与所选模型一致，10 个 cite 的 ID/URL 均属于本次响应，首条为官网；有正文、编号引用与 done，无 error。
7. 在日常页面实际生成千问总结，约 8.76 秒完成；正文 [1] 定位到官网 r_2。四入口默认可见、显示总数 21、键盘选择、无重复、缓存与教程查询正确，390px 无溢出、pageerror=[]。没有新增/删除正式书签，仅 favicon 请求返回 404 以排除图标下载。
8. 最终只读核对书签三表、令牌、8888 PID、构建首页和已验源码指纹；全部一致。同步 README、决策 OFFICIAL-A1～A3、进度与本报告。

## 3 改动清单

| 路径/运行对象 | 说明 |
| --- | --- |
| .env | 仅补 LLM_BASE_URL，本机 Ollama /v1；不记录或改写密钥 |
| 日常原生 API :8000 | 13796→8692→592，新 API 与原模型设置实际生效 |
| apps/web/dist/ | 本轮前端构建，46 modules |
| data/official-deploy-backup-20261108-1620/ | 原库、令牌与端点修正前 .env 备份；私有且被 Git 忽略 |
| data/native-api-official-deploy.log | 后台 API 运行日志，不纳入报告资产 |
| reports/assets/official-entry-deploy/ | 重启/核验脚本、计数摘要、公开查询响应、总结与截图 |
| README.md、docs/决策与接口变更.md、docs/进展与欠账.md | 追加运行状态、端点修复与验证边界 |
| 本报告、reports/INDEX.md | 本任务登记与完成归档 |

无 API/前端业务源码改动。先前 DSH/Codex 的未提交改动保留；没有修改他们的报告正文、引擎配置、回退或熔断，也未访问/迁移 Docker 书签卷。既有日常库三张书签表均为 0，本轮前后相同；不能据此声称 Docker 库也为 0。

## 4 验证与证据

| 命令原文 | 退出码与关键输出 |
| --- | --- |
| `npm --prefix apps/web run build` | 0；tsc+Vite，46 modules；JS 268.15 kB/gzip 84.42 kB |
| `python reports/assets/official-entry-deploy/restart-native.py` | 0；13796→8692，healthy/official_loaded/config_preserved/db_preserved/token_preserved/searxng_preserved 均 true，缓存 true |
| `python reports/assets/official-entry-deploy/verify-live.py`（首轮） | 0；首次 cached=false，10.59 秒；随后 cached=true，4 入口/17 普通；文档 3/17、教程 0/15；总结实际 stub，未当作千问通过 |
| 本机 `GET http://127.0.0.1:11434/api/tags` | 0；已安装模型包含 qwen3.5-4b-local:latest；未调用或下载其他模型 |
| `python reports/assets/official-entry-deploy/restore-ollama.py` | 0；8692→592，changed_settings=[LLM_BASE_URL]，其他环境完全一致；.env 只补一个原为空的值 |
| `python reports/assets/official-entry-deploy/verify-live.py`（修正后） | 0；四次查询均命中已有缓存；SSE model=qwen3.5-4b-local:latest，done=true、10 cite、296 字符、20.11 秒；来源映射通过 |
| `node reports/assets/official-entry-deploy/verify-browser.cjs`（最终） | 0；真实 API 与千问，无搜索/总结打桩；官网/聊天/文档/控制台默认可见；总数 21；[1]→官网；模型输出约 8760ms；390px 无溢出；教程无官方区；pageerror=[] |
| `python reports/assets/official-entry-deploy/verify-preservation.py` | 0；final_pid=592，三表摘要/令牌/8888进程/已验代码指纹均未变，实际 SSE 模型与配置一致，首页与构建 SHA256 相同 |
| `git check-ignore .env data/official-deploy-backup-20261108-1620/.env-before-ollama` | 0；两路径均被忽略，不会作为报告/源码提交 |
| `git -c core.safecrlf=false diff --check` | 0；无空白错误 |

资产：[本轮目录](../assets/official-entry-deploy/)；before.json、restart.json、model-endpoint-restored.json、preservation.json 只含公开配置名、计数/摘要，不含环境凭据。search-live.json、summary-live.json 为端点修正后的结果；首轮冷请求时间来自该次 CLI 真实输出，随后重跑写入了热缓存结果。browser-before-model.json 保留发现桩总结的证据，browser-live.json 与 live-desktop/mobile.png 为最终千问实测。截图已检查。

初次原样重启完全保持配置；第二次是为恢复已选模型而显式补齐端点，这是本轮唯一配置修正。验证脚本最后还增加了“实际 SSE 模型必须等于配置且不能为 stub”的断言；同一最终输出已由 verify-preservation.py 独立核对，无需为新增断言重复调用模型。

本轮是 ops，未重新跑 pytest 或 fixture 冒烟：业务源码未改且最终指纹与上轮一致，427 测试与 16/16、15/15 均为上一轮证据。本轮执行前端构建、日常健康/契约/真实查询/缓存/SSE/浏览器与数据保留验证。未对真实 SearXNG 运行要求固定样本的 smoke.ps1，以免把测试模式差异算作故障。

## 5 关键决策

OFFICIAL-A1：保留当前原生部署与存储，仅重启明确归属的 8000 API，8888 不动。
OFFICIAL-A2：缺失端点导致桩总结；只补本机已有 Ollama 地址，所选千问与参数不变；配置先备份。
OFFICIAL-A3：实际模型调用以 SSE meta、正文和 done 为据，不仅依据 health 的模型名称。

## 6 遗留与风险

- 只验少量公开查询与 fast 总结；未重跑十三引擎、112 品牌入口或 full 正文抓取。已有单引擎 CAPTCHA 警告正常保留，不据整体有结果推算每个上游可用。
- 引用 ID/URL/定位已验，不等同模型正文逐事实准确；20.11 秒和 8.76 秒是两次实际样本，不构成延迟分布或服务承诺。
- 当前仍使用原生既有 data/review-temp/verify.db，路径名字含 review 不改变其当前日常用途。未来固定部署路径、开机恢复、长期备份仍按原上线计划处理，不在本轮迁移。
- API 与 Ollama 原生进程保持运行；无临时 fixture 服务新增。没有提交推送、托管 CI 或容器重建；原 Compose、正式 Chrome/Android 等欠账不抵扣。
- 回退数据备份位于 data/official-deploy-backup-20261108-1620；不要把其中令牌/.env 内容粘到报告或公开仓库。若回退端点配置，实际总结会恢复原来的桩行为。

## 7 交接

现在可直接访问 http://127.0.0.1:8000/?q=deepseek 使用官方入口和现有千问总结；若旧页面已打开，刷新后使用。保留本机 Ollama 运行。

下一步进入日常试用，记录具体误判查询或模型事实问题；然后按既有计划固定日常服务与备份恢复方式。代码发布/提交推送仍按用户当轮明确授权，不自动执行。

本报告完成表示日常部署及本轮真实链路验收完成，不表示历史所有上线门槛已通过。