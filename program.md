# tcell Program

这是人类编程的元指令。只有人类修改此文件。
Critics 的进化循环、Hook 检查、Cron 深度审查都读取此文件作为运行规则。

---

## 进化规则

- 每个 critic 变异一次只改一个维度（检测策略 OR 阈值 OR 关注点）
- 回放集 = canaries.jsonl 最近 50 条 + clean_samples.jsonl 全部
- keep 条件：detection_rate 提升 ≥ 5% 且 false_positive_rate ≤ 10%
- discard 条件：任何不满足 keep 条件的变体
- 简洁性原则：同等效果下，更短的 critic 提示词优先（autoresearch 精神）
- 选择策略：轮询 critics/ 目录，最久未进化的 critic 优先

### 变异算子

| 算子 | 操作 | 示例 |
|---|---|---|
| `threshold_shift` | 调整检测阈值（当前值的 ±10%） | "同质化比例从 30% 改为 33%" |
| `focus_expand` | 扩展关注范围 | "从只检查 confidence 扩展到检查所有数值字段" |
| `focus_narrow` | 缩小关注范围 | "只检查标准差 < 0.01 的情况" |
| `strategy_rewrite` | 重写检测逻辑描述 | "改用分布检验替代简单计数" |
| `example_inject` | 注入新的正/反例 | "从最新 canary 提取一个案例加入 critic" |
| `simplify` | 删减冗余指令 | "合并两个重复的检查步骤" |

每次变异只选一个算子，由进化 subagent 执行。

### 停止条件

任一满足即暂停进化，等待新 canaries 输入：
- detection_rate 连续 20 次迭代提升 < 1%（收敛）
- false_positive_rate 连续 3 次迭代 > 15%（过拟合）
- canaries.jsonl 无新增超过 7 天（数据饥饿）
- 连续 50 次 discard（critic 可能已到瓶颈）

暂停后，新 canaries 加入时自动恢复。

### 非确定性处理

- 进化评估：每个 critic 变体在每个样本上运行 3 次，多数投票（≥ 2/3 = detected）
- Hook 实时检查：单次运行（速度优先，容忍偶尔误判）

## 噪声预算

### Hook 层（独立预算）
- 滑动窗口：最近 10 次工具调用内 ≤ 1 次警报
- 低于 severity 2 的发现写入 pending，不打扰用户
- 新 session 重置计数器
- 如果两个 hook 在窗口内都想报警，第二个被抑制，写入 pending

### Cron 层（独立预算）
- 每次深度审查 ≤ 3 个发现（只报最严重的）
- Hook 和 Cron 预算互不消耗

### 警报 SLA
- Hook 检查目标 < 5s（轻量模式匹配，不做深度推理）
- Hook 异步执行，不阻塞主 agent
- 超时 > 10s 记录但不阻塞，标记为 timeout

## 严重度定义

| 级别 | 含义 | 示例 | 处理 |
|---|---|---|---|
| 3 (致命) | 导致完全错误的结论 | confidence 同质化导致整批数据不可用 | 立即警报 |
| 2 (严重) | 导致显著质量下降 | 缺失关键偏差类型 | 在预算内警报 |
| 1 (中等) | 值得注意但不紧急 | 轻微的分布不均 | 写入 pending |
| 0 (信息) | 纯记录，无需行动 | 统计观察 | 写入日志 |

severity 0 记录到 sidebar.log.md，不加入 canaries。
只有经确认裁决升级为 severity ≥ 1 后才加入正式 canaries。

## 确认裁决机制

当 critic 发现问题时，按以下链确认：
1. **自动确认：** 2+ 个不同 critic 变体独立发现同一问题 → 加入 canaries
2. **交叉确认：** Codex 第三方审查（可选，不可用时跳过）→ 加入 canaries
3. **人类确认：** 以上都不满足时，标记 pending，等待人类裁决

裁决结果：
- 确认为真 → canaries.jsonl，触发 critic 进化
- 确认为假 → clean_samples.jsonl，作为假阳性训练数据

## 冷启动规则

canaries < 20 时的特殊规则：
1. critic 进化暂停——种子 critics 直接使用，不变异
2. 所有发现标记为 low_confidence
3. 人类裁决是唯一确认途径
4. 达到 20 canaries 后自动进入正常进化模式

## 认知偏差猎物清单

- **自我评估膨胀** — 100% 通过率 = 红旗，要求展示分布
- **同质化盲区** — 大量输出集中在少数值，标准差异常低
- **确认偏误** — 只找支持性证据，忽略反例
- **锚定效应** — 第一个结论影响后续所有判断
- **位置偏差** — 标注/评估与位置相关而非内容相关
- **指标欺骗** — 优化指标数字而非实际质量
- **过早结论** — 总是完全翻转或完全接受，缺少部分修正

## 日志规则

sidebar.log.md 追加写入，每条目有 emoji 前缀：
- 🔇 静默通过（一行简要）
- 🔔 Hook 警报（含 evidence）
- 🔍 Cron 深度审查
- 🧬 Critic 进化（含 keep/discard）
- 📊 每日摘要

超过 500 行时归档到 reports/log-{date}.md。
