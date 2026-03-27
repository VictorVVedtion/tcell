# tcell

**AI Agent 的认知免疫系统。**

当一个 AI agent 在长会话中工作时，它在同一个推理上下文中生成产出并评估产出。这产生结构性的自我评估偏差——agent 说"100% 通过"不是证据，是声明。

tcell 是一个独立的认知审查者。它用新鲜上下文审查主 agent 的质量声明，检测思维模式偏差而非只检查代码 bug。它的审查策略通过 autoresearch 风格的进化循环自主优化。

## 为什么需要它

真实案例：Opus 4.6 生成 107 条 SFT 训练数据，自评结果：

| 指标 | 主 agent 自评 | 独立审查 |
|---|---|---|
| 通过率 | 100% | — |
| 质量评分 | 全部 1.000 满分 | 5.5/10 |
| 发现 | "数据质量极高" | 5 个致命问题 |

独立审查发现了什么？
- **45.8% 的 confidence 值同质化在 0.62**（标准差 = 0）
- **偏差标注与位置绑定**（C1 永远是 confirmation_bias）
- **loss_aversion 完全缺席**（交易场景最核心的偏差）
- **质量评分器形同虚设**（107 条全部满分）
- **synthesis 总是完全翻转**（缺少部分修正）

关键洞察：**两次审查用的是同一个模型（Opus 4.6）。** 问题不在模型能力，在上下文隔离。同一个模型在独立上下文中就能发现主 agent 的结构性盲区。

## 架构

基于 [Karpathy 的 autoresearch](https://github.com/karpathy/autoresearch) 哲学：人类编程元指令，agent 自主进化审查策略。

```
                    ┌──────────────┐
                    │  Main Agent  │ ← 被监控的 Claude Code session
                    └──────┬───────┘
                           │ Write/Edit/Bash
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌────────┐  ┌────────┐
         │Hook 层 │  │Cron 层 │  │进化循环│
         │信号收集│  │深度审查│  │(后台)  │
         └───┬────┘  └───┬────┘  └───┬────┘
             │           │           │
             ▼           ▼           ▼
         ┌─────────────────────────────┐
         │  Critics (可进化的审查策略)  │
         └─────────────────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    canaries.jsonl        clean_samples.jsonl
    (已确认盲区)          (已确认无问题样本)
```

**三文件映射（对标 autoresearch）：**

| autoresearch | tcell | 职责 |
|---|---|---|
| `prepare.py` | `prepare.py` | 固定基础设施。不可被 critic 修改 |
| `train.py` | `critics/*.md` | 可进化的审查策略 |
| `program.md` | `program.md` | 人类编程的元指令 |

## 快速开始

```bash
git clone <repo-url> tcell
cd tcell

# 1. 验证系统完整性
python3 prepare.py self-test

# 2. 查看 critic 排行榜
python3 evolve.py leaderboard

# 3. 查看认知健康分
python3 prepare.py session-score

# 4. 审查你的数据
./review.sh <your-data.jsonl>
```

## 核心概念

**Canary** — 已确认的盲区案例。主 agent 声称高质量，但独立审查发现了问题。Canaries 是进化循环的训练数据。

**Critic** — 一个 `.md` 文件，包含检测规则和策略。Critics 通过变异→回放→keep/discard 循环自主进化。

**Detection Rate** — 操作性指标。critic 在已知 canaries 上的检出率。用于进化决策。

**Self-Certification Regret** — 回顾性指标。sidebar 自己也漏掉的问题占比。需要外部确认，不用于自动决策。

**Noise Budget** — 噪声预算。每 10 次工具调用最多 1 次警报。沉默是信任的证明。

**Cold Start** — canaries < 20 时，进化暂停，系统只收集数据不自主进化。

## 进化循环

```
select → mutate → replay → keep/discard → record
  │         │        │          │            │
  ▼         ▼        ▼          ▼            ▼
选最久    变异一    在canaries  detection↑   results.tsv
未进化    个维度    上回放3次   且FP≤10%     sidebar.log
的critic           多数投票    →keep,否则
                               →discard
```

变异算子：`threshold_shift` | `focus_expand` | `focus_narrow` | `strategy_rewrite` | `example_inject` | `simplify`

## 项目结构

```
CLAUDE.md              铁律 + 工程哲学
program.md             人类编程的元指令
prepare.py             固定基础设施（self-test, session-score, hook-check, status）
evolve.py              进化循环控制器（select, evaluate, leaderboard, summary）
review.sh              一键审查脚本
critics/               可进化的 critic 提示词
canaries.jsonl         已确认盲区（进化的训练数据）
clean_samples.jsonl    已确认无问题样本（FP 率计算）
results.tsv            进化记录
sidebar.log.md         人类可读运行日志
.claude/agents/        subagent 定义
.claude/settings.json  hook 配置
```

## 添加 Canary

当你发现主 agent 的自我评估不准确时，把它记录为 canary：

```json
{
  "id": "canary-NNN",
  "timestamp": "2026-03-26T12:00:00Z",
  "source": "你的数据来源",
  "main_agent_claim": "主 agent 的质量声明原文",
  "actual_finding": "独立审查发现的实际问题",
  "severity": 3,
  "blindspot_type": "对应的 critic 名称",
  "discovered_by": "发现者",
  "confirmed_by": "确认方式"
}
```

severity: 3=致命, 2=严重, 1=中等

## 添加 Critic

创建 `critics/your_critic.md`：

```markdown
---
name: your_critic
version: 1
detection_rate: 0.00
fp_rate: 0.00
last_evolved: 2026-01-01T00:00:00Z
---

# Your Critic

## 检测目标
描述这个 critic 要发现什么类型的认知偏差。

## 检测规则
1. 具体规则...
2. 具体规则...

## 输出格式
{"detected": true/false, "severity": 0-3, "evidence": "...", "reasoning": "..."}
```

## 设计哲学

**7 条铁律（摘要）：**
1. 永不信任自我评估
2. 沉默是信任的证明
3. 只说有证据的话
4. 永远用新鲜眼睛
5. 审查思维模式，不只是产出
6. 进化，不固化
7. 噪声预算神圣不可侵犯

完整铁律见 [CLAUDE.md](CLAUDE.md)。
进化规则和噪声预算见 [program.md](program.md)。

## 路线图

- [x] v1 骨架（prepare.py, evolve.py, 5 critics）
- [x] 进化循环（select → mutate → replay → keep/discard）
- [x] Self-test 命令
- [x] Session score（认知健康分）
- [x] Critic leaderboard
- [x] 冷启动门控
- [x] 一键审查脚本（review.sh）
- [ ] 进化复盘（replay）
- [ ] 完全无人值守进化（/loop 集成）
- [ ] 元进化（program.md 参数自动调优）
- [ ] 跨项目 critic 迁移
- [ ] 社区 canary 网络

## License

MIT
