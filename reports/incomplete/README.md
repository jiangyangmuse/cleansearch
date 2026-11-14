# 未完成报告

下表保留报告和台账登记时的状态。最新证据用于更新待办范围，验收通过后可追加到原报告。

| 报告 | 历史状态 | 已有补证与剩余验收 |
| --- | --- | --- |
| [搜索筛选、浏览器终验与真实上游复核](2026-11-14-0044-p2-filters-final-review.md) | 部分完成 | [8000 后端已切换](../completed/2026-11-14-0056-deploy-backend-8000.md)。待补 Google/CSE 真实冒烟、时间与语言逐条核对、真机和读屏。 |
| [部署后十三引擎在线复查](2026-11-08-1447-deployed-engine-matrix.md) | 部分完成 | 等上游恢复后定向补 `mj/sp`。本轮完整 Compose 切换仍缺目标端口和存储的部署验收。 |
| [M19 引擎后缀批量修复](2026-11-08-1137-m19-engine-suffix-repair.md) | 完成 | [后续复核](../completed/2026-11-08-1335-engine-fallback-review.md)已修正直接探测的假阳性。容器版本同宿主机的定向来源对照仍待证据。 |
| [DSH 后续动作收口与证据补强](2026-11-07-1659-next-action-review.md) | 部分完成 | [托管 CI 已补](../completed/2026-11-08-0212-hosted-ci-credits.md)。待补正式浏览器和真机、RDAP 新站正常对照、逐事实总结和检索相关性评估。 |
| [P1 CI、浏览器验收与双模型实测](2026-11-07-1056-p1-ci-browser-model.md) | 部分完成 | [托管 CI](../completed/2026-11-08-0212-hosted-ci-credits.md)和 [RDAP 首版](../completed/2026-11-07-1447-rdap-domain-age.md)已有证据。正式浏览器、Android 真机及凭据依赖项待验。 |
| [P0 真实引擎、缓存与持久化](2026-11-07-1022-p0-real-engines.md) | 完成 | [Compose 持久化](../completed/2026-11-07-1046-p0-2-docker-verify.md)和[千问双模式](2026-11-07-1056-p1-ci-browser-model.md)已有后续证据。各目标环境的受限引擎仍按部署配置验收。 |
| [路线图六阶段](2026-11-06-2342-roadmap-six-phases.md) | 完成 | [真实引擎](2026-11-07-1022-p0-real-engines.md)、[容器](../completed/2026-11-07-1046-p0-2-docker-verify.md)与 [CI](../completed/2026-11-08-0212-hosted-ci-credits.md)已补部分证据。多引擎覆盖仍受上游与目标部署约束。 |
| [M8 一键添加验收与加固](2026-11-06-2214-m8-capture-acceptance.md) | 部分完成 | [自动化加载扩展与分享预填](../completed/2026-11-06-2224-m8-real-browser-verify.md)已有证据。正式 Chrome/Edge 手动加载、Android 系统分享和外站本地网络权限仍待验。 |
| [M0–M3 联合复核](2026-11-06-1934-m0-m3-review.md) | 部分完成 | [容器和书签持久化](../completed/2026-11-07-1046-p0-2-docker-verify.md)已有补证。Chrome/Edge/Firefox 原生书签管理器互迁待验。 |
| [M1 搜索体验独立验收与修复](2026-11-06-1704-m1-acceptance-fixes.md) | 部分完成 | [真实引擎与地区](2026-11-07-1022-p0-real-engines.md)已有样本；目标部署上的 `g/sc` 和地区来源仍需按当前上游验证。 |
| [M0 搜索闭环独立验收](2026-11-06-0014-m0-acceptance.md) | 部分完成 | [输入边界修复](../completed/2026-11-06-0051-m0-validation-followup.md)及后续 [P0 真实上游样本](2026-11-07-1022-p0-real-engines.md)已有证据。原报告保留当时的验收范围，目标部署复测与真实引擎验收合并跟踪。 |

当前验收条件详见[进展与欠账](../../docs/进展与欠账.md)。[返回总台账](../INDEX.md)
