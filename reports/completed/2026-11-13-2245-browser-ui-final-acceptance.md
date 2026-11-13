# 完工报告 · 浏览器与 UI 优化方案终验

| 项 | 值 |
| --- | --- |
| 报告编号 | 20261113-2245 |
| 开始 | 2026-11-13 22:45 |
| 结束 | 2026-11-13 22:45 |
| 耗时 | 不到 1 分钟 |
| 执行者 | DSH/lead |
| 任务类型 | test |
| 状态 | 完成 |

## 1 任务

**目标**

按 [浏览器与 UI 优化方案](../../docs/浏览器与UI优化方案.md) §8.2「必跑」清单做一次完整终验：补齐 768/1024 断点与深色主题断言，跑通单元/契约、构建、冒烟、浏览器断言与视觉回归，并把 P0–P2 的完成状态固定进方案。

**验收标准**

- `python -m pytest apps/api -q` 不回归。
- `npm --prefix apps/web run build` 通过。
- `scripts/smoke.ps1` 在 fixture 模式 16/16；真实模式说明不可用原因。
- `scripts/audit-ui.cjs` 覆盖 320/390/768/900/901/1024/1440/1920、浅/深色、reduce-motion，并全绿。
- 视觉回归 12 张基线 0 变化；`node --test` 静态检查通过。

**不做**

- 真机（Android/iOS）安装、系统分享与 NVDA/VoiceOver 复核：本环境无设备与读屏，保留为待验项。
- 真实 SearXNG 冒烟：本机 8888 无监听。

## 2 做了什么

1. **补断点断言**：768px 断言单列布局 + 抽屉入口可见 + 无横向溢出；1024px 断言三列布局且右栏可见；与既有 320/900/901/1920 形成完整梯度。
2. **补深色断言**：切到 `data-theme=dark` 后校验 `color-scheme=dark` 与页面底色为深色，并对深色结果页跑 axe（serious/critical=0）。
3. **跑完整清单**：单元/契约 481 项、构建、fixture 冒烟 16/16、浏览器断言 253 项、静态检查 28 项、视觉回归 12 张。
4. **方案归档**：§8.1 三阶段标注完成日期；新增 §8.2.1 记录自动化现状与覆盖范围。

## 3 改动清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `scripts/audit-ui.cjs` | 修改 | 新增 768/1024 布局断言与深色主题断言（共 253 项） |
| `reports/assets/final-acceptance/` | 新增 | 审计 JSON、截图与冒烟日志 |
| `docs/浏览器与UI优化方案.md` | 修改 | §8.1 标注完成；新增 §8.2.1 自动化现状 |

## 4 验证与证据

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps/api -q` | 通过 | 481 项，`[100%]` 无 F/E |
| `npm --prefix apps/web run build` | 通过 | 76 modules，主包 236.35 kB |
| `.\scripts\smoke.ps1 -BaseUrl http://127.0.0.1:18198` | 通过 | 16/16：健康、有结果 10/11、三档 3/6/1、缓存、后缀路由、拦截、零结果、上游不可用、SSE 10 引用、过期快照 404、书签、导出、内网拦截、跨域 token、同源首页 |
| `node scripts/audit-ui.cjs --base http://127.0.0.1:18198 --out reports/assets/final-acceptance` | 通过 | `ALL PASS (253)`，含 768 单列/1024 三列/深色 axe |
| `node --test scripts/extension.test.cjs scripts/css-audit.test.cjs scripts/engine-query.test.cjs` | 通过 | 28 项 |
| `node scripts/visual-regression.cjs` | 通过 | 12 张基线「变化 0，缺基线 0」 |

**证据文件**

- `reports/assets/final-acceptance/p0-ui-audit.json`、`smoke.log` 与三张截图
- 视觉基线：`reports/assets/p2-extension-vitals-review/visual-baseline/`

**未验证**

- 真实 SearXNG（8888）冒烟与多页筛选效果：上游未运行，仅 fixture。
- Android/iOS 真机：PWA 安装、系统分享、返回手势。
- NVDA/VoiceOver 朗读：标题层级、结果播报、面板开关。
- 正式 Chrome/Edge 手动加载扩展（Codex 曾用 `verify-extension.cjs` 跑过 14 项，本轮未复跑）。

## 5 关键决策

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 以 253 项浏览器断言作为终验门槛 | 只跑既有 249 项 | 方案 §8.2 要求 768/1024 与深色覆盖，补齐后才算对齐清单 |
| 深色断言用 axe + 底色双重校验 | 只截图目测 | 无头环境无法目测，axe 能覆盖对比度与可访问名 |
| 真实模式缺口写明而非跳过 | 用 fixture 冒充 | 不把未验证写成已验证 |

## 6 遗留与风险

- 真实上游（SearXNG 8888）与真机/读屏复核仍未完成，方案 §8.3 保留这三项待验。
- 浏览器断言只在 Chromium 上跑；Chrome 渠道上一次证据是 Codex 的 245 项（构建接近）。
- 视觉基线依赖本机字体与 DPR，换机器会误报。

## 7 交接

**下一个人第一件事**

恢复 SearXNG（8888）后跑 `scripts/smoke.ps1` 真实模式与筛选组合复测；有真机时补 §8.3 的 PWA 安装、系统分享、读屏朗读三项，并在 `verify-extension.cjs` 复跑扩展。

**相关文件**

- 方案：`docs/浏览器与UI优化方案.md`（§8.1 完成状态、§8.2.1 自动化现状）
- 验收：`scripts/audit-ui.cjs`、`scripts/smoke.ps1`、`scripts/visual-regression.cjs`
- 证据：`reports/assets/final-acceptance/`