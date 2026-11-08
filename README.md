# CleanSearch · 干净搜索聚合器

聚合多引擎检索 + 零广告结果页 + 三档相关性分组 + 侧栏 AI 总结 + 书签启动台。
本机单用户主线已交付：搜索、书签、正文增强、缓存、一键添加、千问/DeepSeek 总结，以及 Serper 真实兜底、RDAP 首轮校准和 Compose 持久化均有验收证据。GitHub 托管 CI 已覆盖本轮修复，正式浏览器/Android 与更广样本仍需验收。[当前进展与待办](docs/进展与欠账.md) · [完工台账](reports/INDEX.md)

[![CI](https://github.com/jiangyangmuse/cleansearch/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jiangyangmuse/cleansearch/actions/workflows/ci.yml) · [贡献者与 AI 协作](CONTRIBUTORS.md)

## M0 做了什么

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 同源前后端 | React + TS + Vite（`apps/web`）+ FastAPI（`apps/api`），发布时 FastAPI 托管 `dist` | ✅ |
| `POST /api/search` | JSON 请求体、结果归一化、URL 去重、契约字段齐全 | ✅ |
| 最小结果列表 | 标题 / 域名面包屑 / 摘要 / 引擎标签 / 序号，原站新标签打开 | ✅ |
| 三态可区分 | 有结果 `status=ok`、零结果 `status=empty`、上游不可用 `503 + error.code` | ✅ |
| 本机启动命令 | `scripts/serve.ps1`（发布形态）、`scripts/dev.ps1`（开发形态）、`scripts/smoke.ps1`（冒烟） | ✅ |
| 固定样本 | `apps/api/fixtures/searxng_hit.json` 等，无 Docker 也能稳定验收 | ✅ |
| 自动测试 | `apps/api/tests` 覆盖三态、去重、契约、同源托管、上游响应结构、外链白名单和 Compose 端口 | ✅ |

M1 增加了后缀路由、去重、打分与三档分组、已知恶意链接拦截。M2 增加了带引用的 AI 侧栏。

已知恶意链接由本地黑名单拦截。已支持刷新 OpenPhish 类无 key feed，可疑结果经签名 `/go` 确认。GSB / URLhaus 待接入。

### 上游响应与 URL 护栏（验收后收紧）

- SearXNG 响应必须是 JSON 对象且带 `results` 列表：缺失或类型错误一律 `UPSTREAM_BAD_RESPONSE`，既不静默当成零结果，也不会冒成 HTTP 500。
- `results` 非空但没有任何一条能解析出标题 + 合法链接时，同样判坏响应。
- 结果 URL 只放行具有明确主机和合法端口的 `http`/`https`，长度 ≤ 2048。含内嵌凭证、反斜杠、控制字符或百分号编码主机的链接在结果归一化时丢弃，前端渲染前再校验。
- Compose 的 SearXNG 端口只绑回环：`127.0.0.1:8888:8080`（limiter 已关，不能对外暴露）。


## M1 做了什么（当前）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 后缀 / bang 路由 | `apps/api/app/core/query_parser.py`；`数分知识点 g` → Google，`python !b` → Bing，`天气预报 zh` → 地区 cn | ✅ |
| 解析护栏 | 单字母前导（`C g`、`x b`）、引号内、未闭合引号、非末尾短码一律保持普通查询 | ✅ |
| URL 去重加强 | canonical URL + 64 位标题 simhash（汉明距离 ≤ 3），合并引擎列表 | ✅ |
| 已知恶意链接拦截 | `apps/api/app/core/safety.py` + `fixtures/blocklist.txt`，先拦截并计入 `meta.filtered.risk`，再去重和打分 | ✅ |
| 启发式风险分 | 可疑 TLD / IP 直连 / 深层子域 / 长随机串 / IDN / 形近字符；0.35 起标记「可疑」 | ✅ |
| 打分与三档分组 | 词法（BM25 饱和 + 查询词覆盖率）、引擎共识、权威域名、时效，负向扣风险与营销特征 | ✅ |
| 前端三档渲染 | 强相关 / 相关默认展开，弱相关折叠；可疑卡片带角标与悬停理由；元信息展示路由与拦截数 | ✅ |
| 查询回归集 | `apps/api/tests/regression/m1_queries.json`，40 条查询断言解析结果 | ✅ |

M1 不做：向量语义分（需 bge-m3）、LLM 复核重排（M2 前置）、三源实时黑名单 feed 与 `/go` 中转（M4）、域名年龄（RDAP）。

### 打分口径（M1 标定）

`score = 0.50·词法 + 0.25·共识 + 0.15·权威 + 0.10·时效 − 0.15·风险 − 0.10·营销`

- 词法 = 0.5 × BM25 饱和值 + 0.5 × 查询词覆盖率（中英文都按二元组/词切分）；
- 共识：1 个引擎 0.4，2 个 0.8，≥3 个 1.0；
- 强相关 ≥ 0.55，相关 ≥ 0.30，弱相关 < 0.30；强相关允许为空，弱相关最多 5 条；
- 分数是**绝对分**，不做 minmax 归一，所以全是垃圾的查询不会凭空出现 0.9 的「强相关」。

### 黑名单

`BLOCKLIST_PATH` 默认指向 `apps/api/fixtures/blocklist.txt`（仓库内的演示规则：`evil-phish.test` 等）。
接真实数据时把该变量指向 URLhaus / OpenPhish 的导出文件即可，文件按 mtime 热加载，无需重启。


## M2 做了什么（当前）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 搜索快照 | `apps/api/app/core/session_store.py`：按 `sid` 存本次通过过滤与分档的结果源，TTL 900s、容量 64，LRU 淘汰 | ✅ |
| SSE 总结端点 | `GET /api/summarize?sid=&mode=fast`，事件 `meta → cite×N → token×M → done`，失败发 `error` | ✅ |
| 引用绑定 | `cite` 事件带 `i` 与稳定的 `result_id`；前端只渲染 cite 里出现过的编号 | ✅ |
| 侧栏 UI | 右侧 sticky 面板：生成 / 停止 / 重新生成，流式正文，点击 `[n]` 滚动并高亮对应卡片 | ✅ |
| 切换查询取消旧流 | 面板按 `sid` 重新挂载 + `AbortController`，上一轮文本不会接到新查询 | ✅ |
| 模型降级 | LLM 超时 / 不可达 → `error` 事件，保留已发引用与正文，结果列表照常可用 | ✅ |
| 离线可验收 | 未配 `LLM_BASE_URL` 时走本地抽取式桩 `stub-extractive`，结构与提示词一致 | ✅ |

M2 不做：`mode=full`（正文抓取，M4）、多轮对话、总结落库缓存、移动端抽屉（M7 打磨）。

### 接口

```
GET /api/summarize?sid=s_9f3a&mode=fast
Accept: text/event-stream

event: meta   data: {"model":"stub-extractive","sources":10,"mode":"fast","sid":"s_9f3a","query":"python 文档"}
event: cite   data: {"i":1,"result_id":"r_1","title":"...","url":"https://...","domain":"fastapi.tiangolo.com"}
event: token  data: {"t":"围绕「python 文档」，"}
event: done   data: {"ms":5763,"tokens":161,"partial":false}
event: error  data: {"code":"LLM_TIMEOUT","message":"等待模型响应超时（1 秒）","retryable":true}
```

- `sid` 不存在或过期 → `404 SESSION_NOT_FOUND`（`retryable=false`）；
- 零结果不落快照，直接 404；
- `mode` 接受 `fast`（使用搜索摘要）和 `full`（尽量补抓正文），其它值返回 `400 MODE_UNSUPPORTED`。
- `GET /api/health` 提供 `llm_provider` / `llm_model`。桩与真实模型都必须输出正文、有效引用并以 `done` 结束，冒烟才会通过。

### 接真实模型

本机 Ollama 已启动时，先用 `ollama list` 查到已安装的模型名，再启动应用。以下命令使用固定搜索样本和真实模型，打开首页后点「有结果」和「生成总结」。

```powershell
ollama list
.\scripts\serve.ps1 -Provider fixture -OllamaModel 'qwen3.5-4b-local:latest'
```

`-OllamaModel` 连接本机 `127.0.0.1:11434/v1`，默认发送 `reasoning_effort=none`，减少等待正文的时间。可在环境变量或 `.env` 里设置 `LLM_REASONING_EFFORT` 覆盖。`LLM_TIMEOUT` 限制等待首段可见正文的时间，随后也用于读取超时，默认 30 秒。

#### 使用 DeepSeek 云端总结

将 API 密钥单独存为工作区内的 `data/deepseek-api-key.txt`，一行即可。该目录已被 Git 忽略。启动后在首页点击「有结果」，再点击「生成总结」。

```powershell
.\scripts\serve.ps1 -Provider fixture -DeepSeek
```

正式检索时把 `fixture` 改为 `searxng`。`-DeepSeek` 连接官方端点，使用 `deepseek-flash` 并关闭推理模式。启用后，发起总结时会把查询与所用的摘要或正文发送给 DeepSeek。需要本机总结时，使用上面的 `-OllamaModel` 命令。[DeepSeek API 文档](https://api-docs.deepseek.com/quick_start/agent_integrations/)

总结遇到认证失败或余额不足时分别返回 `LLM_AUTH_FAILED` 或 `LLM_INSUFFICIENT_BALANCE`。修正配置或余额后重新生成。[DeepSeek 错误码](https://api-docs.deepseek.com/zh-cn/quick_start/error_codes/)

真实 SearXNG 已用 Google CSE 和 Yahoo 对三个公开技术主题验收 `fast` 与 `full`。正文抓取失败时保留搜索摘要并提示降级。[实测结果](docs/进展与欠账.md)

通用 OpenAI 兼容端点也可以直接通过环境变量配置。`LLM_REASONING_EFFORT` 留空时由端点决定。

```dotenv
LLM_BASE_URL=http://127.0.0.1:11434/v1   # Ollama 的 OpenAI 兼容端点
LLM_MODEL=qwen3.5-4b-local:latest
LLM_REASONING_EFFORT=none
LLM_TIMEOUT=30
```

配了 `LLM_BASE_URL` 就走真实模型（`LLM_PROVIDER` 可显式覆盖为 `openai`）；不配则用桩。
提示词在 `apps/api/app/prompts/`，与构建方案 §9.1/§9.2 一致。


## M3 做了什么（当前）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 书签存储 | `apps/api/app/db/`（SQLite WAL + FTS5，FTS5 缺失时自动降级 LIKE） | ✅ |
| 一键收藏 | 结果卡「收藏」按钮，写 `POST /api/bookmarks`，同 URL 不重复 | ✅ |
| 启动台页面 | `/bookmarks`：分组标签、标题与网址子串搜索、分页网格、添加、移组、删除、新建分组 | ✅ |
| 浏览器导入 | `POST /api/bookmarks/import`（Netscape HTML，20MB 上限） | ✅ |
| 浏览器导出 | `GET /api/bookmarks/export`（保留嵌套目录，未分组项保留在根目录） | ✅ |
| 往返一致 | 导入 → 导出 → 再导入后，URL / 标题 / 分组三者不变 | ✅ |

M3 不做：死链检测（M4）、标签 UI、拖拽排序、数字键快捷启动、Chrome 扩展与 bookmarklet（M8）。

### 重复规则（明确写死）

| 场景 | 行为 |
| --- | --- |
| 手动收藏已存在的 URL | 不新增；只补空标题、补备注、按传入的 `group_id` 改分组，返回 `deduplicated=true` |
| 导入时遇到已存在的 URL | **纯跳过**，不覆盖已有标题与分组（用户手动整理的结果优先） |
| 导入时同一文件内重复 | 第一条创建，后续跳过 |
| 分组 | 按需创建，只给真正新增的条目建，不留空分组 |

### 接口

```
GET    /api/bookmarks?q=&group=      -> { items, groups, total, fts }
POST   /api/bookmarks                -> 201 { item, deduplicated:false } / 200 { item, deduplicated:true }
PATCH  /api/bookmarks/{id}           { title?, group_id?, note?, dead? } -> 更新后的书签
DELETE /api/bookmarks/{id}           -> 204
GET    /api/groups                   -> [{ id, name, count }]
POST   /api/groups                   -> 201 { id, name }
POST   /api/bookmarks/import         multipart: file=<Netscape HTML>
GET    /api/bookmarks/export         text/html; attachment
```

本机启动时数据落在 `data/cs.db`（`DB_PATH` 可改）。移组时传 `group_id: null` 可移回「未分组」，省略该字段则保留原分组。导入导出采用 Chrome / Edge / Firefox 使用的 Netscape 书签 HTML 格式。


## M4 做了什么（当前）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 受控抓取入口 | `apps/api/app/core/fetch.py`：只连接已校验地址，逐跳复检重定向目标，总时限 2.5s、正文上限 2MB | ✅ |
| 正文提取 | `apps/api/app/core/extract.py`：trafilatura（装了就用）→ 标准库 HTMLParser 回退；过滤脚本/导航/面包屑 | ✅ |
| 正文增强 | `GET /api/summarize?mode=full` 并发抓前 5 条。`SUMMARY_FETCH_TIMEOUT` 单独控制每条抓取预算，默认 4 秒。失败保留摘要并标 `failed`/`degraded` | ✅ |
| 单页总结 | `POST /api/page/summarize` + `/s?u=<url>` 页面：一句话结论 / 要点 / 分歧 | ✅ |
| 死链检测 | `POST /api/bookmarks/check`：并发 5，只检查当前页所选书签，404/410 标记为「失效」 | ✅ |
| 侧栏交互 | 摘要完成后可增强，页脚显示抓取、降级和截断条数，引用标出素材来源 | ✅ |

M4 不做：三源实时黑名单 feed 与 `/go` 中转（需 API key，见方案 M4 安全部分）、Playwright 渲染兜底、r.jina.ai 兜底、总结结果落库缓存。

### 抓取护栏（M4 核心）

- 协议只放行 `http`/`https`；`file:`、`javascript:`、`data:`、无协议相对地址一律拒绝。
- 主机名黑名单：`localhost`、`*.local`、`metadata*`；IP 字面量直接判内网。
- 检查域名解析出的全部地址，并把连接固定到已通过检查的 IP。HTTP Host 和 TLS 证书校验仍使用原域名。
- 每次重定向都重新做上述校验，最多 3 跳。
- DNS、重定向和下载共用 2.5s 时限。正文只接收未压缩的白名单内容类型，超过 2MB 时截断并标记。死链检测只读取响应状态。

> 本机网络经透明代理把公网域名解析到 `198.18.x.x`（bench 网段），默认会被判为非公网。
> 本机可显式设置 `FETCH_EXTRA_CIDRS=198.18.0.0/15`。该例外仅用于此网段的 DNS 解析结果。默认配置拒绝这类地址。

抓取解析按系统已配置的地址族查询，并复查返回的每个地址。在未配置 IPv6 的容器里，会使用已配置的 IPv4 网络。

### 接口

```
GET  /api/summarize?sid=&mode=fast|full    meta 提供 fetched / failed / truncated / degraded，cite 提供 material
POST /api/page/summarize  {"url": "https://..."}
     -> { url, final_url, title, byline, published, word_count, read_minutes,
          content_hash, extractor, truncated, summary{one_liner,bullets,key_data,caveats},
          summary_text, model }
     403 非公网 / 502 上游失败 / 504 超时 / 422 正文过短
POST /api/bookmarks/check  {"ids"?: [...], "limit"?: 20}
     -> { checked, dead, unknown, items:[{id,url,dead,status,detail}] }
```


## 打磨轮（M7）：缓存、快捷键、暗色、移动端

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 搜索缓存 | `apps/api/app/db/cache.py`，按 `qkey` 存 15 分钟，命中时元信息标「缓存」 | ✅ |
| 单页总结缓存 | 按正文与模型输入复用生成文本，页面信息取本次抓取结果 | ✅ |
| 键盘快捷键 | `/` 聚焦、`j`/`k` 选择、`Enter` 打开、`b` 收藏、`s` 总结、`Esc` 取消、`g s` 回搜索页 | ✅ |
| 暗色主题 | 自动 / 浅色 / 深色三态，`localStorage` 持久化，`data-theme` 驱动 | ✅ |
| 移动端侧栏抽屉 | <1080px 变成底部抽屉（62vh），右下角「AI 总结」开关 | ✅ |
| 错误态收敛 | 断网 / 超时 / 引擎全挂都落到统一 `ErrorState`，带重试与错误码 | ✅ |

### 缓存语义

- 搜索缓存按检索后端、查询参数和当前黑名单版本隔离。上游部分失败的结果不写入缓存；命中时 `meta.cached=true`。
- 快照：命中后按新的 `sid` 重新登记，侧栏总结照常可用；
- 单页总结仍会抓取页面。正文、最终地址、标题、长度上限和模型配置相同时复用生成文本，返回 `cached=true`。
- `CACHE_ENABLED=false` 可关闭缓存；`CACHE_TTL` 控制搜索缓存时效（默认 900 秒）。两张缓存表各保留 `CACHE_MAX_ENTRIES` 条最新写入记录（默认 512）。

### 快捷键一览

```
/      聚焦搜索框
j / k  上下选择结果（弱相关折叠时不参与）
Enter  新标签打开选中结果
b      收藏选中结果
s      生成/重新生成侧栏总结（窄屏同时展开抽屉）
Esc    取消选中、收起抽屉
g s    回搜索页
```


## 一键添加：bookmarklet / 扩展 / PWA

| 通道 | 落点 | 用法 |
| --- | --- | --- |
| Bookmarklet | `GET /api/tools/bookmarklet` + `/tools` 页面 | 把链接拖到书签栏；浏览器拦截直连时，可打开本机书签页确认 |
| Chrome / Edge 扩展 | `apps/extension/`（MV3） | `chrome://extensions` → 开发者模式 → 加载已解压的扩展，填 API 与 token |
| PWA 分享 | `apps/web/public/manifest.webmanifest` 的 `share_target` | 支持的设备安装后可分享 `url` 或含链接的 `text`，在书签页预填并确认 |

### 验证扩展（真实浏览器）

```powershell
# 首次：安装可选依赖与浏览器（仓库默认不带）
npm --prefix apps/web install
npm --prefix apps/web exec playwright install chromium

# 起一个隔离实例，再跑验收脚本（会打开可见 Chromium 加载未打包扩展）
node scripts/verify-extension.cjs http://127.0.0.1:8000
```

脚本会：加载 `apps/extension` → 打开 popup 填 token → 收藏 `docs.python.org` → 调后台保存函数 → 用 CDP 读 PWA 清单与安装性错误。
截图与 `installability.json` 写到 `docs/m9-evidence/`。

### 跨域写入与 token

bookmarklet 和扩展都在「别人的页面」里发起请求，无法用 Origin 白名单，因此统一走 token：

- token 文件：`data/api-token.txt`（`API_TOKEN_PATH` 可改），首次访问 `/api/tools/bookmarklet` 自动生成；
- 服务仅接受 `127.0.0.1`、`localhost`、`[::1]` 的 Host；Compose 的 token 和书签数据库同在 `/data` 卷。
- 跨域只允许带 `X-CS-Token` 的 `POST /api/bookmarks`，只接受 `url` 和 `title`，只返回 `deduplicated`。其余跨域请求返回 `403 CORS_FORBIDDEN`；缺少或无效 token 返回 `401 TOKEN_REQUIRED`。
- 同源书签页照常浏览、修改和删除；跨域预检只允许对添加接口发 POST。

> token 等于「谁能往你书签里写东西」，不要贴到公开地方；泄露后删掉 `data/api-token.txt` 即轮换。

### PWA 安装

安装和系统分享依赖浏览器支持。默认服务仅监听本机，安装设备须能访问对应地址；同一网络里的手机无法通过自己的 `localhost` 访问电脑上的服务。预填后须手动收藏。应用依赖在线服务。


## 真实上游、熔断与中转（本轮）

| 交付项 | 落点 | 状态 |
| --- | --- | --- |
| 真实 SearXNG 跑通 | `D:\agent\build\searxng`（源码 + venv + Windows shim），详情见下 | ✅ 本机实测 |
| 引擎健康与熔断 | `apps/api/app/core/breaker.py`，`engine_health` 表，实例级 + 引擎级分离 | ✅ |
| 黑名单 feed 刷新 | `apps/api/app/core/feeds.py` + `POST /api/tools/refresh-feeds` | ✅（无 key 源） |
| `/go` 风险中转 | `apps/api/app/routers/go.py`，HMAC 签名，可疑结果带 `go_url` | ✅ |
| 查询扩展（词典版） | `apps/api/app/core/expand.py`，别名词半权计入词法 | ✅ |
| 书签标签 | `bookmark_tags` + `/api/bookmarks?tag=` + 启动台标签条 | ✅ |
| 搜索分页 | 结果页「上一页 / 下一页」，空页可返回 | ✅ |
| `/tools` 入口 | 头部导航「一键添加」 | ✅ |
| Git 与 CI | 已有首个本地提交。`.github/workflows/ci.yml` 依次运行测试、构建和完整离线冒烟 | 远端执行待验 |


### 引擎后缀（2026-11-08 复测）

| 后缀 | 引擎 | 本机可用性 | 说明 |
| --- | --- | --- | --- |
| `b` | bing | ✅ 10 条 | SearXNG 必须用 `cn.bing.com`；www 会 302 且引擎默认不跟随 |
| `d` / `ddg` | duckduckgo | ✅ 10 条 | 间歇 CAPTCHA 时回退 `duckduckgo web` |
| `dw` | duckduckgo web | ✅ 10 条 | DuckDuckGo 备用入口 |
| `y` | yahoo | ✅ 7 条 | |
| `mj` | mojeek | ✅ 10 条 | 默认 `inactive: true`，配置里已显式 `inactive: false` |
| `gc` | google cse | ✅ 10–20 条 | 偶发超时；超时 8s，作为 `g` 的首选回退 |
| `g` | google | ⚠️ 403 → `google cse` | 网页端 access denied；回退 CSE，再按配置走 Serper |
| `w` | wikipedia | ✅ 常见词条 | 已补 `display_type: [infobox, list]`；冷门多词查询可能零结果 |
| `n` | naver | ✅ 14–19 条 | |
| `yd` | yandex | ✅ 10–15 条 | |
| `sw` | swisscows | ✅ 9–20 条 | 需 `inactive: false` |
| `so` | 360search | ✅ 4–6 条 | `sg` 的回退目标 |
| `sg` | sogou | ⚠️ SearXNG 侧 crash → `360search` | 失败自动换 360 |
| `sp` | startpage | ⚠️ PoW CAPTCHA → `mojeek` | 失败自动换 Mojeek |
| `sc` | google scholar | ⚠️ access denied → Serper | 配置 `SERPER_API_KEY` 时走 `/scholar` |
| `br` | brave | ⚠️ 限流 | 配置 `BRAVE_API_KEY` 后走官方接口 |
| `yt` / `gh` / `ar` | youtube / github / arxiv | ✅ 10–30 条 | 垂直引擎，显式后缀使用 |

`google`、`google scholar`、`brave`、`startpage` 在 SearXNG 里保持禁用，避免拖慢默认聚合；显式后缀由应用层回退链接管。`/api/engines` 会返回每个后缀的最近状态、平均延迟与错误；前端首页的引擎按钮直接读它。

M19 复核补充：目录的 `status` / `available` 表示主源健康；`can_fallback` 表示首屏还有回退来源可尝试，`selectable` 表示当前至少有一路未冷却。未知状态不保证在线。主源冷却但有回退时按钮仍可用，搜索结束后刷新目录；切换引擎只替换一个可解析的末尾短码，兼容 `!g`，保留 `C g` 等普通查询正文。前端查询回归：`node --test scripts/engine-query.test.cjs`，已纳入托管 CI 配置。

`scripts/probe-engines.py` 的 `ok` / `count` 只统计来源包含指定引擎的结果，`raw_count` 保留原始条数；避免未启用引擎被静默回落默认聚合时误判可用。旧矩阵中 Startpage、Marginalia、Dogpile、Yandex API 的成功计数存在这种误判，旧文件保留，见 M19 报告 §8 更正。

### 真实验收结果（2026-11-07）

```
verify-searxng.py --engines gc y        -> 9/9 PASS（exit 0，无缓存）
    gc: 655 / 591 / 674 ms，10–13 条
    y : 1250 / 1227 / 1312 ms，6–7 条
    含 bang（!gc）、地区（jp）、护栏（C g）

measure-search-quality.py（默认多引擎，8 次）
    8/8 有结果，中位 1736 ms，最大 2623 ms，来源 google cse + yahoo
    每次都有 brave/ddg/sogou 失败（CAPTCHA / 限流 / crash）

冷热缓存（同一查询连打两次）
    asyncio 事件循环 原理: 2783 ms -> 28 ms（cached=True）
    SearXNG 元搜索 配置 : 2227 ms -> 5 ms（cached=True）

真实搜索接本机千问（qwen3.5-4b-local，reasoning=none）
    搜索 2810 ms / 17 条 / 3 引擎
    总结首字 7672 ms，总 18329 ms，176 段，10 条引用全部绑定，done.partial=false
```


### Docker Compose 验收（2026-11-08）

前提：Docker Desktop 4.98（Store/per-user 安装）。若 `docker` 不在 PATH：
`C:\Users\<你>\AppData\Local\Programs\DockerDesktop\resources\bin`（本机为 `C:\Users\HUAWEI\AppData\Local\Programs\DockerDesktop\resources\bin`）。

```powershell
cd D:\agent\llq
Copy-Item .env.example .env          # 首次
npm --prefix apps/web run build      # compose 会把 dist 挂到 /web
docker compose up -d --build
.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8000
```

实测结果：

| 项目 | 结果 |
| --- | --- |
| 镜像 | `llq-api` 242MB 构建成功；`searxng/searxng:latest` 387MB |
| 端口 | 两端点均只绑 `127.0.0.1`（8000 / 8888） |
| 固定样本 | `provider=fixture`、`web_dist=/web`，冒烟 **16/16** |
| 数据持久化 | 写入书签 → `docker compose down` → `up` → 书签与 token 均在（卷 `llq_bookmarks`） |
| 真实上游 | 切 `SEARCH_PROVIDER=searxng` 后 `provider=searxng`、上游 `http://searxng:8080`；`--engines y gc` **9/9** |
| 前端 | 容器同源页面渲染正常，10 张卡片，无 JS 错误 |

注意：容器里的 SearXNG 引擎可用性与宿主机原生实例不同——本机容器内 `duckduckgo` 可用、`google cse` 偶发超时；宿主机原生实例反之。
仓库的 `searxng/settings.yml` 已显式启用 `bing/yahoo/sogou`，保证 `compose up` 后引擎集一致。


### 容器接宿主机模型 / feed 刷新（2026-11-08 实测）

```dotenv
# .env
LLM_PROVIDER=openai
LLM_MODEL=qwen3.5-4b-local:latest
LLM_TIMEOUT=120
LLM_REASONING_EFFORT=none
COMPOSE_LLM_BASE_URL=http://host.docker.internal:11434/v1
FEED_URLS=https://openphish.com/feed.txt
FETCH_EXTRA_CIDRS=198.18.0.0/15   # 仅当容器 DNS 把公网解析到代理网段时需要
```

改完必须 `docker compose up -d --build api`（代码烤进镜像，只 `--force-recreate` 不会生效）。

实测：

| 项目 | 结果 |
| --- | --- |
| fast 总结（容器搜索 + 宿主机千问） | 首字 6.8–10.9s，总 13.4–23.0s，引用全部绑定 |
| full 总结 | 首字 5.1–7.8s，抓取 2/5 与 0/5，均 `partial=true`（真实站点 403/超时） |
| feed 刷新 | OpenPhish 298 条 → `blocklist_rules` 3→301，样本 URL 命中黑名单 |
| 扩展（Edge 157） | 12 项全过；Chrome 156 已移除 `--load-extension`，需手动加载 |

> `mode=full` 的抓取失败是设计内降级：正文不可用时保留搜索摘要并标 `partial`，不是错误。


## P2：检索与正文质量（2026-11-07 首版验收）

### 词典扩展评估（18 条标注查询，真实上游）

同一批候选集下三种条件对比（只统计 12 条命中扩展词典的查询）：

| 条件 | Top10 命中 | 强相关命中 | 首个命中平均位次 |
| --- | --- | --- | --- |
| baseline（不扩展） | 6/12 | 1/12 | 1.33 |
| rank（只影响排序，默认） | 8/12 | 1/12 | 3.62 |
| rewrite（别名并入上游查询） | **9/12** | **2/12** | 3.67 |

脚本：`python scripts/eval-expansion.py --base-url http://127.0.0.1:8000 --json-out docs/m10-evidence/p2-expansion.json`

结论：`rewrite` 提召回但多一次上游请求、平均位次略降；默认仍是 `rank`，需要召回时设 `EXPANSION_MODE=rewrite`（`off` 可完全关闭）。

### 正文提取：trafilatura vs 标准库

| 页面 | trafilatura | 标准库 | 说明 |
| --- | --- | --- | --- |
| docs.python.org/3/library/asyncio.html | 2174 字 | 2236 字 | 两者接近，trafilatura 去掉了页头 |
| developer.mozilla.org/zh-CN/docs/Web/HTTP | 1698 字 | 1487 字 | trafilatura 去掉了「社区翻译」横幅 |
| web.telegram.org/k/（纯 JS） | 0 字 | 0 字 | 都提取不到，接口按设计返回 422 |

容器镜像已装可选依赖（`pip install ".[content]"`），响应里 `extractor=trafilatura`；没装的环境自动回退标准库。

### 单页总结增强

- 单页总结有 10 秒抓取预算。侧栏全文模式默认 4 秒，可用 `SUMMARY_FETCH_TIMEOUT` 设置大于 0 且不超过 10 秒的预算。普通抓取仍由 `FETCH_TIMEOUT` 控制。
- `key_data`：从**原文**抽「数字 + 单位」（%、秒、倍、MB…），最多 8 条，避免模型编数字。
- `anchors`：原文段落序号 + 首句（最多 5 条），用于人工回原文定位；不是 DOM 锚点。

实测：MDN 缓存页 → `extractor=trafilatura`、7396 字、`key_data=5`（如 `604800 秒`）、`anchors=5`；SPA 页面 → 422「正文过短或需要登录」。

### 技术路线取舍（首版评估与后续状态）

| 候选 | 结论 | 理由 |
| --- | --- | --- |
| 语义分（embedding） | 暂不引入 | 尚无向量服务与质量/延迟对照，先扩大词典扩展标注；9/12 是当前小样本结果 |
| LLM 重排 | 暂不引入首屏 | 已测千问总结首字 6.8–10.9s；重排自身的质量与延迟尚未测量，需独立评估 |
| 商用兜底（Brave/Serper） | **Serper 已接入并实测，Brave 待凭据** | 后续 18 条开关对照的期望域名 Top10 命中 6/18→11/18，延迟同步增加，详见下文 |


## P3：扩展体验与部署形态（2026-11-07 首版验收）

| 项 | 交付 | 验证 |
| --- | --- | --- |
| 搜索快照跨进程 | 从进程内存搬到 SQLite（表 `search_sessions`，TTL + 容量淘汰） | 进程 A 搜索 → 进程 B 总结，8 条引用正常 |
| 写入策略 | 主数据及缓存连接使用 `WAL + busy_timeout=5000 + synchronous=NORMAL`；RDAP 派生缓存采用独立短锁等待 | 已有多实例共用主库的验收记录；跨请求 RDAP 压测仍待补 |
| 大量导入进度 | `POST /api/bookmarks/import/jobs` + 轮询，按钮显示 `导入中 x/y` | 2000 条导入，2000/2000 完成 |
| 死链快照 | 新增 `dead_status` / `dead_checked_at`，徽标显示「失效 · 404」 | 真实 404 页面实测 |
| favicon 缓存 | `GET /api/favicon?host=`，只提供完整栅格图标，磁盘缓存 7 天 + 负缓存 1 小时 | 新抓取与旧磁盘缓存均拒绝 SVG，返回的图标带响应类型和沙盒护栏 |
| 拖拽分组 | 书签卡拖到分组 chip 即改分组 | Playwright 拖拽后 `group_id=1` |
| 移动抽屉手势 | 抽屉顶部下滑 >90px 关闭 | 390×844 触摸模拟通过 |
| 观测 | `/api/metrics` 提供分组计数、HTTP 错误率、p50/p95 与运行时间 | 流式请求在正文发送完成后计入，SSE `error` 仍按其 HTTP 响应状态统计 |

**未排期（可选范围）**：Tauri 桌面包、原站广告拦截（EasyList）。这两项需要各自的构建链与规则维护，先记录不实现。

> 多进程范围：搜索快照已落 SQLite，已有跨进程总结证据。指标仍是每进程独立的内存窗口；导入任务状态也在发起进程内存中，重启会丢失进度，多 worker 轮询可能找不到任务。需要多 worker 或重启续查时，应先持久化任务状态。


### 商用检索补充与故障兜底

在本地 `.env` 配置任一 key 后启用，真实搜索的第 1 页、未指定引擎时补一路结果。主上游连接失败、引擎全部失败或实例熔断时，也可由付费结果完成搜索。

```dotenv
BRAVE_API_KEY=        # Brave Search API
SERPER_API_KEY=       # Serper.dev（Google 结果）
PAID_FALLBACK=true    # 关掉可临时停用
```

固定样本和后续页不调用付费接口；指定引擎仅在第 1 页、主引擎与回退链全部失败后才调用对应接口（`g`/`gc` 走 Serper `/search`，`sc` 走 Serper `/scholar`，`br` 走 Brave API）。正常零结果直接返回空态，不回退、不计故障；付费源合法零结果也返回空态。实例故障中止同实例的免费尝试，并保留实例错误分类。来源进入 `meta.engines`，复用安全过滤、打分与 canonical URL 去重，重复结果保留两个来源。调用失败写入 `meta.unresponsive` 并单独计入该来源熔断，冷却中暂停付费请求。

契约测试：`python -m pytest apps/api/tests/test_paid.py -q`（用 MockTransport，不碰真实接口）。
Serper 真实接口和主上游故障兜底均已验证。18 条标注查询关闭/开启兜底的期望域名 Top10 命中为 6/18 与 11/18，P95 为 3.08 秒与 5.81 秒，两侧均关闭缓存。该指标衡量这批标注域名的可见性。[完整对照](reports/assets/serper-validation/labelled-comparison.json) · [Serper](https://serper.dev/)

复验时启动两个隔离实例，分别设置 `PAID_FALLBACK=false` 与 `true`、`CACHE_ENABLED=false`，然后执行下列命令。对照包含 18 条公开查询，开启侧每条查询会请求一次 Serper。

```powershell
python scripts/eval-expansion.py --base-url http://127.0.0.1:18140 --compare-base-url http://127.0.0.1:18141 --json-out reports/assets/serper-validation/labelled-comparison.json
```


### CI 本地执行（2026-11-08，act + Docker）

GitHub Actions 没有远端也能跑：用 `act` 在 Docker 里执行同一份 `.github/workflows/ci.yml`。

```powershell
winget install --id nektos.act -e
docker pull ghcr.io/catthehacker/ubuntu:act-latest   # Docker Hub 的 catthehacker 镜像会要求登录，用 ghcr
act -j verify -P ubuntu-24.04=ghcr.io/catthehacker/ubuntu:act-latest --container-architecture linux/amd64
```

实测结果：

```
✅ actions/checkout@v4
✅ actions/setup-python@v5 (3.12.16)
✅ actions/setup-node@v4 (22.23.4)
✅ Install  (pip install -e apps/api[dev] + npm ci)
✅ API tests  290 passed
✅ Build web  vite built in 809ms
✅ Smoke (fixture, no upstream network)  15 checks
🏁  Job succeeded
```

过程中修掉两个真问题：
1. 冒烟步骤原来用 `shell: pwsh`，在 Linux runner 上直接 `command not found` → 改成 bash + `scripts/ci-smoke.py`（跨平台，15 项检查）。
2. 等待服务就绪的内联 Python 写进 YAML 会破坏缩进 → 抽成 `scripts/ci-wait.py`。

> 历史说明：上述是本地 act 记录。GitHub 托管基线及本轮修复均已通过，具体提交与日志见下文。


### RDAP 域名年龄

启用 `RDAP_ENABLED=true` 后，已有风险信号的真实结果可补充注册年龄。系统使用包内 PSL 把子域名归一到注册域名，注册不足 30 天时增加 0.15 风险分。搜索卡片与确认页会显示年龄理由，确认页只读缓存。

每批最多 8 个注册域名，并发 4，整个批次含排队共用 4 秒预算。固定样本模式只使用已有年龄缓存。SQLite 缓存正常保留 30 天，404/410 或成功响应中未给注册时间时负缓存 1 天，最多保留 4,096 项。429、服务故障和超时可在后续查询重试。[RDAP 引导服务](https://about.rdap.org/)

本机透明代理的 bench 地址仍需显式配置 `FETCH_EXTRA_CIDRS`，网络访问继续执行地址校验与连接钉扎。

已校准公开 feed 的 20 个注册域名与 20 个参考域名。分别获得 18 和 19 个注册时间，不足 30 天的数量为 4 和 0，保留当前阈值及权重。对单批 8 个域名的受控负载复测，缓存耗时 21 ms，慢查询在 4,015 ms 结束。[校准数据](reports/assets/rdap-review/calibration.json) · [负载数据](reports/assets/rdap-review/load.json)

复验命令只访问公开 feed 和 RDAP 服务，样本在输出中使用去链接化的域名。

```powershell
python scripts/eval-rdap.py --db-path data/rdap-calibration-review.db --json-out reports/assets/rdap-review/calibration.json
```


## CI、浏览器与扩大样本复核（2026-11-07）

### CI 的当前边界

DSH [本地记录](reports/completed/2026-11-07-1631-remote-ci-chrome-android-samples.md)中的 bare/act 验证已由后续 GitHub 托管基线补齐。当前 origin 为 `git@github.com:jiangyangmuse/cleansearch.git`；M17 修复与浏览器判断器测试已通过本次 ci #3，结果按具体提交保留。

托管验收按具体提交 SHA 和运行链接记录：早期基线为 315 项，本次修复版本为 323 项，另有浏览器验收判断器测试；各次运行分别保留。

### 扩展与分享的浏览器级验收

本轮使用现有 Chrome for Testing 157 与桌面 Chromium 的 Pixel 7 档案。CfT 扩展 **10/10**、移动档案 **18/18** 通过，使用独立数据库、唯一 URL、精确标题/URL 核对及测试数据清理；JSON 记录实际浏览器版本和未验范围。

```powershell
# 先以独立 DB_PATH 起 fixture 服务；不要使用正式书签库。
$env:CS_CHROME_PATH='<本机已有 Chrome for Testing 的 chrome.exe 完整路径>'
$env:CS_HEADLESS='true'
node scripts/verify-extension.cjs http://127.0.0.1:18160 reports/assets/next-action-review/browser
node scripts/verify-android.cjs http://127.0.0.1:18160 reports/assets/next-action-review/browser
```

覆盖三类分享输入（url、纯 text URL、说明文字内 URL）、参数清除、危险 URL 拒绝、触屏新建、清单解析与安装性错误检查。manifest 已显式设置 `enctype`，解析无警告；安装性检查遇到错误会失败。[扩展证据](reports/assets/next-action-review/browser/extension.json) · [移动模拟证据](reports/assets/next-action-review/browser/android-emulation.json)

正式 Chrome 的开发者模式手动加载、原生书签管理器互迁、Android 真实安装与系统分享面板仍未验。后台保存函数通过也不等同实际点击系统右键菜单。CfT 继续支持加载开关的说明见 [Chrome 官方公告](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/1-g8EFx2BBY)；设备档案的范围见 [Playwright 模拟说明](https://playwright.dev/docs/emulation)。离线启动尚未实现，属于另行排期的能力。

### RDAP 对照与并发

DSH 新增 30 个正常参考域名中年龄可得 26 个、未知 4 个，已知年龄全部超过 365 天；最年轻仍为 1,437 天。它只补充了老站对照，不能用于估计新注册正常站点的误报率，未知不能记为“正常且非新站”。旧记录未保留可证明四个未知原因的状态码。

校准脚本现支持任意长度样本、出处 `provenance`、可选核验时间 `verified_at`、离线汇总及新站数量门槛。例如以下命令对旧 30 条记录会因不足 5 个有出处的新站返回非零，证据中标为未达标：

```powershell
python scripts/eval-rdap.py --aggregate docs/m10-evidence/p3-rdap-sample.json --require-fresh-references 5 --json-out reports/assets/next-action-review/rdap-controls.json
```

网络许可现在由同一应用 store/事件循环中的搜索共享，上限 4；缓存命中不等网络许可，整个批次含排队仍为 4 秒。受控三请求 × 每批八域名测得峰值 4、各批约 4 秒、结束时无在途请求；429 可重试。正常零风险条目也不会因同域其他条目触发年龄查询而被加分。跨 worker 全局限流及真实注册局 429 仍需观察，当前 30 天/0.15 策略保持。[并发数据](reports/assets/next-action-review/rdap-concurrency.json)

### 检索与总结样本的口径

- 40 条检索历史记录的全量 Top10 期望域名命中为 **20/40、20/40、23/40**（baseline/rank/rewrite），12 条扩展词子集为 **6/12、6/12、9/12**；另外 28 条为不改写对照。全量 MRR10 为 **0.3761、0.3629、0.4148**。脚本现同时保留三种分母、计入未命中，并记录新跑的请求失败；旧记录缺少的状态不会补写成成功。[离线重汇总](reports/assets/next-action-review/retrieval-40.json)
- 这些仍是返回候选集上的宽口径期望域名指标，不代表完整相关性或原始上游召回。单看命中时的平均位次会忽略未命中，不能单独判定 rewrite 更优。
- 新增 `scripts/eval-summary.py`，采集公开主题的 fast/full 正文、引用、模型、抓取/降级和耗时。自动验收要求完整 done、来源 ID/URL 绑定、有效编号引用和事件计数一致；事实正确性仍需人工核对。`--reassess` 可以离线重验已采集输出；首段耗时仅指总结请求，搜索耗时单独记录。
- 本轮千问六主题双模式 **12/12 结构通过**；fast/full 首段中位 **7.61/24.14 秒**、总耗时中位 **20.66/36.91 秒**，full 正文取得 **15/30**，六次均降级。三主题事实审读与相同材料提示词重放仍发现 Rust/HTTP2 表述需要改写；GIL 样本增加了版本未核实说明。输入已区分材料类型并补充限定语规则，这不是事实准确率修复证明。[完整输出](reports/assets/next-action-review/summary-12-reassessed.json) · [人工审读](reports/assets/next-action-review/manual-quality.md)


## GitHub 远端与托管 CI（2026-11-08）

[公开仓库](https://github.com/jiangyangmuse/cleansearch)已通过 SSH 接入；现有提交作者保持不变。独立核对 GitHub API、job 步骤及日志，托管基线已验收。

| 运行 | 提交 | 触发与结果 | 日本时间（JST） |
| --- | --- | --- | --- |
| [ci #1](https://github.com/jiangyangmuse/cleansearch/actions/runs/42393430557) | `479978e878a1d75732b696a6f5d28aa97bb744ab` | push main，success，33 秒 | 2026-11-08 01:51:59–01:52:32 |
| [ci #2](https://github.com/jiangyangmuse/cleansearch/actions/runs/42393578528) | `403253542059e6dcc5625f76e07a5ac78b6adab9` | push main，success，42 秒 | 2026-11-08 01:53:47–01:54:29 |
| [ci #3](https://github.com/jiangyangmuse/cleansearch/actions/runs/42395082507) | `43ea950930bc05076f2742597137e78e94db68cd` | push main，success，44 秒 | 2026-11-08 02:11:33–02:12:17 |

ci #3 的安装、API 测试、浏览器验收判断器负例、前端构建、fixture 冒烟及收尾步骤全部成功。日志确认 **323 passed in 8.13s**、Node 判断器 **1 test / pass 1 / fail 0**、**42 modules transformed**、跨平台冒烟 **15/15**。源码与证据已发布，核对见 [托管 CI 证据](reports/assets/hosted-ci-credit/hosted-ci.json)。

ci #1/#2 的 315 项记录是较早版本；本次 323 项修复由 ci #3 的 SHA 对应验证。后续仅更新验收文档时保留这一代码验收关联，不把文档提交误记为新的功能交付。

### 与本地验证的关系

本地 act 用于提前验证工作流；GitHub 托管执行补充真实 runner 与权限环境的证据。两次托管成功不代表所有服务凭据、矩阵构建或分支保护均已验收；本轮未根据单次耗时推断缓存命中或性能收益。

### 贡献署名

项目已记录 Codex 与 DeepSeek Harness（DSH）的实际 AI 协作贡献，见 [贡献者与 AI 协作](CONTRIBUTORS.md)。GitHub Contributors 自动统计依赖提交及关联账号；本文件记录工具署名，不伪造账号映射或改写历史作者。


## 收口与推送（2026-11-08）

工作区里并行执行体留下的 M19 引擎目录/回退、导航去重与评估工具已全部收口：

- 提交：`31764ad feat: engine catalog with fallback routes, navigation dedupe, eval tooling`
- 推送：`5af2daf..31764ad main -> main`
- Actions：工作流 badge 返回 `ci - passing`（https://github.com/jiangyangmuse/cleansearch/actions）

推送前的本地验证：

```
python -m pytest apps/api -q -o addopts=   362 passed
npm --prefix apps/web run build           42 modules
node --test scripts/engine-query.test.cjs  14 passed
node --test scripts/browser-check.test.cjs  1 passed
smoke.ps1（fixture）                        16/16
```

### 分支保护：需要你的 GitHub 凭据

GitHub 的分支保护只能通过 API/网页设置，SSH 推送权限不够。两种做法：

网页：Settings → Branches → Add branch protection rule → 分支填 `main` → 勾选 Require status checks to pass → 选 `verify`（本工作流的 job 名）。

命令行（需要先 `gh auth login`）：

```powershell
gh api --method PUT repos/jiangyangmuse/cleansearch/branches/main/protection `
  -F 'required_status_checks[strict]=true' `
  -F 'required_status_checks[contexts][]=verify' `
  -F 'enforce_admins=true' `
  -F 'required_pull_request_reviews=null' `
  -F 'restrictions=null'
```

### 匿名 API 限制

公开仓库的 Actions 状态可用 badge 读取，但 `/actions/runs` 这类 JSON API 匿名额度是 60 次/小时，本轮已被用尽；需要更细的 job 日志时请用 `gh run view`（带登录）。

### 本机跑真实 SearXNG（无 Docker 时）

```powershell
# 一次性准备（源码在仓库外，避免污染工程）
git clone --depth 1 https://github.com/searxng/searxng.git D:\agent\build\searxng
cd D:\agent\build\searxng
git restore --source=HEAD -- . ':(exclude)utils/templates'   # Windows 无法创建带 ":" 的文件名
python -m venv ..\searxenv
..\searxenv\Scripts\python.exe -m pip install -r requirements.txt

# Windows 兼容 shim（SearXNG 导入期需要 pwd 与 os.getuid）
# 见 D:\agent\build\shims\{pwd.py,sitecustomize.py}

$env:SEARXNG_SETTINGS_PATH='D:\agent\build\searxng-settings.yml'
$env:PYTHONPATH='D:\agent\build\shims;D:\agent\build\searxng'
..\searxenv\Scripts\python.exe -m searx.webapp
```

settings 关键项：`search.formats: [html, json]`、`server.limiter: false`、`bind_address: 127.0.0.1`。

### 本机实测（2026-11-06 23:4x）

只启用了一个能出结果的引擎（`google cse`），其余在生产环境也会遇到：

```
8/8 次成功，延迟中位 936 ms（最大 3303 ms），结果 10–15 条
失败引擎：brave(Suspended: too many requests) / duckduckgo(CAPTCHA) / wikidata(timeout)
```

这也直接验证了熔断的必要性：**引擎级全 CAPTCHA 不会被误判成实例故障**（`EnginesUnresponsive` 只记引擎级失败）。

### 熔断与 `/go` 的接口语义

- `ENGINE_UNAVAILABLE`（503）：显式指定的引擎处于冷却期，提示换引擎；
- `UPSTREAM_UNAVAILABLE`（503）：实例级熔断（连接失败 / 超时 / 坏响应累计 3 次），冷却 `BREAKER_COOLDOWN`；
- `meta.unresponsive`：本次哪些引擎没给结果（来自 SearXNG）；
- 可疑结果（0.35 ≤ risk < 0.6）多出 `go_url`，前端点击先进 `/go?u=&sig=` 确认页；签名错 → 403。

## 本机启动

### 0. 依赖

```powershell
python -m pip install -e "apps/api[dev]"
npm --prefix apps/web install
```

### 1. 没有 Docker 时：固定样本跑通闭环

```powershell
.\scripts\serve.ps1 -Provider fixture
# 打开 http://127.0.0.1:8000
```

固定样本模式下，首页提供有结果、零结果、上游不可用、恶意链接四个自检入口。也可输入 `test`、`__empty 任意词`、`__fail 任意词`、`__risky 任意词`。

### 2. 有 Docker 时：接真实 SearXNG

```powershell
Copy-Item .env.example .env
npm --prefix apps/web run build
docker compose up -d --build        # SearXNG :8888，API :8000
curl "http://127.0.0.1:8888/search?q=test&format=json"   # 先确认能拿到 JSON
```

本机只跑 API（SearXNG 在 Docker 里）：`SEARCH_PROVIDER=searxng` + `SEARXNG_URL=http://127.0.0.1:8888`，然后 `scripts\serve.ps1`。

Compose 将书签数据库保存到命名卷 `bookmarks`，重建 API 容器后仍保留。若旧版 API 容器已有书签，先下载其 `/api/bookmarks/export`，确认备份后再重建并导回。容器默认使用抽取式总结；配置 `COMPOSE_LLM_BASE_URL` 时须使用容器可访问的模型端点。本机 Ollama 可搭配本机 API 使用。

### 3. 开发形态（热更新）

```powershell
.\scripts\dev.ps1 -Provider fixture
# FastAPI :8000 （--reload，被 Vite 代理），浏览器只访问 http://127.0.0.1:5173
```

## 验收与测试

```powershell
# 单元 / 契约测试（固定样本，不依赖网络与 Docker）
python -m pytest apps/api -q

# 固定样本服务启动后：三态、路由、拦截、引用、书签与同源首页
.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8000

# 真实搜索服务启动后：选 2～3 个已启用引擎，逐条记录结果数、来源、延迟和通过率
python scripts/verify-searxng.py --base-url http://127.0.0.1:8000 --engines g b
```

浏览器闭环：输入 `test` 提交 → 结果列表出现 10 条 → 点击标题在原站打开；刷新页面（地址栏保留 `?q=test`）结果复现。

## API 契约（M0 已实现部分）

`POST /api/search`

```json
{ "q": "test", "page": 1, "region": null,
  "opts": { "safe": true, "exact": false, "summarize": false, "fixture": null } }
```

```json
{ "parsed": { "q": "test", "engine": "default", "region": null, "router": "default" },
  "groups": { "strong": [Result...], "related": [], "weak": [] },
  "meta": { "status": "ok|empty", "engines": ["google"], "unresponsive": [],
            "provider": "fixture|searxng", "cached": false, "ms": 3, "total": 10,
            "filtered": { "dup": 1, "risk": 0 }, "sid": "s_1a2b" } }
```

上游错误使用 `{"error":{"code":"...","message":"...","retryable":true}}`。不可用或超时返回 HTTP `503`，错误码为 `UPSTREAM_UNAVAILABLE` 或 `UPSTREAM_TIMEOUT`。坏响应返回 HTTP `502`，错误码为 `UPSTREAM_BAD_RESPONSE`。

其他端点：`GET /api/health`（provider / web_built / 版本）、`GET /api/engines`（后缀目录、回退链、健康状态）、`GET /api/docs`（OpenAPI）。

显式引擎（后缀或 bang）失败时会按目录回退，例如 `g` → `google cse` → Serper，`sc` → Serper `/scholar`；成功响应的 `meta.engines` 是实际来源，`meta.unresponsive` 保留失败尝试。任一路合法零结果立即返回 `200 + status=empty`；只有故障才继续回退，付费兜底限第 1 页且遵守提供商熔断。

## 目录结构

```
llq/
├─ apps/api/
│  ├─ app/main.py            FastAPI 入口 + 同源托管 dist + SPA 回退
│  ├─ app/config.py          环境变量配置
│  ├─ app/schemas.py         请求 / 响应模型
│  ├─ app/routers/search.py  POST /api/search
│  ├─ app/core/searxng.py    真实 SearXNG 客户端（超时 / 连接失败 / 坏响应分类）
│  ├─ app/core/fixture_provider.py  固定样本上游（三态）
│  ├─ app/core/normalize.py  URL 规范化、展示串、去重
│  ├─ app/core/aggregator.py 选择上游 + 计时
│  ├─ fixtures/              SearXNG 形状的固定样本
│  └─ tests/                 API 契约、护栏、解析、安全、打分与缓存测试
├─ apps/web/                 React 19 + TS + Vite
│  ├─ src/App.tsx            状态机 idle/loading/ok/empty/error
│  ├─ src/api.ts             fetch 封装 + 错误码
│  └─ src/components/        SearchBar / ResultList / ResultCard / MetaBar / StatePanel
├─ searxng/settings.yml      开 json、关 limiter
├─ docker-compose.yml        可选：SearXNG + API
└─ scripts/                  serve.ps1 / dev.ps1 / smoke.ps1
```

## 设计取舍（与方案文档的差异）

见 [docs/决策与接口变更.md](docs/决策与接口变更.md)。要点：前端用 Vite 而非 Next.js；搜索端点只保留 POST；M0 结果全落 `strong`；新增 `fixture` 上游用于无 Docker 验收。

## 下一步

托管 CI 已收口；继续补正式浏览器/Android、新注册正常域名与事实质量验收。[待办、前提与完成标准](docs/进展与欠账.md#需要补齐的验收)