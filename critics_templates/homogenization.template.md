---
name: homogenization
version: 1
detection_rate: 0.00
fp_rate: 0.00
last_evolved: {{timestamp}}
---

# Homogenization Critic

## 检测目标
检测输出数据中出现异常的值集中/重复模式，暗示模板化生成而非真实推理。
核心思想：真实推理产生的数值应呈现合理的离散度；模板化生成会产生统计学上不可能的集中。

## 检测规则

### 规则 1: 卡方拟合优度检验（数值/评分字段）
将观测值分布与预期分布进行卡方检验（chi-squared goodness-of-fit）。
- 若无先验，使用均匀分布作为零假设
- p < 0.001 且最高频值占比 > 25% → severity 3（极度集中，模板化铁证）
- p < 0.01 且最高频值占比 > 15% → severity 2（显著偏离，高度可疑）
- p < 0.05 且最高频值占比 > 10% → severity 1（轻微异常，值得关注）

### 规则 2: 零方差 / 近零熵检验
- 对连续数值字段计算信息熵 H = -sum(p(x) * log2(p(x)))
- H = 0（所有值相同）→ severity 3
- H < 1.0 且样本量 > 10 → severity 2
- 方差为 0 且样本量 > 5 → severity 3

### 规则 3: 精确重复率检验（字段级）
- 对于连续型数值，精确重复本身即为强信号：
  - repeat_ratio > 40% → severity 3
  - repeat_ratio > 20% → severity 2
- 对于离散型/有限集，需结合类别数调整阈值：
  - repeat_ratio > 1/类别数 + 30% → severity 2

### 规则 4: 边界与排除
- 对离散标签字段的位置相关性 → 交给 position_bias critic
- 若 claim 描述单一聚合指标（如"平均值 X"）而非分布特征，不适用本 critic

{{#domain_rules}}
## 领域规则
{{domain_rules}}
{{/domain_rules}}

## 来源案例
{{source_case}}

## 输出格式
```json
{"detected": true/false, "severity": 0-3, "evidence": "统计检验结果：卡方p值/信息熵H/精确重复率/最高频值占比", "reasoning": "一句话"}
```
