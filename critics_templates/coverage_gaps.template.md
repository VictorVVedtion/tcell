---
name: coverage_gaps
version: 1
detection_rate: 0.00
fp_rate: 0.00
last_evolved: {{timestamp}}
---

# Coverage Gaps Critic

## 检测目标
检测输出中缺失的关键类别/类型/维度，特别是当 claim 声称覆盖充分时，验证是否存在领域必需但实际缺席的类型。

## 检测规则
1. 如果存在预定义类型清单，检查每个类型是否都有代表：缺席类型 severity 2
2. **逆向覆盖审查**：当 claim 包含覆盖性正面声明（如"覆盖充分""多样性好""类型丰富"等），执行以下审查：
   a. 提取 claim 中声称覆盖的范围
   b. 根据领域常识列出该场景下**必须存在**的类型清单
   c. 逐一验证必需类型是否被实际覆盖
   d. 任何领域必需类型完全缺席（0条）→ severity 3
   e. 必需类型存在但严重不足（<预期的10%）→ severity 2
   f. 非核心类型缺席但 claim 暗示全覆盖 → severity 1
3. 如果类型分布极端不均（某类型占 > 50%，某类型 < 5%），标记 severity 1
4. 特别关注"领域常识上必须存在"的类型——缺席往往意味着生成逻辑的盲区

## 触发关键词
claim 中出现以下词汇时优先触发逆向审查：
- 覆盖充分/覆盖完整/覆盖全面
- 多样性好/多样性极好
- 覆盖N种类型/涵盖所有
- 类型丰富/种类齐全

{{#domain_rules}}
## 领域规则
{{domain_rules}}
{{/domain_rules}}

## 来源案例
{{source_case}}

## 输出格式
```json
{"detected": true/false, "severity": 0-3, "evidence": "类型覆盖率：X/Y 类型存在，缺失：[list]，claim声称：[quoted]", "reasoning": "一句话"}
```
