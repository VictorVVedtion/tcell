# X/Twitter 中文线程

## 推文 1（Hook — 附 tcell-hero.png）

AI agent 自己检查自己的工作，结果可靠吗？

Opus 4.6 生成 107 条 SFT 训练数据后自评：
→「100% 通过率，质量评分 1.000 满分」

独立审查评分：5.5/10，发现 5 个致命问题。

两次审查用的是同一个模型。

tcell：AI agent 的认知免疫系统。🧬🔽

## 推文 2（问题）

问题不在模型能力，在上下文隔离。

当 agent 在同一个上下文中生成并评估产出时：
- 45.8% 的 confidence 值卡在 0.62（标准差=0）
- 偏差标注跟位置绑定（C1 永远是 confirmation_bias）
- 质量评分器给所有样本满分

agent 看不到自己的认知盲区。这是结构性的。

## 推文 3（洞察）

修复方法不是「用更强的模型」。

同一模型 + 新鲜上下文 = 发现盲区。

上下文隔离 > 模型多样性。

这就是 pair programming 有效的原因——搭档不需要比你聪明，只需要不同的视角。

## 推文 4（方案 — 附 tcell-evolution.png）

tcell 把 @karpathy autoresearch 的哲学移植到认知审查：

- Critics（审查策略）通过 变异→回放→keep/discard 自主进化
- Canaries（已确认盲区）是进化的训练数据
- 人类只编程 program.md（元指令），不编程 critics
- 单一指标：在已知盲区上的检出率

给认知审查写一个 program.md。

## 推文 5（铁律）

tcell 的 7 条铁律：

1. 永不信任自我评估
2. 沉默是信任的证明
3. 只说有证据的话
4. 永远用新鲜眼睛
5. 审查思维模式，不只是产出
6. 进化，不固化
7. 噪声预算神圣不可侵犯

第 2 条最重要：如果 50% 的警报是假阳性，你就是一条乱叫的狗。

## 推文 6（CTA）

tcell 开源，MIT 协议，零依赖。

Clone → self-test → 5 分钟审查你的数据。

每一个你贡献的 canary（已确认盲区）都让整个免疫系统更聪明。

github.com/VictorVVedtion/tcell

用 Claude Code 构建。灵感来自 @karpathy 的 autoresearch。
