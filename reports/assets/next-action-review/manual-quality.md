# 总结内容定向审读

本轮由 Codex 审读三个公开技术主题；这不是完整事实准确率评测。原始六主题 fast/full 输出见 `summary-12.json`，三个相同 fast 来源的提示词重放见 `prompt-replay.json`。重放只调用本机千问，未重新检索，来源 ID 与材料哈希保留在 JSON。模型采样及冷热状态未控制，不能把单次差异归因为提示词收益。

## 发现

| 主题 | 观察 | 判定与依据 |
| --- | --- | --- |
| Rust 所有权/借用 | 原 fast 和重放均出现函数返回后“所有权自动收回”的表述；原 full 将内存泄漏并入安全目标，未解释边界 | 仍需改写。借用本身不转移所有权，移动后也不因函数返回而自动归还；Rust 不保证消除所有内存泄漏。见 [Rust 官方借用章节](https://doc.rust-lang.org/book/ch04-02-references-and-borrowing.html) 与 [Rustonomicon](https://doc.rust-lang.org/nomicon/leaking.html)。 |
| HTTP/2 多路复用 | 输出没有清楚区分应用层与 TCP 阻塞；重放出现“要求所有相同域名的请求共享一个 TCP 连接” | 仍需限定。HTTP/2 不消除 TCP 队头阻塞；连接复用建议有边界，不能写成所有请求必须共享的绝对要求。见 [RFC 9113 §1、§9.1](https://www.rfc-editor.org/rfc/rfc9113.html)。 |
| Python GIL | 原输出泛化到 CPython，未说明启用 GIL 与 free-threaded 构建；重放加入了实现范围和版本未核实说明 | 限定说明有所增加，仍需明确 GIL-enabled 前提。Python 3.13 起已有可选 free-threaded 构建，不宜把常规 GIL 行为泛化到所有构建。见 [Python 官方文档](https://docs.python.org/3/howto/free-threading-python.html)。 |

## 本轮处理与剩余

- 提示词补充保留前提、版本和限制，避免从局部优化推成绝对保证；输入明确标记搜索摘要/正文摘录/截断摘录。
- 三次重放的编号引用都合法，但 Rust 和 HTTP/2 仍有需改写内容。不能把引用合法或提示词变更记为事实质量通过；也不据此宣称整体准确率提升。
- 原始 12 次 SSE 的结构验收通过：fast/full 各 6 次；full 正文取得 15/30，全部 6 次如实降级。这个计数与本页的内容审读是两个口径。
- 下一步固定一手来源与逐条预期事实/禁用泛化，开展盲标及多次重放；同时记录来源本身的正确性。需要数据支持后再决定模型、来源选择或重排策略，本轮没有硬编码专题答案或调整默认模型。
