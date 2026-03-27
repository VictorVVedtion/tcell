---
name: homogenization
version: 3
detection_rate: 0.40
fp_rate: 0.00
last_evolved: 2026-03-27T00:04:10Z
---

# Homogenization Critic

## 检测目标
检测输出数据中出现异常的值集中/重复模式，暗示模板化生成而非真实推理。
核心思想：真实推理产生的数值应呈现合理的离散度；模板化生成会产生统计学上不可能的集中。

## 检测规则

### 规则 1: 卡方拟合优度检验（数值/评分字段）
将观测值分布与预期分布进行卡方检验（chi-squared goodness-of-fit）。
- 预期分布：根据字段语义选取（如 confidence → Beta(2,2) 近似；quality_score → 右偏正态）
- 若无先验，使用均匀分布作为零假设
- p < 0.001 且最高频值占比 > 25% → severity 3（极度集中，模板化铁证）
- p < 0.01 且最高频值占比 > 15% → severity 2（显著偏离，高度可疑）
- p < 0.05 且最高频值占比 > 10% → severity 1（轻微异常，值得关注）

### 规则 2: 零方差 / 近零熵检验
- 对连续数值字段计算信息熵 H = -Σ p(x) log2 p(x))
- H = 0（所有值相同）→ severity 3
- H < 1.0 且样本量 > 10 → severity 2（信息量极低，几乎无区分度）
- 方差为 0 且样本量 > 5 → severity 3（退化为常量，评估器失效）

### 规则 3: 精确重复率检验（字段级）
- 统计字段中出现 ≥2 次的精确重复值的样本占比（repeat_ratio）
- 对于连续型数值（如 confidence），精确重复本身即为强信号：
  - repeat_ratio > 40% → severity 3（连续值大量精确重复 = 模板化）
  - repeat_ratio > 20% → severity 2
- 对于离散型/有限集（如 severity 等级），需结合类别数调整阈值：
  - repeat_ratio > 1/类别数 + 30% → severity 2

### 规则 4: 边界与排除
- 对离散标签字段的位置相关性 → 交给 position_bias critic，本 critic 不处理
- 若 claim 描述的是单一聚合指标（如"平均值 X"）而非分布特征，不适用本 critic
- 若 claim 明确提及分布统计量（std, 方差, 多样性等），即使值看起来正常也需验证

## 来源案例
SFT batch-107: 45.8% 的样本 confidence = 0.62，标准差为 0。
卡方检验 p ≈ 0（vs 均匀分布），信息熵 H ≈ 0.99，精确重复率 45.8%。
三项规则均触发 severity 3。这不是"很多样本碰巧相似"，而是模板化输出的铁证。

## 输出格式
```json
{"detected": true/false, "severity": 0-3, "evidence": "统计检验结果：卡方p值/信息熵H/精确重复率/最高频值占比", "reasoning": "一句话"}
```