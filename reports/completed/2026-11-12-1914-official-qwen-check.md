# 完工报告 · 跨类别官网召回与本地千问检索验证

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261112-1914 |
| 开始 | 2026-11-12 19:14 |
| 结束 | 2026-11-12 19:16 |
| 耗时 | 3 分钟 |
| 执行者 | Codex |
| 任务类型 | test |
| 状态 | 完成 |

## 1 任务

抽查明日方舟和 Nexon 之外的官网召回。实测本机千问能否使用真实网页候选给 AI 检索提供结果。

验收覆盖 24 个站点的两路首屏、引擎实际来源、首页与内页、千问的来源映射和查询改写。日常 Bing 请求使用 8000，免费聚合和千问试验使用内存中的隔离 API。

## 2 做了什么

1. 选取目录内和目录外各 12 个样本，涉及软件开发、游戏、通讯、购物、媒体、政府、大学、博物馆和国际组织。分别调用日常 `!b` 和同一 SearXNG 上游的隔离免费聚合。主矩阵有 48 次请求，免费聚合首轮 4 次超时，等条件重试后均成功。
2. 按确切主机、首页路径和可核验的本地化入口判定。区分官方入口区、三档普通结果及目录直达。游戏可接受经核对的米哈游和 HoYoverse 入口。VLC 和空客的本地化首页计入。
3. 用真实候选对 Ollama 的 `qwen3.5-4b-local:latest` 做重排。隔离 `/api/ai-search` 复用当前返回契约及安全过滤，只通过依赖注入更换服务商。千问仅返回候选编号，API 用原候选生成卡片。
4. 用同一模型改写 4 条查询，检查两条日文漏检和两条已召回的对照。对两条日文查询补跑日语地区，并直接检查同一 SearXNG 的 Bing 原始候选。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| [check_official.py](../assets/official-qwen-check/check_official.py) | 新增 | 矩阵、超时复测和首页判定 |
| [check_qwen.py](../assets/official-qwen-check/check_qwen.py) | 新增 | 千问真实候选重排和无首页对照 |
| [check_rewrites.py](../assets/official-qwen-check/check_rewrites.py) | 新增 | 千问改写、Bing 原始候选及日语地区对照 |
| [验收数据](../assets/official-qwen-check/) | 新增 | 4 份 JSON，含来源、区段、位置和计时 |
| [台账](../INDEX.md) | 修改 | 登记验收结果 |

## 4 验证与证据

| 命令 | 结果 |
| --- | --- |
| `python reports/assets/official-qwen-check/check_official.py` | 退出码 0。Bing 24/24 HTTP 200，来源均为 Bing。免费聚合首轮 20/24 HTTP 200，4 次 HTTP 503 UPSTREAM_TIMEOUT，超时阈值 8 秒 |
| `python reports/assets/official-qwen-check/check_official.py --retry-timeouts` | 退出码 0。Apple、Mozilla、原神、UNESCO 重试 4/4 HTTP 200 |
| `python reports/assets/official-qwen-check/check_qwen.py` | 退出码 0。12 个真实样本和 1 个对照均为 HTTP 200。所有返回 URL 可追溯到输入候选 |
| `python reports/assets/official-qwen-check/check_rewrites.py` | 退出码 0。4 个查询改写均执行。两个真实漏检在原地区和日语地区均未找回首页 |
| `python -m pytest apps/api/tests/test_ai_search.py apps/api/tests/test_official.py -q` | 退出码 0，39 项通过 |
| `python -m pytest apps/api -q` | 退出码 0，447 项通过 |
| `git -c core.safecrlf=false diff --check` | 退出码 0，无空白错误 |

### 官网首屏

| 样本 | 日常 Bing | 隔离免费聚合，含超时重试 |
| --- | --- | --- |
| 目录内 12 个 | 12/12 进官方入口区。11 个为搜索命中，Telegram 为目录直达 | 12/12 进官方入口区，均有真实搜索候选 |
| 目录外 12 个 | 10/12 在普通首屏出现，9 个在相关，空客在弱相关。东京大学和日本气象厅缺首页 | 11/12 在普通首屏出现，2 个在强相关、8 个在相关、1 个在弱相关。日本气象厅仅见官网内页 |
| 合计 | 22/24 显示首页，其中 21 个来自搜索 | 首轮 19/24，补跑四次超时后 23/24 显示首页，均来自搜索 |

目录内样本为 Apple、微信、Docker、Telegram、React、Python、JetBrains、淘宝、哔哩哔哩、Mozilla、Stripe、Figma。两个引擎结果均有官方首页，实测目录入口在首位。

| 目录外样本 | 日常 Bing 首个首页 | 免费聚合首个首页 |
| --- | --- | --- |
| 原神 | 相关第 5 | 相关第 5 |
| 崩坏星穹铁道 | 相关第 5 | 相关第 5 |
| Godot | 相关第 5 | 相关第 2 |
| VLC | 相关第 8 | 相关第 5 |
| Krita | 相关第 7 | 相关第 4 |
| Modrinth | 相关第 3 | 相关第 1 |
| UNESCO | 相关第 5 | 相关第 7 |
| 东京大学 | 缺首页 | 强相关第 3 |
| Smithsonian Institution | 相关第 1 | 强相关第 1 |
| 日本气象厅 | 缺首页 | 缺首页，有官网内页 |
| IKEA | 相关第 6 | 相关第 1 |
| 空中客车 | 弱相关第 1 | 弱相关第 3 |

证据为 [首轮](../assets/official-qwen-check/official-matrix.json) 和 [超时复测](../assets/official-qwen-check/official-retries.json)。编号在各自分区内计数。核对入口可参考 [原神](https://ys.mihoyo.com/main/)、[星穹铁道](https://sr.mihoyo.com/)、[Godot](https://godotengine.org/)、[VLC 中文入口](https://images.videolan.org/vlc/index.zh_CN.html)、[Krita](https://krita.org/en/)、[Modrinth](https://modrinth.com/)、[UNESCO](https://www.unesco.org/en)、[东京大学](https://www.u-tokyo.ac.jp/ja/index.html)、[Smithsonian](https://www.si.edu/about)、[日本气象厅](https://www.jma.go.jp/jma/index.html)、[IKEA](https://www.ikea.com/)、[空客中文首页](https://www.airbus.com/zh-hans)。原神的备用首页结合[页面身份](https://www.yuanshen.com/)和[证书记录](https://radar.cloudflare.com/domains/domain/yuanshen.com)复核。

### 千问

- 12 条导航查询中，11 条的候选集包含核验首页。用同一候选集对比，首页排第一由 3/12 到 11/12。Godot 从第 6 到第 1，VLC 从第 7 到第 1，Krita 从第 6 到第 1。
- 12 次真实样本模型请求中位数 6.55 秒，范围 5.23–9.73 秒。计时为本机 Ollama 请求，网页召回耗时另计。候选最多 16 条，输出最多 3 条。
- 日本气象厅只有官网内页可选。千问还选过身份未核验的 Krita 相关域名。去掉 Modrinth 官网首页的对照中，模型略过了合成的指令注入候选，仍返回 YouTube 频道。
- 东京大学和日本气象厅的首页在抽查的原始 Bing 各 10 条里均缺失。千问改写并加日语地区仍未找回两者。对照中 VLC 继续有本地化入口，空客从中文入口变为全球入口。
- 证据为 [千问返回与模型计时](../assets/official-qwen-check/qwen-results.json) 和 [改写与日语地区](../assets/official-qwen-check/rewrite-results.json)。基线位置来自过滤后的同一批候选，包含目录内真实搜索条目，排除目录直达及已标注的品牌身份警示。

## 5 关键决策

- 评估首页召回使用已核验的目标地址。不同语言的正式首页与可核验替代入口均计入，官方内页单独记录。
- 试验采用 SearXNG 取网页、千问选候选编号的链路。模型响应由 JSON schema 和候选集合共同约束。当前日常 AI 服务商为 DeepSeek。
- 直接接本机 Ollama chat 实测，网页候选由现有搜索源提供。Ollama 自带的网络搜索也是另行调用的联网 API。[Ollama chat](https://docs.ollama.com/api/chat) · [Ollama 网页搜索](https://docs.ollama.com/capabilities/web-search)

## 6 遗留与风险

- 当前官网目录有 48 个品牌。24 条是本次分层抽样，结果会随地区、查询写法和上游索引变化。
- 千问在本机可承担排序和查询改写。实际身份认证仍需已核验目录。普通问答型检索、并发下模型延迟、缓存策略及浏览器侧栏接入留待产品化验证。
- 免费聚合首轮四次超时会影响首页的实际到达率。日本气象厅是可复现的首页缺口。

## 7 交接

后续接入可先把千问作为可选服务商，用免费聚合提供候选，千问重排并保留既有官网认证。若需要直接修复已发现缺口，可优先核验日本气象厅入口及日语别名。复跑命令与数据均在 §4。

