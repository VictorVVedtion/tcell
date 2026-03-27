---
name: position_bias
version: 2
detection_rate: 0.20
fp_rate: 0.00
last_evolved: 2026-03-27T00:17:34Z
---

# Position Bias Critic

## 检测目标
检测标注/评估结果与位置（序号、顺序）强相关而非与内容相关的模式。

## 检测规则
1. 对有序列表中的标注做位置-标签交叉分析：
   如果位置 N 总是（> 40%）产出同一标签，标记 severity 3
2. 打乱顺序后重新评估：如果结论显著改变，确认位置偏差
3. 检查"第一个总是 X"模式：如果第一项的标签多样性显著低于其他位置，标记 severity 2
4. 对评分序列做自相关分析：如果相邻位置的评分过度相似，标记 severity 1
5. 文本位置→标签绑定检测（新增）：
   扫描claim和evidence文本，检测以下模式：
   - 显式映射："C1→X, C2→Y"、"第1个→A, 第2个→B"、"Challenge N → label" 等位置到标签的直接映射
   - 隐式绑定：当claim声称"多样性好/覆盖充分"但evidence中存在位置-标签绑定描述时，标记矛盾
   - 百分比佐证：位置→标签映射伴随高百分比（>35%）时加重severity
   如果检测到上述任一模式，标记 severity 3

## 来源案例
SFT batch-107: Challenge 1 → confirmation_bias (48%),
Challenge 2 → anchoring (44%), Challenge 3 → availability_bias (39%)。
偏差类型与 challenge 位置强绑定，而非由内容决定。
这意味着模型学到了"第一个 challenge 就用 confirmation_bias"
这个快捷方式，而非真正分析内容。

## 输出格式
```json
{"detected": true/false, "severity": 0-3, "evidence": "位置-标签相关矩阵：pos1→label(%), pos2→label(%)", "reasoning": "一句话"}
```