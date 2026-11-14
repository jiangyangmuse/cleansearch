# 完工报告 · 日常服务一键启动与开机自启

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261115-0120 |
| 开始 | 2026-11-15 01:20 |
| 结束 | 2026-11-15 01:20 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | ops |
| 状态 | 完成 |

## 1 任务

**目标**

日常 8000 依赖 `cs-searxng` 容器与本机 Ollama，其中一个没起就会降级或报错；机器重启后服务也不会自己回来。做一个带依赖自检的一键启动，并接上开机自启。

**验收标准**

- 8000 已在跑时再次执行直接退出，不起第二个实例。
- SearXNG 没起来时能自动降级到 `fixture` 并写日志；Ollama 不通只告警。
- 登录后自动拉起（无需管理员），日志可查；提供取消自启的办法。
- 停掉服务后，用与自启完全相同的命令行能把服务拉起来并通过 `/api/health`。

**不做**

- 不装 Windows 服务、不改注册表 Run 键、不动 `ONLOGON` 计划任务（需要管理员）。
- 不改 API 契约与前端。

## 2 做了什么

1. `scripts/start-daily.ps1`：先探 8000（在跑就退出）→ 检查 Docker 与 `cs-searxng`（没跑就 `docker compose up -d searxng`，最多等 90 秒）→ 探 Ollama（仅告警）→ 调 `serve.ps1 -SkipBuild`。全程 `Start-Transcript` 写 `data/logs/start-daily.log`。
2. `scripts/install-autostart.ps1`：在**当前用户「启动」文件夹**创建快捷方式（`-WindowStyle Hidden`），无需管理员；`-Remove` 取消。
3. 两次踩坑后改方案：`schtasks /TR` 有 261 字符上限（长路径 + 嵌套引号直接被拒），`Register-ScheduledTask` 建 `AtLogOn` 任务对普通用户返回「拒绝访问」；最终用「启动」文件夹，行为等价且零权限。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `scripts/start-daily.ps1` | 新增 | 依赖自检 + 一键启动 + 日志 |
| `scripts/install-autostart.ps1` | 新增 | 启动文件夹快捷方式（安装/移除） |
| `scripts/smoke.ps1` | 修改 | SSE 模型校验改为「属于已配置模型之一」（上一轮模式切换带出） |
| `README.md` | 修改 | 新增「日常服务与开机自启」小节 |
| `docs/决策与接口变更.md` | 修改 | 启动/自启方案与踩坑 |
| `reports/completed/2026-11-15-0112-searxng-mode-switch.md` | 新增（上一轮） | 模式切换报告 |
| `reports/assets/mode-switch-searxng/` | 新增 | 模式切换的冒烟与守卫日志 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `pwsh scripts\start-daily.ps1 -Provider searxng -Port 8000`（8000 在跑时） | 通过 | 输出 `[skip] 8000 上已有 CleanSearch 在运行`，`EXIT=0`，无新进程 |
| 停掉 8000 后同命令 | 通过 | `[serve] provider=searxng port=8000` → `Uvicorn running on http://127.0.0.1:8000` |
| `pwsh scripts\install-autostart.ps1 -Port 8000 -Provider searxng` | 通过 | `C:\Users\HUAWEI\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\CleanSearch.lnk` |
| 停掉 8000 后按自启命令行拉起（`Start-Process pwsh -WindowStyle Hidden -File scripts\start-daily.ps1 …`） | 通过 | `/api/health` → `provider=searxng`、`api_version=2`、`llm_model=qwen3.5-4b-local:latest`；`data/logs/start-daily.log` 记录完整启动 |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8000` | 通过 | `冒烟通过 13/13，跳过 3`（searxng 模式，跳过项为固定样本专用） |

未验证：真实重启/登录后的自启（本轮用相同命令行模拟，没有重启机器）；`-Remove` 只做了代码路径检查。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 自启放「启动」文件夹 | `ONLOGON` 计划任务 | 计划任务需要管理员（实测被拒），启动文件夹零权限且行为等价 |
| SearXNG 起不来就降级 fixture | 直接失败退出 | 降级后仍能看界面、查书签；日志写明原因，不至于开机后完全不能用 |
| Ollama 只告警 | 阻塞启动 | 搜索不依赖模型；模型没起时总结报错比整个服务不启更容易接受 |
| 启动日志用 `Start-Transcript` | 手工重定向 | 隐藏窗口时没有 stdout，transcript 能留下完整过程且无需额外包装 |

## 6 遗留与风险

- Docker Desktop 本身不会随开机自启（脚本只能保证容器在 Docker 起来后启动；Docker 没起时会被判为「找不到 docker」而降级 fixture）。要彻底解决需把 Docker Desktop 也加入自启。
- `/api/health` 的 `llm_model` 仍来自 `.env`，不是设置页实际指派的模型；两者可以不同（本轮就不同：env 是 qwen，指派也是 qwen，但早前 env/DB 曾不一致）。要做「真实生效模型」展示需要让 health 读数据库设置。
- 开机自启用隐藏窗口，出问题时只能翻 `data/logs/start-daily.log`；没有托盘图标或重启按钮。

## 7 交接

**下一个人第一件事**

重启机器验证一次自启（`data/logs/start-daily.log` 应出现新的启动记录，`/api/health` 为 `provider=searxng`）；若 Docker 没自启，需要把 Docker Desktop 也加入「启动」文件夹。

**相关文件**

- 启动：`scripts/start-daily.ps1`、`scripts/serve.ps1`、`scripts/install-autostart.ps1`
- 日志：`data/logs/start-daily.log`、`data/logs/serve-8000.*.log`
- 文档：`README.md` §7、`docs/决策与接口变更.md`（2026-11-15 日常服务一键启动与开机自启）
